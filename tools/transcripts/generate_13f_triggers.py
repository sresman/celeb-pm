#!/usr/bin/env python3
"""Generate auditable 13F AI-signal trigger events from the existing pipeline views.

Reads Gavin Baker's (Atreides, CIK 0001777813) position-lifecycle and new-idea view
CSVs plus analysis/ai_basket_reclassification.json, and emits every instance of three
triggers to analysis/13f_signal_triggers.csv:

    AI_BASKET_RAMP        total AI-basket equity weight rose >= 5.0 pt filing-to-filing
    NEW_AI_SUBTHEME       first-ever entry into a resolved AI sub-theme
    NEW_AI_POSITION_2PCT  new equity AI position opened at >= 2.0% initial weight

Purely derived from committed pipeline output — no API calls, no external data. Every
event row carries supporting fields so it can be verified against the source CSVs.

Usage:
    python tools/transcripts/generate_13f_triggers.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = REPO_ROOT / "analysis"
RECLASS_PATH = ANALYSIS_DIR / "ai_basket_reclassification.json"
OUTPUT_PATH = ANALYSIS_DIR / "13f_signal_triggers.csv"

RAMP_THRESHOLD_PT = 5.0
NEW_POSITION_MIN_WEIGHT_PCT = 2.0
SUBSEQUENT_ADD_WINDOW = 2  # number of subsequent filings to scan for adds
AI_THEME_PREFIXES = ("AI/", "Semiconductor")

# Union of every column any trigger emits; unused cells are left blank per trigger.
COLUMNS = [
    "trigger_type", "filing_date", "quarter",
    # AI_BASKET_RAMP
    "ai_weight_prior", "ai_weight_current", "ai_weight_change",
    "total_portfolio_weight", "ai_positions_count",
    "new_ai_entries_this_quarter", "ai_adds_this_quarter", "ai_exits_this_quarter",
    "top_5_ai_positions",
    # NEW_AI_SUBTHEME
    "subtheme", "entering_tickers", "entering_weights", "total_subtheme_weight",
    "subsequent_add", "subsequent_add_tickers", "quarters_held",
    # NEW_AI_POSITION_2PCT
    "ticker", "company", "theme", "initial_weight_pct", "became_active_add",
    "filing_to_filing_return_pct", "max_weight_pct", "exit_date",
    "cumulative_return_pct",
]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def find_views_dir() -> Path:
    """Locate the investor's views/ dir (prefer atreides), else fall back."""
    matches = sorted(REPO_ROOT.glob("data/*/views/position_lifecycles.csv"))
    for m in matches:
        if "atreides" in str(m):
            return m.parent
    if matches:
        return matches[0].parent
    fallback = REPO_ROOT / "data" / "atreides_management" / "views"
    if (fallback / "position_lifecycles.csv").exists():
        return fallback
    raise SystemExit("Could not locate position_lifecycles.csv under data/*/views/")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(value: str | None) -> float | None:
    s = (value or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt(value: float | None, nd: int = 2) -> str:
    return "" if value is None else f"{value:.{nd}f}"


# --------------------------------------------------------------------------
# AI classification (single shared resolver)
# --------------------------------------------------------------------------


def _pick_segment(segments: list[dict[str, Any]], filing_date: str) -> dict[str, Any]:
    """Choose the date-segment matching filing_date (ISO strings compare lexically)."""
    chosen: dict[str, Any] | None = None
    for seg in segments:
        if "before" in seg and filing_date < seg["before"]:
            chosen = seg
        elif "after" in seg and filing_date >= seg["after"]:
            chosen = seg
    return chosen if chosen is not None else segments[-1]


def resolve_ai(
    reclass: dict[str, Any], ticker: str, filing_date: str, theme_col: str
) -> tuple[bool, str | None]:
    """Return (is_ai, subtheme). Reclass file is authoritative; theme column is the
    fallback for tickers not present in it.

    The pipeline emits digit-prefixed ticker variants for some listings (e.g. Confluent
    as "1CFLT", Juniper as "0JPHL"). The reclass file is keyed by clean tickers, so we
    retry the lookup with leading digits stripped; this recovers CFLT's explicit
    exclusion. US tickers never start with a digit, so the strip is safe."""
    entry = reclass.get(ticker) or reclass.get(ticker.lstrip("0123456789"))
    if entry is not None:
        if "date_segments" in entry:
            seg = _pick_segment(entry["date_segments"], filing_date)
            is_ai, bucket = bool(seg["ai"]), seg.get("bucket")
        else:
            is_ai, bucket = bool(entry["ai"]), entry.get("bucket")
        return (is_ai, bucket if is_ai else None)
    theme = (theme_col or "").strip()
    is_ai = theme.startswith(AI_THEME_PREFIXES)
    return (is_ai, theme if is_ai else None)


# --------------------------------------------------------------------------
# Trigger 1: AI_BASKET_RAMP
# --------------------------------------------------------------------------


def trigger_ai_basket_ramp(
    common: list[dict[str, Any]], filings: list[str], fd_to_period: dict[str, str]
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    prior_ai_weight: float | None = None
    for fd in filings:
        fd_rows = [r for r in common if r["filing_date"] == fd]
        non_exit = [r for r in fd_rows if r["change_type"] != "EXIT"]
        ai_rows = [r for r in non_exit if r["is_ai"]]
        ai_weight = sum(r["weight"] or 0.0 for r in ai_rows)
        total_weight = sum(r["weight"] or 0.0 for r in non_exit)

        if prior_ai_weight is not None:
            change = ai_weight - prior_ai_weight
            if change >= RAMP_THRESHOLD_PT:
                new_entries = [r["ticker"] for r in ai_rows if r["change_type"] == "NEW"]
                adds = [r["ticker"] for r in ai_rows if r["change_type"] == "ACTIVE_ADD"]
                exits = [
                    r["ticker"] for r in fd_rows
                    if r["change_type"] == "EXIT" and r["is_ai"]
                ]
                top5 = sorted(ai_rows, key=lambda r: r["weight"] or 0.0, reverse=True)[:5]
                top5_str = ", ".join(f"{r['ticker']}:{_fmt(r['weight'])}" for r in top5)
                events.append({
                    "trigger_type": "AI_BASKET_RAMP",
                    "filing_date": fd,
                    "quarter": fd_to_period.get(fd, ""),
                    "ai_weight_prior": _fmt(prior_ai_weight),
                    "ai_weight_current": _fmt(ai_weight),
                    "ai_weight_change": _fmt(change),
                    "total_portfolio_weight": _fmt(total_weight),
                    "ai_positions_count": str(len(ai_rows)),
                    "new_ai_entries_this_quarter": ", ".join(new_entries),
                    "ai_adds_this_quarter": ", ".join(adds),
                    "ai_exits_this_quarter": ", ".join(exits),
                    "top_5_ai_positions": top5_str,
                })
        prior_ai_weight = ai_weight
    return events


# --------------------------------------------------------------------------
# Trigger 2: NEW_AI_SUBTHEME
# --------------------------------------------------------------------------


def trigger_new_ai_subtheme(
    common: list[dict[str, Any]], filings: list[str], fd_to_period: dict[str, str]
) -> list[dict[str, str]]:
    ai_nonexit = [r for r in common if r["is_ai"] and r["change_type"] != "EXIT"]
    fd_index = {fd: i for i, fd in enumerate(filings)}

    # subtheme -> sorted list of filing_dates where it is present
    present: dict[str, set[str]] = {}
    for r in ai_nonexit:
        present.setdefault(r["subtheme"], set()).add(r["filing_date"])

    events: list[dict[str, str]] = []
    for subtheme, fds in present.items():
        first_fd = min(fds, key=lambda f: fd_index[f])
        entering = [
            r for r in ai_nonexit
            if r["subtheme"] == subtheme and r["filing_date"] == first_fd
        ]
        entering.sort(key=lambda r: r["weight"] or 0.0, reverse=True)
        tickers = [r["ticker"] for r in entering]

        # subsequent adds within the next SUBSEQUENT_ADD_WINDOW filings
        i = fd_index[first_fd]
        window = set(filings[i + 1: i + 1 + SUBSEQUENT_ADD_WINDOW])
        added = sorted({
            r["ticker"] for r in common
            if r["ticker"] in set(tickers)
            and r["change_type"] == "ACTIVE_ADD"
            and r["filing_date"] in window
        })

        events.append({
            "trigger_type": "NEW_AI_SUBTHEME",
            "filing_date": first_fd,
            "quarter": fd_to_period.get(first_fd, ""),
            "subtheme": subtheme,
            "entering_tickers": ", ".join(tickers),
            "entering_weights": ", ".join(_fmt(r["weight"]) for r in entering),
            "total_subtheme_weight": _fmt(sum(r["weight"] or 0.0 for r in entering)),
            "subsequent_add": "TRUE" if added else "FALSE",
            "subsequent_add_tickers": ", ".join(added),
            "quarters_held": str(len(fds)),
        })
    return events


# --------------------------------------------------------------------------
# Trigger 3: NEW_AI_POSITION_2PCT
# --------------------------------------------------------------------------


def trigger_new_ai_position(
    new_ideas: list[dict[str, str]],
    common: list[dict[str, Any]],
    reclass: dict[str, Any],
) -> tuple[list[dict[str, str]], list[str]]:
    # Index NEW COMMON lifecycle rows for the theme join, and group cycles.
    new_common: dict[tuple[str, str], dict[str, Any]] = {}
    cycles: dict[str, list[dict[str, Any]]] = {}
    for r in common:
        cycles.setdefault(r["cycle_id"], []).append(r)
        if r["change_type"] == "NEW":
            new_common[(r["cusip"], r["filing_date"])] = r

    events: list[dict[str, str]] = []
    warnings: list[str] = []
    for row in new_ideas:
        if row.get("is_option", "") != "False":
            continue
        initial = _f(row.get("initial_weight_pct"))
        if initial is None or initial < NEW_POSITION_MIN_WEIGHT_PCT:
            continue

        ticker = row["ticker"]
        fd = row["filing_date"]
        life_new = new_common.get((row["cusip"], fd))
        theme_col = life_new["theme"] if life_new else ""
        is_ai, subtheme = resolve_ai(reclass, ticker, fd, theme_col)
        if not is_ai:
            continue

        # Derive holding stats from the lifecycle cycle (auditability req #4).
        cycle_id = life_new["cycle_id"] if life_new else ""
        cyc = cycles.get(cycle_id, [])
        non_exit = [r for r in cyc if r["change_type"] != "EXIT"]
        quarters_held = len(non_exit)
        weights = [r["weight"] for r in non_exit if r["weight"] is not None]
        max_weight = max(weights) if weights else None
        exit_rows = [r for r in cyc if r["change_type"] == "EXIT"]
        exit_date = exit_rows[0]["filing_date"] if exit_rows else "CURRENT"
        # Last non-empty cumulative return over the cycle (EXIT rows carry none).
        cum_rows = sorted(
            (r for r in cyc if r["cum_return"] is not None),
            key=lambda r: r["period"],
        )
        cum_return = cum_rows[-1]["cum_return"] if cum_rows else None

        # Consistency check against new_ideas' own derived fields.
        ni_qh = _f(row.get("quarters_held"))
        ni_mw = _f(row.get("max_weight_pct"))
        if ni_qh is not None and int(ni_qh) != quarters_held:
            warnings.append(
                f"{ticker} {fd}: quarters_held lifecycle={quarters_held} "
                f"new_ideas={int(ni_qh)}")
        if ni_mw is not None and max_weight is not None and abs(ni_mw - max_weight) > 0.01:
            warnings.append(
                f"{ticker} {fd}: max_weight lifecycle={max_weight:.2f} "
                f"new_ideas={ni_mw:.2f}")

        events.append({
            "trigger_type": "NEW_AI_POSITION_2PCT",
            "filing_date": fd,
            "quarter": row.get("quarter", ""),
            "ticker": ticker,
            "company": row.get("company", ""),
            "theme": subtheme or "",
            "initial_weight_pct": _fmt(initial),
            "became_active_add": (
                "TRUE" if row.get("became_active_add") == "True" else "FALSE"),
            "filing_to_filing_return_pct": _fmt(_f(row.get("filing_to_filing_return_pct"))),
            "quarters_held": str(quarters_held),
            "max_weight_pct": _fmt(max_weight),
            "exit_date": exit_date,
            "cumulative_return_pct": _fmt(cum_return),
        })
    return events, warnings


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    views = find_views_dir()
    reclass = json.loads(RECLASS_PATH.read_text(encoding="utf-8"))

    raw_life = _read_csv(views / "position_lifecycles.csv")
    new_ideas = _read_csv(views / "new_ideas.csv")

    # Annotate COMMON lifecycle rows with parsed weight/return + AI classification.
    common: list[dict[str, Any]] = []
    fd_to_period: dict[str, str] = {}
    for r in raw_life:
        fd_to_period.setdefault(r["filing_date"], r["period"])
        if r["security_type"] != "COMMON":
            continue
        is_ai, subtheme = resolve_ai(reclass, r["ticker"], r["filing_date"], r["theme"])
        row: dict[str, Any] = dict(r)
        row["weight"] = _f(r["weight_pct"])
        row["cum_return"] = _f(r["cum_return_from_entry_pct"])
        row["is_ai"] = is_ai
        row["subtheme"] = subtheme
        common.append(row)

    filings = sorted({r["filing_date"] for r in common})

    ramp = trigger_ai_basket_ramp(common, filings, fd_to_period)
    subtheme_events = trigger_new_ai_subtheme(common, filings, fd_to_period)
    positions, warnings = trigger_new_ai_position(new_ideas, common, reclass)

    all_events = ramp + subtheme_events + positions
    all_events.sort(key=lambda e: (e["filing_date"], e["trigger_type"]))

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, restval="")
        writer.writeheader()
        writer.writerows(all_events)

    # Summary
    ramp_dates = [e["filing_date"] for e in ramp]
    n_subthemes = len({e["subtheme"] for e in subtheme_events})
    n_became_add = sum(1 for e in positions if e["became_active_add"] == "TRUE")
    print(f"Trigger 1 (AI_BASKET_RAMP >=5pt): {len(ramp)} events, dates: {ramp_dates}")
    print(f"Trigger 2 (NEW_AI_SUBTHEME): {len(subtheme_events)} events across "
          f"{n_subthemes} sub-themes")
    print(f"Trigger 3 (NEW_AI_POSITION_2PCT): {len(positions)} events, "
          f"{n_became_add} that became adds")
    print(f"\nWrote {len(all_events)} events -> {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    if warnings:
        print(f"\n{len(warnings)} lifecycle/new_ideas consistency notes:")
        for w in warnings:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
