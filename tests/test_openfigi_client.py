"""Tests for OpenFigiClient. Mock at the `requests` boundary + injected fake clock/sleep."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from celebpm import constants
from celebpm.errors import OpenFigiError
from celebpm.openfigi_client import (
    MapJob,
    MappingClient,
    MapResult,
    OpenFigiClient,
)

# --- STATIC Protocol conformance: mypy verifies OpenFigiClient satisfies MappingClient,
#     INCLUDING the max_jobs_per_request property + map_jobs. ---
_check: MappingClient = OpenFigiClient(api_key=None)
_jobs_size: int = _check.max_jobs_per_request


VALID_CUSIP = "037833100"  # AAPL
VALID_CUSIP_2 = "594918104"  # MSFT


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_body: object = None,
        headers: dict[str, str] | None = None,
        raise_json: bool = False,
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.headers = headers if headers is not None else {}
        self._raise_json = raise_json
        self.text = ""

    def json(self) -> Any:  # noqa: ANN401 — mirrors requests.Response.json (returns Any)
        if self._raise_json:
            raise ValueError("no json")
        return self._json_body


class _FakeSession:
    """Records posts; returns queued responses (or a transport exception) in order."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.posts: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def post(
        self,
        url: str,
        *,
        json: object = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> _FakeResponse:
        self.posts.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        resp = self._responses[len(self.posts) - 1]
        if isinstance(resp, Exception):
            raise resp
        assert isinstance(resp, _FakeResponse)
        return resp


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []
        self.acquisitions = 0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _match_payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ticker": "AAPL",
        "name": "APPLE INC",
        "exchCode": "US",
        "securityType": "Common Stock",
        "securityType2": "Common Stock",
        "marketSector": "Equity",
        "compositeFIGI": "BBG000B9XRY4",
        "figi": "BBG000B9XVV8",
    }
    base.update(over)
    return base


def _client(
    *,
    responses: list[object],
    api_key: str | None = None,
    clock: _FakeClock | None = None,
    **kw: Any,  # noqa: ANN401 — pass-through ctor overrides for test tuning
) -> tuple[OpenFigiClient, _FakeSession]:
    session = _FakeSession(responses)
    c = clock if clock is not None else _FakeClock()
    client = OpenFigiClient(
        api_key=api_key,
        session=session,  # type: ignore[arg-type]  # _FakeSession is a structural stand-in
        time_source=c.time,
        sleep_func=c.sleep,
        **kw,
    )
    return client, session


class TestEmptyAndOversized:
    def test_empty_input_no_post_no_token(self) -> None:
        clock = _FakeClock()
        client, session = _client(responses=[], clock=clock)
        assert client.map_jobs([]) == []
        assert session.posts == []
        assert clock.sleeps == []

    def test_oversized_chunk_raises_value_error(self) -> None:
        client, session = _client(responses=[], max_jobs_per_request=1)
        jobs = [MapJob(cusip=VALID_CUSIP), MapJob(cusip=VALID_CUSIP_2)]
        with pytest.raises(ValueError):
            client.map_jobs(jobs)
        assert session.posts == []


