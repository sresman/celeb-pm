"""EODHD daily-EOD GET choke point + the PriceClient seam. Mockable at the METHOD level.

Mirrors openfigi_client.py exactly: structurally satisfies the PriceClient Protocol (defined in
price_types); `_get` is the single throttle/retry choke point (one token per attempt, incl.
retries). Reuse ONE EodhdClient across a whole run so the per-minute throttle is honored once.

Auth is a query param (api_token=), NOT a header (VERIFIED). A 404 is NOT an error — fetch_eod
returns an EMPTY SymbolSeries (unpriceable). Other 4xx (401/403/422) raise EodhdError. The
top-level response MUST be a JSON list (VERIFIED); a 200 + HTML/error body decodes to a non-list
-> EodhdError. The token value is NEVER logged.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Callable

import requests

from celebpm import constants
from celebpm.errors import EodhdError
from celebpm.price_types import PriceBar, SymbolSeries
from celebpm.ratelimit import TokenBucket, parse_retry_after

logger = logging.getLogger(__name__)


class _NotFound(Exception):
    """Private 404 sentinel: caught in fetch_eod and converted to an empty SymbolSeries."""


def _narrow_float(value: object) -> float | None:
    """Boundary narrowing: int/float -> float; reject bool; reject numeric strings; else None.

    OHLC / adjusted_close fields TOLERATE absence/garbage by narrowing to None (NOT raising) —
    a missing close on one bar should not fail the whole fetch.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _narrow_int(value: object) -> int | None:
    """Boundary narrowing: int -> int; reject bool; reject numeric strings/floats; else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _narrow_date_str(value: object) -> str | None:
    """A date row value must be a non-blank str; else None (the caller raises EodhdError)."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


