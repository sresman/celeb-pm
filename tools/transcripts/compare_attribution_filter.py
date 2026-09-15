"""Aggregate before/after comparison for the speaker-attribution filter.

THE QUESTION THIS ANSWERS. Not "is each thesis attributed correctly" — that is
per-thesis accuracy and the audit already reports it. The operator's question is
whether the contamination *matters*: if the repeat-mention population and the
basket membership barely move once non-subject theses are dropped, the
contamination was noise around a stable signal and the existing work stands.

DELIBERATELY NO RETURNS. This runs cluster -> mention rows -> basket resolution
for both modes and stops. It touches no price data and writes no vN deliverable,
so it can be run before returns are unheld.

Usage::

    python -m tools.transcripts.compare_attribution_filter
    python -m tools.transcripts.compare_attribution_filter --out analysis/foo.md
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from . import targets
from .build_repeat_mention_events import (
    BASKETS_JSON,
    TIMELINE_JSON,
    generate_mention_rows,
)
from .theme_returns_v2 import (
    NO_BASKET,
    apply_cluster_overrides,
    apply_event_override,
    cluster_theses,
    filter_by_attribution,
    find_event_override,
    load_overrides,
    resolve_basket,
)

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
OUT_MD = ANALYSIS_DIR / "attribution_filter_comparison.md"
OUT_CSV = ANALYSIS_DIR / "attribution_filter_comparison_by_theme.csv"

MODES = ("all", "subject")


def build_rows(
    theses: list[dict[str, Any]], baskets: dict[str, Any], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    """Mention rows with baskets resolved and event overrides applied."""
    assignments, _ = cluster_theses(theses, baskets)
    apply_cluster_overrides(assignments, overrides)

    rows: list[dict[str, Any]] = []
    for theme, theme_theses in assignments.items():
        rows.extend(generate_mention_rows(theme, theme_theses, overrides))

    for r in rows:
        tickers, source, direction, asterisk = resolve_basket(r["theme"], r["date"], baskets)
        r["resolved_basket"] = ", ".join(tickers)
        r["basket_source"] = source if source else NO_BASKET
        r["basket_direction"] = direction
        r["basket_asterisk"] = str(asterisk)
        ov = find_event_override(
            overrides, theme=r["theme"], date=r["date"],
            summary=str(r.get("summary", "")), mention_number=r["mention_number"],
        )
        if ov is not None:
            apply_event_override(r, ov)
    return rows


def _basket_tickers(row: dict[str, Any]) -> set[str]:
    if row.get("basket_source") == NO_BASKET:
        return set()
    return {x.strip() for x in str(row.get("resolved_basket", "")).split(",") if x.strip()}


def _named_tickers(theses: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for t in theses:
        out.update(t.get("tickers_direct") or [])
    return out


def profile(rows: list[dict[str, Any]], theses: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in rows if r.get("basket_source") != NO_BASKET]
    basket_universe: set[str] = set()
    for r in scored:
        basket_universe |= _basket_tickers(r)
    return {
        "theses": len(theses),
        "named_ticker_slots": sum(len(t.get("tickers_direct") or []) for t in theses),
        "named_ticker_universe": _named_tickers(theses),
        "themes": {r["theme"] for r in rows},
        "mention_rows": len(rows),
        "repeat_mentions": sum(1 for r in rows if r.get("is_repeat_mention") == "TRUE"),
        "meets_criteria": sum(1 for r in rows if r.get("meets_existing_criteria") == "TRUE"),
        "scored_rows": len(scored),
        "basket_universe": basket_universe,
        "row_keys": {(r["theme"], r["date"]) for r in rows},
        "rows": rows,
    }


def _pct(new: float, old: float) -> str:
    if not old:
        return "n/a"
    return f"{100 * (new - old) / old:+.1f}%"


def _delta_line(name: str, a: Any, b: Any) -> str:
    if isinstance(a, set):
        return (
            f"| {name} | {len(a)} | {len(b)} | {len(b) - len(a):+d} | "
            f"{_pct(len(b), len(a))} |"
        )
    return f"| {name} | {a} | {b} | {b - a:+d} | {_pct(b, a)} |"


def report(pa: dict[str, Any], ps: dict[str, Any], counts: dict[str, int]) -> str:
    lost_themes = sorted(pa["themes"] - ps["themes"])
    lost_rows = sorted(pa["row_keys"] - ps["row_keys"])
    lost_names = sorted(pa["named_ticker_universe"] - ps["named_ticker_universe"])
    lost_basket = sorted(pa["basket_universe"] - ps["basket_universe"])

    by_theme: dict[str, tuple[int, int]] = {}
    for theme in sorted(pa["themes"] | ps["themes"]):
        a = sum(1 for r in pa["rows"] if r["theme"] == theme)
        b = sum(1 for r in ps["rows"] if r["theme"] == theme)
        by_theme[theme] = (a, b)

    lines = [
        "# Attribution filter — aggregate before/after",
        "",
        "`all` = every thesis in the corpus (pre-attribution behaviour). ",
        "`subject` = only theses both audit passes attributed to the subject; ",
        "`other` and `indeterminate` stay in the corpus, tagged, but are excluded.",
        "",
        "Returns are NOT computed here. Cluster -> mention rows -> basket resolution only.",
        "",
        "## Corpus attribution split",
        "",
        "| verdict | theses |",
        "| --- | ---: |",
    ]
    total = sum(counts.values()) or 1
    for k in ("subject", "other", "indeterminate"):
        v = counts.get(k, 0)
        lines.append(f"| {k} | {v} ({100 * v / total:.0f}%) |")
    lines += [
        "",
        "## Aggregate",
        "",
        "| measure | all | subject | delta | |",
        "| --- | ---: | ---: | ---: | ---: |",
        _delta_line("theses", pa["theses"], ps["theses"]),
        _delta_line("named-ticker slots", pa["named_ticker_slots"], ps["named_ticker_slots"]),
        _delta_line("distinct named tickers", pa["named_ticker_universe"], ps["named_ticker_universe"]),
        _delta_line("themes with >=1 mention", pa["themes"], ps["themes"]),
        _delta_line("mention rows", pa["mention_rows"], ps["mention_rows"]),
        _delta_line("repeat mentions", pa["repeat_mentions"], ps["repeat_mentions"]),
        _delta_line("meets existing criteria", pa["meets_criteria"], ps["meets_criteria"]),
        _delta_line("scored rows (basket resolved)", pa["scored_rows"], ps["scored_rows"]),
        _delta_line("basket ticker universe", pa["basket_universe"], ps["basket_universe"]),
        "",
        "## What disappears",
        "",
        f"**Themes lost entirely ({len(lost_themes)}):** "
        + (", ".join(f"`{t}`" for t in lost_themes) if lost_themes else "_none_"),
        "",
        f"**Named tickers lost from the corpus ({len(lost_names)}):** "
        + (", ".join(f"`{t}`" for t in lost_names) if lost_names else "_none_"),
        "",
        f"**Tickers lost from resolved baskets ({len(lost_basket)}):** "
        + (", ".join(f"`{t}`" for t in lost_basket) if lost_basket else "_none_"),
        "",
        f"**Mention rows lost ({len(lost_rows)}):**",
        "",
    ]
    if lost_rows:
        lines += ["| theme | date |", "| --- | --- |"]
        lines += [f"| `{t}` | {d} |" for t, d in lost_rows]
    else:
        lines.append("_none_")

    lines += [
        "",
        "## Per theme (mention rows)",
        "",
        "| theme | all | subject | delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for theme, (a, b) in sorted(by_theme.items(), key=lambda kv: (kv[1][1] - kv[1][0], kv[0])):
        flag = "" if a == b else "  <-"
        lines.append(f"| `{theme}` | {a} | {b} | {b - a:+d}{flag} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_MD)
    parser.add_argument("--out-csv", type=Path, default=OUT_CSV)
    args = parser.parse_args(argv)

    baskets = json.loads(BASKETS_JSON.read_text())
    overrides = load_overrides()
    all_theses = json.loads(TIMELINE_JSON.read_text())

    profiles: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for mode in MODES:
        theses, counts = filter_by_attribution(all_theses, mode)
        rows = build_rows(theses, baskets, overrides)
        profiles[mode] = profile(rows, theses)
        print(
            f"[{mode:<7}] theses {len(theses):>4}  rows {len(rows):>4}  "
            f"repeat {profiles[mode]['repeat_mentions']:>3}  "
            f"criteria {profiles[mode]['meets_criteria']:>3}  "
            f"themes {len(profiles[mode]['themes']):>3}"
        )

    if counts.get("subject", 0) == 0:
        print(
            "\n  WARNING: no thesis is attributed 'subject'. Has "
            "attribution_resolved.json been built and the timeline rebuilt?"
        )

    pa, ps = profiles["all"], profiles["subject"]
    args.out.write_text(report(pa, ps, counts), encoding="utf-8")

    with args.out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["theme", "rows_all", "rows_subject", "delta"])
        for theme in sorted(pa["themes"] | ps["themes"]):
            a = sum(1 for r in pa["rows"] if r["theme"] == theme)
            b = sum(1 for r in ps["rows"] if r["theme"] == theme)
            w.writerow([theme, a, b, b - a])

    print(f"\n  -> {args.out}\n  -> {args.out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