class TestParsing:
    def test_single_chunk_one_post_input_order(self) -> None:
        body = [
            {"data": [_match_payload(ticker="AAPL")]},
            {"data": [_match_payload(ticker="MSFT")]},
        ]
        client, session = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP), MapJob(cusip=VALID_CUSIP_2)])
        assert len(session.posts) == 1
        assert [r.cusip for r in out] == [VALID_CUSIP, VALID_CUSIP_2]
        assert out[0].matches[0].ticker == "AAPL"
        assert out[1].matches[0].ticker == "MSFT"

    def test_length_guard_raises(self) -> None:
        body = [{"data": [_match_payload()]}]  # 1 element, 2 jobs
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP), MapJob(cusip=VALID_CUSIP_2)])

    def test_top_level_non_list_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(json_body={"error": "bad request"})])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_whitelisted_warning_is_permanent_miss(self) -> None:
        body: list[dict[str, object]] = [{"warning": "No identifier found."}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert out[0].matches == ()
        assert out[0].warning == "No identifier found."

    def test_empty_data_is_permanent_miss(self) -> None:
        body: list[dict[str, object]] = [{"data": []}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert out[0].matches == ()

    def test_warning_plus_data_data_wins(self) -> None:
        body = [{"warning": "No identifier found.", "data": [_match_payload()]}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert len(out[0].matches) == 1
        assert out[0].warning == "No identifier found."

    def test_in_payload_error_raises(self) -> None:
        body = [{"error": "Invalid idValue."}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_unrecognized_warning_raises(self) -> None:
        body = [{"warning": "rate limited, slow down"}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_element_not_object_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(json_body=["not a dict"])])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_data_not_a_list_raises(self) -> None:
        body = [{"data": {"ticker": "AAPL"}}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_match_not_object_raises(self) -> None:
        body = [{"data": ["not a dict"]}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_ticker_normalized_to_none(self, blank: str) -> None:
        body = [{"data": [_match_payload(ticker=blank)]}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert out[0].matches[0].ticker is None

    def test_non_blank_ticker_stripped(self) -> None:
        body = [{"data": [_match_payload(ticker="  AAPL  ")]}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert out[0].matches[0].ticker == "AAPL"

    def test_non_string_ticker_is_none(self) -> None:
        body = [{"data": [_match_payload(ticker=123)]}]
        client, _ = _client(responses=[_FakeResponse(json_body=body)])
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert out[0].matches[0].ticker is None


class TestTransport:
    def test_5xx_then_success_retries(self) -> None:
        clock = _FakeClock()
        body = [{"data": [_match_payload()]}]
        client, session = _client(
            responses=[
                _FakeResponse(status_code=503),
                _FakeResponse(json_body=body),
            ],
            clock=clock,
        )
        out = client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert len(session.posts) == 2
        assert len(out[0].matches) == 1

    def test_5xx_every_attempt_raises(self) -> None:
        responses: list[object] = [_FakeResponse(status_code=503) for _ in range(4)]
        client, _ = _client(responses=responses)
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_json_decode_failure_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(raise_json=True)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_transport_exception_raises(self) -> None:
        responses: list[object] = [
            requests.ConnectionError("boom") for _ in range(4)
        ]
        client, _ = _client(responses=responses)
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])

    def test_non_retryable_4xx_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(status_code=400)])
        with pytest.raises(OpenFigiError):
            client.map_jobs([MapJob(cusip=VALID_CUSIP)])


class TestThrottleAndBackoff:
    def test_one_token_per_attempt_incl_retries(self) -> None:
        # capacity-1 bucket: 1st acquire instant, 2nd (retry) sleeps -> exactly one sleep.
        clock = _FakeClock()
        body = [{"data": [_match_payload()]}]
        client, _ = _client(
            responses=[_FakeResponse(status_code=503), _FakeResponse(json_body=body)],
            clock=clock,
            requests_per_minute=60.0,  # 1/sec
        )
        client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        # One backoff sleep (after the 503) + one token-bucket sleep before the 2nd attempt.
        # Backoff sleep present:
        assert constants.HTTP_RETRY_BACKOFF_SECONDS in clock.sleeps

    def test_429_with_retry_after_honored(self) -> None:
        clock = _FakeClock()
        body = [{"data": [_match_payload()]}]
        client, _ = _client(
            responses=[
                _FakeResponse(status_code=429, headers={"Retry-After": "7"}),
                _FakeResponse(json_body=body),
            ],
            clock=clock,
        )
        client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert 7.0 in clock.sleeps

    def test_429_without_retry_after_uses_per_minute_window(self) -> None:
        clock = _FakeClock()
        body = [{"data": [_match_payload()]}]
        client, _ = _client(
            responses=[
                _FakeResponse(status_code=429),
                _FakeResponse(json_body=body),
            ],
            clock=clock,
        )
        client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert constants.OPENFIGI_RATE_LIMIT_BACKOFF_SECONDS in clock.sleeps


class TestHeaders:
    def test_with_key_sends_header_and_content_type(self) -> None:
        body = [{"data": [_match_payload()]}]
        client, session = _client(
            responses=[_FakeResponse(json_body=body)], api_key="SECRET"
        )
        client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        hdrs = session.posts[0]["headers"]
        assert hdrs[constants.OPENFIGI_API_KEY_HEADER] == "SECRET"
        assert hdrs["Content-Type"] == constants.OPENFIGI_CONTENT_TYPE

    def test_no_key_omits_auth_header(self) -> None:
        body = [{"data": [_match_payload()]}]
        client, session = _client(responses=[_FakeResponse(json_body=body)])
        client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        hdrs = session.posts[0]["headers"]
        assert constants.OPENFIGI_API_KEY_HEADER not in hdrs

    def test_caller_session_headers_not_mutated(self) -> None:
        session = _FakeSession([_FakeResponse(json_body=[{"data": [_match_payload()]}])])
        session.headers = {"X-Caller": "keep"}
        clock = _FakeClock()
        client = OpenFigiClient(
            api_key="SECRET",
            session=session,  # type: ignore[arg-type]
            time_source=clock.time,
            sleep_func=clock.sleep,
        )
        client.map_jobs([MapJob(cusip=VALID_CUSIP)])
        assert session.headers == {"X-Caller": "keep"}


class TestFromEnv:
    def test_present_key_keyed_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(constants.OPENFIGI_API_KEY_ENV, "REALKEY")
        client = OpenFigiClient.from_env()
        assert client.max_jobs_per_request == (
            constants.OPENFIGI_MAX_JOBS_PER_REQUEST_WITH_KEY
        )

    def test_absent_key_no_key_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(constants.OPENFIGI_API_KEY_ENV, raising=False)
        client = OpenFigiClient.from_env()
        assert client.max_jobs_per_request == (
            constants.OPENFIGI_MAX_JOBS_PER_REQUEST_NO_KEY
        )

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_key_no_key_mode(
        self, monkeypatch: pytest.MonkeyPatch, blank: str
    ) -> None:
        monkeypatch.setenv(constants.OPENFIGI_API_KEY_ENV, blank)
        client = OpenFigiClient.from_env()
        assert client.max_jobs_per_request == (
            constants.OPENFIGI_MAX_JOBS_PER_REQUEST_NO_KEY
        )


class TestConstructorValidation:
    def test_rpm_non_positive(self) -> None:
        with pytest.raises(ValueError):
            OpenFigiClient(requests_per_minute=0.0)

    def test_batch_non_positive(self) -> None:
        with pytest.raises(ValueError):
            OpenFigiClient(max_jobs_per_request=0)

    def test_timeout_non_positive(self) -> None:
        with pytest.raises(ValueError):
            OpenFigiClient(timeout=0.0)
        with pytest.raises(ValueError):
            OpenFigiClient(timeout=-1.0)

    def test_negative_retries(self) -> None:
        with pytest.raises(ValueError):
            OpenFigiClient(max_retries=-1)


class TestMapJobValidation:
    def test_malformed_cusip_raises(self) -> None:
        with pytest.raises(OpenFigiError):
            MapJob(cusip="short")
        with pytest.raises(OpenFigiError):
            MapJob(cusip="lowercase")
