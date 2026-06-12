"""Single EDGAR HTTP choke point. Mockable at the METHOD level.

Defines the HttpClient Protocol seam (discovery depends on this, not the concrete class).
Nothing else in the codebase calls `requests` against EDGAR. See plan §9.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Final, Protocol

import requests

from celebpm import constants
from celebpm.constants import JSONObject
from celebpm.errors import EdgarError

# Behavior-preserving lift: the token bucket and Retry-After parser now live in ratelimit.py
# (shared with OpenFigiClient). Re-exported under their historical PRIVATE names so the EDGAR
# tests (which import `_TokenBucket`) and the internal `_parse_retry_after` call site below are
# UNCHANGED. See plan §3.
from celebpm.ratelimit import TokenBucket, parse_retry_after

# Explicit re-export (NOT `import as`) so mypy strict's implicit-reexport rule accepts the
# historical private names; tests/test_edgar_client.py imports `_TokenBucket` from here.
_TokenBucket = TokenBucket
_parse_retry_after = parse_retry_after

logger = logging.getLogger(__name__)


class HttpClient(Protocol):
    """Structural seam. discover_filings depends on THIS, not the concrete class.

    NOT @runtime_checkable — conformance is asserted statically in tests (see §12).
    """

    def get_json(self, url: str) -> JSONObject: ...

    def get_text(self, url: str) -> str: ...


class EdgarClient:
    """Structurally satisfies HttpClient (no explicit subclassing needed).

    IMPORTANT (v3): the rate-limiter state lives on THIS instance. Multi-CIK workflows MUST
    reuse ONE EdgarClient across all CIKs. Constructing a fresh client per CIK resets the
    token bucket (fresh full token each time) and defeats the rolling-window protection.
    """

    def __init__(
        self,
        user_agent: str = constants.USER_AGENT,
        rate_per_sec: float = constants.EDGAR_RATE_LIMIT_PER_SEC,
        timeout: float = constants.HTTP_TIMEOUT_SECONDS,
        max_retries: int = constants.HTTP_MAX_RETRIES,
        session: requests.Session | None = None,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        self._session = session if session is not None else requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep_func = sleep_func
        self._bucket = _TokenBucket(rate_per_sec, sleep_func=sleep_func)

    def get_json(self, url: str) -> JSONObject:
        """Throttled GET -> parsed JSON (JSONObject).

        Retries on HTTP_RETRY_STATUS and requests.RequestException. HTTP_MAX_RETRIES = number
        of RETRIES; total attempts = 1 + HTTP_MAX_RETRIES; EVERY attempt passes through the
        token bucket. 403 is NOT retryable. Honors Retry-After on 429 else exponential backoff.
        Raises EdgarError on exhaustion, non-retryable 4xx, or JSON decode failure.
        """
        response = self._request(url)
        try:
            parsed: object = response.json()
        except ValueError as exc:
            raise EdgarError(f"failed to decode JSON from {url}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise EdgarError(
                f"expected a JSON object from {url}, got {type(parsed).__name__}"
            )
        # response.json() returns Any; isinstance narrows to dict. The discovery boundary
        # narrows the untyped contents into typed FilingRecords (D0.12).
        return parsed

    def get_text(self, url: str) -> str:
        """Throttled GET -> raw text (for XML in Prompt 2). Same retry/throttle/403 policy."""
        response = self._request(url)
        return response.text

    def _request(self, url: str) -> requests.Response:
        """Throttled GET with retry/backoff. Returns a 2xx response or raises EdgarError."""
        total_attempts = 1 + self._max_retries
        last_error: str = "no attempts made"

        for attempt in range(total_attempts):
            self._bucket.acquire()  # every attempt is throttled (incl. retries)
            try:
                response = self._session.get(url, timeout=self._timeout)
            except requests.RequestException as exc:
                last_error = f"transport error: {exc}"
                logger.warning("EDGAR request to %s failed (attempt %d): %s", url, attempt + 1, exc)
                self._backoff(attempt, retry_after=None)
                continue

            status = response.status_code

            if status == 403:
                raise EdgarError(
                    f"EDGAR returned 403 for {url} — likely a SEC block or bad User-Agent "
                    f"(User-Agent must be 'Name email'; current: "
                    f"{self._session.headers.get('User-Agent')!r}). Not retrying."
                )

            if status in constants.HTTP_RETRY_STATUS:
                last_error = f"HTTP {status}"
                retry_after = _parse_retry_after(response.headers.get("Retry-After"))
                logger.warning(
                    "EDGAR request to %s got HTTP %d (attempt %d)", url, status, attempt + 1
                )
                self._backoff(attempt, retry_after=retry_after)
                continue

            if status >= 400:
                raise EdgarError(f"EDGAR returned non-retryable HTTP {status} for {url}")

            return response

        raise EdgarError(
            f"EDGAR request to {url} exhausted {total_attempts} attempts; last error: {last_error}"
        )

    def _backoff(self, attempt: int, retry_after: float | None) -> None:
        """Sleep before the next retry. Honors Retry-After, else exponential backoff."""
        if retry_after is not None:
            wait = retry_after
        else:
            wait = constants.HTTP_RETRY_BACKOFF_SECONDS * (2**attempt)
        self._sleep_func(wait)


# Module-level constant documenting the retry-count contract for callers/tests.
TOTAL_ATTEMPTS: Final[int] = 1 + constants.HTTP_MAX_RETRIES
