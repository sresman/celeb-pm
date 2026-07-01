"""Regenerate Gavin Baker signal events from scratch and compute theme-basket returns.

Clean v3 regeneration. Reads two source-of-truth files:
  - ``analysis/thesis_timeline.json``    (319 theses)
  - ``analysis/theme_baskets_v2.json``   (52 themes, regex ``keys``/``exclude`` + baskets)

Pipeline:
  1. Cluster each thesis into themes via the regex ``keys``/``exclude`` patterns (multi-assign).
  2. Generate signal events per theme via a state machine (first mention, first HC, third within
     1yr, first-with-tickers, first SMID ticker, HC at high-profile venue, thesis reversal).
  3. Resolve each event's basket (date-aware) from ``theme_baskets_v2.json``.
  4. Pull/cache adjusted daily closes from EODHD for the 46-ticker universe.
  5. Compute equal-weight basket return + SMH benchmark + excess at 1m/1q/1y/2y.
  6. Write ``analysis/step4_signal_events_v3.csv`` + print summary stats.

Standalone of ``src/celebpm`` (imports nothing from it).

Usage:
    python -m tools.transcripts.theme_returns_v2 [--force-refetch]
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import dotenv
import requests

from . import targets

# --- Paths ------------------------------------------------------------------
ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
TIMELINE_JSON = ANALYSIS_DIR / "thesis_timeline.json"
BASKETS_JSON = ANALYSIS_DIR / "theme_baskets_v2.json"
OUTPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v3.csv"
PRICE_CACHE_DIR = ANALYSIS_DIR / "eod_prices"

# --- EODHD -------------------------------------------------------------------
EODHD_URL_TEMPLATE = "https://eodhd.com/api/eod/{symbol}.US"
EODHD_FROM_DATE = "2020-01-01"
EODHD_ADJ_CLOSE_KEY = "adjusted_close"
EODHD_DATE_KEY = "date"
SLEEP_BETWEEN_FETCH = 0.5
HTTP_TIMEOUT = 30

# --- Benchmarks / calendar ---------------------------------------------------
SMH_SYMBOL = "SMH"
CALENDAR_SYMBOL = "SPY"

# --- Return horizons (forward trading days) ----------------------------------
INTERVALS: dict[str, int] = {"1m": 21, "1q": 63, "1y": 252, "2y": 504}

# --- Full ticker universe (46, incl. benchmarks) -----------------------------
UNIVERSE: list[str] = [
    "AAPL", "ALAB", "AMD", "AMZN", "ANET", "ASML", "ASTS", "AVGO", "CCJ", "CEG",
    "CIEN", "COHR", "CRM", "CRWV", "DISH", "EA", "EXAI", "GOOGL", "INTC", "LITE",
    "LUNR", "MA", "META", "MSFT", "MSTR", "MU", "NOW", "NVDA", "ORCL", "QCOM",
    "RBLX", "RDW", "RKLB", "RXRX", "SDGR", "SMH", "SNOW", "SPCE", "SPCX", "SPY",
    "TEAM", "TGT", "TSLA", "TTWO", "V", "VST",
]

# --- Event-generation config -------------------------------------------------
HIGH_CONVICTION = "high_conviction"
MEGA_CAPS: frozenset[str] = frozenset({
    "NVDA", "AMD", "INTC", "GOOGL", "AMZN", "MSFT", "META", "AAPL", "TSM",
    "ASML", "AVGO", "TSLA", "NFLX", "CRM", "ORCL",
})
HIGH_PROFILE_VENUES: list[str] = [
    "sohn", "iconn", "iconnections", "boston investment conference", "hedgefundalpha",
]
REVERSAL_KEYWORDS: list[str] = [
    "losing", "lost", "risk", "mistake", "bubble", "worst", "flinched", "break down",
]

# --- Status sentinels --------------------------------------------------------
NO_BASKET = "NO_BASKET"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NO_DATA = "NO_DATA"


def load_api_key() -> str:
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    key = os.environ.get("EODHD_API_KEY", "")
    if not key:
        raise SystemExit("EODHD_API_KEY missing — it must be set in .env.")
    return key


# ---------------------------------------------------------------------------
# Step 4: price fetch + cache (only new tickers hit the API)
# ---------------------------------------------------------------------------
def fetch_prices(api_key: str, force_refetch: bool) -> dict[str, dict[str, float]]:
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    prices: dict[str, dict[str, float]] = {}

    for ticker in UNIVERSE:
        cache_path = PRICE_CACHE_DIR / f"{ticker}.json"
        if cache_path.exists() and not force_refetch:
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
        else:
            print(f"  {ticker}: {len(series)} bars [{min(series)} .. {max(series)}]")
    return prices


def _series_from_rows(rows: Any) -> dict[str, float]:
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
# Step 1: cluster theses into themes (regex keys/exclude)
# ---------------------------------------------------------------------------
def cluster_theses(
    theses: list[dict[str, Any]], baskets: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Return (theme -> [theses], unclustered_count). A thesis may map to many themes."""
    compiled: dict[str, tuple[list[re.Pattern[str]], list[re.Pattern[str]]]] = {}
    for theme, cfg in baskets.items():
        keys = [re.compile(p) for p in cfg.get("keys", [])]
        excl = [re.compile(p) for p in cfg.get("exclude", [])]
        compiled[theme] = (keys, excl)

    assignments: dict[str, list[dict[str, Any]]] = {theme: [] for theme in baskets}
    unclustered = 0
    for thesis in theses:
        summary_lc = str(thesis.get("summary", "")).lower()
        matched_any = False
        for theme, (keys, excl) in compiled.items():
            if not any(p.search(summary_lc) for p in keys):
                continue
            if any(p.search(summary_lc) for p in excl):
                continue
            assignments[theme].append(thesis)
            matched_any = True
        if not matched_any:
            unclustered += 1
    return assignments, unclustered


