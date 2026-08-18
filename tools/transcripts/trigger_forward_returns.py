#!/usr/bin/env python3
"""Fresh forward-returns performance read on the CORRECTED trigger set
(analysis/13f_signal_triggers_clean.csv — thesis-investable equity, ex-SPCX basis).

Filing-date-anchored, buy-and-hold. Horizons: 1m, 1q(3m), 6m, 1y(12m), 2y(24m).
Benchmarks: SMH and SPY over the identical window. Per trigger type it answers
"does the signal make money": win rate, average return, and excess vs each benchmark.

Tradeable interpretation per trigger:
  NEW_AI_POSITION_2PCT   -> the single named ticker
  NEW_AI_SUBTHEME        -> equal-weight basket of the entering tickers
  AI_SUBTHEME_*_CROSS_*  -> equal-weight basket of all tickers in the subtheme
  AI_BASKET_RAMP         -> equal-weight of the narrow AI picks-and-shovels basket
                            held that filing (same basket the RampBasket sheet uses)

Baskets are equal-weight, buy-and-hold locked at the signal's filing date; a name
missing price data that period is dropped from that basket (renormalized). An event
is counted for a horizon only if the full window fits inside the cached price series.

Usage:
    python tools/transcripts/trigger_forward_returns.py
"""

from __future__ import annotations

import bisect
import csv
import datetime as dt
import json
import statistics
from pathlib import Path
from typing import Any

try:
    from . import generate_13f_triggers as trig
except ImportError:
    import generate_13f_triggers as trig  # type: ignore[import-not-found, no-redef]

ANALYSIS_DIR = trig.ANALYSIS_DIR
RECLASS_PATH = ANALYSIS_DIR / "ai_basket_reclassification.json"
RAMP_EXCLUDED_BUCKETS = {"AI/Hyperscaler", "AI/EV"}  # narrow picks-and-shovels basket
PRICE_CACHE_DIR = ANALYSIS_DIR / "eod_prices"
TRIGGERS_IN = ANALYSIS_DIR / "13f_signal_triggers_clean.csv"
OUT_CSV = ANALYSIS_DIR / "trigger_forward_returns_ex_spcx.csv"
OUT_MD = ANALYSIS_DIR / "trigger_forward_returns_ex_spcx.md"

HORIZONS = [("1m", 1), ("1q", 3), ("6m", 6), ("1y", 12), ("2y", 24)]
BENCHMARKS = ["SMH", "SPY"]
TRIGGER_ORDER = [
    "NEW_AI_POSITION_2PCT", "NEW_AI_SUBTHEME",
    "AI_SUBTHEME_ACTIVE_CROSS_2PCT", "AI_SUBTHEME_ACTIVE_CROSS_4PCT",
    "AI_BASKET_RAMP",
]


# --------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------


class Prices:
    """Adjusted-close series with as-of (first trading day >= target) lookup."""

    def __init__(self) -> None:
        self.dates: dict[str, list[str]] = {}
        self.px: dict[str, list[float]] = {}
        self.last: str = ""

    def load(self, tickers: set[str]) -> None:
        for t in tickers:
            f = PRICE_CACHE_DIR / f"{t}.json"
            if not f.exists():
                continue
            rows = json.loads(f.read_text(encoding="utf-8"))
            ds = [r["date"] for r in rows]
            self.dates[t] = ds
            self.px[t] = [float(r["adjusted_close"]) for r in rows]
            if ds:
                self.last = max(self.last, ds[-1])

    def asof(self, ticker: str, target: str) -> float | None:
        ds = self.dates.get(ticker)
        if not ds or target > ds[-1]:
            return None
        i = bisect.bisect_left(ds, target)
        return self.px[ticker][i] if i < len(ds) else None

    def ret(self, ticker: str, start: str, end: str) -> float | None:
        p0 = self.asof(ticker, start)
        p1 = self.asof(ticker, end)
        if p0 is None or p1 is None or p0 == 0:
            return None
        return p1 / p0 - 1.0


def add_months(iso: str, n: int) -> str:
    d = dt.date.fromisoformat(iso)
    total = (d.year * 12 + (d.month - 1)) + n
    y, m = divmod(total, 12)
    m += 1
    last_day = [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last_day)).isoformat()


