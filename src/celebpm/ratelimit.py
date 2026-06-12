"""Shared rate-limiting primitives used by every HTTP client in the codebase.

Lifted (behavior-preserving) out of edgar_client.py so both EdgarClient and OpenFigiClient
share ONE TokenBucket implementation and ONE Retry-After parser. edgar_client.py re-exports
`TokenBucket as _TokenBucket` and `parse_retry_after as _parse_retry_after`, so the EDGAR
tests / call sites are unchanged. See plan §3.
"""

from __future__ import annotations

import email.utils
import time
from typing import Callable

from celebpm import constants


class TokenBucket:
    """Monotonic-clock token bucket. CAPACITY = 1 (EDGAR_BURST_CAPACITY), refill rate
    = rate_per_sec.

    Capacity-1 forces uniform spacing from the first call onward (no startup burst),
    avoiding rolling-window blocks. Single-threaded (no lock). The bucket starts with
    exactly `capacity` tokens, so the FIRST acquire() is instant; every subsequent call
    blocks (via sleep_func) until a token has refilled.
    """

    def __init__(
        self,
        rate_per_sec: float,
        capacity: float = constants.EDGAR_BURST_CAPACITY,
        time_source: Callable[[], float] = time.monotonic,
        sleep_func: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_sec <= 0:
            raise ValueError(f"rate_per_sec must be > 0, got {rate_per_sec}")
        self._rate = rate_per_sec
        self._capacity = capacity
        self._time_source = time_source
        self._sleep_func = sleep_func
        self._tokens = capacity  # start full -> first acquire is instant
        self._last = time_source()

    def acquire(self) -> None:
        """Block (via sleep_func) until one token is available, then consume it."""
        now = self._time_source()
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)

        if self._tokens < 1.0:
            deficit = 1.0 - self._tokens
            wait = deficit / self._rate
            self._sleep_func(wait)
            # Account for the wait: advance our clock view and refill accordingly.
            after = self._time_source()
            self._last = after
            self._tokens = min(self._capacity, self._tokens + (after - now) * self._rate)
            # If the injected sleep_func / clock did not advance enough (test fakes),
            # still grant the token we waited for (we slept for it).
            if self._tokens < 1.0:
                self._tokens = 1.0

        self._tokens -= 1.0


def parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header. Supports integer-seconds and HTTP-date forms.

    Returns the wait in seconds, or None if absent/unparseable.
    """
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    # Integer-seconds form.
    try:
        seconds = int(value)
        return max(0.0, float(seconds))
    except ValueError:
        pass
    # HTTP-date form. parsedate_to_datetime raises ValueError (Py>=3.10) or returns None
    # (older) on an unparseable value; treat BOTH as "no usable Retry-After" -> None.
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (ValueError, TypeError):
        return None
    if parsed is None:
        return None
    delta = parsed.timestamp() - time.time()
    return max(0.0, delta)
