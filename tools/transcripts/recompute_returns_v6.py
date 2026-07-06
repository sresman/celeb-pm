"""Recompute v6 signal-event returns from resolved_basket, with SMH + SPY benchmarks.

analysis/step4_signal_events_v6.csv has hand-corrected baskets, so its stored return
columns are stale. This reruns the EXACT return computation from theme_returns_v2
(equal-weight basket, SHORT inverts sign, MIXED/LONG raw; NO_BASKET and PAIR_TRADE
skip basket returns but still compute benchmarks) against the corrected
resolved_basket / basket_direction, and additionally emits an SPY benchmark block
alongside the existing SMH block. Every passthrough column is preserved.

Skip labels are kept distinct: NO_BASKET rows emit "NO_BASKET" and PAIR_TRADE rows
emit "PAIR_TRADE" in the basket-return cells (ret_/excess_/excess_spy_). The
benchmark cells (smh_/spy_) are numeric regardless (INSUFFICIENT_DATA past calendar).

Tickers already in analysis/eod_prices/ are reused; any new basket ticker is fetched
from EODHD and cached (same format/logic as theme_returns_v2.fetch_prices).

Usage:
    python -m tools.transcripts.recompute_returns_v6
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import json
import time
from typing import Any

import requests

from . import targets
from .theme_returns_v2 import (
    CALENDAR_SYMBOL,
    EODHD_FROM_DATE,
    EODHD_URL_TEMPLATE,
    HTTP_TIMEOUT,
    INSUFFICIENT_DATA,
    INTERVALS,
    NO_BASKET,
    NO_DATA,
    PRICE_CACHE_DIR,
    SLEEP_BETWEEN_FETCH,
    SMH_SYMBOL,
    _series_from_rows,
    _ticker_return,
    load_api_key,
)

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
INPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v6.csv"
OUTPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v6_with_returns.csv"

PAIR_TRADE = "PAIR_TRADE"
SKIP_LABELS = frozenset({NO_BASKET, PAIR_TRADE})

# New benchmark columns appended after the existing excess_ block.
NEW_COLS = [
    *(f"spy_{label}" for label in INTERVALS),
    *(f"excess_spy_{label}" for label in INTERVALS),
]


def parse_basket(resolved: str) -> tuple[list[str], str | None]:
    """resolved_basket cell -> (tickers, skip_label). Empty/NO_BASKET/PAIR_TRADE -> ([], label)."""
    cell = resolved.strip()
    if cell in SKIP_LABELS:
        return [], cell
    if not cell:
        return [], NO_BASKET
    return [t.strip() for t in cell.split(",") if t.strip()], None


def load_prices(needed: set[str], api_key: str) -> dict[str, dict[str, float]]:
    """Load each needed ticker from cache; fetch+cache any that are missing."""
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    prices: dict[str, dict[str, float]] = {}
    for ticker in sorted(needed):
        cache_path = PRICE_CACHE_DIR / f"{ticker}.json"
        if cache_path.exists():
            rows = json.loads(cache_path.read_text())
        else:
            params = {
                "from": EODHD_FROM_DATE, "to": today, "period": "d",
                "fmt": "json", "api_token": api_key,
            }
            resp = requests.get(
                EODHD_URL_TEMPLATE.format(symbol=ticker), params=params, timeout=HTTP_TIMEOUT
            )
            resp.raise_for_status()
            rows = resp.json()
            cache_path.write_text(json.dumps(rows))
            print(f"  [fetched] {ticker}")
            time.sleep(SLEEP_BETWEEN_FETCH)
        series = _series_from_rows(rows)
        prices[ticker] = series
        if not series:
            print(f"  [no data] {ticker}: EODHD returned no usable rows")
    return prices


def compute_all(
    event_date: str, basket: list[str], direction: str, skip_label: str | None,
    prices: dict[str, dict[str, float]], calendar: list[str],
) -> dict[str, Any]:
    """Mirror theme_returns_v2.compute_returns, with two benchmarks (SMH + SPY)."""
    smh_series = prices.get(SMH_SYMBOL, {})
    spy_series = prices.get(CALENDAR_SYMBOL, {})
    basket_skip = skip_label if skip_label is not None else NO_BASKET
    start_idx = bisect.bisect_left(calendar, event_date)
    out: dict[str, Any] = {}

    if start_idx >= len(calendar):
        for label in INTERVALS:
            out[f"ret_{label}"] = INSUFFICIENT_DATA
            out[f"smh_{label}"] = INSUFFICIENT_DATA
            out[f"spy_{label}"] = INSUFFICIENT_DATA
            out[f"excess_{label}"] = INSUFFICIENT_DATA
            out[f"excess_spy_{label}"] = INSUFFICIENT_DATA
        return out

    start_date = calendar[start_idx]
    for label, n_days in INTERVALS.items():
        end_idx = start_idx + n_days
        if end_idx >= len(calendar):
            out[f"ret_{label}"] = INSUFFICIENT_DATA
            out[f"smh_{label}"] = INSUFFICIENT_DATA
            out[f"spy_{label}"] = INSUFFICIENT_DATA
            out[f"excess_{label}"] = INSUFFICIENT_DATA
            out[f"excess_spy_{label}"] = INSUFFICIENT_DATA
            continue
        end_date = calendar[end_idx]

        smh_ret = _ticker_return(smh_series, start_date, end_date)
        spy_ret = _ticker_return(spy_series, start_date, end_date)
        out[f"smh_{label}"] = round(smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA
        out[f"spy_{label}"] = round(spy_ret, 2) if spy_ret is not None else INSUFFICIENT_DATA

        if not basket:
            out[f"ret_{label}"] = basket_skip
            out[f"excess_{label}"] = basket_skip
            out[f"excess_spy_{label}"] = basket_skip
            continue

        per_ticker = [
            r for t in basket
            if (r := _ticker_return(prices.get(t, {}), start_date, end_date)) is not None
        ]
        if not per_ticker:
            out[f"ret_{label}"] = NO_DATA
            out[f"excess_{label}"] = NO_DATA
            out[f"excess_spy_{label}"] = NO_DATA
            continue

        raw = sum(per_ticker) / len(per_ticker)
        signed = -raw if direction == "SHORT" else raw
        out[f"ret_{label}"] = round(signed, 2)
        out[f"excess_{label}"] = (
            round(signed - smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA
        )
        out[f"excess_spy_{label}"] = (
            round(signed - spy_ret, 2) if spy_ret is not None else INSUFFICIENT_DATA
        )
    return out


def main() -> None:
    with INPUT_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        in_fields = reader.fieldnames or []
        rows = list(reader)
    print(f"Loaded {len(rows)} rows from {INPUT_CSV.name}.")

    needed: set[str] = {SMH_SYMBOL, CALENDAR_SYMBOL}
    for r in rows:
        tickers, _ = parse_basket(r["resolved_basket"])
        needed.update(tickers)

    api_key = load_api_key()
    prices = load_prices(needed, api_key)

    calendar = sorted(prices.get(CALENDAR_SYMBOL, {}).keys())
    if not calendar:
        raise SystemExit(f"No {CALENDAR_SYMBOL} calendar data — cannot anchor returns.")
    print(f"Calendar ({CALENDAR_SYMBOL}): {len(calendar)} days "
          f"[{calendar[0]} .. {calendar[-1]}]")

    for r in rows:
        basket, skip_label = parse_basket(r["resolved_basket"])
        recomputed = compute_all(
            r["date"], basket, r["basket_direction"], skip_label, prices, calendar
        )
        r.update(recomputed)

    out_fields = list(in_fields) + [c for c in NEW_COLS if c not in in_fields]
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows ({len(out_fields)} cols) -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
