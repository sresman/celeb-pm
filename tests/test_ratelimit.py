"""Tests for ratelimit: TokenBucket + parse_retry_after (no real sleeps)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from celebpm.ratelimit import TokenBucket, parse_retry_after


class _FakeClock:
    """Injectable monotonic clock + sleep that advances the clock (deterministic)."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class TestTokenBucket:
    def test_rejects_non_positive_rate(self) -> None:
        with pytest.raises(ValueError):
            TokenBucket(0.0)
        with pytest.raises(ValueError):
            TokenBucket(-1.0)

    def test_first_acquire_instant(self) -> None:
        clock = _FakeClock()
        bucket = TokenBucket(
            1.0, capacity=1.0, time_source=clock.time, sleep_func=clock.sleep
        )
        bucket.acquire()
        assert clock.sleeps == []  # first call is instant (starts full)

    def test_capacity_one_spaces_subsequent_calls(self) -> None:
        clock = _FakeClock()
        bucket = TokenBucket(
            2.0, capacity=1.0, time_source=clock.time, sleep_func=clock.sleep
        )
        bucket.acquire()  # instant
        bucket.acquire()  # must wait 1/2s for a token
        assert len(clock.sleeps) == 1
        assert clock.sleeps[0] == pytest.approx(0.5)


class TestParseRetryAfter:
    def test_none_and_blank(self) -> None:
        assert parse_retry_after(None) is None
        assert parse_retry_after("") is None
        assert parse_retry_after("   ") is None

    def test_integer_seconds(self) -> None:
        assert parse_retry_after("5") == 5.0
        assert parse_retry_after(" 0 ") == 0.0
        # Negative integer floors at 0.
        assert parse_retry_after("-3") == 0.0

    def test_http_date_form(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(seconds=30)
        header = format_datetime(future, usegmt=True)
        wait = parse_retry_after(header)
        assert wait is not None
        assert 20.0 <= wait <= 40.0  # ~30s, allowing scheduling slop

    def test_past_http_date_floors_at_zero(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(seconds=120)
        header = format_datetime(past, usegmt=True)
        assert parse_retry_after(header) == 0.0

    def test_unparseable_returns_none(self) -> None:
        assert parse_retry_after("not-a-date") is None
