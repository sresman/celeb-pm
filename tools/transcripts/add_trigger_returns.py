#!/usr/bin/env python3
"""Filing-to-filing returns reference table + forward returns on trigger events.

Three deliverables, all derived from committed pipeline output + EODHD adjusted-close
prices (fetch/cache pattern mirrors theme_returns_v2.py; AI classification reuses
resolve_ai from generate_13f_triggers.py):

  1. analysis/filing_to_filing_returns.csv        ticker x filing-to-filing period
  2. forward 1q-4q returns on every trigger event (locked, buy-and-hold baskets)
  3. Trigger 2b: sub-theme active-allocation threshold crossings (2% and 4%)
     -> appended to analysis/13f_signal_triggers_with_returns.csv

Usage:
    python tools/transcripts/add_trigger_returns.py
"""

from __future__ import annotations

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

try:  # works both as `python tools/transcripts/add_trigger_returns.py` and `-m`
    from . import generate_13f_triggers as trig
except ImportError:
    import generate_13f_triggers as trig  # type: ignore[import-not-found, no-redef]

REPO_ROOT = trig.REPO_ROOT
ANALYSIS_DIR = trig.ANALYSIS_DIR
PRICE_CACHE_DIR = ANALYSIS_DIR / "eod_prices"
RECLASS_PATH = ANALYSIS_DIR / "ai_basket_reclassification.json"
TRIGGERS_IN = ANALYSIS_DIR / "13f_signal_triggers.csv"
REF_TABLE_OUT = ANALYSIS_DIR / "filing_to_filing_returns.csv"
TRIGGERS_OUT = ANALYSIS_DIR / "13f_signal_triggers_with_returns.csv"

EODHD_URL = "https://eodhd.com/api/eod/{symbol}.US"
EODHD_FROM = "2020-01-01"
SLEEP_BETWEEN_FETCH = 0.5
HTTP_TIMEOUT = 30
BENCHMARKS = ["SMH", "SPY"]
SMH_SYMBOL = "SMH"
THRESHOLDS = [2.0, 4.0]
HORIZONS = [1, 2, 3, 4]

PRE_IPO = "PRE_IPO"
NO_DATA = "NO_DATA"
INSUFFICIENT = "INSUFFICIENT_DATA"

NEW_2B_COLUMNS = [
    "subtheme_weight_prior", "subtheme_weight_current", "subtheme_weight_change",
    "active_tickers", "all_tickers_in_subtheme",
]
FWD_COLUMNS = (
    [f"fwd_{n}q_return" for n in HORIZONS]
    + [f"smh_fwd_{n}q" for n in HORIZONS]
    + [f"excess_fwd_{n}q" for n in HORIZONS]
)
OUT_COLUMNS = list(trig.COLUMNS) + NEW_2B_COLUMNS + FWD_COLUMNS

Return = float | str  # a per-period return: a number, or a sentinel string


# --------------------------------------------------------------------------
# Price layer (mirrors theme_returns_v2.py)
# --------------------------------------------------------------------------


def load_eodhd_key() -> str:
    dotenv.load_dotenv(REPO_ROOT / ".env", override=True)
    key = os.environ.get("EODHD_API_KEY", "")
    if not key:
        raise SystemExit("EODHD_API_KEY missing — it must be set in .env.")
    return key


def _series_from_rows(rows: Any) -> dict[str, float]:
    series: dict[str, float] = {}
    if not isinstance(rows, list):
        return series
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        date_str = raw.get("date")
        close = raw.get("adjusted_close")
        if isinstance(date_str, str) and isinstance(close, (int, float)) and close > 0:
            series[date_str] = float(close)
    return series


def load_prices(
    tickers: list[str], api_key: str
) -> tuple[dict[str, dict[str, float]], list[str]]:
    PRICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    prices: dict[str, dict[str, float]] = {}
    warnings: list[str] = []
    for ticker in tickers:
        symbol = ticker.lstrip("0123456789") or ticker
        cache_path = PRICE_CACHE_DIR / f"{ticker}.json"
        if cache_path.exists():
            rows = json.loads(cache_path.read_text())
        else:
            try:
                resp = requests.get(
                    EODHD_URL.format(symbol=symbol),
                    params={"from": EODHD_FROM, "to": today, "period": "d",
                            "fmt": "json", "api_token": api_key},
                    timeout=HTTP_TIMEOUT,
                )
                resp.raise_for_status()
                rows = resp.json()
                cache_path.write_text(json.dumps(rows))
                print(f"  [fetched] {ticker}")
                time.sleep(SLEEP_BETWEEN_FETCH)
            except Exception as exc:  # keep going; this ticker -> NO_DATA
                warnings.append(f"fetch failed {ticker}: {exc}")
                rows = []
        series = _series_from_rows(rows)
        prices[ticker] = series
        if not series:
            warnings.append(f"no usable price data: {ticker}")
    return prices, warnings


def _price_at(sorted_dates: list[str], series: dict[str, float], target: str) -> float | None:
    """Exact price, else the first trading day on/after target."""
    p = series.get(target)
    if p is not None:
        return p
    i = bisect.bisect_left(sorted_dates, target)
    return series[sorted_dates[i]] if i < len(sorted_dates) else None


