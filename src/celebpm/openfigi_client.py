"""OpenFIGI POST choke point + the MappingClient seam. Mockable at the METHOD level.

The existing HttpClient / EdgarClient is GET-only, EDGAR host, EDGAR limits. OpenFIGI is POST,
a different host, different (per-minute) limits, optional auth header — so a separate client +
a separate Protocol seam, mockable at the method level exactly like EdgarClient. See plan §3.

The CLIENT owns chunking-alignment: OpenFIGI's response array is 1:1 POSITIONAL with the request
array (it does NOT echo the cusip). map_jobs takes ONE pre-sized chunk, makes ONE throttled POST
(with retries), zips the response positionally against the request jobs, and a length-guard
(response length == request length else OpenFigiError) is the alignment safety check. The RESOLVER
owns chunking (cusip_map.resolve_tickers); the client does NOT chunk internally.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import requests

from celebpm import constants
from celebpm.errors import OpenFigiError
from celebpm.ratelimit import TokenBucket, parse_retry_after

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class MapJob:
    """One CUSIP->ticker mapping job. Queried UNFILTERED (no exchCode)."""

    cusip: str  # validated 9-char in __post_init__ (DEFENSE-IN-DEPTH)

    def __post_init__(self) -> None:
        # DEFENSE-IN-DEPTH: jobs are built only from already-validated PositionRecord.cusip,
        # so in normal operation this guard never fires. It is a belt-and-suspenders boundary
        # check that a malformed cusip never reaches the wire if a future caller bypasses
        # PositionRecord. Same idiom as PositionRecord/CusipMapEntry.
        if (
            len(self.cusip) != constants.CUSIP_LENGTH
            or self.cusip != self.cusip.upper()
            or constants.CUSIP_PATTERN.fullmatch(self.cusip) is None
        ):
            raise OpenFigiError(f"invalid cusip for MapJob: {self.cusip!r}")


@dataclass(frozen=True, kw_only=True)
class MapMatch:
    """One candidate mapping from OpenFIGI's `data` list. ticker may be None (no usable ticker)."""

    ticker: str | None
    name: str | None
    exch_code: str | None
    security_type: str | None  # FIGI securityType
    security_type2: str | None  # FIGI securityType2 (strongest common-equity signal)
    market_sector: str | None
    composite_figi: str | None
    figi: str | None


@dataclass(frozen=True, kw_only=True)
class MapResult:
    """One response element aligned 1:1 (POSITIONALLY) with the request job."""

    cusip: str  # assigned POSITIONALLY from the originating job (alignment via the length-guard)
    matches: tuple[MapMatch, ...]  # empty on a WHITELISTED in-payload warning or empty data
    warning: str | None = None
    error: str | None = None


class MappingClient(Protocol):
    """Structural seam for CUSIP->ticker mapping. Resolver depends on THIS, not the concrete class.
    NOT @runtime_checkable — conformance asserted statically in tests (mirrors HttpClient).

    map_jobs takes ONE already-sized chunk (<= max_jobs_per_request jobs) and returns that
    chunk's results. The RESOLVER owns chunking; the client does NOT chunk internally.

    max_jobs_per_request is a read-only int the resolver reads to size its chunks. It MUST be on
    the Protocol or `client.max_jobs_per_request` fails mypy strict against a MappingClient param.
    """

    @property
    def max_jobs_per_request(self) -> int: ...

    def map_jobs(self, jobs: list[MapJob]) -> list[MapResult]: ...


def _narrow_str(value: object) -> str | None:
    """Boundary narrowing: return value iff it is a str, else None (no Any)."""
    if isinstance(value, str):
        return value
    return None


