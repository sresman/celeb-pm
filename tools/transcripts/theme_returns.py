"""Compute theme-basket returns at each signal-event date.

For every signal event in ``analysis/step4_signal_events_v2.csv`` this resolves the
theme's ticker basket (date-aware, from ``analysis/theme_baskets.json``), pulls adjusted
daily closes from EODHD, and computes the equal-weight basket return plus the SMH
benchmark return and the excess over SMH at four forward horizons (1m=21, 1q=63,
1y=252, 2y=504 trading days). The completed CSV is written to
``analysis/step4_signal_events_with_returns.csv``.

This is a one-shot data-enrichment script. It is standalone of ``src/celebpm`` and
imports nothing from it.

Usage:
    python -m tools.transcripts.theme_returns [--force-refetch]

Options:
    --force-refetch   Re-pull every ticker from EODHD even if a local cache exists.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

import dotenv
import requests

from . import targets

# --- Paths ------------------------------------------------------------------
ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
EVENTS_CSV = ANALYSIS_DIR / "step4_signal_events_v2.csv"
BASKETS_JSON = ANALYSIS_DIR / "theme_baskets.json"
OUTPUT_CSV = ANALYSIS_DIR / "step4_signal_events_with_returns.csv"
PRICE_CACHE_DIR = ANALYSIS_DIR / "eod_prices"

# --- EODHD -------------------------------------------------------------------
EODHD_URL_TEMPLATE = "https://eodhd.com/api/eod/{symbol}.US"
EODHD_FROM_DATE = "2020-01-01"
EODHD_ADJ_CLOSE_KEY = "adjusted_close"
EODHD_DATE_KEY = "date"
SLEEP_BETWEEN_FETCH = 0.5  # seconds, polite pacing between live calls
HTTP_TIMEOUT = 30

# --- Benchmarks / calendar ---------------------------------------------------
SMH_SYMBOL = "SMH"
CALENDAR_SYMBOL = "SPY"  # continuous US market calendar; master trading-day index

# --- Return horizons (forward trading days) ----------------------------------
INTERVALS: dict[str, int] = {"1m": 21, "1q": 63, "1y": 252, "2y": 504}

# --- Full ticker universe (38, incl. benchmarks) -----------------------------
UNIVERSE: list[str] = [
    "AAPL", "ALAB", "AMAT", "AMD", "AMZN", "ANET", "ASTS", "AVGO", "CEG", "CIEN",
    "COHR", "CRM", "CRWV", "EXAI", "GOOGL", "INTC", "KLAC", "LITE", "LRCX", "LUNR",
    "MSFT", "MU", "NOW", "NVDA", "QCOM", "RDW", "RKLB", "RXRX", "SDGR", "SMH",
    "SNOW", "SPCE", "SPCX", "SPY", "TEAM", "TSLA", "TSM", "VST",
]

# --- Status sentinels (written into return columns when no number applies) ---
NO_BASKET = "NO_BASKET"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
PRE_IPO = "PRE_IPO"

RETAIL_PROXY = "RETAIL_PROXY"


def load_api_key() -> str:
    """Load EODHD_API_KEY from .env with override (shell var may be a placeholder)."""
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    key = os.environ.get("EODHD_API_KEY", "")
    if not key:
        raise SystemExit("EODHD_API_KEY missing — it must be set in .env.")
    return key


# ---------------------------------------------------------------------------
# Step 1: price fetch + cache
# ---------------------------------------------------------------------------
def fetch_prices(api_key: str, force_refetch: bool) -> dict[str, dict[str, float]]:
    """Return {ticker: {date_str: adjusted_close}} for the whole universe.

    Raw EODHD JSON is cached at ``analysis/eod_prices/{TICKER}.json``; cached
    tickers are not re-fetched unless ``force_refetch`` is set.
    """
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    prices: dict[str, dict[str, float]] = {}

    for ticker in UNIVERSE:
        cache_path = PRICE_CACHE_DIR / f"{ticker}.json"
        if cache_path.exists() and not force_refetch:
            rows = json.loads(cache_path.read_text())
        else:
            url = EODHD_URL_TEMPLATE.format(symbol=ticker)
            params = {
                "from": EODHD_FROM_DATE,
                "to": today,
                "period": "d",
                "fmt": "json",
                "api_token": api_key,
            }
            resp = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
            resp.raise_for_status()
            rows = resp.json()
            cache_path.write_text(json.dumps(rows))
            time.sleep(SLEEP_BETWEEN_FETCH)

        series = _series_from_rows(rows)
        prices[ticker] = series
        if not series:
            print(f"  [no data] {ticker}: EODHD returned no usable rows")
        else:
            first = min(series)
            last = max(series)
            print(f"  {ticker}: {len(series)} bars [{first} .. {last}]")

    return prices


def _series_from_rows(rows: Any) -> dict[str, float]:
    """Extract {date_str: adjusted_close} from raw EODHD rows, dropping bad bars."""
    series: dict[str, float] = {}
    if not isinstance(rows, list):
        return series
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        date_str = raw.get(EODHD_DATE_KEY)
        close = raw.get(EODHD_ADJ_CLOSE_KEY)
        if not isinstance(date_str, str):
            continue
        if not isinstance(close, (int, float)) or close <= 0:
            continue
        series[date_str] = float(close)
    return series


# ---------------------------------------------------------------------------
# Step 2: basket resolution
# ---------------------------------------------------------------------------
def resolve_basket(
    theme: str, event_date: str, baskets: dict[str, Any]
) -> tuple[list[str], str, str, bool]:
    """Resolve a theme to (tickers, source, direction, asterisk) at an event date.

    Date-segmented themes use chronological-breakpoint semantics: walk the segments
    in order and pick the FIRST whose ``before`` bound exceeds the event date; if no
    ``before`` matches, use the ``after`` segment (operator-confirmed interpretation).
    """
    if theme not in baskets:
        raise SystemExit(f"Theme not found in theme_baskets.json: {theme!r}")
    entry = baskets[theme]
    direction = entry.get("direction", "LONG")
    asterisk = bool(entry.get("asterisk", False))

    if "tickers" in entry:
        tickers = list(entry["tickers"])
        source = entry.get("source", "")
        return tickers, source, direction, asterisk

    segments = entry["date_segments"]
    chosen = None
    after_segment = None
    for seg in segments:
        if "before" in seg:
            if event_date < seg["before"]:
                chosen = seg
                break
        elif "after" in seg:
            after_segment = seg
            if event_date >= seg["after"]:
                chosen = seg
                break
    if chosen is None:
        chosen = after_segment
    if chosen is None:
        raise SystemExit(
            f"No applicable date_segment for theme {theme!r} at {event_date}"
        )
    tickers = list(chosen.get("tickers", []))
    source = chosen.get("source", "")
    return tickers, source, direction, asterisk


# ---------------------------------------------------------------------------
# Step 3: return computation
# ---------------------------------------------------------------------------
def _ticker_return(
    series: dict[str, float], start_date: str, end_date: str
) -> float | None:
    """Percent return for one ticker between two calendar dates, or None if either
    endpoint is missing (pre-IPO / delisted / untraded that day)."""
    start = series.get(start_date)
    end = series.get(end_date)
    if start is None or end is None:
        return None
    return (end / start - 1.0) * 100.0


def compute_returns(
    event_date: str,
    basket: list[str],
    direction: str,
    prices: dict[str, dict[str, float]],
    calendar: list[str],
) -> dict[str, Any]:
    """Compute basket / SMH / excess returns at every interval for one event.

    Returns a dict mapping each output column (ret_*, smh_*, excess_*) to a float
    (rounded, 2dp) or a status sentinel string.
    """
    smh_series = prices.get(SMH_SYMBOL, {})

    # First trading day >= event_date on the master calendar.
    start_idx = bisect.bisect_left(calendar, event_date)
    out: dict[str, Any] = {}

    if start_idx >= len(calendar):
        # Event date is past the end of available history entirely.
        for label in INTERVALS:
            out[f"ret_{label}"] = INSUFFICIENT_DATA
            out[f"smh_{label}"] = INSUFFICIENT_DATA
            out[f"excess_{label}"] = INSUFFICIENT_DATA
        return out

    start_date = calendar[start_idx]

    for label, n_days in INTERVALS.items():
        end_idx = start_idx + n_days
        if end_idx >= len(calendar):
            out[f"ret_{label}"] = INSUFFICIENT_DATA
            out[f"smh_{label}"] = INSUFFICIENT_DATA
            out[f"excess_{label}"] = INSUFFICIENT_DATA
            continue
        end_date = calendar[end_idx]

        # SMH benchmark — always attempted.
        smh_ret = _ticker_return(smh_series, start_date, end_date)
        out[f"smh_{label}"] = round(smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA

        if not basket:
            out[f"ret_{label}"] = NO_BASKET
            out[f"excess_{label}"] = NO_BASKET
            continue

        per_ticker = [
            r
            for t in basket
            if (r := _ticker_return(prices.get(t, {}), start_date, end_date)) is not None
        ]
        if not per_ticker:
            out[f"ret_{label}"] = PRE_IPO
            out[f"excess_{label}"] = PRE_IPO
            continue

        raw = sum(per_ticker) / len(per_ticker)
        # SHORT: a decline is a positive signal → negate. MIXED/LONG: raw.
        signed = -raw if direction == "SHORT" else raw
        out[f"ret_{label}"] = round(signed, 2)

        if smh_ret is None:
            out[f"excess_{label}"] = INSUFFICIENT_DATA
        else:
            out[f"excess_{label}"] = round(signed - smh_ret, 2)

    return out


# ---------------------------------------------------------------------------
# Step 4: orchestration + output
# ---------------------------------------------------------------------------
NEW_COLUMNS = ["resolved_basket", "basket_source", "basket_asterisk"]
RETURN_COLUMNS = [
    f"{prefix}_{label}"
    for prefix in ("ret", "smh", "excess")
    for label in INTERVALS
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-refetch",
        action="store_true",
        help="Re-pull every ticker from EODHD even if cached.",
    )
    args = parser.parse_args()

    api_key = load_api_key()

    print(f"Fetching prices for {len(UNIVERSE)} tickers (cache: {PRICE_CACHE_DIR}) ...")
    prices = fetch_prices(api_key, args.force_refetch)

    calendar = sorted(prices.get(CALENDAR_SYMBOL, {}).keys())
    if not calendar:
        raise SystemExit(f"No {CALENDAR_SYMBOL} calendar data — cannot anchor returns.")
    print(f"Calendar ({CALENDAR_SYMBOL}): {len(calendar)} trading days "
          f"[{calendar[0]} .. {calendar[-1]}]")

    baskets = json.loads(BASKETS_JSON.read_text())

    with EVENTS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        original_fields = list(reader.fieldnames or [])
        events = list(reader)
    print(f"Loaded {len(events)} signal events.")

    # Output fieldnames: original columns + new basket cols, with return columns
    # overwritten in place (they already exist in the input but are blank).
    out_fields = list(original_fields)
    for col in NEW_COLUMNS:
        if col not in out_fields:
            out_fields.append(col)
    for col in RETURN_COLUMNS:
        if col not in out_fields:
            out_fields.append(col)

    for row in events:
        theme = row["theme"]
        event_date = row["date"]
        tickers, source, direction, asterisk = resolve_basket(theme, event_date, baskets)

        row["resolved_basket"] = ", ".join(tickers)
        row["basket_source"] = source if source else NO_BASKET
        row["basket_asterisk"] = str(asterisk or source == RETAIL_PROXY)

        returns = compute_returns(event_date, tickers, direction, prices, calendar)
        for col, val in returns.items():
            row[col] = val

    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fields)
        writer.writeheader()
        writer.writerows(events)
    print(f"\nWrote {len(events)} rows → {OUTPUT_CSV}")

    _print_summary(events)


def _print_summary(events: list[dict[str, Any]]) -> None:
    """Print an event_type × avg-return table per interval (numeric rows only)."""
    print("\n=== Average basket return by event_type (numeric events only) ===")
    cols = [f"ret_{label}" for label in INTERVALS]
    header = f"{'event_type':<24} {'n':>3}  " + "  ".join(f"{label:>8}" for label in INTERVALS)
    print(header)
    print("-" * len(header))

    by_type: dict[str, list[dict[str, Any]]] = {}
    for row in events:
        by_type.setdefault(row["event_type"], []).append(row)

    for event_type in sorted(by_type):
        rows = by_type[event_type]
        cells = []
        n_used = 0
        for col in cols:
            vals = [r[col] for r in rows if isinstance(r[col], (int, float))]
            n_used = max(n_used, len(vals))
            cells.append(f"{sum(vals) / len(vals):>8.2f}" if vals else f"{'--':>8}")
        print(f"{event_type:<24} {len(rows):>3}  " + "  ".join(cells))


if __name__ == "__main__":
    main()