# ---------------------------------------------------------------------------
# Step 2: generate signal events per theme
# ---------------------------------------------------------------------------
def _is_hc(thesis: dict[str, Any]) -> bool:
    return thesis.get("confidence") == HIGH_CONVICTION


def _venue_match(source: str) -> bool:
    src = source.lower()
    return any(v in src for v in HIGH_PROFILE_VENUES)


def _has_smid(tickers: list[str]) -> bool:
    return any(t.upper() not in MEGA_CAPS for t in tickers)


def _days_between(d1: str, d2: str) -> int:
    a = dt.date.fromisoformat(d1)
    b = dt.date.fromisoformat(d2)
    return (b - a).days


def generate_events(
    theme: str, theses: list[dict[str, Any]], direction: str, key_patterns: list[str]
) -> list[dict[str, Any]]:
    """Generate (pre-dedup) signal-event records for one theme's assigned theses."""
    if not theses:
        return []
    theses = sorted(theses, key=lambda t: (t["date"], t["thesis_id"]))
    unique_dates = sorted({t["date"] for t in theses})
    total_mentions = len(unique_dates)
    date_index = {d: i + 1 for i, d in enumerate(unique_dates)}
    by_date: dict[str, list[dict[str, Any]]] = {}
    for t in theses:
        by_date.setdefault(t["date"], []).append(t)

    events: list[dict[str, Any]] = []

    def emit(event_type: str, thesis: dict[str, Any]) -> None:
        date = thesis["date"]
        events.append({
            "date": date,
            "theme": theme,
            "event_type": event_type,
            "confidence": thesis.get("confidence", ""),
            "mention_number": date_index[date],
            "total_theme_mentions": total_mentions,
            "source": thesis.get("source", ""),
            "summary": thesis.get("summary", ""),
            "tickers_named": ", ".join(thesis.get("tickers_named", []) or []),
        })

    first_date = unique_dates[0]
    first_date_theses = by_date[first_date]

    # FIRST_MENTION_AND_HC / FIRST_MENTION (first unique date)
    hc_on_first = next((t for t in first_date_theses if _is_hc(t)), None)
    if hc_on_first is not None:
        emit("FIRST_MENTION_AND_HC", hc_on_first)
    else:
        emit("FIRST_MENTION", first_date_theses[0])

    # FIRST_HC_NOT_FIRST_MENTION (earliest HC date that is not the first date)
    for d in unique_dates:
        hc = next((t for t in by_date[d] if _is_hc(t)), None)
        if hc is not None:
            if d != first_date:
                emit("FIRST_HC_NOT_FIRST_MENTION", hc)
            break

    # THIRD_MENTION_WITHIN_1YR
    if total_mentions >= 3 and _days_between(unique_dates[0], unique_dates[2]) <= 365:
        emit("THIRD_MENTION_WITHIN_1YR", by_date[unique_dates[2]][0])

    # FIRST_MENTION_WITH_TICKERS (earliest thesis with named tickers)
    with_tickers = next((t for t in theses if t.get("tickers_named")), None)
    if with_tickers is not None:
        emit("FIRST_MENTION_WITH_TICKERS", with_tickers)

    # FIRST_SMID_TICKER (earliest thesis with a non-mega-cap named ticker)
    with_smid = next(
        (t for t in theses if t.get("tickers_named") and _has_smid(t["tickers_named"])), None
    )
    if with_smid is not None:
        emit("FIRST_SMID_TICKER", with_smid)

    # HC_HIGH_PROFILE_VENUE (every HC thesis at a high-profile venue)
    for t in theses:
        if _is_hc(t) and _venue_match(str(t.get("source", ""))):
            emit("HC_HIGH_PROFILE_VENUE", t)

    # THESIS_REVERSAL (LONG themes only; light self-reference guard)
    if direction == "LONG":
        key_blob = " ".join(key_patterns).lower()
        for t in theses:
            summary_lc = str(t.get("summary", "")).lower()
            for kw in REVERSAL_KEYWORDS:
                if kw in summary_lc and kw not in key_blob:
                    emit("THESIS_REVERSAL", t)
                    break

    return events


