"""Tests for edgar_client. Throttle uses injected time/sleep (no real sleeps)."""

from __future__ import annotations

from typing import Callable

import pytest
import requests

from celebpm import constants
from celebpm.edgar_client import EdgarClient, HttpClient, _TokenBucket
from celebpm.errors import EdgarError

# --- STATIC Protocol conformance (v3): mypy verifies this; NOT a runtime isinstance check ---
# The Protocol is NOT @runtime_checkable. This annotated assignment type-checks under strict
# mypy iff EdgarClient structurally satisfies HttpClient.
_check: HttpClient = EdgarClient()


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

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestTokenBucket:
    def test_first_acquire_instant(self) -> None:
        clock = _FakeClock()
        bucket = _TokenBucket(9.0, time_source=clock.time, sleep_func=clock.sleep)
        bucket.acquire()
        assert clock.sleeps == []  # first call did not sleep

    def test_second_acquire_spaced(self) -> None:
        clock = _FakeClock()
        bucket = _TokenBucket(9.0, time_source=clock.time, sleep_func=clock.sleep)
        bucket.acquire()  # instant
        bucket.acquire()  # must wait ~1/9 s
        assert len(clock.sleeps) == 1
        assert clock.sleeps[0] == pytest.approx(1.0 / 9.0, rel=1e-6)

    def test_no_burst_of_rate(self) -> None:
        # Capacity 1: only the first call is instant; subsequent calls each sleep.
        clock = _FakeClock()
        bucket = _TokenBucket(9.0, time_source=clock.time, sleep_func=clock.sleep)
        for _ in range(5):
            bucket.acquire()
        assert len(clock.sleeps) == 4  # not 0; not a burst of 9 instant calls

    def test_refill_after_advance_makes_next_instant(self) -> None:
        clock = _FakeClock()
        bucket = _TokenBucket(9.0, time_source=clock.time, sleep_func=clock.sleep)
        bucket.acquire()  # instant, consumes the token
        clock.advance(1.0)  # plenty of time to refill (capacity 1)
        bucket.acquire()  # should be instant again
        assert clock.sleeps == []

    def test_rate_zero_raises(self) -> None:
        with pytest.raises(ValueError):
            _TokenBucket(0.0)

    def test_negative_rate_raises(self) -> None:
        with pytest.raises(ValueError):
            _TokenBucket(-1.0)


class _FakeResponse:
    def __init__(
        self,
        status_code: int,
        json_body: object = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}
        self.text = ""

    def json(self) -> object:
        if self._json is None:
            raise ValueError("no json")
        return self._json


def _client_with_responses(
    responses: list[_FakeResponse | requests.RequestException],
    sleeps: list[float],
) -> EdgarClient:
    """Build an EdgarClient whose session.get yields the given responses in order."""
    calls = {"i": 0}

    def fake_get(url: str, timeout: float) -> _FakeResponse:
        item = responses[calls["i"]]
        calls["i"] += 1
        if isinstance(item, requests.RequestException):
            raise item
        return item

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    session = requests.Session()
    # Replace session.get with our fake (method-adjacent seam; the plan sanctions this one
    # session-level retry test).
    session.get = fake_get  # type: ignore[assignment]  # test stub for retry logic
    return EdgarClient(session=session, sleep_func=fake_sleep)


class TestEdgarClientHttp:
    def test_user_agent_header_set(self) -> None:
        client = EdgarClient()
        assert client._session.headers["User-Agent"] == constants.USER_AGENT

    def test_get_json_success(self) -> None:
        sleeps: list[float] = []
        client = _client_with_responses([_FakeResponse(200, {"ok": True})], sleeps)
        assert client.get_json("https://example.test/x") == {"ok": True}

    def test_get_json_retries_then_succeeds(self) -> None:
        sleeps: list[float] = []
        client = _client_with_responses(
            [_FakeResponse(429), _FakeResponse(200, {"ok": 1})], sleeps
        )
        result = client.get_json("https://example.test/x")
        assert result == {"ok": 1}
        assert len(sleeps) >= 1  # backed off once

    def test_get_json_exhaustion_raises(self) -> None:
        sleeps: list[float] = []
        responses: list[_FakeResponse | requests.RequestException] = [
            _FakeResponse(503) for _ in range(constants.HTTP_MAX_RETRIES + 1)
        ]
        client = _client_with_responses(responses, sleeps)
        with pytest.raises(EdgarError):
            client.get_json("https://example.test/x")

    def test_total_attempts_is_one_plus_retries(self) -> None:
        sleeps: list[float] = []
        calls = {"i": 0}

        def fake_get(url: str, timeout: float) -> _FakeResponse:
            calls["i"] += 1
            return _FakeResponse(500)

        session = requests.Session()
        session.get = fake_get  # type: ignore[assignment]  # test stub
        client = EdgarClient(session=session, sleep_func=lambda s: sleeps.append(s))
        with pytest.raises(EdgarError):
            client.get_json("https://example.test/x")
        assert calls["i"] == 1 + constants.HTTP_MAX_RETRIES

    def test_403_raises_immediately_no_retry(self) -> None:
        sleeps: list[float] = []
        calls = {"i": 0}

        def fake_get(url: str, timeout: float) -> _FakeResponse:
            calls["i"] += 1
            return _FakeResponse(403)

        session = requests.Session()
        session.get = fake_get  # type: ignore[assignment]  # test stub
        client = EdgarClient(session=session, sleep_func=lambda s: sleeps.append(s))
        with pytest.raises(EdgarError) as exc_info:
            client.get_json("https://example.test/x")
        assert calls["i"] == 1  # no retry
        assert sleeps == []  # no backoff
        msg = str(exc_info.value).lower()
        assert "block" in msg or "user-agent" in msg

    def test_retry_after_honored(self) -> None:
        sleeps: list[float] = []
        client = _client_with_responses(
            [
                _FakeResponse(429, headers={"Retry-After": "2"}),
                _FakeResponse(200, {"ok": 1}),
            ],
            sleeps,
        )
        client.get_json("https://example.test/x")
        assert sleeps[0] == pytest.approx(2.0)

    def test_request_exception_retried(self) -> None:
        sleeps: list[float] = []
        client = _client_with_responses(
            [requests.ConnectionError("boom"), _FakeResponse(200, {"ok": 1})], sleeps
        )
        assert client.get_json("https://example.test/x") == {"ok": 1}

    def test_non_object_json_raises(self) -> None:
        sleeps: list[float] = []
        client = _client_with_responses([_FakeResponse(200, [1, 2, 3])], sleeps)
        with pytest.raises(EdgarError):
            client.get_json("https://example.test/x")


def test_sleep_func_signature() -> None:
    # Ensure the injected sleep_func type matches what EdgarClient expects.
    fn: Callable[[float], None] = lambda s: None
    EdgarClient(sleep_func=fn)
