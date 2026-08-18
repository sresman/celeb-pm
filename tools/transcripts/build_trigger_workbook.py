#!/usr/bin/env python3
"""Build analysis/trigger_analysis.xlsx — a 5-sheet workbook, one sheet per trigger
type, events as rows and quarter-by-quarter (filing-to-filing) SINGLE-PERIOD returns
across columns, with allocation tracking and green/red return shading.

Values are hardcoded (no formulas) from the existing CSVs — no recalc needed.
Every return cell is one filing-to-filing period return; nothing is compounded.

Usage:
    python tools/transcripts/build_trigger_workbook.py
"""

from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment, Font, PatternFill  # type: ignore[import-untyped]
from openpyxl.utils import get_column_letter  # type: ignore[import-untyped]
from openpyxl.worksheet.worksheet import Worksheet  # type: ignore[import-untyped]

try:  # runs both as a direct script and under `-m`
    from . import generate_13f_triggers as trig
    from . import trigger_forward_returns as fr
except ImportError:
    import generate_13f_triggers as trig  # type: ignore[import-not-found, no-redef]
    import trigger_forward_returns as fr  # type: ignore[import-not-found, no-redef]

ANALYSIS_DIR = trig.ANALYSIS_DIR
RECLASS_PATH = ANALYSIS_DIR / "ai_basket_reclassification.json"
TRIGGERS_IN = ANALYSIS_DIR / "13f_signal_triggers_clean.csv"
UNIVERSAL_IN = ANALYSIS_DIR / "filing_to_filing_returns_universal.csv"
OUT_PATH = ANALYSIS_DIR / "trigger_analysis.xlsx"

FWD_QUARTERS = 24  # Q+1 .. Q+24 for the variable-length sheets
SENTINELS = {"PRE_IPO", "NO_DATA", ""}
RAMP_EXCLUDED_BUCKETS = {"AI/Hyperscaler", "AI/EV"}  # narrow "picks-and-shovels" basket

HEADER_FONT = Font(bold=True)
CENTER = Alignment(horizontal="center")
LEFT = Alignment(horizontal="left")
WRAP = Alignment(horizontal="left", vertical="top", wrap_text=True)
GREEN = PatternFill("solid", fgColor="DCF0DC")  # (220,240,220)
RED = PatternFill("solid", fgColor="F0DCDC")    # (240,220,220)
SECTION_FILL = PatternFill("solid", fgColor="E4E8F4")  # basket section header band
CALLOUT_FILL = PatternFill("solid", fgColor="FFF3CD")  # SpaceX / caveat callout band
TITLE_FONT = Font(bold=True, size=13)
SECTION_FONT = Font(bold=True, size=11)
NOTE_FONT = Font(italic=True, color="666666")
RET_FMT = "+0.0%;-0.0%;0.0%"
ALLOC_FMT = "0.0%"
DATE_FMT = "yyyy-mm-dd"
DOLLAR_FMT = "#,##0"
SIGNED_DOLLAR_FMT = "#,##0;(#,##0)"