# ---------------------------------------------------------------------------
# Step 3: basket resolution
# ---------------------------------------------------------------------------
def resolve_basket(
    theme: str, event_date: str, baskets: dict[str, Any]
) -> tuple[list[str], str, str, bool]:
    """(tickers, source, direction, asterisk). Date segments = chronological breakpoint:
    first `before` whose bound > event_date wins, else the `after` segment."""
    entry = baskets[theme]
    direction = entry.get("direction", "LONG")
    asterisk = bool(entry.get("asterisk", False))

    if "tickers" in entry:
        tickers = list(entry["tickers"])
        source = entry.get("source", "")
        return tickers, source, direction, asterisk

    chosen = None
    after_segment = None
    for seg in entry["date_segments"]:
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
        raise SystemExit(f"No applicable date_segment for {theme!r} at {event_date}")
    return list(chosen.get("tickers", [])), chosen.get("source", ""), direction, asterisk


# ---------------------------------------------------------------------------
# Step 5: return computation
# ---------------------------------------------------------------------------
def _ticker_return(series: dict[str, float], start: str, end: str) -> float | None:
    s = series.get(start)
    e = series.get(end)
    if s is None or e is None:
        return None
    return (e / s - 1.0) * 100.0


def compute_returns(
    event_date: str, basket: list[str], direction: str,
    prices: dict[str, dict[str, float]], calendar: list[str],
) -> dict[str, Any]:
    smh_series = prices.get(SMH_SYMBOL, {})
    start_idx = bisect.bisect_left(calendar, event_date)
    out: dict[str, Any] = {}

    if start_idx >= len(calendar):
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

        smh_ret = _ticker_return(smh_series, start_date, end_date)
        out[f"smh_{label}"] = round(smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA

        if not basket:
            out[f"ret_{label}"] = NO_BASKET
            out[f"excess_{label}"] = NO_BASKET
            continue

        per_ticker = [
            r for t in basket
            if (r := _ticker_return(prices.get(t, {}), start_date, end_date)) is not None
        ]
        if not per_ticker:
            out[f"ret_{label}"] = NO_DATA
            out[f"excess_{label}"] = NO_DATA
            continue

        raw = sum(per_ticker) / len(per_ticker)
        signed = -raw if direction == "SHORT" else raw
        out[f"ret_{label}"] = round(signed, 2)
        out[f"excess_{label}"] = (
            round(signed - smh_ret, 2) if smh_ret is not None else INSUFFICIENT_DATA
        )
    return out


# ---------------------------------------------------------------------------
# Orchestration + output
# ---------------------------------------------------------------------------
OUTPUT_FIELDS = [
    "date", "theme", "event_type", "confidence", "mention_number", "total_theme_mentions",
    "source", "summary", "tickers_named",
    "resolved_basket", "basket_source", "basket_direction", "basket_asterisk",
    *(f"ret_{l}" for l in INTERVALS),
    *(f"smh_{l}" for l in INTERVALS),
    *(f"excess_{l}" for l in INTERVALS),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-refetch", action="store_true",
                        help="Re-pull every ticker from EODHD even if cached.")
    args = parser.parse_args()

    api_key = load_api_key()
    baskets = json.loads(BASKETS_JSON.read_text())
    theses = json.loads(TIMELINE_JSON.read_text())
    print(f"Loaded {len(theses)} theses, {len(baskets)} themes.")

    # Step 1: cluster
    assignments, unclustered = cluster_theses(theses, baskets)
    clustered = len(theses) - unclustered

    # Step 2: generate events
    raw_events: list[dict[str, Any]] = []
    for theme, theme_theses in assignments.items():
        direction = baskets[theme].get("direction", "LONG")
        key_patterns = baskets[theme].get("keys", [])
        raw_events.extend(generate_events(theme, theme_theses, direction, key_patterns))

    # Dedup on (date, theme, event_type) — keep first occurrence.
    seen: set[tuple[str, str, str]] = set()
    events: list[dict[str, Any]] = []
    for ev in raw_events:
        triple = (ev["date"], ev["theme"], ev["event_type"])
        if triple in seen:
            continue
        seen.add(triple)
        events.append(ev)

    # Step 4: prices
    print(f"\nFetching prices for {len(UNIVERSE)} tickers (cache: {PRICE_CACHE_DIR}) ...")
    prices = fetch_prices(api_key, args.force_refetch)
    calendar = sorted(prices.get(CALENDAR_SYMBOL, {}).keys())
    if not calendar:
        raise SystemExit(f"No {CALENDAR_SYMBOL} calendar data — cannot anchor returns.")
    print(f"Calendar ({CALENDAR_SYMBOL}): {len(calendar)} days [{calendar[0]} .. {calendar[-1]}]")

    # Steps 3 + 5: resolve baskets, compute returns
    for ev in events:
        tickers, source, direction, asterisk = resolve_basket(ev["theme"], ev["date"], baskets)
        ev["resolved_basket"] = ", ".join(tickers)
        ev["basket_source"] = source if source else NO_BASKET
        ev["basket_direction"] = direction
        ev["basket_asterisk"] = str(asterisk)
        ev.update(compute_returns(ev["date"], tickers, direction, prices, calendar))

    # Step 6: sort + write
    events.sort(key=lambda e: (e["date"], e["theme"]))
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    print(f"\nWrote {len(events)} signal events → {OUTPUT_CSV}")

    _print_summary(events, clustered, unclustered)


def _avg(vals: list[float]) -> str:
    return f"{sum(vals) / len(vals):>8.2f}" if vals else f"{'--':>8}"


def _print_summary(events: list[dict[str, Any]], clustered: int, unclustered: int) -> None:
    labels = list(INTERVALS)
    ret_cols = [f"ret_{l}" for l in labels]

    print(f"\n=== Totals ===\nSignal events: {len(events)}")
    print(f"Theses clustered: {clustered} | unclustered: {unclustered}")

    print("\n=== Events by type ===")
    by_type: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_type.setdefault(ev["event_type"], []).append(ev)
    for et in sorted(by_type, key=lambda k: -len(by_type[k])):
        print(f"  {et:<28} {len(by_type[et])}")

    def table(title: str, groups: dict[str, list[dict[str, Any]]], win: bool = False) -> None:
        print(f"\n=== {title} ===")
        header = f"{'group':<28} {'n':>3}  " + "  ".join(f"{l:>8}" for l in labels)
        print(header)
        print("-" * len(header))
        for g in sorted(groups):
            rows = groups[g]
            cells = []
            for col in ret_cols:
                nums = [r[col] for r in rows if isinstance(r[col], (int, float))]
                if win:
                    cells.append(
                        f"{100 * sum(1 for v in nums if v > 0) / len(nums):>7.1f}%"
                        if nums else f"{'--':>8}"
                    )
                else:
                    cells.append(_avg(nums))
            print(f"{g:<28} {len(rows):>3}  " + "  ".join(cells))

    table("Avg basket return by event_type", by_type)

    by_source: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_source.setdefault(ev["basket_source"], []).append(ev)
    table("Avg basket return by basket_source", by_source)

    table("Win rate (% positive) by event_type", by_type, win=True)


if __name__ == "__main__":
    main()