# --------------------------------------------------------------------------
# Part 1: reference table
# --------------------------------------------------------------------------


def _period_return(
    series: dict[str, float], sorted_dates: list[str], start: str, end: str
) -> tuple[Return, float | None, float | None]:
    if not series:
        return NO_DATA, None, None
    first, last = sorted_dates[0], sorted_dates[-1]
    if start < first:
        return PRE_IPO, None, None
    if start > last or end > last:
        return NO_DATA, None, None
    ps = _price_at(sorted_dates, series, start)
    pe = _price_at(sorted_dates, series, end)
    if ps is None or pe is None:
        return NO_DATA, None, None
    return round((pe / ps - 1.0) * 100.0, 2), round(ps, 2), round(pe, 2)


def build_reference_table(
    universe: list[str], filings: list[str], prices: dict[str, dict[str, float]]
) -> tuple[list[dict[str, str]], dict[tuple[str, int], Return]]:
    rows: list[dict[str, str]] = []
    ref: dict[tuple[str, int], Return] = {}
    for ticker in universe:
        series = prices.get(ticker, {})
        sorted_dates = sorted(series)
        for i in range(len(filings) - 1):
            start, end = filings[i], filings[i + 1]
            ret, ps, pe = _period_return(series, sorted_dates, start, end)
            ref[(ticker, i)] = ret
            rows.append({
                "ticker": ticker,
                "period_start_filing": start,
                "period_end_filing": end,
                "price_start": trig._fmt(ps) if ps is not None else "",
                "price_end": trig._fmt(pe) if pe is not None else "",
                "return_pct": trig._fmt(ret) if isinstance(ret, float) else ret,
            })
    return rows, ref


# --------------------------------------------------------------------------
# Part 2: forward returns (locked, buy-and-hold baskets)
# --------------------------------------------------------------------------


def _compound(returns: list[Return]) -> Return:
    prod = 1.0
    for r in returns:
        if not isinstance(r, float):
            return r  # propagate the sentinel (PRE_IPO / NO_DATA)
        prod *= 1.0 + r / 100.0
    return round((prod - 1.0) * 100.0, 2)


def ticker_fwd(ref: dict[tuple[str, int], Return], ticker: str, k: int, n: int, nperiods: int) -> Return:
    if k + n > nperiods:
        return INSUFFICIENT
    return _compound([ref.get((ticker, j), NO_DATA) for j in range(k, k + n)])


def basket_fwd(ref: dict[tuple[str, int], Return], basket: list[str], k: int, n: int, nperiods: int) -> Return:
    if k + n > nperiods:
        return INSUFFICIENT
    vals = [v for t in basket if isinstance(v := ticker_fwd(ref, t, k, n, nperiods), float)]
    return round(sum(vals) / len(vals), 2) if vals else NO_DATA


def _excess(fwd: Return, smh: Return) -> Return:
    if isinstance(fwd, float) and isinstance(smh, float):
        return round(fwd - smh, 2)
    return ""


def forward_columns(
    ref: dict[tuple[str, int], Return],
    trigger_type: str,
    filing_date: str,
    filing_index: dict[str, int],
    entering_tickers: list[str],
    ticker: str,
    nperiods: int,
) -> dict[str, str]:
    k = filing_index[filing_date]
    out: dict[str, str] = {}
    for n in HORIZONS:
        smh = ticker_fwd(ref, SMH_SYMBOL, k, n, nperiods)
        if trigger_type == "AI_BASKET_RAMP":
            fwd: Return = smh  # measure = SMH
        elif trigger_type == "NEW_AI_POSITION_2PCT":
            fwd = ticker_fwd(ref, ticker, k, n, nperiods)
        else:  # NEW_AI_SUBTHEME / AI_SUBTHEME_ACTIVE_CROSS_* -> locked basket
            fwd = basket_fwd(ref, entering_tickers, k, n, nperiods)
        exc = _excess(fwd, smh)
        out[f"fwd_{n}q_return"] = trig._fmt(fwd) if isinstance(fwd, float) else fwd
        out[f"smh_fwd_{n}q"] = trig._fmt(smh) if isinstance(smh, float) else smh
        out[f"excess_fwd_{n}q"] = trig._fmt(exc) if isinstance(exc, float) else exc
    return out


# --------------------------------------------------------------------------
# Part 3: Trigger 2b
# --------------------------------------------------------------------------