# --- Context-sheet inputs (Baker = Atreides; Leopold = Situational Awareness) ---
BAKER_PERIOD = "2026-06-30"
BAKER_PRIOR_PERIOD = "2026-03-31"
BAKER_FILING_DATE = "2026-08-14"
BAKER_HISTORY_PERIODS = ["2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
THEME_BASKETS_PATH = ANALYSIS_DIR / "theme_baskets_v3.json"
THESIS_PATH = ANALYSIS_DIR / "thesis_timeline_v2_flat.json"
BAKER_OVERLAY_PATH = ANALYSIS_DIR / "baker_basket_overlay.json"
TICKER_CLASS_PATH = trig.REPO_ROOT / "data" / "ticker_classifications.json"
SA_CSV = ANALYSIS_DIR / "sa_q2_2026_mtm_vs_trading.csv"
SA_BASKETS_PATH = ANALYSIS_DIR / "sa_theme_baskets.json"

# Positions that entered the 13F via an IPO (pre-existing private holding becoming a
# reportable security), NOT via market purchase. Excluded from net-buying/MTM totals.
IPO_RECLASS_TICKERS = {"SPCX"}


def ex_reclass_scale_by_fd() -> dict[str, float]:
    """filing_date -> (total_book / thesis-investable equity) rescale factor. Multiplying
    a reported weight by this converts it to a % of equity ex IPO-reclass — the basis the
    triggers now use, so the workbook's forward-alloc tracking stays consistent."""
    positions = json.loads((trig.find_views_dir().parent / "positions.json").read_text(encoding="utf-8"))
    tot: dict[str, float] = {}
    exq: dict[str, float] = {}
    fd_of: dict[str, str] = {}
    for r in positions:
        p = r["period"]
        v = r["value_reported"] or 0.0
        tot[p] = tot.get(p, 0.0) + v
        fd_of[p] = r["filing_date"]
        if r["security_type"] == "COMMON" and (r.get("ticker") or "") not in IPO_RECLASS_TICKERS:
            exq[p] = exq.get(p, 0.0) + v
    return {fd_of[p]: (tot[p] / exq[p] if exq.get(p) else 1.0) for p in tot}


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------


def build_lookups() -> tuple[
    dict[tuple[str, str], float],       # return: (ticker, period_start) -> pct
    dict[tuple[str, str], float],       # ticker alloc: (ticker, filing_date) -> weight
    dict[tuple[str, str], float],       # subtheme alloc: (subtheme, filing_date) -> weight
    list[str],                          # sorted filing dates (25)
]:
    ret: dict[tuple[str, str], float] = {}
    filings_set: set[str] = set()
    for r in trig._read_csv(UNIVERSAL_IN):
        filings_set.add(r["period_start_filing"])
        filings_set.add(r["period_end_filing"])
        val = r["return_pct"]
        if val not in SENTINELS:
            ret[(r["ticker"], r["period_start_filing"])] = float(val)

    reclass = json.loads(RECLASS_PATH.read_text(encoding="utf-8"))
    views = trig.find_views_dir()
    scale = ex_reclass_scale_by_fd()  # reported weight -> ex-reclass-equity basis
    ticker_alloc: dict[tuple[str, str], float] = {}
    subtheme_alloc: dict[tuple[str, str], float] = {}
    for r in trig._read_csv(views / "position_lifecycles.csv"):
        if r["security_type"] != "COMMON" or r["change_type"] == "EXIT":
            continue
        if (r.get("ticker") or "") in IPO_RECLASS_TICKERS:
            continue  # excluded from the thesis-investable book
        fd = r["filing_date"]
        weight = (trig._f(r["weight_pct"]) or 0.0) * scale.get(fd, 1.0)
        ticker_alloc[(r["ticker"], fd)] = weight
        is_ai, subtheme = trig.resolve_ai(reclass, r["ticker"], fd, r["theme"])
        if is_ai and subtheme is not None:
            key = (subtheme, fd)
            subtheme_alloc[key] = subtheme_alloc.get(key, 0.0) + weight

    return ret, ticker_alloc, subtheme_alloc, sorted(filings_set)


def basket_return(ret: dict[tuple[str, str], float], tickers: list[str], start: str) -> float | None:
    """Equal-weight average of constituents' single-period returns; drop missing."""
    vals = [ret[(t, start)] for t in tickers if (t, start) in ret]
    return sum(vals) / len(vals) if vals else None


def cw_return(ret: dict[tuple[str, str], float], pairs: list[tuple[str, float]], start: str) -> float | None:
    """Capital-weighted single-period return; renormalize among constituents with
    data that period (denominator = summed weights of the available names)."""
    num = den = 0.0
    for ticker, weight in pairs:
        v = ret.get((ticker, start))
        if v is not None:
            num += weight * v
            den += weight
    return num / den if den > 0 else None


def build_ramp_holdings() -> dict[str, list[tuple[str, float]]]:
    """Per filing date: the AI picks-and-shovels COMMON non-EXIT holdings
    (ticker, weight_pct), sorted by weight desc. Same narrow filter as Trigger 1."""
    reclass = json.loads(RECLASS_PATH.read_text(encoding="utf-8"))
    views = trig.find_views_dir()
    holdings: dict[str, list[tuple[str, float]]] = {}
    for r in trig._read_csv(views / "position_lifecycles.csv"):
        if r["security_type"] != "COMMON" or r["change_type"] == "EXIT":
            continue
        is_ai, bucket = trig.resolve_ai(reclass, r["ticker"], r["filing_date"], r["theme"])
        if is_ai and bucket not in RAMP_EXCLUDED_BUCKETS:
            holdings.setdefault(r["filing_date"], []).append(
                (r["ticker"], trig._f(r["weight_pct"]) or 0.0))
    for fd in holdings:
        holdings[fd].sort(key=lambda x: x[1], reverse=True)
    return holdings


# --------------------------------------------------------------------------
# Cell writers
# --------------------------------------------------------------------------


def _put_ret(ws: Worksheet, row: int, col: int, pct: float | None) -> None:
    if pct is None:
        return
    cell = ws.cell(row, col, pct / 100.0)
    cell.number_format = RET_FMT
    if pct > 0:
        cell.fill = GREEN
    elif pct < 0:
        cell.fill = RED


def _put_weight(ws: Worksheet, row: int, col: int, pct: float | None, fmt: str = ALLOC_FMT) -> None:
    if pct is None:
        return
    cell = ws.cell(row, col, pct / 100.0)
    cell.number_format = fmt


def _put_date(ws: Worksheet, row: int, col: int, iso: str) -> None:
    cell = ws.cell(row, col, dt.date.fromisoformat(iso))
    cell.number_format = DATE_FMT


def _finish(ws: Worksheet, headers: list[str], id_widths: list[float], period_w: float = 10) -> None:
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
    for i, w in enumerate(id_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for i in range(len(id_widths) + 1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = period_w
    ws.freeze_panes = f"{get_column_letter(len(id_widths) + 1)}2"


def _tickers(cell: str) -> list[str]:
    return [t.strip() for t in cell.split(",") if t.strip()]


# Buying-detail block shared by the Ramp and RampBasket sheets (net-buying trigger metrics
# + what was bought/sold/entered/exited). Placed after the weight columns, before returns.
BUYING_DETAIL_HEADERS = [
    "net_buying_pct", "net_buying_dollars", "gross_buying_pct", "gross_selling_pct",
    "tickers_bought", "tickers_sold", "tickers_new", "tickers_exited",
]
BUYING_DETAIL_WIDTHS: list[float] = [14, 16, 14, 14, 30, 30, 22, 22]


def _put_buying_detail(ws: Worksheet, row: int, col: int, e: dict[str, str]) -> int:
    """Write the 8 buying-detail cells starting at `col`; return the next free column."""
    _put_weight(ws, row, col, trig._f(e.get("net_buying_pct")))
    nbd = trig._f(e.get("net_buying_dollars"))
    if nbd is not None:
        ws.cell(row, col + 1, nbd).number_format = "#,##0"
    _put_weight(ws, row, col + 2, trig._f(e.get("gross_buying_pct")))
    _put_weight(ws, row, col + 3, trig._f(e.get("gross_selling_pct")))
    ws.cell(row, col + 4, e.get("tickers_bought", ""))
    ws.cell(row, col + 5, e.get("tickers_sold", ""))
    ws.cell(row, col + 6, e.get("tickers_new", ""))
    ws.cell(row, col + 7, e.get("tickers_exited", ""))
    return col + 8


# --------------------------------------------------------------------------
# Sheets
# --------------------------------------------------------------------------


def sheet_ramp(ws: Worksheet, events: list[dict[str, str]], ret: dict[tuple[str, str], float],
               filings: list[str], fidx: dict[str, int]) -> None:
    pre = [4, 3, 2, 1]
    fwd = list(range(1, 9))
    headers = (["filing_date", "ai_weight_change", "ai_weight_current"] + BUYING_DETAIL_HEADERS
               + [f"Q-{i}_SMH" for i in pre] + [f"Q+{j}_SMH" for j in fwd])
    _finish(ws, headers, [12.0, 16.0, 16.0, *BUYING_DETAIL_WIDTHS])
    for row, e in enumerate(events, 2):
        k = fidx[e["filing_date"]]
        _put_date(ws, row, 1, e["filing_date"])
        _put_weight(ws, row, 2, trig._f(e["ai_weight_change"]), RET_FMT)
        _put_weight(ws, row, 3, trig._f(e["ai_weight_current"]))
        col = _put_buying_detail(ws, row, 4, e)  # cols 4..11
        for i in pre:
            if k - i >= 0:
                _put_ret(ws, row, col, ret.get(("SMH", filings[k - i])))
            col += 1
        for j in fwd:
            if k + j <= len(filings) - 1:
                _put_ret(ws, row, col, ret.get(("SMH", filings[k + j - 1])))
            col += 1


def sheet_ramp_basket(ws: Worksheet, events: list[dict[str, str]], ret: dict[tuple[str, str], float],
                      holdings: dict[str, list[tuple[str, float]]], filings: list[str],
                      fidx: dict[str, int]) -> None:
    pre = [4, 3, 2, 1]
    fwd = list(range(1, 9))
    max_n = max((len(holdings.get(e["filing_date"], [])) for e in events), default=0)
    headers = ["filing_date", "ai_weight_change", "ai_weight_current"] + BUYING_DETAIL_HEADERS
    for i in range(1, max_n + 1):
        headers += [f"ticker_{i}", f"wt_{i}"]
    for i in pre:
        headers += [f"Q-{i}_EW", f"Q-{i}_CW", f"Q-{i}_SMH"]
    for j in fwd:
        headers += [f"Q+{j}_EW", f"Q+{j}_CW", f"Q+{j}_SMH"]
    _finish(ws, headers, [12.0, 16.0, 16.0, *BUYING_DETAIL_WIDTHS])

    comp_start = 4 + len(BUYING_DETAIL_HEADERS)  # composition begins after the detail block
    for row, e in enumerate(events, 2):
        k = fidx[e["filing_date"]]
        pairs = holdings.get(e["filing_date"], [])
        tickers = [t for t, _ in pairs]
        _put_date(ws, row, 1, e["filing_date"])
        _put_weight(ws, row, 2, trig._f(e["ai_weight_change"]), RET_FMT)
        _put_weight(ws, row, 3, trig._f(e["ai_weight_current"]))
        _put_buying_detail(ws, row, 4, e)  # cols 4..11
        col = comp_start
        for ticker, weight in pairs:
            ws.cell(row, col, ticker)
            _put_weight(ws, row, col + 1, weight)
            col += 2
        col = comp_start + max_n * 2  # start of the period block (past all ticker/wt pairs)
        starts = ([filings[k - i] if k - i >= 0 else None for i in pre]
                  + [filings[k + j - 1] if k + j <= len(filings) - 1 else None for j in fwd])
        for start in starts:
            if start is not None:
                _put_ret(ws, row, col, basket_return(ret, tickers, start))
                _put_ret(ws, row, col + 1, cw_return(ret, pairs, start))
                _put_ret(ws, row, col + 2, ret.get(("SMH", start)))
            col += 3


def sheet_new_subtheme(ws: Worksheet, events: list[dict[str, str]], ret: dict[tuple[str, str], float],
                       subtheme_alloc: dict[tuple[str, str], float], filings: list[str],
                       fidx: dict[str, int]) -> None:
    headers = ["filing_date", "subtheme", "entering_tickers", "total_subtheme_weight"]
    for j in range(1, FWD_QUARTERS + 1):
        headers += [f"Q+{j}_alloc", f"Q+{j}_basket", f"Q+{j}_SMH"]
    _finish(ws, headers, [12, 26, 26, 18])
    for row, e in enumerate(events, 2):
        k = fidx[e["filing_date"]]
        basket = _tickers(e["entering_tickers"])
        _put_date(ws, row, 1, e["filing_date"])
        ws.cell(row, 2, e["subtheme"])
        ws.cell(row, 3, e["entering_tickers"])
        _put_weight(ws, row, 4, trig._f(e["total_subtheme_weight"]))
        col = 5
        for j in range(1, FWD_QUARTERS + 1):
            if k + j <= len(filings) - 1:
                _put_weight(ws, row, col, subtheme_alloc.get((e["subtheme"], filings[k + j])))
                _put_ret(ws, row, col + 1, basket_return(ret, basket, filings[k + j - 1]))
                _put_ret(ws, row, col + 2, ret.get(("SMH", filings[k + j - 1])))
            col += 3


def sheet_new_position(ws: Worksheet, events: list[dict[str, str]], ret: dict[tuple[str, str], float],
                       ticker_alloc: dict[tuple[str, str], float], filings: list[str],
                       fidx: dict[str, int]) -> None:
    headers = ["filing_date", "ticker", "theme", "initial_weight_pct"]
    for j in range(1, FWD_QUARTERS + 1):
        headers += [f"Q+{j}_alloc", f"Q+{j}_ticker", f"Q+{j}_SMH"]
    _finish(ws, headers, [12, 10, 24, 16])
    for row, e in enumerate(events, 2):
        k = fidx[e["filing_date"]]
        ticker = e["ticker"]
        _put_date(ws, row, 1, e["filing_date"])
        ws.cell(row, 2, ticker)
        ws.cell(row, 3, e["theme"])
        _put_weight(ws, row, 4, trig._f(e["initial_weight_pct"]))
        col = 5
        for j in range(1, FWD_QUARTERS + 1):
            if k + j <= len(filings) - 1:
                _put_weight(ws, row, col, ticker_alloc.get((ticker, filings[k + j])))
                _put_ret(ws, row, col + 1, ret.get((ticker, filings[k + j - 1])))
                _put_ret(ws, row, col + 2, ret.get(("SMH", filings[k + j - 1])))
            col += 3


def sheet_cross(ws: Worksheet, events: list[dict[str, str]], ret: dict[tuple[str, str], float],
                subtheme_alloc: dict[tuple[str, str], float], filings: list[str],
                fidx: dict[str, int]) -> None:
    pre = [4, 3, 2, 1]
    headers = ["filing_date", "subtheme", "subtheme_weight_prior",
               "subtheme_weight_current", "active_tickers", "all_tickers"]
    for i in pre:
        headers += [f"Q-{i}_basket", f"Q-{i}_SMH"]
    for j in range(1, FWD_QUARTERS + 1):
        headers += [f"Q+{j}_alloc", f"Q+{j}_basket", f"Q+{j}_SMH"]
    _finish(ws, headers, [12, 26, 20, 20, 28, 34])
    for row, e in enumerate(events, 2):
        k = fidx[e["filing_date"]]
        basket = _tickers(e["all_tickers_in_subtheme"])
        _put_date(ws, row, 1, e["filing_date"])
        ws.cell(row, 2, e["subtheme"])
        _put_weight(ws, row, 3, trig._f(e["subtheme_weight_prior"]))
        _put_weight(ws, row, 4, trig._f(e["subtheme_weight_current"]))
        ws.cell(row, 5, e["active_tickers"])
        ws.cell(row, 6, e["all_tickers_in_subtheme"])
        col = 7
        for i in pre:
            if k - i >= 0:
                _put_ret(ws, row, col, basket_return(ret, basket, filings[k - i]))
                _put_ret(ws, row, col + 1, ret.get(("SMH", filings[k - i])))
            col += 2
        for j in range(1, FWD_QUARTERS + 1):
            if k + j <= len(filings) - 1:
                _put_weight(ws, row, col, subtheme_alloc.get((e["subtheme"], filings[k + j])))
                _put_ret(ws, row, col + 1, basket_return(ret, basket, filings[k + j - 1]))
                _put_ret(ws, row, col + 2, ret.get(("SMH", filings[k + j - 1])))
            col += 3


# ==========================================================================
# CONTEXT SHEETS — holdings / baskets / flows / summary for two managers
# (Baker = Atreides; Leopold = Situational Awareness). Additive; the trigger
# sheets above are untouched.
# ==========================================================================


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def decompose(
    prior_shares: float | None, prior_value: float | None,
    curr_shares: float | None, curr_value: float | None, change_type: str,
) -> tuple[float, float]:
    """Split a position's Q/Q dollar change into (MTM, Trading) using the fund's
    own 13F marks as the quarter-end price (value / shares). By construction
    MTM + Trading == value_delta exactly (recon_gap == 0). Conventions:
    NEW -> all Trading (no prior mark); EXIT -> all Trading = -prior_value."""
    ps = prior_shares or 0.0
    pv = prior_value or 0.0
    cs = curr_shares or 0.0
    cv = curr_value or 0.0
    if change_type == "NEW" or ps == 0 or pv == 0:
        return 0.0, cv
    if change_type == "EXIT" or cs == 0 or cv == 0:
        return 0.0, -pv
    p1, p2 = pv / ps, cv / cs
    return ps * (p2 - p1), (cs - ps) * p2


def decomp_label(mtm: float | None, trade: float | None, change_type: str) -> str:
    if change_type == "NEW":
        return "NEW — buy"
    if change_type == "EXIT":
        return "EXIT — sell"
    if mtm is None or trade is None:
        return ""
    if trade == 0 and mtm == 0:
        return "flat"
    if abs(trade) < abs(mtm):
        return "MTM-driven"
    return "net buying" if trade > 0 else "net selling"


def build_theme_index(path: Path, filing_date: str) -> dict[str, list[str]]:
    """Reverse index ticker -> [basket names] from theme_baskets_v3.json, honoring
    date_segments at the given filing_date. A ticker may appear in several baskets."""
    data = _load_json(path)
    idx: dict[str, list[str]] = {}
    for name, v in data.items():
        if name.startswith("_") or not isinstance(v, dict):
            continue
        if "date_segments" in v:
            seg = trig._pick_segment(v["date_segments"], filing_date)
            tickers = seg.get("tickers", [])
        else:
            tickers = v.get("tickers", [])
        for t in tickers:
            idx.setdefault(t, []).append(name)
    return idx


def load_sa_baskets() -> list[tuple[str, dict[str, Any]]]:
    data = _load_json(SA_BASKETS_PATH)
    return [(n, v) for n, v in data.items() if not n.startswith("_") and isinstance(v, dict)]


def sa_basket_for(baskets: list[tuple[str, dict[str, Any]]], ticker: str, company: str) -> str | None:
    """Single primary basket for a Leopold position: ticker match first, then a
    company-name alias (for positions that file with an unresolved ticker)."""
    for name, v in baskets:
        if ticker and ticker in v.get("tickers", []):
            return name
        for alias in v.get("companies", []):
            if alias and company and alias.upper() in company.upper():
                return name
    return None


# --------------------------------------------------------------------------
# Single primary-basket assignment (one basket per ticker — matches the prior
# trigger_analysis behavior, which classified each ticker via one reclass bucket)
# --------------------------------------------------------------------------


def load_baker_overlay() -> tuple[dict[str, str], dict[str, str]]:
    """Returns (by_ticker, by_cusip) primary-basket override maps. by_cusip covers
    positions that file with an unresolved (null) ticker."""
    data = _load_json(BAKER_OVERLAY_PATH)
    return dict(data.get("primary_basket", {})), dict(data.get("primary_basket_by_cusip", {}))


def reclass_bucket(reclass: dict[str, Any], ticker: str, filing_date: str) -> str | None:
    """Raw single bucket from ai_basket_reclassification.json (regardless of the ai
    flag), honoring date_segments. resolve_ai nulls buckets for ai=False names, so we
    read it directly to keep names like QNT->Quantum Computing, NTRA->Healthcare."""
    if not ticker:
        return None
    entry = reclass.get(ticker) or reclass.get(ticker.lstrip("0123456789"))
    if entry is None:
        return None
    if "date_segments" in entry:
        entry = trig._pick_segment(entry["date_segments"], filing_date)
    return entry.get("bucket")


def primary_basket(ticker: str, cusip: str, theme_col: str, overlay: dict[str, str],
                   overlay_cusip: dict[str, str], reclass: dict[str, Any],
                   filing_date: str) -> str:
    """Exactly ONE basket per ticker: curated overlay (by ticker, then by cusip for
    null-ticker names) → reclass single bucket → position theme → 'Unassigned'."""
    if ticker and ticker in overlay:
        return overlay[ticker]
    if cusip in overlay_cusip:
        return overlay_cusip[cusip]
    b = reclass_bucket(reclass, ticker, filing_date)
    if b:
        return b
    return theme_col or "Unassigned"


def theme_memberships(theme_idx: dict[str, list[str]], ticker: str, primary: str) -> list[str]:
    """Other theme_baskets_v3 baskets the ticker belongs to (for the 'also_in' note)."""
    return [b for b in theme_idx.get(ticker, []) if b != primary]


# --------------------------------------------------------------------------
# Context builders (compute once, reused across sheets)
# --------------------------------------------------------------------------


def build_baker_context() -> dict[str, Any]:
    """Q2 snapshot + Q/Q decomposition for every current Baker position, plus the
    quarter's exits. Returns holdings (COMMON, sorted by value desc), options, and
    exits, each as a list of computed row dicts, with portfolio totals."""
    data_dir = trig.find_views_dir().parent
    positions = _load_json(data_dir / "positions.json")
    changes = _load_json(data_dir / "changes.json")
    reclass = _load_json(RECLASS_PATH)
    overlay, overlay_cusip = load_baker_overlay()
    tclass = _load_json(TICKER_CLASS_PATH)  # ticker -> {sector, industry, theme}
    theme_idx = build_theme_index(THEME_BASKETS_PATH, BAKER_FILING_DATE)
    # Weights on the thesis-investable basis: % of COMMON equity EXCLUDING IPO-reclass
    # positions (SPCX), consistent with the triggers. SPCX itself is a memo (its share
    # of total equity), excluded from the denominator so it doesn't compress everyone.
    def _denom(period: str, ex_reclass: bool) -> float:
        return sum(
            (pp["value_reported"] or 0.0) for pp in positions
            if pp["period"] == period and pp["security_type"] == "COMMON"
            and not (ex_reclass and (pp.get("ticker") or "") in IPO_RECLASS_TICKERS)
        )
    ex_q1 = _denom(BAKER_PRIOR_PERIOD, True) or 1.0
    ex_q2 = _denom(BAKER_PERIOD, True) or 1.0
    equity_q2 = _denom(BAKER_PERIOD, False) or 1.0  # incl SPCX, for the SPCX memo weight
    q1_val = {
        p["cusip"]: (p["value_reported"] or 0.0)
        for p in positions
        if p["period"] == BAKER_PRIOR_PERIOD and p["security_type"] == "COMMON"
    }
    life = {
        (r["ticker"], r["security_type"]): r
        for r in trig._read_csv(trig.find_views_dir() / "position_lifecycles.csv")
        if r["period"] == BAKER_PERIOD
    }
    chg_idx = {
        (c["cusip"], c["security_type"]): c
        for c in changes if c["period"] == BAKER_PERIOD
    }

    holdings: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []
    for p in positions:
        if p["period"] != BAKER_PERIOD:
            continue
        st = p["security_type"]
        ticker = p.get("ticker") or ""
        company = p.get("company_name", "")
        c = chg_idx.get((p["cusip"], st))
        ct = c["change_type"] if c else "HOLD"
        lc = life.get((ticker, st), {})
        theme_col = lc.get("theme", "")
        is_ai, bucket = (
            trig.resolve_ai(reclass, ticker, BAKER_FILING_DATE, theme_col)
            if ticker else (False, None)
        )
        is_reclass = ticker in IPO_RECLASS_TICKERS
        if is_reclass:
            # IPO reclassification: not a market buy or a price move — exclude from
            # every net-buying/MTM total. Position value/weight still shown.
            ct = "IPO_RECLASSIFICATION"
            mtm, trade, value_delta = (None, None, None)
        elif st == "COMMON" and c is not None:
            mtm, trade = decompose(
                c["prior_shares"], c["prior_value_reported"],
                c["current_shares"], c["current_value_reported"], ct)
            # Compute value_delta ourselves: changes.json leaves it None for NEW,
            # which would break the MTM+Trade == value_delta reconciliation on the sheet.
            value_delta = (c["current_value_reported"] or 0.0) - (c["prior_value_reported"] or 0.0)
        else:
            mtm, trade, value_delta = (None, None, c["value_delta"] if c else None)
        prim = primary_basket(ticker, p["cusip"], theme_col, overlay, overlay_cusip,
                              reclass, BAKER_FILING_DATE)
        cur_val = p["value_reported"] or 0.0
        if is_reclass:
            # memo: SPCX as a share of TOTAL equity; excluded from thesis-book weights.
            wt_q2 = 100.0 * cur_val / equity_q2
            wt_q1 = None
            wt_delta = None
        else:
            wt_q2 = 100.0 * cur_val / ex_q2
            q1v = q1_val.get(p["cusip"])
            wt_q1 = (100.0 * q1v / ex_q1) if q1v is not None else None
            wt_delta = wt_q2 - (wt_q1 or 0.0)
        row = {
            "ticker": ticker, "cusip": p["cusip"], "company": company,
            "display": ticker or company or p["cusip"],
            "security_type": st, "put_call": p.get("put_call", ""),
            "shares": p["shares"], "value": p["value_reported"],
            "weight_eo": wt_q2, "weight_rep": p.get("weight_pct_reported"),
            "wt_q1": wt_q1, "wt_q2": wt_q2, "wt_delta_pp": wt_delta,
            "shares_delta": c["shares_delta"] if c else None,
            "shares_delta_pct": c["shares_delta_pct"] if c else None,
            "value_delta": value_delta,
            "mtm": mtm, "trade": trade, "change_type": ct,
            "is_reclass": is_reclass,
            "is_ai": is_ai, "ai_bucket": bucket,
            "basket": prim,
            "also_in": theme_memberships(theme_idx, ticker, prim) if ticker else [],
            "theme": theme_col,
            "cum_return": trig._f(lc.get("cum_return_from_entry_pct")),
        }
        (holdings if st == "COMMON" else options).append(row)
    holdings.sort(key=lambda r: r["value"], reverse=True)

    exits: list[dict[str, Any]] = []
    for c in changes:
        if c["period"] != BAKER_PERIOD or c["change_type"] != "EXIT":
            continue
        ticker = c.get("ticker") or ""
        _, trade = decompose(
            c["prior_shares"], c["prior_value_reported"],
            c["current_shares"], c["current_value_reported"], "EXIT")
        # Exited names aren't in the Q2 lifecycle; get their theme from the shared
        # ticker_classifications so they land in a real basket (not "Unassigned").
        ex_theme = (tclass.get(ticker, {}).get("theme")
                    or tclass.get(ticker, {}).get("bucket") or "") if ticker else ""
        is_ai, bucket = trig.resolve_ai(reclass, ticker, BAKER_FILING_DATE, ex_theme) if ticker else (False, None)
        prim = primary_basket(ticker, c["cusip"], ex_theme, overlay, overlay_cusip,
                              reclass, BAKER_FILING_DATE)
        exits.append({
            "ticker": ticker, "cusip": c["cusip"], "security_type": c["security_type"],
            "display": ticker or c["cusip"],
            "prior_value": c["prior_value_reported"], "trade": trade,
            # Q1 weight on the thesis-investable basis; COMMON only (an option exit may
            # carry the underlying's cusip and would otherwise double-count its weight).
            "wt_q1": (100.0 * (q1_val.get(c["cusip"]) or 0.0) / ex_q1)
                     if c["security_type"] == "COMMON" and c["cusip"] in q1_val else None,
            "is_ai": is_ai, "ai_bucket": bucket, "basket": prim,
        })

    spcx = next((h for h in holdings if h["ticker"] in IPO_RECLASS_TICKERS), None)
    common_total = sum(h["value"] for h in holdings)
    opt_notional = sum(o["value"] for o in options)
    return {
        "holdings": holdings, "options": options, "exits": exits,
        "theme_idx": theme_idx, "reclass": reclass, "overlay": overlay,
        "spcx_reclass_value": spcx["value"] if spcx else 0.0,
        "equity_value": common_total, "options_notional": opt_notional,
        "total_reported": common_total + opt_notional,
    }


def build_leo_context() -> dict[str, Any]:
    """Leopold's Q2 book straight from the already-computed decomposition CSV."""
    baskets = load_sa_baskets()
    rows: list[dict[str, Any]] = []
    for r in trig._read_csv(SA_CSV):
        ticker = (r["ticker"] or "").strip()
        company = (r["company"] or "").strip()
        rows.append({
            "ticker": ticker, "company": company, "display": ticker or company,
            "security_type": r["security_type"], "status": r["status"],
            "q1_shares": trig._f(r["q1_shares"]), "q2_shares": trig._f(r["q2_shares"]),
            "share_delta": trig._f(r["share_delta"]), "share_delta_pct": trig._f(r["share_delta_pct"]),
            "q1_value": trig._f(r["q1_value"]), "q2_value": trig._f(r["q2_value"]),
            "value_delta": trig._f(r["value_delta"]),
            "mtm": trig._f(r["mtm_component"]), "trade": trig._f(r["trading_component"]),
            "recon_gap": trig._f(r["recon_gap"]), "note": r.get("note", ""),
            "basket": sa_basket_for(baskets, ticker, company),
        })
    common = [r for r in rows if r["security_type"] == "COMMON"]
    options = [r for r in rows if r["security_type"] in ("PUT", "CALL")]
    equity_value = sum(r["q2_value"] or 0.0 for r in common)
    return {
        "rows": rows, "common": common, "options": options,
        "baskets": baskets, "equity_value": equity_value,
    }


def write_baker_decomp_csv(ctx: dict[str, Any], path: Path) -> None:
    """Baker's Q2 MTM-vs-trading decomposition as a flat CSV — parity with
    analysis/sa_q2_2026_mtm_vs_trading.csv, for auditing the split outside Excel."""
    fields = ["ticker", "company", "security_type", "change_type",
              "prior_shares", "current_shares", "shares_delta", "shares_delta_pct",
              "prior_value", "current_value", "value_delta",
              "mtm_component", "trading_component", "recon_gap", "basket"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for h in ctx["holdings"] + ctx["exits"]:
            cur_sh = h.get("shares")
            sd = h.get("shares_delta")
            cur_val = h.get("value", h.get("prior_value"))
            vd = h.get("value_delta")
            mtm = h.get("mtm") or 0.0
            trade = h.get("trade") or 0.0
            if "prior_value" in h and "value" not in h:  # exit row
                cur_val, vd = 0.0, -h["prior_value"]
            prior_sh = (cur_sh - sd) if (cur_sh is not None and sd is not None) else None
            prior_val = (cur_val - vd) if (cur_val is not None and vd is not None) else None
            recon = (vd - (mtm + trade)) if vd is not None else None
            w.writerow({
                "ticker": h.get("ticker", ""), "company": h.get("company", ""),
                "security_type": h["security_type"], "change_type": h.get("change_type", "EXIT"),
                "prior_shares": prior_sh, "current_shares": cur_sh, "shares_delta": sd,
                "shares_delta_pct": h.get("shares_delta_pct"),
                "prior_value": prior_val, "current_value": cur_val, "value_delta": vd,
                "mtm_component": round(mtm), "trading_component": round(trade),
                "recon_gap": round(recon) if recon is not None else "",
                "basket": h.get("basket", ""),
            })


def latest_thesis_for(theses: list[dict[str, Any]], tickers: set[str], cutoff: str) -> dict[str, Any] | None:
    """Most recent thesis (on/before cutoff) whose direct/subject tickers intersect
    the basket's tickers. Used for the Flow-of-Funds thesis-to-action cross-reference."""
    hits = [
        t for t in theses
        if t.get("date", "") <= cutoff
        and tickers & (set(t.get("tickers_direct", [])) | set(t.get("tickers_subject", [])))
    ]
    return max(hits, key=lambda t: t["date"]) if hits else None


# --------------------------------------------------------------------------
# Context-sheet cell/layout helpers
# --------------------------------------------------------------------------


def _headers(ws: Worksheet, headers: list[str], widths: list[float], freeze_cols: int = 1) -> None:
    for c, h in enumerate(headers, 1):
        cell = ws.cell(1, c, h)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"{get_column_letter(freeze_cols + 1)}2"


def _put_dollars(ws: Worksheet, row: int, col: int, v: float | None, signed: bool = False) -> None:
    if v is None:
        return
    cell = ws.cell(row, col, round(v))
    cell.number_format = SIGNED_DOLLAR_FMT if signed else DOLLAR_FMT
    if signed:
        if v > 0:
            cell.fill = GREEN
        elif v < 0:
            cell.fill = RED


def _put_pct(ws: Worksheet, row: int, col: int, pct: float | None, fmt: str = ALLOC_FMT) -> None:
    _put_weight(ws, row, col, pct, fmt)


def _section(ws: Worksheet, row: int, span: int, text: str) -> None:
    cell = ws.cell(row, 1, text)
    cell.font = SECTION_FONT
    for c in range(1, span + 1):
        ws.cell(row, c).fill = SECTION_FILL


# --------------------------------------------------------------------------
# Baker context sheets
# --------------------------------------------------------------------------

HOLDINGS_HEADERS = [
    "ticker", "company", "shares", "market_value",
    "wt_Q1%", "wt_Q2%", "Δwt_pp", "wt_book%",
    "shares_Δ", "shares_Δ%", "value_Δ$", "MTM_$", "Trading_$", "decomp",
    "change_type", "basket", "also_in", "theme", "cum_ret%",
]
HOLDINGS_WIDTHS: list[float] = [10, 30, 13, 16, 9, 9, 9, 9, 13, 10, 15, 15, 15,
                                14, 20, 28, 40, 20, 10]


def sheet_baker_holdings(ws: Worksheet, ctx: dict[str, Any]) -> None:
    _headers(ws, HOLDINGS_HEADERS, HOLDINGS_WIDTHS, freeze_cols=2)
    for row, h in enumerate(ctx["holdings"], 2):
        ws.cell(row, 1, h["ticker"])
        ws.cell(row, 2, h["company"])
        ws.cell(row, 3, h["shares"]).number_format = DOLLAR_FMT
        _put_dollars(ws, row, 4, h["value"])
        _put_pct(ws, row, 5, h["wt_q1"])
        _put_pct(ws, row, 6, h["wt_q2"])
        _put_pct(ws, row, 7, h["wt_delta_pp"], RET_FMT)
        # shade the allocation-change cell like the other signed columns
        d = h["wt_delta_pp"]
        if d is not None:
            dcell = ws.cell(row, 7)
            if d > 0.05:
                dcell.fill = GREEN
            elif d < -0.05:
                dcell.fill = RED
        _put_pct(ws, row, 8, h["weight_rep"])
        if h["shares_delta"] is not None:
            ws.cell(row, 9, h["shares_delta"]).number_format = SIGNED_DOLLAR_FMT
        _put_pct(ws, row, 10, h["shares_delta_pct"], RET_FMT)
        _put_dollars(ws, row, 11, h["value_delta"], signed=True)
        _put_dollars(ws, row, 12, h["mtm"], signed=True)
        _put_dollars(ws, row, 13, h["trade"], signed=True)
        ws.cell(row, 14, "IPO reclass — not a buy" if h["is_reclass"]
                else decomp_label(h["mtm"], h["trade"], h["change_type"]))
        ws.cell(row, 15, h["change_type"])
        ws.cell(row, 16, h["basket"])
        ws.cell(row, 17, ", ".join(h["also_in"]))
        ws.cell(row, 18, h["theme"])
        _put_pct(ws, row, 19, h["cum_return"], RET_FMT)


def sheet_baker_ai_basket(ws: Worksheet, ctx: dict[str, Any]) -> None:
    """AI/tech-infra roll-up: aggregate + trailing weight history + constituents.
    AI membership uses resolve_ai (same taxonomy as the triggers), so the total
    weight here ties to `ai_weight_current` on the trigger sheets."""
    reclass = ctx["reclass"]
    # Trailing AI-basket weight per quarter (thesis-investable basis, ex-reclass), from
    # the lifecycle view rescaled by the same factor the triggers use.
    life_rows = trig._read_csv(trig.find_views_dir() / "position_lifecycles.csv")
    scale = ex_reclass_scale_by_fd()
    hist: dict[str, float] = {}
    for p in BAKER_HISTORY_PERIODS:
        wt = 0.0
        for lr in life_rows:
            if lr["period"] != p or lr["security_type"] != "COMMON" or lr["change_type"] == "EXIT":
                continue
            if (lr.get("ticker") or "") in IPO_RECLASS_TICKERS:
                continue
            is_ai, _ = trig.resolve_ai(reclass, lr["ticker"], lr["filing_date"], lr["theme"])
            if is_ai:
                wt += (trig._f(lr["weight_pct"]) or 0.0) * scale.get(lr["filing_date"], 1.0)
        hist[p] = wt

    ai = [h for h in ctx["holdings"] if h["is_ai"]]
    ai.sort(key=lambda r: r["value"], reverse=True)
    ai_value = sum(h["value"] for h in ai)
    ai_wt = sum(h["weight_eo"] or 0.0 for h in ai)
    ai_trade = sum((h["trade"] or 0.0) for h in ai) + sum(e["trade"] for e in ctx["exits"] if e["is_ai"])
    ai_mtm = sum((h["mtm"] or 0.0) for h in ai)
    gross_buy = sum(h["trade"] for h in ai if (h["trade"] or 0.0) > 0)
    gross_sell = (sum(h["trade"] for h in ai if (h["trade"] or 0.0) < 0)
                  + sum(e["trade"] for e in ctx["exits"] if e["is_ai"]))

    ws.cell(1, 1, "AI / tech-infrastructure basket — Q2 2026").font = TITLE_FONT
    r = 3
    for label, val, money in [
        ("AI basket market value", ai_value, True),
        ("AI basket weight (ex-SPCX, thesis book)", ai_wt, False),
        ("Net trading (deliberate) $", ai_trade, True),
        ("Net mark-to-market $", ai_mtm, True),
        ("Gross AI buying $", gross_buy, True),
        ("Gross AI selling $", gross_sell, True),
    ]:
        ws.cell(r, 1, label).font = SECTION_FONT
        if money:
            _put_dollars(ws, r, 3, val, signed=True)
        else:
            _put_pct(ws, r, 3, val)
        r += 1
    ws.cell(r, 1, "Self-funded rotation: gross AI buys ≈ AI trims (Astera-funded Cerebras/CoreWeave).").font = NOTE_FONT
    r += 2

    _section(ws, r, 5, "Trailing AI-basket weight (ex-SPCX, thesis book)")
    r += 1
    for i, p in enumerate(BAKER_HISTORY_PERIODS):
        ws.cell(r, 1 + i, p).font = HEADER_FONT
        _put_pct(ws, r + 1, 1 + i, hist[p])
    r += 3

    _section(ws, r, 5, "Constituents (sorted by size)")
    r += 1
    heads = ["ticker", "company", "market_value", "wt_eq%", "MTM_$", "Trading_$", "bucket"]
    for c, h in enumerate(heads, 1):
        ws.cell(r, c, h).font = HEADER_FONT
    for w, col in zip([10, 30, 16, 10, 15, 15, 26], range(1, 8)):
        ws.column_dimensions[get_column_letter(col)].width = w
    r += 1
    for h in ai:
        ws.cell(r, 1, h["ticker"])
        ws.cell(r, 2, h["company"])
        _put_dollars(ws, r, 3, h["value"])
        _put_pct(ws, r, 4, h["weight_eo"])
        _put_dollars(ws, r, 5, h["mtm"], signed=True)
        _put_dollars(ws, r, 6, h["trade"], signed=True)
        ws.cell(r, 7, h["ai_bucket"])
        r += 1


def sheet_baker_baskets(ws: Worksheet, ctx: dict[str, Any]) -> None:
    """PRIMARY VIEW: theme-level allocation summary (Q2 wt, Q1 wt, ΔpP by basket,
    sorted by Q2 weight) — which themes Baker is adding to / trimming. SECONDARY:
    per-basket position detail below. Each ticker appears in exactly one basket; its
    other theme_baskets_v3 memberships show in the 'also_in' note, not as extra rows.
    Q1 basket weight includes since-exited names so a fully-exited theme shows its drop."""
    # Build basket -> {holdings, exits} from current holdings ∪ this quarter's exits.
    # IPO-reclass positions (SPCX) are excluded so thesis baskets sum to 100%; SPCX is
    # shown as a separate memo row (it is ~42% of equity but not a thesis capital bet).
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {}
    memo = [h for h in ctx["holdings"] if h["is_reclass"]]
    for h in ctx["holdings"]:
        if h["is_reclass"]:
            continue
        groups.setdefault(h["basket"], {"held": [], "exited": []})["held"].append(h)
    for e in ctx["exits"]:
        if e["security_type"] != "COMMON":  # option exits belong on the Options sheet
            continue
        groups.setdefault(e["basket"], {"held": [], "exited": []})["exited"].append(e)

    def wt_q2(b: str) -> float:
        return sum(m["weight_eo"] or 0.0 for m in groups[b]["held"])

    def wt_q1(b: str) -> float:
        return (sum(m["wt_q1"] or 0.0 for m in groups[b]["held"])
                + sum(m["wt_q1"] or 0.0 for m in groups[b]["exited"]))

    order = sorted(groups, key=lambda b: (b == "Unassigned", -wt_q2(b)))

    # ---- PRIMARY: theme allocation summary ----
    ws.cell(1, 1, "Baker — theme allocation (Q2 2026), % of thesis-investable equity "
            "(ex-SPCX), sorted by current weight").font = TITLE_FONT
    sum_heads = ["basket", "wt_Q2%", "wt_Q1%", "Δwt_pp", "# held", "net_trade_$"]
    sum_widths: list[float] = [40, 10, 10, 10, 8, 16]
    for i, w in enumerate(sum_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 3
    for c, hd in enumerate(sum_heads, 1):
        cell = ws.cell(r, c, hd)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
    r += 1
    for name in order:
        q2, q1 = wt_q2(name), wt_q1(name)
        d = q2 - q1
        tot_trade = (sum(m["trade"] or 0.0 for m in groups[name]["held"])
                     + sum(m["trade"] or 0.0 for m in groups[name]["exited"]))
        ws.cell(r, 1, name)
        _put_pct(ws, r, 2, q2)
        _put_pct(ws, r, 3, q1)
        _put_pct(ws, r, 4, d, RET_FMT)
        dc = ws.cell(r, 4)
        if d > 0.05:
            dc.fill = GREEN
        elif d < -0.05:
            dc.fill = RED
        ws.cell(r, 5, len(groups[name]["held"]))
        _put_dollars(ws, r, 6, tot_trade, signed=True)
        r += 1
    # Memo: IPO-reclass positions, shown as % of TOTAL equity, excluded from the above.
    for m in memo:
        cell = ws.cell(r, 1, f"[memo] {m['basket']} — SPCX (IPO reclass)")
        cell.fill = CALLOUT_FILL
        c2 = ws.cell(r, 2, m["wt_q2"] / 100.0)
        c2.number_format = ALLOC_FMT
        c2.fill = CALLOUT_FILL
        ws.cell(r, 5, 1).fill = CALLOUT_FILL
        r += 1
    ws.cell(r, 1, "Weights are % of thesis-investable equity (COMMON ex IPO-reclass), the same "
            "basis as the triggers. [memo] SPCX = % of TOTAL equity. Δwt includes since-exited "
            "names in Q1; SPCX excluded from net_trade.").font = NOTE_FONT
    r += 3

    # ---- SECONDARY: per-basket position detail ----
    _section(ws, r, 9, "POSITION DETAIL BY BASKET")
    r += 2
    heads = ["ticker", "company", "market_value", "wt_eq%", "Δwt_pp",
             "value_Δ$", "Trading_$", "change", "also_in (other theses)"]
    det_widths: list[float] = [10, 30, 16, 9, 9, 15, 15, 20, 44]
    for i, w in enumerate(det_widths, 1):
        cur = ws.column_dimensions[get_column_letter(i)].width
        if not cur or w > cur:
            ws.column_dimensions[get_column_letter(i)].width = w
    for name in order:
        members = sorted(groups[name]["held"], key=lambda x: x["value"], reverse=True)
        exited = sorted(groups[name]["exited"], key=lambda x: x["prior_value"], reverse=True)
        _section(ws, r, len(heads),
                 f"{name}   —   wt {wt_q2(name):.1f}% (Q1 {wt_q1(name):.1f}%, "
                 f"Δ {wt_q2(name)-wt_q1(name):+.1f}pp) · {len(members)} held"
                 + (f" · {len(exited)} exited" if exited else ""))
        r += 1
        for c, hd in enumerate(heads, 1):
            ws.cell(r, c, hd).font = HEADER_FONT
        r += 1
        for m in members:
            ws.cell(r, 1, m["display"])
            ws.cell(r, 2, m["company"])
            _put_dollars(ws, r, 3, m["value"])
            _put_pct(ws, r, 4, m["weight_eo"])
            _put_pct(ws, r, 5, m["wt_delta_pp"], RET_FMT)
            _put_dollars(ws, r, 6, m["value_delta"], signed=True)
            _put_dollars(ws, r, 7, m["trade"], signed=True)
            ws.cell(r, 8, m["change_type"])
            ws.cell(r, 9, ", ".join(m["also_in"]))
            r += 1
        for e in exited:
            ws.cell(r, 1, e["display"])
            ws.cell(r, 2, "")
            _put_dollars(ws, r, 3, 0.0)
            _put_pct(ws, r, 4, 0.0)
            _put_pct(ws, r, 5, -(e["wt_q1"] or 0.0), RET_FMT)
            _put_dollars(ws, r, 6, -e["prior_value"], signed=True)
            _put_dollars(ws, r, 7, e["trade"], signed=True)
            ws.cell(r, 8, "EXIT")
            r += 1
        r += 1  # blank separator row between baskets


def sheet_baker_flows(ws: Worksheet, ctx: dict[str, Any]) -> None:
    """Net buying vs selling by the single primary basket + thesis-to-action cross-
    reference. Same one-basket-per-ticker attribution as the Holdings/Baskets sheets,
    so all three agree; flows sum to the book (SPCX reclassification excluded)."""
    theses = _load_json(THESIS_PATH)
    agg: dict[str, dict[str, float]] = {}
    members: dict[str, set[str]] = {}
    for h in ctx["holdings"]:
        b = h["basket"]
        a = agg.setdefault(b, {"trade": 0.0, "mtm": 0.0, "buy": 0.0, "sell": 0.0})
        t = h["trade"] or 0.0
        a["trade"] += t
        a["mtm"] += h["mtm"] or 0.0
        a["buy" if t > 0 else "sell"] += t
        members.setdefault(b, set()).add(h["ticker"])
    for e in ctx["exits"]:
        if e["security_type"] != "COMMON":  # keep equity flows separate from options
            continue
        b = e["basket"]
        a = agg.setdefault(b, {"trade": 0.0, "mtm": 0.0, "buy": 0.0, "sell": 0.0})
        a["trade"] += e["trade"]
        a["sell"] += e["trade"]
        members.setdefault(b, set()).add(e["ticker"])

    heads = ["basket", "net_trade_$", "net_MTM_$", "gross_buy_$", "gross_sell_$",
             "latest_thesis (date · conf)", "thesis_summary", "align?", "manual_note"]
    widths: list[float] = [30, 15, 15, 15, 15, 26, 60, 12, 24]
    _headers(ws, heads, widths, freeze_cols=1)
    ws.cell(1, 7).alignment = LEFT
    order = sorted(agg, key=lambda b: agg[b]["trade"], reverse=True)
    for row, b in enumerate(order, 2):
        a = agg[b]
        ws.cell(row, 1, b)
        _put_dollars(ws, row, 2, a["trade"], signed=True)
        _put_dollars(ws, row, 3, a["mtm"], signed=True)
        _put_dollars(ws, row, 4, a["buy"], signed=True)
        _put_dollars(ws, row, 5, a["sell"], signed=True)
        th = latest_thesis_for(theses, members.get(b, set()), BAKER_FILING_DATE)
        if th is not None:
            ws.cell(row, 6, f"{th['date']} · {th.get('confidence', '')}")
            summ = th.get("summary", "")
            ws.cell(row, 7, summ[:200]).alignment = WRAP
            ws.cell(row, 8, _align_flag(a["trade"], th))
        else:
            ws.cell(row, 8, "manual")  # no ticker-tagged thesis; use the manual column
        ws.cell(row, 9, "")  # manual override, intentionally blank


def _align_flag(net_trade: float, thesis: dict[str, Any]) -> str:
    """Heuristic thesis-to-action flag (eyeball, don't trust blindly): recent
    conviction thesis + net buying -> ALIGNS; conviction + net selling -> CHECK."""
    conf = thesis.get("confidence", "")
    recent = thesis.get("date", "") >= "2025-06-30"
    if not recent or conf not in ("high_conviction", "moderate"):
        return "NEUTRAL"
    if abs(net_trade) < 5e6:
        return "NEUTRAL"
    return "ALIGNS" if net_trade > 0 else "CHECK (sold)"


def sheet_baker_options(ws: Worksheet, ctx: dict[str, Any]) -> None:
    heads = ["underlying", "company", "put/call", "notional_$", "shares_underlying", "change_type", "direction"]
    widths: list[float] = [12, 30, 10, 16, 16, 14, 30]
    _headers(ws, heads, widths, freeze_cols=1)
    ws.cell(1, 7).alignment = LEFT
    opts = sorted(ctx["options"], key=lambda o: o["value"], reverse=True)
    for row, o in enumerate(opts, 2):
        ws.cell(row, 1, o["display"])
        ws.cell(row, 2, o["company"])
        ws.cell(row, 3, o["put_call"])
        _put_dollars(ws, row, 4, o["value"])
        ws.cell(row, 5, o["shares"]).number_format = DOLLAR_FMT
        ws.cell(row, 6, o["change_type"])
        pc = (o["put_call"] or o["security_type"]).upper()
        ws.cell(row, 7, "downside hedge / bearish" if pc == "PUT" else
                "upside / bullish" if pc == "CALL" else "")
    note = len(opts) + 3
    ws.cell(note, 1, "Notional = underlying market value, not premium/capital-at-risk. "
            "Options are a directional signal only and are excluded from equity weights.").font = NOTE_FONT


def sheet_baker_exits_new(ws: Worksheet, ctx: dict[str, Any]) -> None:
    # Genuine NEW positions exclude IPO reclassifications (SPCX), which are broken out
    # separately below — they are not fresh Q2 capital deployment.
    news = sorted((h for h in ctx["holdings"]
                   if h["change_type"] == "NEW" and not h["is_reclass"]),
                  key=lambda h: h["value"], reverse=True)
    reclass_rows = sorted((h for h in ctx["holdings"] if h["is_reclass"]),
                          key=lambda h: h["value"], reverse=True)
    exits = sorted(ctx["exits"], key=lambda e: e["prior_value"], reverse=True)
    heads = ["ticker", "company_or_cusip", "market_value", "wt_eq%", "basket", "AI?"]
    widths: list[float] = [12, 30, 16, 10, 34, 6]
    _headers(ws, heads, widths, freeze_cols=1)
    r = 2
    _section(ws, r, len(heads), f"NEW positions (genuine buys) — {len(news)}")
    r += 1
    for h in news:
        ws.cell(r, 1, h["ticker"] or h["cusip"])
        ws.cell(r, 2, h["company"])
        _put_dollars(ws, r, 3, h["value"])
        _put_pct(ws, r, 4, h["weight_eo"])
        ws.cell(r, 5, h["basket"])
        ws.cell(r, 6, "AI" if h["is_ai"] else "")
        r += 1
    r += 1
    _section(ws, r, len(heads),
             f"IPO reclassification — {len(reclass_rows)} (entered the 13F at IPO, NOT a Q2 buy)")
    for row_h in reclass_rows:
        r += 1
        cell = ws.cell(r, 1, row_h["ticker"] or row_h["cusip"])
        cell.fill = CALLOUT_FILL
        ws.cell(r, 2, row_h["company"]).fill = CALLOUT_FILL
        _put_dollars(ws, r, 3, row_h["value"])
        _put_pct(ws, r, 4, row_h["weight_eo"])
        ws.cell(r, 5, row_h["basket"])
        ws.cell(r, 6, "AI" if row_h["is_ai"] else "")
    r += 2
    _section(ws, r, len(heads), f"EXIT positions — {len(exits)} (size = prior-quarter value)")
    r += 1
    for e in exits:
        ws.cell(r, 1, e["ticker"] or e["cusip"])
        ws.cell(r, 2, e["cusip"] if e["ticker"] else "")
        _put_dollars(ws, r, 3, e["prior_value"])
        ws.cell(r, 4, "")
        ws.cell(r, 5, e["basket"])
        ws.cell(r, 6, "AI" if e["is_ai"] else "")
        r += 1


# --------------------------------------------------------------------------
# Leopold context sheets (from the SA decomposition CSV)
# --------------------------------------------------------------------------


def sheet_leo_holdings(ws: Worksheet, ctx: dict[str, Any]) -> None:
    heads = ["ticker", "company", "shares", "market_value", "wt%", "shares_Δ",
             "shares_Δ%", "value_Δ$", "MTM_$", "Trading_$", "status", "basket"]
    widths: list[float] = [10, 30, 14, 16, 8, 14, 10, 15, 15, 15, 14, 28]
    _headers(ws, heads, widths, freeze_cols=2)
    eq = ctx["equity_value"] or 1.0
    common = sorted(ctx["common"], key=lambda r: r["q2_value"] or 0.0, reverse=True)
    for row, h in enumerate(common, 2):
        ws.cell(row, 1, h["ticker"])
        ws.cell(row, 2, h["company"])
        if h["q2_shares"] is not None:
            ws.cell(row, 3, round(h["q2_shares"])).number_format = DOLLAR_FMT
        _put_dollars(ws, row, 4, h["q2_value"])
        _put_pct(ws, row, 5, 100.0 * (h["q2_value"] or 0.0) / eq)
        if h["share_delta"] is not None:
            ws.cell(row, 6, round(h["share_delta"])).number_format = SIGNED_DOLLAR_FMT
        _put_pct(ws, row, 7, h["share_delta_pct"], RET_FMT)
        _put_dollars(ws, row, 8, h["value_delta"], signed=True)
        _put_dollars(ws, row, 9, h["mtm"], signed=True)
        _put_dollars(ws, row, 10, h["trade"], signed=True)
        ws.cell(row, 11, h["status"])
        ws.cell(row, 12, h["basket"] or "")


def sheet_leo_baskets(ws: Worksheet, ctx: dict[str, Any]) -> None:
    widths: list[float] = [10, 30, 16, 8, 15, 15, 15, 14]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    heads = ["ticker", "company", "market_value", "wt%", "value_Δ$", "MTM_$", "Trading_$", "status"]
    eq = ctx["equity_value"] or 1.0
    r = 1
    assigned: set[str] = set()
    for name, _v in ctx["baskets"]:
        members = [h for h in ctx["common"] if h["basket"] == name and (h["q2_value"] or 0.0) > 0]
        if not members:
            continue
        members.sort(key=lambda x: x["q2_value"] or 0.0, reverse=True)
        for m in members:
            assigned.add(m["display"])
        tot_val = sum(m["q2_value"] or 0.0 for m in members)
        tot_trade = sum(m["trade"] or 0.0 for m in members)
        _section(ws, r, len(heads), f"{name}  —  {len(members)} held · {tot_val/1e6:,.0f}M · "
                 f"net trade {tot_trade/1e6:+,.0f}M")
        r += 1
        for c, h in enumerate(heads, 1):
            ws.cell(r, c, h).font = HEADER_FONT
        r += 1
        for m in members:
            ws.cell(r, 1, m["ticker"])
            ws.cell(r, 2, m["company"])
            _put_dollars(ws, r, 3, m["q2_value"])
            _put_pct(ws, r, 4, 100.0 * (m["q2_value"] or 0.0) / eq)
            _put_dollars(ws, r, 5, m["value_delta"], signed=True)
            _put_dollars(ws, r, 6, m["mtm"], signed=True)
            _put_dollars(ws, r, 7, m["trade"], signed=True)
            ws.cell(r, 8, m["status"])
            r += 1
        r += 1
    unassigned = [h for h in ctx["common"] if h["basket"] is None and (h["q2_value"] or 0.0) > 0]
    if unassigned:
        _section(ws, r, len(heads), f"UNASSIGNED — {len(unassigned)} positions")
        r += 1
        for h in sorted(unassigned, key=lambda x: x["q2_value"] or 0.0, reverse=True):
            ws.cell(r, 1, h["display"])
            ws.cell(r, 2, h["company"])
            _put_dollars(ws, r, 3, h["q2_value"])
            r += 1


def sheet_leo_flows(ws: Worksheet, ctx: dict[str, Any]) -> None:
    agg: dict[str, dict[str, float]] = {}
    for h in ctx["common"]:
        b = h["basket"] or "Unassigned"
        a = agg.setdefault(b, {"trade": 0.0, "mtm": 0.0, "buy": 0.0, "sell": 0.0})
        t = h["trade"] or 0.0
        a["trade"] += t
        a["mtm"] += h["mtm"] or 0.0
        a["buy" if t > 0 else "sell"] += t
    heads = ["basket", "net_trade_$", "net_MTM_$", "gross_buy_$", "gross_sell_$", "thesis_note (manual)"]
    widths: list[float] = [30, 15, 15, 15, 15, 40]
    _headers(ws, heads, widths, freeze_cols=1)
    for row, b in enumerate(sorted(agg, key=lambda x: agg[x]["trade"], reverse=True), 2):
        a = agg[b]
        ws.cell(row, 1, b)
        _put_dollars(ws, row, 2, a["trade"], signed=True)
        _put_dollars(ws, row, 3, a["mtm"], signed=True)
        _put_dollars(ws, row, 4, a["buy"], signed=True)
        _put_dollars(ws, row, 5, a["sell"], signed=True)
        ws.cell(row, 6, "")
    note = len(agg) + 3
    ws.cell(note, 1, "No Leopold thesis corpus in-repo; seed the manual column from "
            "situational_awareness_q2_2026_liquidation_analysis.md.").font = NOTE_FONT


# --------------------------------------------------------------------------
# Summary dashboard (two managers side by side) + SpaceX IPO callout
# --------------------------------------------------------------------------


def _top_n_concentration(values: list[float], total: float, n: int = 10) -> float:
    top = sum(sorted(values, reverse=True)[:n])
    return 100.0 * top / total if total else 0.0


def sheet_summary(ws: Worksheet, baker: dict[str, Any], leo: dict[str, Any]) -> None:
    ws.cell(1, 1, "Q2 2026 13F — two-manager snapshot").font = TITLE_FONT
    ws.cell(2, 1, "Baker = Atreides Management  ·  Leopold = Situational Awareness  ·  filing-date marks").font = NOTE_FONT

    # Baker aggregates. SPCX carries trade=None (IPO reclassification), so these sums
    # already EXCLUDE it — b_net_trade is the true ex-SpaceX market flow.
    bh = baker["holdings"]
    b_new = [h for h in bh if h["change_type"] == "NEW" and not h["is_reclass"]]
    b_net_trade_ex = sum(h["trade"] or 0.0 for h in bh) + sum(e["trade"] for e in baker["exits"])
    b_net_mtm = sum(h["mtm"] or 0.0 for h in bh)
    spcx = next((h for h in bh if h["is_reclass"]), None)
    spcx_value = baker["spcx_reclass_value"]
    b_net_trade_asfiled = b_net_trade_ex + spcx_value  # add SPCX back as if it were a buy
    b_ai_wt = sum(h["weight_eo"] or 0.0 for h in bh if h["is_ai"])

    # Leopold aggregates
    lc = leo["common"]
    l_new = [h for h in lc if h["status"] == "NEW"]
    l_exit = [h for h in leo["rows"] if h["status"] == "CLOSED/EXIT" and h["security_type"] == "COMMON"]
    l_net_trade = sum(h["trade"] or 0.0 for h in lc)
    l_net_mtm = sum(h["mtm"] or 0.0 for h in lc)

    for c, w in zip(range(1, 5), [34, 22, 6, 22]):
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.cell(4, 2, "Baker (Atreides)").font = HEADER_FONT
    ws.cell(4, 4, "Leopold (Sit. Awareness)").font = HEADER_FONT

    def money(row: int, label: str, bval: float | None, lval: float | None, signed: bool = False) -> None:
        ws.cell(row, 1, label)
        _put_dollars(ws, row, 2, bval, signed=signed)
        _put_dollars(ws, row, 4, lval, signed=signed)

    def pct(row: int, label: str, bval: float | None, lval: float | None) -> None:
        ws.cell(row, 1, label)
        _put_pct(ws, row, 2, bval)
        _put_pct(ws, row, 4, lval)

    def num(row: int, label: str, bval: Any, lval: Any) -> None:
        ws.cell(row, 1, label)
        ws.cell(row, 2, bval)
        ws.cell(row, 4, lval)

    money(5, "Equity book value", baker["equity_value"], leo["equity_value"])
    money(6, "Options notional", baker["options_notional"], None)
    num(7, "# equity positions", len(bh), len(lc))
    pct(8, "Top-10 concentration (equity)",
        _top_n_concentration([h["value"] for h in bh], baker["equity_value"]),
        _top_n_concentration([h["q2_value"] or 0.0 for h in lc], leo["equity_value"]))
    pct(9, "AI basket weight (ex-SPCX, thesis book)", b_ai_wt, None)
    money(10, "Net trading, ex-IPO reclass $", b_net_trade_ex, l_net_trade, signed=True)
    money(11, "Net mark-to-market $", b_net_mtm, l_net_mtm, signed=True)
    num(12, "# NEW (genuine) / # EXIT", f"{len(b_new)} / {len(baker['exits'])}",
        f"{len(l_new)} / {len(l_exit)}")

    # --- SpaceX IPO callout (Baker) ---
    r = 14
    ws.cell(r, 1, "⚠ SpaceX (SPCX) IPO disclosure — read before the ramp number").font = SECTION_FONT
    for c in range(1, 5):
        ws.cell(r, c).fill = CALLOUT_FILL
    lines = [
        f"SPCX is a ${spcx_value/1e9:,.2f}B position "
        f"({(spcx['weight_rep'] if spcx else 0):.1f}% of the book) labeled IPO_RECLASSIFICATION — it "
        "entered the 13F because SpaceX IPO'd in Q2 2026, converting a pre-existing private holding",
        "into a reportable security. It was NOT freshly bought in the market, so it is excluded from "
        "every net-buying total on these sheets (Holdings, Baskets, Flows).",
        f"Net trading AS-FILED (SPCX counted as a buy):   ${b_net_trade_asfiled/1e9:,.2f}B",
        f"Net trading EX-SpaceX (true market flow):   ${b_net_trade_ex/1e9:,.2f}B  "
        f"→ {'net BUYER' if b_net_trade_ex > 0 else 'net SELLER'} once SPCX is stripped.",
        "Ex-SpaceX, the AI book was self-funded (sold Astera −$1.04B to fund Cerebras/CoreWeave/"
        "Amphenol); genuinely new capital went to SPCX + the QQQ hedge, not the AI names.",
    ]
    for i, ln in enumerate(lines, 1):
        cell = ws.cell(r + i, 1, ln)
        cell.font = NOTE_FONT if i <= 2 or i == 5 else HEADER_FONT
        cell.alignment = LEFT
        ws.merge_cells(start_row=r + i, start_column=1, end_row=r + i, end_column=4)


# --------------------------------------------------------------------------
# Performance — forward-returns read on the corrected trigger set
# --------------------------------------------------------------------------

PERF_HEADERS = [
    "trigger", "horizon", "n", "win_rate", "avg_return", "median_return",
    "excess_vs_SMH", "beat_SMH", "excess_vs_SPY", "beat_SPY",
]
PERF_WIDTHS: list[float] = [30, 8, 5, 9, 10, 11, 12, 9, 12, 9]


def _perf_num(cell: Any, val: str) -> None:
    """Green/red shade a signed percent string like '+4.4%' / '-1.0%'."""
    if val.startswith("+") and val not in ("+0.0%",):
        cell.fill = GREEN
    elif val.startswith("-"):
        cell.fill = RED


def sheet_performance(ws: Worksheet, rows: list[dict[str, Any]], last: str) -> None:
    """Does the corrected signal make money? Filing-anchored buy-and-hold returns at
    1m/1q/6m/1y/2y vs SMH and SPY, per trigger type. Same ex-SPCX event set as the
    trigger sheets; equal-weight baskets; an event counts only once its window is fully
    observed. Right-skewed — read median alongside average."""
    ws.cell(1, 1, "Does the signal make money? — forward returns on the corrected "
            "(ex-SPCX) trigger set").font = TITLE_FONT
    ws.cell(2, 1, f"Filing-date-anchored, buy-and-hold, equal-weight baskets · prices through "
            f"{last} · excess = signal − benchmark over the same window").font = NOTE_FONT
    for i, w in enumerate(PERF_WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    r = 4
    for c, h in enumerate(PERF_HEADERS, 1):
        cell = ws.cell(r, c, h)
        cell.font = HEADER_FONT
        cell.alignment = CENTER
    ws.freeze_panes = "A5"
    r += 1
    for row in rows:
        band = row["trigger_type"] == "ALL_TRIGGERS"
        if row["horizon"] == "1m":  # separate each trigger block
            r += 1
        ws.cell(r, 1, row["trigger_type"])
        ws.cell(r, 2, row["horizon"])
        ws.cell(r, 3, row["n"])
        for col, key in ((4, "win_rate"), (5, "avg_return"), (6, "median_return"),
                         (7, "avg_excess_smh"), (8, "beat_smh_rate"),
                         (9, "avg_excess_spy"), (10, "beat_spy_rate")):
            cell = ws.cell(r, col, row[key])
            cell.alignment = CENTER
            if key in ("avg_return", "median_return", "avg_excess_smh", "avg_excess_spy"):
                _perf_num(cell, row[key])
            if band:
                cell.font = HEADER_FONT
        if band:
            ws.cell(r, 1).font = HEADER_FONT
            ws.cell(r, 2).font = HEADER_FONT
            ws.cell(r, 3).font = HEADER_FONT
        r += 1
    r += 1
    for note in [
        "Tradeable basket: NewPosition=named ticker; NewSubtheme=entering tickers; "
        "Cross=all subtheme tickers; Ramp=narrow AI picks-and-shovels basket held that filing.",
        "Read: beats SPY at every horizon; vs SMH the edge is thin (beat-rate < 50% at most "
        "horizons) — largely AI-beta. AI_BASKET_RAMP (deliberate deployment) is the only trigger "
        "that beats SMH consistently. Single-regime (2020–26 AI bull); avg ≫ median (right-skew).",
    ]:
        ws.cell(r, 1, note).font = NOTE_FONT
        r += 1


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def _by_type(rows: list[dict[str, str]], ttype: str) -> list[dict[str, str]]:
    return sorted((r for r in rows if r["trigger_type"] == ttype),
                  key=lambda r: r["filing_date"])


def main() -> int:
    ret, ticker_alloc, subtheme_alloc, filings = build_lookups()
    fidx = {d: i for i, d in enumerate(filings)}
    rows = trig._read_csv(TRIGGERS_IN)

    wb = Workbook()
    wb.remove(wb.active)  # drop the default sheet

    # --- Context sheets first (foundation), triggers after ---
    baker = build_baker_context()
    leo = build_leo_context()
    write_baker_decomp_csv(baker, ANALYSIS_DIR / "atreides_q2_2026_mtm_vs_trading.csv")
    sheet_summary(wb.create_sheet("Summary"), baker, leo)
    perf_rows, perf_last = fr.compute_stats()
    sheet_performance(wb.create_sheet("Performance"), perf_rows, perf_last)
    sheet_baker_holdings(wb.create_sheet("Baker Holdings"), baker)
    sheet_baker_ai_basket(wb.create_sheet("Baker AI Basket"), baker)
    sheet_baker_baskets(wb.create_sheet("Baker Baskets"), baker)
    sheet_baker_flows(wb.create_sheet("Baker Flows"), baker)
    sheet_baker_options(wb.create_sheet("Baker Options"), baker)
    sheet_baker_exits_new(wb.create_sheet("Baker Exits+New"), baker)
    sheet_leo_holdings(wb.create_sheet("Leo Holdings"), leo)
    sheet_leo_baskets(wb.create_sheet("Leo Baskets"), leo)
    sheet_leo_flows(wb.create_sheet("Leo Flows"), leo)

    sheet_ramp(wb.create_sheet("Ramp"),
               _by_type(rows, "AI_BASKET_RAMP"), ret, filings, fidx)
    sheet_new_subtheme(wb.create_sheet("NewSubtheme"),
                       _by_type(rows, "NEW_AI_SUBTHEME"), ret, subtheme_alloc, filings, fidx)
    sheet_new_position(wb.create_sheet("NewPosition"),
                       _by_type(rows, "NEW_AI_POSITION_2PCT"), ret, ticker_alloc, filings, fidx)
    sheet_cross(wb.create_sheet("Cross4pct"),
                _by_type(rows, "AI_SUBTHEME_ACTIVE_CROSS_4PCT"), ret, subtheme_alloc, filings, fidx)
    sheet_cross(wb.create_sheet("Cross2pct"),
                _by_type(rows, "AI_SUBTHEME_ACTIVE_CROSS_2PCT"), ret, subtheme_alloc, filings, fidx)
    sheet_ramp_basket(wb.create_sheet("RampBasket"),
                      _by_type(rows, "AI_BASKET_RAMP"), ret, build_ramp_holdings(), filings, fidx)

    wb.save(OUT_PATH)
    counts = {ws.title: ws.max_row - 1 for ws in wb.worksheets}
    print(f"Wrote {OUT_PATH.relative_to(trig.REPO_ROOT)}")
    for title, n in counts.items():
        print(f"  {title}: {n} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
