"""Tests for EodhdClient. Mock at the `requests` boundary + injected fake clock/sleep.

Also covers PriceBar/SymbolSeries round-trip and WindowExtrema's non-persistence.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pytest

from celebpm import constants
from celebpm.eodhd_client import (
    EodhdClient,
    _narrow_float,
    _narrow_int,
)
from celebpm.errors import EodhdError
from celebpm.price_types import PriceBar, PriceClient, SymbolSeries, WindowExtrema

# --- STATIC Protocol conformance: mypy verifies EodhdClient satisfies PriceClient. ---
_check: PriceClient = EodhdClient(api_token=None)


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

    def json(self) -> Any:  # noqa: ANN401 — mirrors requests.Response.json
        if self._raise_json:
            raise ValueError("no json")
        return self._json_body


class _FakeSession:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.gets: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def get(
        self,
        url: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> _FakeResponse:
        self.gets.append({"url": url, "params": params, "timeout": timeout})
        resp = self._responses[len(self.gets) - 1]
        if isinstance(resp, Exception):
            raise resp
        assert isinstance(resp, _FakeResponse)
        return resp


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _client(
    *,
    responses: list[object],
    api_token: str | None = "TOKEN",
    clock: _FakeClock | None = None,
    **kw: Any,  # noqa: ANN401
) -> tuple[EodhdClient, _FakeSession]:
    session = _FakeSession(responses)
    c = clock if clock is not None else _FakeClock()
    client = EodhdClient(
        api_token=api_token,
        session=session,  # type: ignore[arg-type]
        time_source=c.time,
        sleep_func=c.sleep,
        **kw,
    )
    return client, session


def _row(d: str, close: float, adj: float | None = None) -> dict[str, object]:
    return {
        "date": d,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "adjusted_close": adj if adj is not None else close,
        "volume": 1000,
    }


FROM = date(2024, 1, 2)
TO = date(2024, 1, 8)


class TestFromEnv:
    def test_token_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(constants.EODHD_API_KEY_ENV, "abc")
        client = EodhdClient.from_env()
        assert client._api_token == "abc"

    def test_blank_warns_no_raise(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setenv(constants.EODHD_API_KEY_ENV, "   ")
        caplog.set_level(logging.WARNING)
        client = EodhdClient.from_env()
        assert client._api_token is None
        assert caplog.records

    def test_absent_warns_no_raise(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.delenv(constants.EODHD_API_KEY_ENV, raising=False)
        caplog.set_level(logging.WARNING)
        client = EodhdClient.from_env()
        assert client._api_token is None
        assert caplog.records


class TestTokenParam:
    def test_token_present_in_params(self) -> None:
        client, session = _client(
            responses=[_FakeResponse(json_body=[_row("2024-01-02", 10.0)])],
            api_token="SECRET",
        )
        client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        params = session.gets[0]["params"]
        assert params[constants.EODHD_PARAM_API_TOKEN] == "SECRET"

    def test_token_none_omits_param_and_401_raises(self) -> None:
        client, session = _client(
            responses=[_FakeResponse(status_code=401)], api_token=None
        )
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        params = session.gets[0]["params"]
        assert constants.EODHD_PARAM_API_TOKEN not in params

    def test_token_never_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)
        client, _ = _client(
            responses=[
                _FakeResponse(status_code=500),
                _FakeResponse(json_body=[_row("2024-01-02", 10.0)]),
            ],
            api_token="TOPSECRET",
        )
        client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        for rec in caplog.records:
            assert "TOPSECRET" not in rec.getMessage()


class TestThrottleRetry:
    def test_token_per_attempt(self) -> None:
        clock = _FakeClock()
        client, session = _client(
            responses=[
                _FakeResponse(status_code=500),
                _FakeResponse(json_body=[_row("2024-01-02", 10.0)]),
            ],
            clock=clock,
            requests_per_minute=60.0,
        )
        client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        # 2 attempts; the retry backoff slept once.
        assert len(session.gets) == 2
        assert clock.sleeps  # at least the backoff sleep happened

    def test_429_honors_retry_after(self) -> None:
        clock = _FakeClock()
        client, _ = _client(
            responses=[
                _FakeResponse(status_code=429, headers={"Retry-After": "7"}),
                _FakeResponse(json_body=[_row("2024-01-02", 10.0)]),
            ],
            clock=clock,
        )
        client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        assert 7.0 in clock.sleeps

    def test_exhaustion_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(status_code=500)] * 4)
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)

    def test_decode_error_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(raise_json=True)])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)


class TestStatusHandling:
    def test_404_empty_series_no_raise(self) -> None:
        client, _ = _client(responses=[_FakeResponse(status_code=404)])
        series = client.fetch_eod("ZZZZ.US", from_date=FROM, to_date=TO)
        assert series.bars == ()
        assert series.symbol == "ZZZZ.US"

    def test_401_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(status_code=401)])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)

    def test_403_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(status_code=403)])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)

    def test_422_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(status_code=422)])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)

    def test_html_body_non_list_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(json_body="<html>error</html>")])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)


class TestParseSeries:
    def test_empty_list_empty_bars(self) -> None:
        client, _ = _client(responses=[_FakeResponse(json_body=[])])
        series = client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        assert series.bars == ()

    def test_top_level_dict_raises(self) -> None:
        client, _ = _client(responses=[_FakeResponse(json_body={"x": 1})])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)

    def test_row_missing_date_raises(self) -> None:
        bad = {"close": 10.0}
        client, _ = _client(responses=[_FakeResponse(json_body=[bad])])
        with pytest.raises(EodhdError):
            client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)

    def test_ohlc_none_tolerated(self) -> None:
        row: dict[str, object] = {"date": "2024-01-02", "close": None, "adjusted_close": None}
        client, _ = _client(responses=[_FakeResponse(json_body=[row])])
        series = client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        assert series.bars[0].close is None

    def test_keeps_all_bars_and_sorts(self) -> None:
        rows = [_row("2024-01-04", 3.0), _row("2024-01-02", 1.0), _row("2024-01-03", 2.0)]
        client, _ = _client(responses=[_FakeResponse(json_body=rows)])
        series = client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        assert [b.bar_date for b in series.bars] == [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
        ]

    def test_duplicate_date_keeps_last_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        rows = [_row("2024-01-02", 1.0), _row("2024-01-02", 9.0)]
        client, _ = _client(responses=[_FakeResponse(json_body=rows)])
        series = client.fetch_eod("AAPL.US", from_date=FROM, to_date=TO)
        assert len(series.bars) == 1
        assert series.bars[0].close == 9.0
        assert any("duplicate" in r.message for r in caplog.records)


class TestNarrowers:
    def test_narrow_float_rejects_bool(self) -> None:
        assert _narrow_float(True) is None
        assert _narrow_float(1.5) == 1.5
        assert _narrow_float(2) == 2.0

    def test_narrow_float_rejects_numeric_string(self) -> None:
        assert _narrow_float("1.5") is None

    def test_narrow_int_rejects_bool(self) -> None:
        assert _narrow_int(True) is None
        assert _narrow_int(5) == 5

    def test_narrow_int_rejects_numeric_string_and_float(self) -> None:
        assert _narrow_int("5") is None
        assert _narrow_int(5.0) is None


class TestSymbolSeriesRoundTrip:
    def test_round_trip(self) -> None:
        series = SymbolSeries(
            symbol="AAPL.US",
            fetched_at="2026-06-12T14:00:00+00:00",
            requested_from=date(2018, 1, 1),
            requested_to=date(2024, 1, 8),
            bars=(
                PriceBar(
                    bar_date=date(2024, 1, 2),
                    open=1.0,
                    high=2.0,
                    low=0.5,
                    close=1.5,
                    adjusted_close=1.4,
                    volume=100,
                ),
                PriceBar(
                    bar_date=date(2024, 1, 3),
                    open=2.0,
                    high=3.0,
                    low=1.5,
                    close=2.5,
                    adjusted_close=2.4,
                    volume=200,
                ),
            ),
        )
        d = series.to_dict()
        assert "schema_version" not in d
        back = SymbolSeries.from_dict(d)
        assert back == series
        assert back.first_bar_date == date(2024, 1, 2)
        assert back.last_bar_date == date(2024, 1, 3)

    def test_non_ascending_raises(self) -> None:
        d: dict[str, object] = {
            "symbol": "X.US",
            "fetched_at": "2026-06-12T14:00:00+00:00",
            "requested_from": "2018-01-01",
            "requested_to": "2024-01-08",
            "rows": [_row("2024-01-03", 1.0), _row("2024-01-02", 2.0)],
        }
        with pytest.raises(ValueError):
            SymbolSeries.from_dict(d)

    def test_duplicate_date_raises(self) -> None:
        d: dict[str, object] = {
            "symbol": "X.US",
            "fetched_at": "2026-06-12T14:00:00+00:00",
            "requested_from": "2018-01-01",
            "requested_to": "2024-01-08",
            "rows": [_row("2024-01-02", 1.0), _row("2024-01-02", 2.0)],
        }
        with pytest.raises(ValueError):
            SymbolSeries.from_dict(d)

    def test_bad_fetched_at_raises(self) -> None:
        d: dict[str, object] = {
            "symbol": "X.US",
            "fetched_at": "not-a-date",
            "requested_from": "2018-01-01",
            "requested_to": "2024-01-08",
            "rows": [],
        }
        with pytest.raises(ValueError):
            SymbolSeries.from_dict(d)


class TestWindowExtremaNotPersisted:
    def test_no_to_from_dict(self) -> None:
        assert not hasattr(WindowExtrema, "to_dict")
        assert not hasattr(WindowExtrema, "from_dict")
