"""Tests for price_cache: read/write cache I/O + CachingPriceProvider behavior."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pytest

from celebpm import constants
from celebpm.errors import EodhdError
from celebpm.price_cache import (
    CachingPriceProvider,
    read_price_cache,
    write_price_cache,
)
from celebpm.price_types import PriceProvider, SymbolSeries

from tests.conftest import FakePriceClient, build_series

TODAY = date(2026, 6, 12)


def _series(symbol: str, closes: dict[date, float], **kw: object) -> SymbolSeries:
    return build_series(symbol, closes, requested_to=TODAY, **kw)  # type: ignore[arg-type]


class TestCacheIO:
    def test_missing_returns_none(self, tmp_path: Path) -> None:
        assert read_price_cache("AAPL.US", tmp_path) is None

    def test_round_trip_through_wrapper(self, tmp_path: Path) -> None:
        s = _series("AAPL.US", {date(2024, 1, 2): 10.0, date(2024, 1, 3): 11.0})
        write_price_cache(s, tmp_path)
        back = read_price_cache("AAPL.US", tmp_path)
        assert back == s

    def test_wrapper_has_schema_version(self, tmp_path: Path) -> None:
        s = _series("AAPL.US", {date(2024, 1, 2): 10.0})
        path = write_price_cache(s, tmp_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["schema_version"] == constants.PRICE_CACHE_SCHEMA_VERSION
        assert "series" in raw
        assert "schema_version" not in raw["series"]

    def test_bad_symbol_write_raises(self, tmp_path: Path) -> None:
        s = build_series(".bad", {date(2024, 1, 2): 1.0})
        with pytest.raises(EodhdError):
            write_price_cache(s, tmp_path)

    def test_bad_symbol_read_returns_none(self, tmp_path: Path) -> None:
        assert read_price_cache(".bad", tmp_path) is None

    def _write_raw(self, tmp_path: Path, symbol: str, payload: object) -> None:
        d = constants.price_cache_dir(tmp_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{symbol}{constants.PRICE_CACHE_SUFFIX}").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_version_mismatch_miss(self, tmp_path: Path) -> None:
        self._write_raw(tmp_path, "AAPL.US", {"schema_version": 999, "series": {}})
        assert read_price_cache("AAPL.US", tmp_path) is None

    def test_missing_series_miss(self, tmp_path: Path) -> None:
        self._write_raw(
            tmp_path,
            "AAPL.US",
            {"schema_version": constants.PRICE_CACHE_SCHEMA_VERSION, "series": 5},
        )
        assert read_price_cache("AAPL.US", tmp_path) is None

    def test_corrupt_json_miss(self, tmp_path: Path) -> None:
        d = constants.price_cache_dir(tmp_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / "AAPL.US.json").write_text("{not json", encoding="utf-8")
        assert read_price_cache("AAPL.US", tmp_path) is None

    def test_symbol_mismatch_miss_before_from_dict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # series.symbol mismatches the requested symbol -> miss WITHOUT calling from_dict.
        s = _series("MSFT.US", {date(2024, 1, 2): 10.0})
        self._write_raw(
            tmp_path,
            "AAPL.US",
            {
                "schema_version": constants.PRICE_CACHE_SCHEMA_VERSION,
                "series": s.to_dict(),
            },
        )
        called = {"n": 0}
        orig = SymbolSeries.from_dict

        def spy(raw: dict[str, object]) -> SymbolSeries:
            called["n"] += 1
            return orig(raw)

        monkeypatch.setattr(SymbolSeries, "from_dict", staticmethod(spy))
        assert read_price_cache("AAPL.US", tmp_path) is None
        assert called["n"] == 0

    def test_bad_fetched_at_miss(self, tmp_path: Path) -> None:
        s = _series("AAPL.US", {date(2024, 1, 2): 10.0})
        d = s.to_dict()
        d["fetched_at"] = "garbage"
        self._write_raw(
            tmp_path,
            "AAPL.US",
            {"schema_version": constants.PRICE_CACHE_SCHEMA_VERSION, "series": d},
        )
        assert read_price_cache("AAPL.US", tmp_path) is None

    def test_path_traversal_guard(self, tmp_path: Path) -> None:
        # a '../' style symbol fails the pattern -> miss (never escapes root).
        assert read_price_cache("../evil", tmp_path) is None


# --- STATIC conformance ---
_check: PriceProvider = CachingPriceProvider(FakePriceClient(), today=TODAY)


class TestProviderBasics:
    def test_history_start_after_today_raises(self) -> None:
        with pytest.raises(ValueError):
            CachingPriceProvider(
                FakePriceClient(), today=date(2017, 1, 1)
            )

    def test_resolve_symbol(self, tmp_path: Path) -> None:
        p = CachingPriceProvider(FakePriceClient(), data_root=tmp_path, today=TODAY)
        assert p.resolve_symbol("AAPL") == "AAPL.US"
        assert p.resolve_symbol(None) is None

    def test_cache_hit_avoids_refetch(self, tmp_path: Path) -> None:
        client = FakePriceClient(
            {"AAPL.US": _series("AAPL.US", {date(2024, 1, 2): 10.0, date(2024, 6, 1): 12.0})}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.price_asof("AAPL", date(2024, 1, 2)) == 10.0
        assert client.call_count == 1
        assert p.price_asof("AAPL", date(2024, 6, 1)) == 12.0
        assert client.call_count == 1  # no refetch within [floor, requested_to]

    def test_ticker_none(self, tmp_path: Path) -> None:
        p = CachingPriceProvider(FakePriceClient(), data_root=tmp_path, today=TODAY)
        assert p.price_asof(None, TODAY) is None
        assert p.window_extrema(None, date(2024, 1, 1), date(2024, 2, 1)) is None


class TestPerCallFloorRule:
    def _provider(self, tmp_path: Path) -> tuple[CachingPriceProvider, FakePriceClient]:
        client = FakePriceClient(
            {
                "AAPL.US": _series(
                    "AAPL.US",
                    {date(2024, 1, 2): 10.0, date(2024, 1, 3): 11.0},
                )
            }
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        return p, client

    def test_future_date_none_no_fetch(self, tmp_path: Path) -> None:
        p, client = self._provider(tmp_path)
        assert p.price_asof("AAPL", date(2027, 1, 1)) is None
        assert client.call_count == 0

    def test_below_floor_none_no_fetch(self, tmp_path: Path) -> None:
        p, client = self._provider(tmp_path)
        assert p.price_asof("AAPL", date(2017, 5, 1)) is None
        assert client.call_count == 0  # cache HIT (refuse below floor); no fetch

    def test_within_span_no_refetch(self, tmp_path: Path) -> None:
        p, client = self._provider(tmp_path)
        assert p.price_asof("AAPL", date(2024, 1, 2)) == 10.0
        assert client.call_count == 1
        assert p.price_asof("AAPL", date(2024, 1, 3)) == 11.0
        assert client.call_count == 1

    def test_beyond_requested_to_refetches_and_updates_memo(
        self, tmp_path: Path
    ) -> None:
        # seed cache with requested_to in the past.
        old = build_series(
            "AAPL.US",
            {date(2024, 1, 2): 10.0},
            requested_to=date(2024, 6, 1),
        )
        write_price_cache(old, tmp_path)
        client = FakePriceClient(
            {
                "AAPL.US": _series(
                    "AAPL.US",
                    {date(2024, 1, 2): 10.0, date(2026, 6, 11): 50.0},
                )
            }
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        # a lookup beyond the cached requested_to (but <= today) -> refetch.
        assert p.price_asof("AAPL", date(2026, 6, 11)) == 50.0
        assert client.call_count == 1
        # the memo is updated -> the new bar is now served without a second fetch.
        assert p.price_asof("AAPL", date(2026, 6, 11)) == 50.0
        assert client.call_count == 1

    def test_window_start_after_end_value_error(self, tmp_path: Path) -> None:
        p, _ = self._provider(tmp_path)
        with pytest.raises(ValueError):
            p.window_extrema("AAPL", date(2024, 2, 1), date(2024, 1, 1))

    def test_post_ipo_no_refetch_loop(self, tmp_path: Path) -> None:
        # first bar 2021; floor 2018; a 2019/2020 lookup is None (before first bar), no loop.
        client = FakePriceClient(
            {"NEWCO.US": _series("NEWCO.US", {date(2021, 3, 1): 5.0, date(2024, 1, 2): 8.0})}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.price_asof("NEWCO", date(2019, 5, 1)) is None
        assert p.price_asof("NEWCO", date(2020, 5, 1)) is None
        assert p.price_asof("NEWCO", date(2019, 5, 1)) is None
        assert client.call_count == 1  # one fetch; no refetch loop


class TestHasSeriesData:
    def test_true_with_usable(self, tmp_path: Path) -> None:
        client = FakePriceClient({"AAPL.US": _series("AAPL.US", {date(2024, 1, 2): 10.0})})
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.has_series_data("AAPL") is True

    def test_false_empty(self, tmp_path: Path) -> None:
        client = FakePriceClient({})  # unknown -> empty series
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.has_series_data("NOPE") is False

    def test_false_all_unusable(self, tmp_path: Path) -> None:
        # negative close everywhere -> no usable price.
        client = FakePriceClient(
            {
                "BAD.US": _series(
                    "BAD.US",
                    {date(2024, 1, 2): -1.0, date(2024, 1, 3): -2.0},
                    adjusted={date(2024, 1, 2): -1.0, date(2024, 1, 3): -2.0},
                )
            }
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.has_series_data("BAD") is False

    def test_unmappable_false(self, tmp_path: Path) -> None:
        p = CachingPriceProvider(FakePriceClient(), data_root=tmp_path, today=TODAY)
        assert p.has_series_data("$$$") is False

    def test_spy_via_constant(self, tmp_path: Path) -> None:
        client = FakePriceClient(
            {constants.SPY_BENCHMARK_SYMBOL: _series(constants.SPY_BENCHMARK_SYMBOL, {date(2024, 1, 2): 400.0})}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.has_series_data(constants.SPY_BENCHMARK_SYMBOL) is True
        assert p.price_asof(constants.SPY_BENCHMARK_SYMBOL, date(2024, 1, 2)) == 400.0


class TestCoverageThreshold:
    def test_one_bad_adjusted_bar_uses_adjusted(self, tmp_path: Path) -> None:
        # 3 bars, one adjusted None -> coverage 2/3 >= 0.5 -> adjusted used; bad bar skipped.
        closes = {date(2024, 1, 2): 100.0, date(2024, 1, 3): 100.0, date(2024, 1, 4): 100.0}
        adjusted = {date(2024, 1, 2): 25.0, date(2024, 1, 3): None, date(2024, 1, 4): 25.0}
        client = FakePriceClient(
            {"X.US": _series("X.US", closes, adjusted=adjusted)}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        # adjusted (25) used, not raw (100); the None bar carries forward to prior usable.
        assert p.price_asof("X", date(2024, 1, 2)) == 25.0
        assert p.price_asof("X", date(2024, 1, 3)) == 25.0  # skipped -> prior

    def test_low_coverage_falls_back_to_raw_warns(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        closes = {date(2024, 1, 2): 100.0, date(2024, 1, 3): 110.0, date(2024, 1, 4): 120.0}
        adjusted = {date(2024, 1, 2): 50.0, date(2024, 1, 3): None, date(2024, 1, 4): None}
        client = FakePriceClient(
            {"X.US": _series("X.US", closes, adjusted=adjusted)}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        # coverage 1/3 < 0.5 -> raw close used throughout (never mixed).
        assert p.price_asof("X", date(2024, 1, 2)) == 100.0
        w = p.window_extrema("X", date(2024, 1, 2), date(2024, 1, 4))
        assert w is not None and w.high == 120.0
        assert any("coverage" in r.message for r in caplog.records)

    def test_coverage_exactly_half_uses_adjusted(self, tmp_path: Path) -> None:
        closes = {date(2024, 1, 2): 100.0, date(2024, 1, 3): 100.0}
        adjusted = {date(2024, 1, 2): 50.0, date(2024, 1, 3): None}
        client = FakePriceClient(
            {"X.US": _series("X.US", closes, adjusted=adjusted)}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.price_asof("X", date(2024, 1, 2)) == 50.0  # adjusted (coverage 0.5)


class TestZeroAndUsability:
    def test_zero_is_usable(self, tmp_path: Path) -> None:
        client = FakePriceClient(
            {"BANK.US": _series("BANK.US", {date(2024, 1, 2): 5.0, date(2024, 1, 3): 0.0})}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.price_asof("BANK", date(2024, 1, 3)) == 0.0
        assert p.has_series_data("BANK") is True
        w = p.window_extrema("BANK", date(2024, 1, 2), date(2024, 1, 3))
        assert w is not None and w.low == 0.0

    def test_negative_unusable_skipped(self, tmp_path: Path) -> None:
        client = FakePriceClient(
            {
                "X.US": _series(
                    "X.US",
                    {date(2024, 1, 2): 5.0, date(2024, 1, 3): -1.0},
                    adjusted={date(2024, 1, 2): 5.0, date(2024, 1, 3): -1.0},
                )
            }
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        # negative bar skipped -> carries forward to the prior usable (5.0).
        assert p.price_asof("X", date(2024, 1, 3)) == 5.0


class TestStalenessAndAlignment:
    def test_carry_forward_prior_trading_day(self, tmp_path: Path) -> None:
        client = FakePriceClient(
            {"X.US": _series("X.US", {date(2024, 1, 2): 10.0, date(2024, 1, 5): 12.0})}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        # 2024-01-03 (no bar) -> prior usable 2024-01-02.
        assert p.price_asof("X", date(2024, 1, 3)) == 10.0

    def test_before_first_bar_none(self, tmp_path: Path) -> None:
        client = FakePriceClient({"X.US": _series("X.US", {date(2024, 1, 2): 10.0})})
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.price_asof("X", date(2018, 6, 1)) is None

    def test_staleness_soft_warn_returns_price(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        client = FakePriceClient({"DELIST.US": _series("DELIST.US", {date(2024, 1, 2): 10.0})})
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        # ask months later -> last available price + WARN (NEVER None due to age).
        assert p.price_asof("DELIST", date(2024, 6, 1)) == 10.0
        assert any("stale" in r.message for r in caplog.records)

    def test_no_hard_staleness_constant(self) -> None:
        assert not hasattr(constants, "PRICE_STALENESS_MAX_DAYS")

    def test_window_clamps_below_floor(self, tmp_path: Path) -> None:
        client = FakePriceClient(
            {"X.US": _series("X.US", {date(2024, 1, 2): 10.0, date(2024, 1, 3): 12.0})}
        )
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        w = p.window_extrema("X", date(2010, 1, 1), date(2024, 1, 3))
        assert w is not None and w.high == 12.0 and w.low == 10.0

    def test_empty_window_none(self, tmp_path: Path) -> None:
        client = FakePriceClient({"X.US": _series("X.US", {date(2024, 1, 2): 10.0})})
        p = CachingPriceProvider(client, data_root=tmp_path, today=TODAY)
        assert p.window_extrema("X", date(2025, 1, 1), date(2025, 2, 1)) is None