def _load_ai_common(reclass: dict[str, Any], views: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in trig._read_csv(views / "position_lifecycles.csv"):
        if r["security_type"] != "COMMON":
            continue
        is_ai, subtheme = trig.resolve_ai(reclass, r["ticker"], r["filing_date"], r["theme"])
        if not is_ai or subtheme is None:
            continue
        rows.append({
            "ticker": r["ticker"], "filing_date": r["filing_date"],
            "period": r["period"], "change_type": r["change_type"],
            "subtheme": subtheme, "weight": trig._f(r["weight_pct"]) or 0.0,
        })
    return rows


def trigger_2b(
    ai_common: list[dict[str, Any]], filings: list[str], fd_to_period: dict[str, str]
) -> list[dict[str, str]]:
    # (subtheme, filing) -> weight / active tickers / all tickers (COMMON non-EXIT AI)
    weight: dict[tuple[str, str], float] = {}
    active: dict[tuple[str, str], list[str]] = {}
    everyone: dict[tuple[str, str], list[str]] = {}
    subthemes: set[str] = set()
    for r in ai_common:
        if r["change_type"] == "EXIT":
            continue
        key = (r["subtheme"], r["filing_date"])
        subthemes.add(r["subtheme"])
        weight[key] = weight.get(key, 0.0) + r["weight"]
        everyone.setdefault(key, []).append(r["ticker"])
        if r["change_type"] in ("NEW", "ACTIVE_ADD"):
            active.setdefault(key, []).append(r["ticker"])

    events: list[dict[str, str]] = []
    for subtheme in sorted(subthemes):
        prior = 0.0
        for fd in filings:
            cur = weight.get((subtheme, fd), 0.0)
            actives = active.get((subtheme, fd), [])
            for thr in THRESHOLDS:
                if prior < thr <= cur and actives:
                    events.append({
                        "trigger_type": f"AI_SUBTHEME_ACTIVE_CROSS_{int(thr)}PCT",
                        "filing_date": fd,
                        "quarter": fd_to_period.get(fd, ""),
                        "subtheme": subtheme,
                        "subtheme_weight_prior": trig._fmt(prior),
                        "subtheme_weight_current": trig._fmt(cur),
                        "subtheme_weight_change": trig._fmt(cur - prior),
                        "active_tickers": ", ".join(actives),
                        "all_tickers_in_subtheme": ", ".join(
                            everyone.get((subtheme, fd), [])),
                    })
            prior = cur
    return events


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    views = trig.find_views_dir()
    reclass = json.loads(RECLASS_PATH.read_text(encoding="utf-8"))

    ai_common = _load_ai_common(reclass, views)
    fd_to_period: dict[str, str] = {}
    for r in trig._read_csv(views / "position_lifecycles.csv"):
        fd_to_period.setdefault(r["filing_date"], r["period"])
    filings = sorted({r["filing_date"] for r in ai_common})
    filing_index = {fd: i for i, fd in enumerate(filings)}
    nperiods = len(filings) - 1

    universe = sorted({r["ticker"] for r in ai_common}) + BENCHMARKS

    # Part 1: prices + reference table
    prices, warnings = load_prices(universe, load_eodhd_key())
    ref_rows, ref = build_reference_table(universe, filings, prices)
    with REF_TABLE_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "ticker", "period_start_filing", "period_end_filing",
            "price_start", "price_end", "return_pct"])
        w.writeheader()
        w.writerows(ref_rows)

    # Part 3: Trigger 2b events
    twob = trigger_2b(ai_common, filings, fd_to_period)

    # Existing 55 events + 2b events, all annotated with forward returns
    existing = trig._read_csv(TRIGGERS_IN)
    all_events: list[dict[str, str]] = existing + twob
    for e in all_events:
        entering = (
            e.get("all_tickers_in_subtheme") or e.get("entering_tickers") or ""
        )
        basket = [t.strip() for t in entering.split(",") if t.strip()]
        e.update(forward_columns(
            ref, e["trigger_type"], e["filing_date"], filing_index,
            basket, e.get("ticker", ""), nperiods))
    all_events.sort(key=lambda e: (e["filing_date"], e["trigger_type"]))

    with TRIGGERS_OUT.open("w", newline="", encoding="utf-8") as fh:
        w2 = csv.DictWriter(fh, fieldnames=OUT_COLUMNS, restval="", extrasaction="ignore")
        w2.writeheader()
        w2.writerows(all_events)

    # Summary
    n_periods_full = sum(
        1 for i in range(nperiods)
        if isinstance(ref.get((SMH_SYMBOL, i)), float)
    )
    pre_ipo = sum(1 for v in ref.values() if v == PRE_IPO)
    no_data = sum(1 for v in ref.values() if v == NO_DATA)
    from collections import Counter
    by_type = Counter(e["trigger_type"] for e in all_events)
    print(f"\nReference table: {len(universe)} tickers x {nperiods} periods "
          f"= {len(ref_rows)} rows -> {REF_TABLE_OUT.relative_to(REPO_ROOT)}")
    print(f"  SMH periods with data: {n_periods_full}/{nperiods}; "
          f"PRE_IPO cells: {pre_ipo}; NO_DATA cells: {no_data}")
    print(f"\nTrigger 2b: {len(twob)} events "
          f"({sum(1 for e in twob if e['trigger_type'].endswith('2PCT'))} @2%, "
          f"{sum(1 for e in twob if e['trigger_type'].endswith('4PCT'))} @4%)")
    print(f"\n{len(all_events)} events with forward returns -> "
          f"{TRIGGERS_OUT.relative_to(REPO_ROOT)}")
    for t, n in sorted(by_type.items()):
        print(f"  {t}: {n}")
    if warnings:
        print(f"\n{len(warnings)} price warnings:")
        for wmsg in warnings:
            print(f"  - {wmsg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
