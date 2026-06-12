"""LIVE smoke test — hits the real EODHD EOD endpoint. MANUAL only; NOT in CI.

Run with: .venv/bin/pytest tests_live/test_returns_live.py
Requires EODHD_API_KEY in the environment (.env). ONE shared EodhdClient. Loose structural
assertions (no hard-coded price anchors). Validates F1-F5 + adjusted_close + the F7 (404/empty)
shape. F6 (rate limits) is best-effort/UNVERIFIED — NOT asserted here. See plan §12.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from celebpm import constants
from celebpm.eodhd_client import EodhdClient

pytestmark = pytest.mark.skipif(
    not (os.environ.get(constants.EODHD_API_KEY_ENV) or "").strip(),
    reason="EODHD_API_KEY not set",
)


@pytest.fixture(scope="module")
def client() -> EodhdClient:
    return EodhdClient.from_env()


def test_aapl_and_spy_structural(client: EodhdClient) -> None:
    frm, to = date(2024, 1, 2), date(2024, 1, 31)
    for symbol in ("AAPL.US", constants.SPY_BENCHMARK_SYMBOL):
        series = client.fetch_eod(symbol, from_date=frm, to_date=to)
        assert series.bars, f"{symbol} returned no bars"
        dates = [b.bar_date for b in series.bars]
        assert dates == sorted(dates)  # strictly ascending
        assert frm <= dates[0] and dates[-1] <= to
        for bar in series.bars:
            assert bar.close is not None and bar.close > 0
            assert bar.adjusted_close is not None and bar.adjusted_close > 0  # F4


def test_invalid_symbol_unpriceable(client: EodhdClient) -> None:
    series = client.fetch_eod(
        "ZZZZINVALIDXYZ.US", from_date=date(2024, 1, 2), to_date=date(2024, 1, 31)
    )
    # 404 OR empty list -> both resolve to an unpriceable empty series (no raise).
    assert series.bars == ()


def test_aapl_split_adjusted(client: EodhdClient) -> None:
    # AAPL 4:1 split on 2020-08-31; adjusted_close on 2020-08-28 ~ 1/4 of raw close.
    series = client.fetch_eod(
        "AAPL.US", from_date=date(2020, 8, 24), to_date=date(2020, 8, 28)
    )
    pre_split = [b for b in series.bars if b.bar_date == date(2020, 8, 28)]
    assert pre_split
    bar = pre_split[0]
    assert bar.close is not None and bar.adjusted_close is not None
    assert bar.adjusted_close == pytest.approx(bar.close / 4.0, rel=0.05)