def basket_ret(px: Prices, tickers: list[str], start: str, end: str) -> float | None:
    """Equal-weight buy-and-hold return; drop names missing price data that window."""
    vals = [r for t in tickers if (r := px.ret(t, start, end)) is not None]
    return sum(vals) / len(vals) if vals else None


# --------------------------------------------------------------------------
# Event -> tradeable basket
# --------------------------------------------------------------------------


def build_ramp_holdings() -> dict[str, list[str]]:
    """Per filing date: the narrow AI picks-and-shovels COMMON non-EXIT tickers held
    that quarter (same basket the RampBasket sheet uses). Self-contained so this module
    has no dependency on build_trigger_workbook (avoids a circular import)."""
    reclass = json.loads(RECLASS_PATH.read_text(encoding="utf-8"))
    holdings: dict[str, list[str]] = {}
    for r in trig._read_csv(trig.find_views_dir() / "position_lifecycles.csv"):
        if r["security_type"] != "COMMON" or r["change_type"] == "EXIT":
            continue
        is_ai, bucket = trig.resolve_ai(reclass, r["ticker"], r["filing_date"], r["theme"])
        if is_ai and bucket not in RAMP_EXCLUDED_BUCKETS:
            holdings.setdefault(r["filing_date"], []).append(r["ticker"])
    return holdings


def _split(cell: str) -> list[str]:
    return [t.strip() for t in (cell or "").replace(";", ",").split(",") if t.strip()]


def event_tickers(row: dict[str, str], ramp_holdings: dict[str, list[str]]) -> list[str]:
    tt = row["trigger_type"]
    if tt == "NEW_AI_POSITION_2PCT":
        return [row["ticker"]] if row.get("ticker") else []
    if tt == "NEW_AI_SUBTHEME":
        return _split(row.get("entering_tickers", ""))
    if tt.startswith("AI_SUBTHEME_ACTIVE_CROSS"):
        return _split(row.get("all_tickers_in_subtheme", ""))
    if tt == "AI_BASKET_RAMP":
        return list(ramp_holdings.get(row["filing_date"], []))
    return []


# --------------------------------------------------------------------------
# Stats
# --------------------------------------------------------------------------


def pct(x: float | None) -> str:
    return "" if x is None else f"{x * 100:+.1f}%"


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """records: each has ret, smh, spy for one event+horizon (all non-None)."""
    n = len(records)
    if n == 0:
        return {"n": 0}
    rets = [r["ret"] for r in records]
    ex_smh = [r["ret"] - r["smh"] for r in records]
    ex_spy = [r["ret"] - r["spy"] for r in records]
    return {
        "n": n,
        "win_rate": sum(1 for r in rets if r > 0) / n,
        "avg_return": statistics.mean(rets),
        "median_return": statistics.median(rets),
        "avg_excess_smh": statistics.mean(ex_smh),
        "beat_smh_rate": sum(1 for e in ex_smh if e > 0) / n,
        "avg_excess_spy": statistics.mean(ex_spy),
        "beat_spy_rate": sum(1 for e in ex_spy if e > 0) / n,
    }


def compute_grouped() -> tuple[dict[tuple[str, str], list[dict[str, Any]]], str]:
    """(trigger_type, horizon) -> list of {ret, smh, spy} for every observed event."""
    rows = trig._read_csv(TRIGGERS_IN)
    ramp_holdings = build_ramp_holdings()
    universe: set[str] = set(BENCHMARKS)
    for r in rows:
        universe.update(event_tickers(r, ramp_holdings))
    px = Prices()
    px.load(universe)

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        tt = r["trigger_type"]
        fd = r["filing_date"]
        tickers = event_tickers(r, ramp_holdings)
        if not tickers:
            continue
        for hlabel, months in HORIZONS:
            end = add_months(fd, months)
            if end > px.last:  # forward window not fully observed yet
                continue
            ret = basket_ret(px, tickers, fd, end)
            smh = px.ret("SMH", fd, end)
            spy = px.ret("SPY", fd, end)
            if ret is None or smh is None or spy is None:
                continue
            grouped.setdefault((tt, hlabel), []).append({"ret": ret, "smh": smh, "spy": spy})
    return grouped, px.last