def _narrow_ticker(value: object) -> str | None:
    """A ticker is a str; blank/whitespace is normalized to None and non-blank is stripped."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


class OpenFigiClient:
    """Structurally satisfies MappingClient. Single POST choke point + per-minute throttle.

    The rate-limiter state lives on THIS instance. Reuse ONE OpenFigiClient across a whole run
    so the per-minute throttle is honored once across all investors (same discipline as
    EdgarClient).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        requests_per_minute: float | None = None,
        max_jobs_per_request: int | None = None,
        timeout: float = constants.HTTP_TIMEOUT_SECONDS,
        max_retries: int = constants.HTTP_MAX_RETRIES,
        session: requests.Session | None = None,
        time_source: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        keyed = api_key is not None
        rpm = (
            requests_per_minute
            if requests_per_minute is not None
            else (
                constants.OPENFIGI_REQUESTS_PER_MINUTE_WITH_KEY
                if keyed
                else constants.OPENFIGI_REQUESTS_PER_MINUTE_NO_KEY
            )
        )
        batch = (
            max_jobs_per_request
            if max_jobs_per_request is not None
            else (
                constants.OPENFIGI_MAX_JOBS_PER_REQUEST_WITH_KEY
                if keyed
                else constants.OPENFIGI_MAX_JOBS_PER_REQUEST_NO_KEY
            )
        )
        # Constructor validation: fail fast on misconfiguration.
        if rpm <= 0:
            raise ValueError(f"requests_per_minute must be > 0, got {rpm}")
        if batch <= 0:
            raise ValueError(f"max_jobs_per_request must be > 0, got {batch}")
        if timeout <= 0:
            raise ValueError(f"timeout must be > 0, got {timeout}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")

        self._api_key = api_key
        self._max_jobs_per_request = batch
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep_func = sleep_func
        self._session = session if session is not None else requests.Session()
        self._bucket = TokenBucket(
            rpm / 60.0,  # per-minute -> per-second
            capacity=constants.OPENFIGI_RATE_BUCKET_CAPACITY,
            time_source=time_source,
            sleep_func=sleep_func,
        )

    @classmethod
    def from_env(cls, *, session: requests.Session | None = None) -> OpenFigiClient:
        """Read OPENFIGI_API_KEY from os.environ; a non-blank value -> with-key mode + header,
        absent OR empty/whitespace-only -> no-key mode. Secrets come from the process env (same
        channel Prompt 5's EODHD key will use), NOT from config_loader.
        """
        raw = os.environ.get(constants.OPENFIGI_API_KEY_ENV)
        key = raw.strip() if raw is not None else None
        return cls(api_key=(key or None), session=session)  # ""/whitespace -> None (no-key)

    @property
    def max_jobs_per_request(self) -> int:
        """Read-only chunk size the resolver reads to size its chunks (Protocol property)."""
        return self._max_jobs_per_request

    def map_jobs(self, jobs: list[MapJob]) -> list[MapResult]:
        """ONE pre-sized chunk -> ONE POST -> that chunk's results, in input order.

        Empty input -> [] with NO HTTP request and NO token acquisition. An oversized chunk
        (> max_jobs_per_request) is a programmer error -> ValueError. Does NOT swallow
        OpenFigiError — it propagates to the resolver (partial-success decision lives there).
        """
        if not jobs:
            return []
        if len(jobs) > self._max_jobs_per_request:
            raise ValueError(
                f"map_jobs received {len(jobs)} jobs > max_jobs_per_request "
                f"{self._max_jobs_per_request}; the resolver must pre-size chunks"
            )
        body = [
            {
                "idType": constants.OPENFIGI_ID_TYPE_CUSIP,
                "idValue": job.cusip,
            }
            for job in jobs
        ]
        raw_json = self._post(body)
        return self._parse_batch(raw_json, jobs)

    def _headers(self) -> dict[str, str]:
        """Per-request headers (never mutate a caller-supplied Session)."""
        headers = {"Content-Type": constants.OPENFIGI_CONTENT_TYPE}
        if self._api_key is not None:
            headers[constants.OPENFIGI_API_KEY_HEADER] = self._api_key
        return headers

    def _post(self, body: list[dict[str, str]]) -> object:
        """Throttled POST with retry/backoff. Returns parsed JSON or raises OpenFigiError.

        SINGLE throttle owner: acquires ONE token before EACH HTTP attempt (incl. retries).
        429 honors Retry-After else sleeps the per-minute window; other retryable statuses use
        the normal exponential backoff. All sleeps go through the injected sleep_func.
        """
        url = constants.OPENFIGI_MAPPING_URL
        total_attempts = 1 + self._max_retries
        last_error = "no attempts made"

        for attempt in range(total_attempts):
            self._bucket.acquire()  # every attempt is throttled (incl. retries)
            try:
                response = self._session.post(
                    url, json=body, headers=self._headers(), timeout=self._timeout
                )
            except requests.RequestException as exc:
                last_error = f"transport error: {exc}"
                logger.warning("OpenFIGI POST failed (attempt %d): %s", attempt + 1, exc)
                self._backoff(attempt, retry_after=None, rate_limited=False)
                continue

            status = response.status_code

            if status in constants.HTTP_RETRY_STATUS:
                last_error = f"HTTP {status}"
                rate_limited = status == 429
                retry_after = (
                    parse_retry_after(response.headers.get("Retry-After"))
                    if rate_limited
                    else None
                )
                logger.warning("OpenFIGI POST got HTTP %d (attempt %d)", status, attempt + 1)
                self._backoff(attempt, retry_after=retry_after, rate_limited=rate_limited)
                continue

            if status >= 400:
                raise OpenFigiError(f"OpenFIGI returned non-retryable HTTP {status}")

            try:
                parsed: object = response.json()
            except ValueError as exc:
                raise OpenFigiError(f"failed to decode OpenFIGI JSON: {exc}") from exc
            return parsed

        raise OpenFigiError(
            f"OpenFIGI POST exhausted {total_attempts} attempts; last error: {last_error}"
        )

    def _backoff(self, attempt: int, retry_after: float | None, rate_limited: bool) -> None:
        """Sleep before the next retry. 429 honors Retry-After else the per-minute window;
        other retryable statuses use exponential backoff. Logs the sleep (CLI not hung).
        """
        if retry_after is not None:
            wait = retry_after
        elif rate_limited:
            wait = constants.OPENFIGI_RATE_LIMIT_BACKOFF_SECONDS
        else:
            wait = constants.HTTP_RETRY_BACKOFF_SECONDS * (2**attempt)
        logger.info("OpenFIGI backoff: sleeping %.3fs before retry", wait)
        self._sleep_func(wait)

    def _parse_batch(self, raw_json: object, batch: list[MapJob]) -> list[MapResult]:
        """Strict boundary narrowing (no Any). See plan §3.

        Top-level must be a list; length-guard (THE alignment mechanism) before zipping;
        per-element transient-vs-permanent classification.
        """
        if not isinstance(raw_json, list):
            raise OpenFigiError(
                f"OpenFIGI returned a non-list response: {type(raw_json).__name__}"
            )
        if len(raw_json) != len(batch):
            raise OpenFigiError(
                f"OpenFIGI response length {len(raw_json)} != request length {len(batch)} "
                f"(alignment guard)"
            )

        results: list[MapResult] = []
        for element, job in zip(raw_json, batch):
            results.append(self._parse_element(element, job.cusip))
        return results

    def _parse_element(self, element: object, cusip: str) -> MapResult:
        """Parse one response element into a MapResult (positional cusip assigned by caller)."""
        if not isinstance(element, dict):
            raise OpenFigiError(
                f"OpenFIGI element for {cusip} is not an object: {type(element).__name__}"
            )

        warning = _narrow_str(element.get(constants.OPENFIGI_RESP_WARNING_KEY))
        error = _narrow_str(element.get(constants.OPENFIGI_RESP_ERROR_KEY))
        data = element.get(constants.OPENFIGI_RESP_DATA_KEY)

        # data present AND non-empty -> PARSE IT, even if a warning co-exists (data wins).
        if data is not None and data != []:
            if not isinstance(data, list):
                raise OpenFigiError(
                    f"OpenFIGI `data` for {cusip} is not a list: {type(data).__name__}"
                )
            matches: list[MapMatch] = []
            for raw_match in data:
                if not isinstance(raw_match, dict):
                    raise OpenFigiError(
                        f"OpenFIGI match for {cusip} is not an object: "
                        f"{type(raw_match).__name__}"
                    )
                matches.append(self._parse_match(raw_match))
            return MapResult(
                cusip=cusip, matches=tuple(matches), warning=warning, error=error
            )

        # No usable data -> classify the in-payload signal.
        # Empty data: [] OR a whitelisted miss warning -> PERMANENT miss (resolver caches unresolved).
        normalized_warning = warning.strip().lower() if warning is not None else None
        is_whitelisted_miss = (
            normalized_warning is not None
            and normalized_warning in constants.OPENFIGI_MISS_WARNINGS
        )
        if data == [] or is_whitelisted_miss:
            return MapResult(cusip=cusip, matches=(), warning=warning, error=error)

        # An in-payload error string, OR an unrecognized warning -> TRANSIENT -> raise.
        if error is not None:
            raise OpenFigiError(f"OpenFIGI returned an error for {cusip}: {error!r}")
        if warning is not None:
            raise OpenFigiError(
                f"OpenFIGI returned an unrecognized warning for {cusip}: {warning!r}"
            )
        # Neither data, warning, nor error — an unexpected shape; transient/structural.
        raise OpenFigiError(
            f"OpenFIGI element for {cusip} has neither data nor warning/error"
        )

    @staticmethod
    def _parse_match(raw: dict[str, object]) -> MapMatch:
        """Field-level narrowing: non-string fields -> None; blank ticker -> None (stripped)."""
        return MapMatch(
            ticker=_narrow_ticker(raw.get(constants.OPENFIGI_MATCH_TICKER_KEY)),
            name=_narrow_str(raw.get(constants.OPENFIGI_MATCH_NAME_KEY)),
            exch_code=_narrow_str(raw.get(constants.OPENFIGI_MATCH_EXCH_CODE_KEY)),
            security_type=_narrow_str(raw.get(constants.OPENFIGI_MATCH_SECURITY_TYPE_KEY)),
            security_type2=_narrow_str(raw.get(constants.OPENFIGI_MATCH_SECURITY_TYPE2_KEY)),
            market_sector=_narrow_str(raw.get(constants.OPENFIGI_MATCH_MARKET_SECTOR_KEY)),
            composite_figi=_narrow_str(raw.get(constants.OPENFIGI_MATCH_COMPOSITE_FIGI_KEY)),
            figi=_narrow_str(raw.get(constants.OPENFIGI_MATCH_FIGI_KEY)),
        )
