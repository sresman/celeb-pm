"""Recompute return columns on a corrected signal-event CSV from its resolved_basket.

Some baskets were hand-corrected after the v5 run, so the return columns are stale.
This reruns the EXACT return computation from theme_returns_v2 (equal-weight basket,
SHORT inverts sign, MIXED/LONG raw, NO_BASKET skips basket returns but still computes
SMH) against the corrected ``resolved_basket`` / ``basket_direction`` columns, and
rewrites the 12 return columns. Every other column is passed through untouched.

Tickers already in analysis/eod_prices/ are reused; any new basket ticker is fetched
from EODHD and cached (same cache format/logic as theme_returns_v2.fetch_prices).

Usage:
    python -m tools.transcripts.recompute_returns_final
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import time

from . import targets
from .theme_returns_v2 import (
    CALENDAR_SYMBOL,
    EODHD_FROM_DATE,
    EODHD_URL_TEMPLATE,
    HTTP_TIMEOUT,
    INTERVALS,
    NO_BASKET,
    PRICE_CACHE_DIR,
    SLEEP_BETWEEN_FETCH,
    SMH_SYMBOL,
    _series_from_rows,
    compute_returns,
    load_api_key,
)

import requests

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
INPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v5_corrected.csv"
OUTPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v5_final.csv"

RETURN_COLS = [
    *(f"ret_{label}" for label in INTERVALS),
    *(f"smh_{label}" for label in INTERVALS),
    *(f"excess_{label}" for label in INTERVALS),
]


def parse_basket(resolved: str) -> list[str]:
    """resolved_basket cell -> ticker list. Empty or the literal NO_BASKET -> []."""
    cell = resolved.strip()
    if not cell or cell == NO_BASKET:
        return []
    return [t.strip() for t in cell.split(",") if t.strip()]


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


def main() -> None:
    with INPUT_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    print(f"Loaded {len(rows)} rows from {INPUT_CSV.name}.")

    # Every ticker referenced by any basket + the two benchmarks/calendar anchors.
    needed: set[str] = {SMH_SYMBOL, CALENDAR_SYMBOL}
    for r in rows:
        needed.update(parse_basket(r["resolved_basket"]))

    api_key = load_api_key()
    prices = load_prices(needed, api_key)

    calendar = sorted(prices.get(CALENDAR_SYMBOL, {}).keys())
    if not calendar:
        raise SystemExit(f"No {CALENDAR_SYMBOL} calendar data — cannot anchor returns.")
    print(f"Calendar ({CALENDAR_SYMBOL}): {len(calendar)} days "
          f"[{calendar[0]} .. {calendar[-1]}]")

    for r in rows:
        basket = parse_basket(r["resolved_basket"])
        direction = r["basket_direction"]
        recomputed = compute_returns(r["date"], basket, direction, prices, calendar)
        for col in RETURN_COLS:
            r[col] = recomputed[col]

    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