def compute_stats() -> tuple[list[dict[str, Any]], str]:
    """Formatted per trigger_type × horizon rows (+ ALL_TRIGGERS) and the last price date.
    Reused by build_trigger_workbook to render the Performance sheet."""
    grouped, last = compute_grouped()
    out_rows: list[dict[str, Any]] = []
    for tt in TRIGGER_ORDER + ["ALL_TRIGGERS"]:
        for hlabel, _ in HORIZONS:
            if tt == "ALL_TRIGGERS":
                recs = [rec for (t, h), lst in grouped.items() if h == hlabel for rec in lst]
            else:
                recs = grouped.get((tt, hlabel), [])
            s = summarize(recs)
            out_rows.append({
                "trigger_type": tt, "horizon": hlabel, "n": s["n"],
                "win_rate": f"{s['win_rate']*100:.0f}%" if s["n"] else "",
                "avg_return": pct(s.get("avg_return")),
                "median_return": pct(s.get("median_return")),
                "avg_excess_smh": pct(s.get("avg_excess_smh")),
                "beat_smh_rate": f"{s['beat_smh_rate']*100:.0f}%" if s["n"] else "",
                "avg_excess_spy": pct(s.get("avg_excess_spy")),
                "beat_spy_rate": f"{s['beat_spy_rate']*100:.0f}%" if s["n"] else "",
            })
    return out_rows, last


def main() -> int:
    out_rows, last = compute_stats()
    fields = ["trigger_type", "horizon", "n", "win_rate", "avg_return", "median_return",
              "avg_excess_smh", "beat_smh_rate", "avg_excess_spy", "beat_spy_rate"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    _write_md(out_rows, last)
    print(f"Wrote {OUT_CSV.relative_to(trig.REPO_ROOT)} and {OUT_MD.relative_to(trig.REPO_ROOT)}")
    print(f"Prices through {last}. Buy-and-hold, filing-anchored, equal-weight baskets.\n")
    _print_table(out_rows)
    return 0


def _write_md(out_rows: list[dict[str, Any]], last: str) -> None:
    lines = [
        "# Forward-returns performance — corrected trigger set (ex-SPCX basis)",
        "",
        f"Prices through **{last}**. Filing-date-anchored, buy-and-hold, equal-weight baskets. "
        "Excess = signal return − benchmark return over the identical window. An event counts "
        "for a horizon only if the full forward window is observed.",
        "",
        "| trigger | horizon | n | win rate | avg ret | median | exc SMH | beat SMH | exc SPY | beat SPY |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    for r in out_rows:
        lines.append("| {trigger_type} | {horizon} | {n} | {win_rate} | {avg_return} | "
                     "{median_return} | {avg_excess_smh} | {beat_smh_rate} | {avg_excess_spy} | "
                     "{beat_spy_rate} |".format(**r))
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _print_table(out_rows: list[dict[str, Any]]) -> None:
    hdr = ["trigger", "hor", "n", "win", "avg", "med", "excSMH", "bSMH", "excSPY", "bSPY"]
    print(f"{hdr[0]:<30}{hdr[1]:>4}{hdr[2]:>4}{hdr[3]:>6}{hdr[4]:>8}{hdr[5]:>8}"
          f"{hdr[6]:>8}{hdr[7]:>6}{hdr[8]:>8}{hdr[9]:>6}")
    for r in out_rows:
        if r["horizon"] == "1m" and r["trigger_type"] != "NEW_AI_POSITION_2PCT":
            print()
        print(f"{r['trigger_type']:<30}{r['horizon']:>4}{r['n']:>4}{r['win_rate']:>6}"
              f"{r['avg_return']:>8}{r['median_return']:>8}{r['avg_excess_smh']:>8}"
              f"{r['beat_smh_rate']:>6}{r['avg_excess_spy']:>8}{r['beat_spy_rate']:>6}")


if __name__ == "__main__":
    raise SystemExit(main())