class EodhdClient:
    """Structurally satisfies PriceClient. Single GET choke point + per-minute throttle.

    The rate-limiter state lives on THIS instance. Reuse ONE EodhdClient per run.
    """

    def __init__(
        self,
        *,
        api_token: str | None = None,
        requests_per_minute: float = constants.EODHD_REQUESTS_PER_MINUTE,
        timeout: float = constants.HTTP_TIMEOUT_SECONDS,
        max_retries: int = constants.HTTP_MAX_RETRIES,
        session: requests.Session | None = None,
        time_source: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_minute <= 0:
            raise ValueError(f"requests_per_minute must be > 0, got {requests_per_minute}")
        if timeout <= 0:
            raise ValueError(f"timeout must be > 0, got {timeout}")
        if max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {max_retries}")

        self._api_token = api_token  # may be None -> the token param is OMITTED (-> 401)
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep_func = sleep_func
        self._session = session if session is not None else requests.Session()
        self._bucket = TokenBucket(
            requests_per_minute / 60.0,  # per-minute -> per-second
            capacity=constants.EODHD_RATE_BUCKET_CAPACITY,
            time_source=time_source,
            sleep_func=sleep_func,
        )

    @classmethod
    def from_env(cls, *, session: requests.Session | None = None) -> EodhdClient:
        """Read EODHD_API_KEY from os.environ; non-blank -> token, blank/absent -> None.

        DECISION (KEPT as WARN): do NOT raise on a blank/missing token — emit a WARN (a fast
        config signal) and continue. The real failure still surfaces as the first 401 ->
        EodhdError at _get time. Keeps from_env total + testable.
        """
        raw = os.environ.get(constants.EODHD_API_KEY_ENV)
        key = raw.strip() if raw is not None else None
        token = key or None
        if token is None:
            logger.warning(
                "%s is blank/absent; EODHD requests will 401 until a token is set",
                constants.EODHD_API_KEY_ENV,
            )
        return cls(api_token=token, session=session)

    def fetch_eod(self, symbol: str, *, from_date: date, to_date: date) -> SymbolSeries:
        """Fetch the daily EOD series for `symbol` over [from_date, to_date] (inclusive).

        A 404 -> an EMPTY SymbolSeries (unpriceable). Validates from_date <= to_date
        (ValueError) and the symbol vs EODHD_SYMBOL_PATTERN (EodhdError).
        """
        if from_date > to_date:
            raise ValueError(f"from_date {from_date} must be <= to_date {to_date}")
        if constants.EODHD_SYMBOL_PATTERN.fullmatch(symbol) is None:
            raise EodhdError(f"invalid EODHD symbol: {symbol!r}")

        params = {
            constants.EODHD_PARAM_FMT: constants.EODHD_PARAM_FMT_JSON,
            constants.EODHD_PARAM_PERIOD: constants.EODHD_PARAM_PERIOD_DAILY,
            constants.EODHD_PARAM_FROM: from_date.isoformat(),
            constants.EODHD_PARAM_TO: to_date.isoformat(),
        }
        # OMIT the token param entirely when None (do NOT put None into a dict[str, str]).
        if self._api_token is not None:
            params[constants.EODHD_PARAM_API_TOKEN] = self._api_token

        try:
            raw = self._get(symbol, params)
        except _NotFound:
            return SymbolSeries(
                symbol=symbol,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                requested_from=from_date,
                requested_to=to_date,
                bars=(),
            )
        return self._parse_series(
            raw, symbol, requested_from=from_date, requested_to=to_date
        )

    def _get(self, symbol: str, params: dict[str, str]) -> object:
        """Throttled GET with retry/backoff. Returns parsed JSON or raises EodhdError/_NotFound.

        SINGLE throttle owner: acquires ONE token before EACH HTTP attempt (incl. retries).
        429 honors Retry-After else the per-minute window; other retryable statuses use
        exponential backoff. A 404 raises _NotFound (fetch_eod converts to an empty series).
        The token value is NEVER logged (we log the symbol only, never the params).
        """
        url = constants.EODHD_EOD_URL_TEMPLATE.format(symbol=symbol)
        total_attempts = 1 + self._max_retries
        last_error = "no attempts made"

        for attempt in range(total_attempts):
            self._bucket.acquire()  # every attempt is throttled (incl. retries)
            try:
                response = self._session.get(url, params=params, timeout=self._timeout)
            except requests.RequestException as exc:
                last_error = f"transport error: {exc}"
                logger.warning(
                    "EODHD GET %s failed (attempt %d): %s", symbol, attempt + 1, exc
                )
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
                logger.warning(
                    "EODHD GET %s got HTTP %d (attempt %d)", symbol, status, attempt + 1
                )
                self._backoff(attempt, retry_after=retry_after, rate_limited=rate_limited)
                continue

            if status == 404:
                logger.info("EODHD GET %s -> 404 (unpriceable, empty series)", symbol)
                raise _NotFound(symbol)

            if status >= 400:
                raise EodhdError(f"EODHD returned non-retryable HTTP {status} for {symbol}")

            try:
                parsed: object = response.json()
            except ValueError as exc:
                raise EodhdError(
                    f"failed to decode EODHD JSON for {symbol}: {exc}"
                ) from exc
            return parsed

        raise EodhdError(
            f"EODHD GET {symbol} exhausted {total_attempts} attempts; last error: {last_error}"
        )

    def _backoff(self, attempt: int, retry_after: float | None, rate_limited: bool) -> None:
        """Sleep before the next retry. 429 honors Retry-After else the per-minute window;
        other retryable statuses use exponential backoff. Logs the sleep (CLI not hung)."""
        if retry_after is not None:
            wait = retry_after
        elif rate_limited:
            wait = constants.EODHD_RATE_LIMIT_BACKOFF_SECONDS
        else:
            wait = constants.HTTP_RETRY_BACKOFF_SECONDS * (2**attempt)
        logger.info("EODHD backoff: sleeping %.3fs before retry", wait)
        self._sleep_func(wait)

    def _parse_series(
        self,
        raw: object,
        symbol: str,
        *,
        requested_from: date,
        requested_to: date,
    ) -> SymbolSeries:
        """Parse a LIVE EODHD response into a SymbolSeries. Raises EodhdError on a shape violation.

        NOTE: this must NOT call SymbolSeries.from_dict — they have DIFFERENT error contracts.
        from_dict raises ValueError/TypeError/KeyError (the best-effort cache path); _parse_series
        raises EodhdError (a LIVE response shape violation is a real transport/API failure).

        The TOP-LEVEL must be a list (VERIFIED). A 200 + HTML body (e.g. an error page) decodes
        to a str/dict (non-list) -> EodhdError. An empty list -> bars=() (unpriceable, NOT an
        error). KEEPS ALL returned bars (no range filtering). Stable ascending sort; on a
        DUPLICATE bar_date keep the LAST after the stable sort + WARN.
        """
        if not isinstance(raw, list):
            raise EodhdError(
                f"EODHD returned a non-list response for {symbol}: {type(raw).__name__}"
            )
        bars: list[PriceBar] = []
        for element in raw:
            if not isinstance(element, dict):
                raise EodhdError(
                    f"EODHD row for {symbol} is not an object: {type(element).__name__}"
                )
            bars.append(self._parse_bar(element, symbol))

        # stable ascending sort by date; dedupe keeping the LAST occurrence + WARN.
        bars.sort(key=lambda b: b.bar_date)
        deduped: list[PriceBar] = []
        for bar in bars:
            if deduped and deduped[-1].bar_date == bar.bar_date:
                logger.warning(
                    "EODHD %s: duplicate bar_date %s; keeping the last occurrence",
                    symbol,
                    bar.bar_date,
                )
                deduped[-1] = bar
            else:
                deduped.append(bar)

        return SymbolSeries(
            symbol=symbol,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            requested_from=requested_from,
            requested_to=requested_to,
            bars=tuple(deduped),
        )

    @staticmethod
    def _parse_bar(raw: dict[str, object], symbol: str) -> PriceBar:
        """Narrow one live row. A missing/garbled date -> EodhdError (a dateless bar is unusable);
        OHLC/adjusted/volume tolerate None (narrow to None, not raise)."""
        date_str = _narrow_date_str(raw.get(constants.EODHD_ROW_DATE_KEY))
        if date_str is None:
            raise EodhdError(f"EODHD row for {symbol} has a missing/invalid date")
        try:
            bar_date = date.fromisoformat(date_str)
        except ValueError as exc:
            raise EodhdError(
                f"EODHD row for {symbol} has an unparseable date {date_str!r}: {exc}"
            ) from exc
        return PriceBar(
            bar_date=bar_date,
            open=_narrow_float(raw.get(constants.EODHD_ROW_OPEN_KEY)),
            high=_narrow_float(raw.get(constants.EODHD_ROW_HIGH_KEY)),
            low=_narrow_float(raw.get(constants.EODHD_ROW_LOW_KEY)),
            close=_narrow_float(raw.get(constants.EODHD_ROW_CLOSE_KEY)),
            adjusted_close=_narrow_float(raw.get(constants.EODHD_ROW_ADJ_CLOSE_KEY)),
            volume=_narrow_int(raw.get(constants.EODHD_ROW_VOLUME_KEY)),
        )
