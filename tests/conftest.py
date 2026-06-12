"""Shared fixtures. Unit tests mock at the client-METHOD level (no HTTP)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from celebpm import constants
from celebpm.constants import JSONObject
from celebpm.errors import EdgarError, EodhdError, OpenFigiError
from celebpm.openfigi_client import MapJob, MapResult
from celebpm.price_types import PriceBar, SymbolSeries, WindowExtrema

_FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> JSONObject:
    with (_FIXTURES / name).open(encoding="utf-8") as fh:
        data: object = json.load(fh)
    assert isinstance(data, dict)
    return data


@pytest.fixture
def sample_submissions() -> JSONObject:
    return _load("submissions_sample.json")


@pytest.fixture
def overflow_submissions() -> JSONObject:
    return _load("submissions_overflow.json")


class FakeClient:
    """Typed fake satisfying the HttpClient Protocol. Routes get_json by URL.

    Structural conformance means it type-checks under strict mypy without subclassing
    EdgarClient. Method-level mock — no HTTP.
    """

    def __init__(
        self,
        routes: dict[str, JSONObject],
        text_routes: dict[str, str] | None = None,
    ) -> None:
        self._routes = routes
        self._text_routes = text_routes if text_routes is not None else {}
        self.calls: list[str] = []
        self.json_calls: list[str] = []
        self.text_calls: list[str] = []

    def get_json(self, url: str) -> JSONObject:
        self.calls.append(url)
        self.json_calls.append(url)
        if url not in self._routes:
            raise EdgarError(f"FakeClient: no route for {url}")
        return self._routes[url]

    def get_text(self, url: str) -> str:
        self.calls.append(url)
        self.text_calls.append(url)
        if url not in self._text_routes:
            raise EdgarError(f"FakeClient: no text route for {url}")
        return self._text_routes[url]


class FakeMappingClient:
    """Typed fake satisfying the MappingClient Protocol. Method-level mock — no HTTP.

    Returns canned MapResults keyed by cusip (a missing cusip -> empty-match MapResult, i.e.
    an unresolved miss). Records map_jobs call count + the chunks received. Exposes a SETTABLE
    `max_jobs_per_request` attribute (structurally satisfies the read-only Protocol property).
    Can be configured to RAISE OpenFigiError on the Nth (1-based) call (partial-success tests).
    Structurally conforms to MappingClient (asserted statically in test_cusip_map).
    """

    def __init__(
        self,
        results: dict[str, MapResult] | None = None,
        *,
        max_jobs_per_request: int = 10,
        raise_on_call: int | None = None,
    ) -> None:
        self._results = results if results is not None else {}
        self.max_jobs_per_request = max_jobs_per_request
        self._raise_on_call = raise_on_call
        self.call_count = 0
        self.chunks: list[list[MapJob]] = []

    def map_jobs(self, jobs: list[MapJob]) -> list[MapResult]:
        if not jobs:
            return []
        self.call_count += 1
        self.chunks.append(list(jobs))
        if self._raise_on_call is not None and self.call_count == self._raise_on_call:
            raise OpenFigiError(f"FakeMappingClient: forced failure on call {self.call_count}")
        out: list[MapResult] = []
        for job in jobs:
            canned = self._results.get(job.cusip)
            if canned is not None:
                out.append(canned)
            else:
                out.append(MapResult(cusip=job.cusip, matches=()))
        return out


def build_series(
    symbol: str,
    closes: dict[date, float],
    *,
    requested_from: date = constants.EODHD_HISTORY_START,
    requested_to: date | None = None,
    adjusted: dict[date, float | None] | None = None,
    fetched_at: str | None = None,
) -> SymbolSeries:
    """Synthesize an ascending SymbolSeries from {date: close}.

    By default adjusted_close == close (100% coverage -> adjusted used). Pass `adjusted` to
    override per-date adjusted_close (None marks an unusable adjusted bar). high/low default to
    the close (so window_extrema over closes is deterministic).
    """
    dates = sorted(closes)
    bars: list[PriceBar] = []
    for d in dates:
        close = closes[d]
        adj = adjusted.get(d, close) if adjusted is not None else close
        bars.append(
            PriceBar(
                bar_date=d,
                open=close,
                high=close,
                low=close,
                close=close,
                adjusted_close=adj,
                volume=1000,
            )
        )
    return SymbolSeries(
        symbol=symbol,
        fetched_at=fetched_at or datetime.now(timezone.utc).isoformat(),
        requested_from=requested_from,
        requested_to=requested_to if requested_to is not None else (dates[-1] if dates else requested_from),
        bars=tuple(bars),
    )


class FakePriceClient:
    """Typed fake satisfying the PriceClient Protocol. Method-level mock — no HTTP.

    Constructed with `series: dict[symbol, SymbolSeries]`. fetch_eod returns the canned series
    (re-stamped with the requested from/to), increments call_count, records fetched_symbols.
    Unknown symbol -> empty SymbolSeries (unpriceable). Optionally RAISES EodhdError for a given
    symbol (per-symbol transport-isolation tests).
    """

    def __init__(
        self,
        series: dict[str, SymbolSeries] | None = None,
        *,
        raise_for: set[str] | None = None,
    ) -> None:
        self._series = series if series is not None else {}
        self._raise_for = raise_for if raise_for is not None else set()
        self.call_count = 0
        self.fetched_symbols: list[str] = []

    def fetch_eod(
        self, symbol: str, *, from_date: date, to_date: date
    ) -> SymbolSeries:
        self.call_count += 1
        self.fetched_symbols.append(symbol)
        if symbol in self._raise_for:
            raise EodhdError(f"FakePriceClient: forced failure for {symbol}")
        canned = self._series.get(symbol)
        if canned is None:
            return SymbolSeries(
                symbol=symbol,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                requested_from=from_date,
                requested_to=to_date,
                bars=(),
            )
        import dataclasses

        return dataclasses.replace(
            canned, requested_from=from_date, requested_to=to_date
        )


class FakePriceProvider:
    """Typed fake satisfying the authoritative PriceProvider Protocol. Keyed by TICKER.

    Canned maps for pure engine-math tests without the cache layer. The SPY benchmark is keyed
    under SPY_BENCHMARK_SYMBOL (the engine passes the literal constant). Records lookups; exposes
    an injected `today`. Can RAISE EodhdError for a given ticker (per-symbol isolation tests).
    """

    def __init__(
        self,
        *,
        today: date,
        prices: dict[str, dict[date, float]] | None = None,
        windows: dict[tuple[str, date, date], WindowExtrema | None] | None = None,
        symbols: dict[str | None, str | None] | None = None,
        has_data: dict[str, bool] | None = None,
        raise_for: set[str] | None = None,
    ) -> None:
        self._today = today
        self._prices = prices if prices is not None else {}
        self._windows = windows if windows is not None else {}
        self._symbols = symbols if symbols is not None else {}
        self._has_data = has_data if has_data is not None else {}
        self._raise_for = raise_for if raise_for is not None else set()
        self.price_asof_calls: list[tuple[str | None, date]] = []
        self.window_calls: list[tuple[str | None, date, date]] = []
        self.has_data_calls: list[str] = []

    @property
    def today(self) -> date:
        return self._today

    def resolve_symbol(self, ticker: str | None) -> str | None:
        if ticker is None:
            return None
        if ticker in self._symbols:
            return self._symbols[ticker]
        # default normalization mirror: append .US unless already suffixed.
        if constants.EODHD_EXCHANGE_SUFFIX_PATTERN.search(ticker) is not None:
            return ticker
        return f"{ticker}{constants.EODHD_US_EXCHANGE_SUFFIX}"

    def has_series_data(self, ticker: str) -> bool:
        self.has_data_calls.append(ticker)
        if ticker in self._raise_for:
            raise EodhdError(f"FakePriceProvider: forced failure for {ticker}")
        if ticker in self._has_data:
            return self._has_data[ticker]
        return bool(self._prices.get(ticker))

    def price_asof(self, ticker: str | None, on: date) -> float | None:
        self.price_asof_calls.append((ticker, on))
        if ticker is None:
            return None
        if ticker in self._raise_for:
            raise EodhdError(f"FakePriceProvider: forced failure for {ticker}")
        if on > self._today:
            return None
        series = self._prices.get(ticker)
        if not series:
            return None
        if on in series:
            return series[on]
        prior = [d for d in series if d <= on]
        if not prior:
            return None
        return series[max(prior)]

    def window_extrema(
        self, ticker: str | None, start: date, end: date
    ) -> WindowExtrema | None:
        if start > end:
            raise ValueError(f"start {start} > end {end}")
        self.window_calls.append((ticker, start, end))
        if ticker is None:
            return None
        if ticker in self._raise_for:
            raise EodhdError(f"FakePriceProvider: forced failure for {ticker}")
        key = (ticker, start, end)
        if key in self._windows:
            return self._windows[key]
        series = self._prices.get(ticker)
        if not series:
            return None
        in_range = {d: p for d, p in series.items() if start <= d <= end}
        if not in_range:
            return None
        hi = max(in_range, key=lambda d: (in_range[d], d.toordinal()))
        lo = min(in_range, key=lambda d: (in_range[d], -d.toordinal()))
        return WindowExtrema(
            high=in_range[hi], high_date=hi, low=in_range[lo], low_date=lo
        )


@pytest.fixture
def fake_client(
    sample_submissions: JSONObject, overflow_submissions: JSONObject
) -> FakeClient:
    """Routes the sample submissions + its single overflow file."""
    cik = "0001777813"
    routes = {
        constants.submissions_url(cik): sample_submissions,
        constants.submissions_overflow_url("CIK0001777813-submissions-001.json"): (
            overflow_submissions
        ),
    }
    return FakeClient(routes)
