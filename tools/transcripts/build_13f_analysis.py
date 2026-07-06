#!/usr/bin/env python3
"""Clean-separation build of the 13F signal infrastructure — three layers:

  1. analysis/filing_to_filing_returns_universal.csv  every COMMON ticker Baker has
       ever held (+ SMH, SPY) x 24 filing-to-filing periods. Pure returns, no signals.
  2. analysis/13f_signal_triggers_clean.csv           all trigger events, NO returns.
       Trigger 1 (ramp) uses a NARROW "picks-and-shovels" AI basket (excludes the
       AI/Hyperscaler and AI/EV buckets); Triggers 2/2b/3 use the full classification.
  3. analysis/ai_basket_definition.json               documents the two AI scopes.

Reuses primitives from generate_13f_triggers.py (resolve_ai, _f, _fmt, _read_csv,
find_views_dir) and the EODHD fetch/cache pattern from add_trigger_returns.py.

Usage:
    python tools/transcripts/build_13f_analysis.py [--skip-universal]
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

import dotenv
import requests

try:  # runs both as a direct script and under `-m`
    from . import generate_13f_triggers as trig
except ImportError:
    import generate_13f_triggers as trig  # type: ignore[import-not-found, no-redef]

REPO_ROOT = trig.REPO_ROOT
ANALYSIS_DIR = trig.ANALYSIS_DIR
PRICE_CACHE_DIR = ANALYSIS_DIR / "eod_prices"
RECLASS_PATH = ANALYSIS_DIR / "ai_basket_reclassification.json"
UNIVERSAL_OUT = ANALYSIS_DIR / "filing_to_filing_returns_universal.csv"
TRIGGERS_OUT = ANALYSIS_DIR / "13f_signal_triggers_clean.csv"
DEFINITION_OUT = ANALYSIS_DIR / "ai_basket_definition.json"

EODHD_URL = "https://eodhd.com/api/eod/{symbol}.US"
EODHD_FROM = "2020-01-01"
SLEEP_BETWEEN_FETCH = 0.5
HTTP_TIMEOUT = 30
BENCHMARKS = ["SMH", "SPY"]
PRE_IPO = "PRE_IPO"
NO_DATA = "NO_DATA"

RAMP_THRESHOLD_PT = 5.0
NEW_POSITION_MIN_WEIGHT_PCT = 2.0
SUBSEQUENT_ADD_WINDOW = 2
THRESHOLDS = [2.0, 4.0]

# NARROW ramp basket: everything AI except these two buckets.
RAMP_EXCLUDED_BUCKETS = {"AI/Hyperscaler", "AI/EV"}
RAMP_INCLUDED_BUCKETS = [
    "AI/Datacenter Chips", "AI/Datacenter Optical", "AI/Datacenter Memory",
    "AI/Datacenter Networking", "AI/Datacenter Storage", "AI/Datacenter Compute",
    "AI/Datacenter Power", "AI/Datacenter Infrastructure", "AI/Edge Computing",
    "AI/Data Infrastructure", "Semiconductor Manufacturing", "Semiconductor Supply Chain",
]

Return = float | str

OUT_COLUMNS = [
    "trigger_type", "filing_date", "quarter",
    # Trigger 1 (narrow ramp basket)
    "ai_weight_prior", "ai_weight_current", "ai_weight_change",
    "total_portfolio_weight", "ai_positions_count",
    "new_ai_entries_this_quarter", "ai_adds_this_quarter", "ai_exits_this_quarter",
    "top_5_ai_positions",
    # Trigger 2
    "subtheme", "entering_tickers", "entering_weights", "total_subtheme_weight",
    "subsequent_add", "subsequent_add_tickers",
    # Trigger 2b
    "subtheme_weight_prior", "subtheme_weight_current", "subtheme_weight_change",
    "active_tickers", "all_tickers_in_subtheme",
    # Trigger 3
    "ticker", "company", "theme", "initial_weight_pct", "became_active_add",
]


# --------------------------------------------------------------------------
# Price layer
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
    n_fetched = 0
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
                n_fetched += 1
                print(f"  [fetched {n_fetched}] {ticker}")
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
    p = series.get(target)
    if p is not None:
        return p
    i = bisect.bisect_left(sorted_dates, target)
    return series[sorted_dates[i]] if i < len(sorted_dates) else None


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


def build_universal_table(
    universe: list[str], filings: list[str], prices: dict[str, dict[str, float]]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ticker in universe:
        series = prices.get(ticker, {})
        sorted_dates = sorted(series)
        for i in range(len(filings) - 1):
            start, end = filings[i], filings[i + 1]
            ret, ps, pe = _period_return(series, sorted_dates, start, end)
            rows.append({
                "ticker": ticker,
                "period_start_filing": start,
                "period_end_filing": end,
                "price_start": trig._fmt(ps) if ps is not None else "",
                "price_end": trig._fmt(pe) if pe is not None else "",
                "return_pct": trig._fmt(ret) if isinstance(ret, float) else ret,
            })
    return rows


# --------------------------------------------------------------------------
# Common-row annotation (shared by Triggers 1/2/2b)
# --------------------------------------------------------------------------


def annotate_common(raw_life: list[dict[str, str]], reclass: dict[str, Any]) -> list[dict[str, Any]]:
    common: list[dict[str, Any]] = []
    for r in raw_life:
        if r["security_type"] != "COMMON":
            continue
        is_ai, subtheme = trig.resolve_ai(reclass, r["ticker"], r["filing_date"], r["theme"])
        common.append({
            "ticker": r["ticker"], "cusip": r["cusip"], "filing_date": r["filing_date"],
            "period": r["period"], "change_type": r["change_type"], "theme": r["theme"],
            "weight": trig._f(r["weight_pct"]), "is_ai": is_ai, "subtheme": subtheme,
        })
    return common


def _in_ramp(row: dict[str, Any]) -> bool:
    return bool(row["is_ai"]) and row["subtheme"] not in RAMP_EXCLUDED_BUCKETS


# --------------------------------------------------------------------------
# Trigger 1: AI_BASKET_RAMP (narrow basket)
# --------------------------------------------------------------------------


def trigger_ramp(
    common: list[dict[str, Any]], filings: list[str], fd_to_period: dict[str, str]
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    prior: float | None = None
    for fd in filings:
        fd_rows = [r for r in common if r["filing_date"] == fd]
        non_exit = [r for r in fd_rows if r["change_type"] != "EXIT"]
        ramp = [r for r in non_exit if _in_ramp(r)]
        ai_weight = sum((r["weight"] or 0.0) for r in ramp)
        total_weight = sum((r["weight"] or 0.0) for r in non_exit)
        if prior is not None and ai_weight - prior >= RAMP_THRESHOLD_PT:
            new_entries = [r["ticker"] for r in ramp if r["change_type"] == "NEW"]
            adds = [r["ticker"] for r in ramp if r["change_type"] == "ACTIVE_ADD"]
            exits = [r["ticker"] for r in fd_rows if r["change_type"] == "EXIT" and _in_ramp(r)]
            top5 = sorted(ramp, key=lambda r: r["weight"] or 0.0, reverse=True)[:5]
            events.append({
                "trigger_type": "AI_BASKET_RAMP",
                "filing_date": fd,
                "quarter": fd_to_period.get(fd, ""),
                "ai_weight_prior": trig._fmt(prior),
                "ai_weight_current": trig._fmt(ai_weight),
                "ai_weight_change": trig._fmt(ai_weight - prior),
                "total_portfolio_weight": trig._fmt(total_weight),
                "ai_positions_count": str(len(ramp)),
                "new_ai_entries_this_quarter": ", ".join(new_entries),
                "ai_adds_this_quarter": ", ".join(adds),
                "ai_exits_this_quarter": ", ".join(exits),
                "top_5_ai_positions": ", ".join(
                    f"{r['ticker']}:{trig._fmt(r['weight'])}" for r in top5),
            })
        prior = ai_weight
    return events


# --------------------------------------------------------------------------
# Trigger 2: NEW_AI_SUBTHEME (full classification)
# --------------------------------------------------------------------------


def trigger_subtheme(
    common: list[dict[str, Any]], filings: list[str], fd_to_period: dict[str, str]
) -> list[dict[str, str]]:
    ai_nonexit = [r for r in common if r["is_ai"] and r["change_type"] != "EXIT"]
    fd_index = {fd: i for i, fd in enumerate(filings)}
    present: dict[str, set[str]] = {}
    for r in ai_nonexit:
        present.setdefault(r["subtheme"], set()).add(r["filing_date"])

    events: list[dict[str, str]] = []
    for subtheme, fds in present.items():
        first_fd = min(fds, key=lambda f: fd_index[f])
        entering = [r for r in ai_nonexit
                    if r["subtheme"] == subtheme and r["filing_date"] == first_fd]
        entering.sort(key=lambda r: r["weight"] or 0.0, reverse=True)
        tickers = [r["ticker"] for r in entering]
        i = fd_index[first_fd]
        window = set(filings[i + 1: i + 1 + SUBSEQUENT_ADD_WINDOW])
        added = sorted({
            r["ticker"] for r in common
            if r["ticker"] in set(tickers)
            and r["change_type"] == "ACTIVE_ADD" and r["filing_date"] in window
        })
        events.append({
            "trigger_type": "NEW_AI_SUBTHEME",
            "filing_date": first_fd,
            "quarter": fd_to_period.get(first_fd, ""),
            "subtheme": subtheme,
            "entering_tickers": ", ".join(tickers),
            "entering_weights": ", ".join(trig._fmt(r["weight"]) for r in entering),
            "total_subtheme_weight": trig._fmt(sum(r["weight"] or 0.0 for r in entering)),
            "subsequent_add": "TRUE" if added else "FALSE",
            "subsequent_add_tickers": ", ".join(added),
        })
    return events


# --------------------------------------------------------------------------
# Trigger 2b: AI_SUBTHEME_ACTIVE_CROSS_{2,4}PCT (full classification)
# --------------------------------------------------------------------------


def trigger_2b(
    common: list[dict[str, Any]], filings: list[str], fd_to_period: dict[str, str]
) -> list[dict[str, str]]:
    weight: dict[tuple[str, str], float] = {}
    active: dict[tuple[str, str], list[str]] = {}
    everyone: dict[tuple[str, str], list[str]] = {}
    subthemes: set[str] = set()
    for r in common:
        if not r["is_ai"] or r["subtheme"] is None or r["change_type"] == "EXIT":
            continue
        key = (r["subtheme"], r["filing_date"])
        subthemes.add(r["subtheme"])
        weight[key] = weight.get(key, 0.0) + (r["weight"] or 0.0)
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
# Trigger 3: NEW_AI_POSITION_2PCT (full classification)
# --------------------------------------------------------------------------


def trigger_new_position(
    new_ideas: list[dict[str, str]], common: list[dict[str, Any]], reclass: dict[str, Any]
) -> list[dict[str, str]]:
    new_common = {
        (r["cusip"], r["filing_date"]): r for r in common if r["change_type"] == "NEW"
    }
    events: list[dict[str, str]] = []
    for row in new_ideas:
        if row.get("is_option", "") != "False":
            continue
        initial = trig._f(row.get("initial_weight_pct"))
        if initial is None or initial < NEW_POSITION_MIN_WEIGHT_PCT:
            continue
        fd = row["filing_date"]
        life_new = new_common.get((row["cusip"], fd))
        theme_col = life_new["theme"] if life_new else ""
        is_ai, subtheme = trig.resolve_ai(reclass, row["ticker"], fd, theme_col)
        if not is_ai:
            continue
        events.append({
            "trigger_type": "NEW_AI_POSITION_2PCT",
            "filing_date": fd,
            "quarter": row.get("quarter", ""),
            "ticker": row["ticker"],
            "company": row.get("company", ""),
            "theme": subtheme or "",
            "initial_weight_pct": trig._fmt(initial),
            "became_active_add": (
                "TRUE" if row.get("became_active_add") == "True" else "FALSE"),
        })
    return events


# --------------------------------------------------------------------------
# Part 3: definition file
# --------------------------------------------------------------------------


def write_definition(reclass: dict[str, Any]) -> None:
    ai_buckets = sorted({
        v["bucket"] for v in reclass.values()
        if "date_segments" not in v and v.get("ai") and v.get("bucket")
    } | {
        seg["bucket"] for v in reclass.values() if "date_segments" in v
        for seg in v["date_segments"] if seg.get("ai") and seg.get("bucket")
    })
    definition = {
        "ramp_basket": {
            "description": (
                "Picks-and-shovels AI infrastructure only. Used for Trigger 1 "
                "(AI basket weight ramp). Excludes hyperscalers and EV."),
            "included_buckets": RAMP_INCLUDED_BUCKETS,
            "excluded_buckets": sorted(RAMP_EXCLUDED_BUCKETS),
        },
        "thematic_basket": {
            "description": (
                "Full AI classification including hyperscalers and EV. Used for "
                "Triggers 2, 2b, 3 (sub-theme entries and individual positions)."),
            "included_buckets": ai_buckets,
        },
    }
    DEFINITION_OUT.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build clean 13F analysis layers")
    parser.add_argument("--skip-universal", action="store_true",
                        help="skip the (fetch-heavy) universal returns table")
    args = parser.parse_args(argv)

    views = trig.find_views_dir()
    reclass = json.loads(RECLASS_PATH.read_text(encoding="utf-8"))
    raw_life = trig._read_csv(views / "position_lifecycles.csv")
    new_ideas = trig._read_csv(views / "new_ideas.csv")

    common = annotate_common(raw_life, reclass)
    fd_to_period: dict[str, str] = {}
    for r in raw_life:
        fd_to_period.setdefault(r["filing_date"], r["period"])
    filings = sorted({r["filing_date"] for r in common})

    # Part 3: definition
    write_definition(reclass)

    # Part 1: universal returns
    universe = sorted({r["ticker"] for r in common}) + BENCHMARKS
    warnings: list[str] = []
    if not args.skip_universal:
        prices, warnings = load_prices(universe, load_eodhd_key())
        uni_rows = build_universal_table(universe, filings, prices)
        with UNIVERSAL_OUT.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=[
                "ticker", "period_start_filing", "period_end_filing",
                "price_start", "price_end", "return_pct"])
            w.writeheader()
            w.writerows(uni_rows)

    # Part 2: clean triggers
    events = (
        trigger_ramp(common, filings, fd_to_period)
        + trigger_subtheme(common, filings, fd_to_period)
        + trigger_2b(common, filings, fd_to_period)
        + trigger_new_position(new_ideas, common, reclass)
    )
    events.sort(key=lambda e: (e["filing_date"], e["trigger_type"]))
    with TRIGGERS_OUT.open("w", newline="", encoding="utf-8") as fh:
        w2 = csv.DictWriter(fh, fieldnames=OUT_COLUMNS, restval="", extrasaction="ignore")
        w2.writeheader()
        w2.writerows(events)

    # Summary
    by_type = Counter(e["trigger_type"] for e in events)
    print(f"\nDefinition -> {DEFINITION_OUT.relative_to(REPO_ROOT)}")
    if not args.skip_universal:
        print(f"Universal returns: {len(universe)} tickers x {len(filings) - 1} "
              f"periods = {len(uni_rows)} rows -> {UNIVERSAL_OUT.relative_to(REPO_ROOT)}")
    print(f"Clean triggers: {len(events)} events -> {TRIGGERS_OUT.relative_to(REPO_ROOT)}")
    for t, n in sorted(by_type.items()):
        print(f"  {t}: {n}")
    ramp_dates = [e["filing_date"] for e in events if e["trigger_type"] == "AI_BASKET_RAMP"]
    print(f"  ramp dates: {ramp_dates}")
    if warnings:
        print(f"\n{len(warnings)} price warnings (first 20):")
        for wmsg in warnings[:20]:
            print(f"  - {wmsg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
