"""Extend the v6 return file with 6m/9m/18m horizons (SMH + SPY benchmarks).

Reads analysis/step4_signal_events_v6_with_returns.csv and recomputes returns at
SEVEN horizons — 1m/1q/6m/9m/1y/18m/2y (21/63/126/189/252/378/504 fwd trading days)
— from the corrected resolved_basket / basket_direction, using the exact logic of
theme_returns_v2 / recompute_returns_v6. The four pre-existing horizons reproduce
identically (deterministic); the three new ones are added. Columns are emitted in
ascending-horizon order per family, which matches the requested interleaving
("after _1q add _6m,_9m; after _1y add _18m").

NO_BASKET / PAIR_TRADE rows skip basket returns (keeping their distinct skip label)
but still get numeric benchmarks. No new tickers are needed — longer horizons reuse
the existing analysis/eod_prices/ cache.

Usage:
    python -m tools.transcripts.recompute_returns_v6_extended
"""

from __future__ import annotations

import bisect
import csv
from typing import Any

from . import targets
from .recompute_returns_v6 import load_prices, parse_basket
from .theme_returns_v2 import (
    CALENDAR_SYMBOL,
    INSUFFICIENT_DATA,
    NO_BASKET,
    NO_DATA,
    SMH_SYMBOL,
    _ticker_return,
    load_api_key,
)

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
INPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v6_with_returns.csv"
OUTPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v6_with_returns_extended.csv"

# Seven horizons, ascending in forward trading days (= requested column order).
HORIZONS: dict[str, int] = {
    "1m": 21, "1q": 63, "6m": 126, "9m": 189, "1y": 252, "18m": 378, "2y": 504,
}
FAMILIES = ["ret", "smh", "excess", "spy", "excess_spy"]
RETURN_COLS = [f"{fam}_{h}" for fam in FAMILIES for h in HORIZONS]


def compute_all(
    event_date: str, basket: list[str], direction: str, skip_label: str | None,
    prices: dict[str, dict[str, float]], calendar: list[str],
) -> dict[str, Any]:
    """Mirror recompute_returns_v6.compute_all, over the 7-horizon HORIZONS set."""
    smh_series = prices.get(SMH_SYMBOL, {})
    spy_series = prices.get(CALENDAR_SYMBOL, {})
    basket_skip = skip_label if skip_label is not None else NO_BASKET
    start_idx = bisect.bisect_left(calendar, event_date)
    out: dict[str, Any] = {}

    if start_idx >= len(calendar):
        for label in HORIZONS:
            for fam in FAMILIES:
                out[f"{fam}_{label}"] = INSUFFICIENT_DATA
        return out

    start_date = calendar[start_idx]
    for label, n_days in HORIZONS.items():
        end_idx = start_idx + n_days
        if end_idx >= len(calendar):
            for fam in FAMILIES:
                out[f"{fam}_{label}"] = INSUFFICIENT_DATA
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

    passthrough = [c for c in in_fields if c not in set(RETURN_COLS)]

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
        r.update(compute_all(r["date"], basket, r["basket_direction"], skip_label, prices, calendar))

    out_fields = passthrough + RETURN_COLS
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows ({len(out_fields)} cols) -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
