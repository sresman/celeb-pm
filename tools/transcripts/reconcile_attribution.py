"""Two-of-two reconciliation of the speaker-attribution audit.

WHY. ``audit_attribution`` is a single LLM call per episode and its per-thesis
verdicts are not stable run to run — the same instability that shows up in
extraction yield. The operator's rule (2026-09-08) is a two-of-two agreement
test: run the audit twice over the same corpus and keep a verdict only when both
passes agree. Disagreement resolves to ``indeterminate``, which the filtering
layer treats as not-the-subject. The test can only lose Baker attributions, never
invent them, which is the right direction for a contamination audit.

VOCABULARY. The audit emits ``baker``; everything downstream of here speaks the
investor-agnostic ``subject`` / ``other`` / ``indeterminate`` that ``audit_theses``
and the filtering layer expect. The mapping happens here, once.

KEY. ``(label, thesis_id)``. ``thesis_id`` is unique only within an appearance —
T1 occurs 47 times across the corpus — and ``date`` is not unique either, since
2026-05-12 carries two records of the one Sohn NY event whose ids collide on
T1..T4. Label is the only safe key.

Usage::

    python -m tools.transcripts.reconcile_attribution
    python -m tools.transcripts.reconcile_attribution --pass1 DIR --pass2 DIR
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.transcripts import targets

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
PASS1_DIR = ANALYSIS_DIR / "attribution_audit_pass1"
PASS2_DIR = ANALYSIS_DIR / "attribution_audit_pass2"
OUT_PATH = ANALYSIS_DIR / "attribution_resolved.json"

# audit vocabulary -> corpus vocabulary
VERDICT_MAP = {"baker": "subject", "other": "other", "indeterminate": "indeterminate"}
VERDICTS = ("subject", "other", "indeterminate")

Key = tuple[str, str]


def _relpath(path: Path) -> str:
    """Repo-relative when it can be, absolute otherwise — never raises."""
    try:
        return str(path.relative_to(targets.REPO_ROOT))
    except ValueError:
        return str(path)


def load_pass(directory: Path) -> tuple[dict[Key, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return {(label, thesis_id): result} and {label: episode metadata}."""
    results: dict[Key, dict[str, Any]] = {}
    episodes: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        raise SystemExit(f"missing pass directory: {directory}")
    for path in sorted(directory.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        label = str(record.get("label") or path.stem)
        episodes[label] = {
            "label": label,
            "date": str(record.get("date", "")),
            "source": str(record.get("source", "")),
            "host": str(record.get("host", "")),
            "kind": str(record.get("kind", "")),
        }
        for row in record.get("results", []):
            key = (label, str(row.get("thesis_id", "")))
            if key in results:
                raise SystemExit(f"duplicate thesis key {key} in {path}")
            results[key] = row
    return results, episodes


def _verdict(row: dict[str, Any] | None) -> str:
    if row is None:
        return ""
    raw = str(row.get("speaker_attribution", ""))
    return VERDICT_MAP.get(raw, "indeterminate")


def reconcile(
    p1: dict[Key, dict[str, Any]], p2: dict[Key, dict[str, Any]]
) -> list[dict[str, Any]]:
    """One record per thesis, resolved by the two-of-two rule."""
    out: list[dict[str, Any]] = []
    for key in sorted(p1.keys() | p2.keys()):
        label, thesis_id = key
        a, b = p1.get(key), p2.get(key)
        va, vb = _verdict(a), _verdict(b)
        seed = a or b or {}

        if a is None or b is None:
            resolved, agreement, note = "indeterminate", False, (
                "missing_in_pass2" if b is None else "missing_in_pass1"
            )
        elif va == vb:
            resolved, agreement, note = va, True, ""
        else:
            resolved, agreement, note = "indeterminate", False, f"disagreement:{va}|{vb}"

        out.append(
            {
                "label": label,
                "thesis_id": thesis_id,
                "speaker_attribution": resolved,
                "agreement": agreement,
                "note": note,
                "tickers": list(seed.get("tickers") or []),
                "summary": str(seed.get("summary", ""))[:200],
                "quote": str(seed.get("quote", ""))[:240],
                "pass1": {
                    "speaker_attribution": va,
                    "confidence": str((a or {}).get("attribution_confidence", "")),
                    "likely_speaker": str((a or {}).get("likely_speaker", "")),
                    "evidence": str((a or {}).get("evidence", "")),
                },
                "pass2": {
                    "speaker_attribution": vb,
                    "confidence": str((b or {}).get("attribution_confidence", "")),
                    "likely_speaker": str((b or {}).get("likely_speaker", "")),
                    "evidence": str((b or {}).get("evidence", "")),
                },
                # The speaker name only survives when both passes agree it is not
                # Baker AND they name the same person; otherwise it is noise.
                "speaker_name": (
                    str((a or {}).get("likely_speaker", ""))
                    if agreement
                    and resolved == "other"
                    and (a or {}).get("likely_speaker") == (b or {}).get("likely_speaker")
                    else ""
                ),
            }
        )
    return out


def summarise(
    records: list[dict[str, Any]], episodes: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    def blank() -> dict[str, int]:
        d = {"theses": 0, "tickers": 0}
        for v in VERDICTS:
            d[v] = 0
            d[f"tickers_{v}"] = 0
        return d

    total = blank()
    per_label: dict[str, dict[str, int]] = {}
    matrix: Counter[tuple[str, str]] = Counter()
    pass1_only = blank()

    for r in records:
        v = str(r["speaker_attribution"])
        n = len(r["tickers"])
        row = per_label.setdefault(str(r["label"]), blank())
        for bucket in (total, row):
            bucket["theses"] += 1
            bucket[v] += 1
            bucket["tickers"] += n
            bucket[f"tickers_{v}"] += n
        matrix[(r["pass1"]["speaker_attribution"], r["pass2"]["speaker_attribution"])] += 1
        # what pass 1 alone would have said, for the cost-of-the-rule line
        v1 = r["pass1"]["speaker_attribution"] or "indeterminate"
        pass1_only["theses"] += 1
        pass1_only[v1] += 1
        pass1_only["tickers"] += n
        pass1_only[f"tickers_{v1}"] += n

    agreed = sum(1 for r in records if r["agreement"])
    return {
        "total": total,
        "pass1_only": pass1_only,
        "agreement_rate": round(agreed / len(records), 4) if records else 0.0,
        "agreed": agreed,
        "disagreed": len(records) - agreed,
        "confusion": {f"{a or 'MISSING'}->{b or 'MISSING'}": n for (a, b), n in sorted(matrix.items())},
        "episodes": [
            {**episodes.get(label, {"label": label}), **row}
            for label, row in sorted(
                per_label.items(),
                key=lambda kv: -(kv[1]["tickers_other"] + kv[1]["tickers_indeterminate"]),
            )
        ],
    }


def print_report(summary: dict[str, Any]) -> None:
    t, p1 = summary["total"], summary["pass1_only"]
    print("\n" + "=" * 100)
    print("ATTRIBUTION — two-of-two reconciliation")
    print("=" * 100)
    for name, b in (("resolved (2-of-2)", t), ("pass 1 alone   ", p1)):
        if b["theses"]:
            print(
                f"  {name}  theses {b['theses']:>4}   "
                f"subject {b['subject']:>4} ({b['subject']/b['theses']:.0%})   "
                f"other {b['other']:>3} ({b['other']/b['theses']:.0%})   "
                f"indet {b['indeterminate']:>3} ({b['indeterminate']/b['theses']:.0%})"
            )
        if b["tickers"]:
            print(
                f"  {' ' * len(name)}  named  {b['tickers']:>4}   "
                f"subject {b['tickers_subject']:>4} ({b['tickers_subject']/b['tickers']:.0%})   "
                f"other {b['tickers_other']:>3} ({b['tickers_other']/b['tickers']:.0%})   "
                f"indet {b['tickers_indeterminate']:>3} "
                f"({b['tickers_indeterminate']/b['tickers']:.0%})"
            )
    print(
        f"\n  agreement {summary['agreement_rate']:.1%}  "
        f"({summary['agreed']} agreed / {summary['disagreed']} disagreed)"
    )
    print(
        f"  cost of the rule (resolved vs pass 1 alone): "
        f"{t['subject'] - p1['subject']:+d} subject theses, "
        f"{t['tickers_subject'] - p1['tickers_subject']:+d} subject named tickers"
    )
    print("\n  pass1 -> pass2 confusion:")
    for k, n in summary["confusion"].items():
        print(f"    {k:<34}{n:>5}")

    print("\n" + "-" * 100)
    print("PER EPISODE — sorted by non-subject named tickers")
    print("-" * 100)
    print(
        f"  {'label':<46}{'kind':<9}{'th':>4}{'subj':>6}{'oth':>5}{'ind':>5}"
        f"{'tk':>5}{'tk_s':>6}{'%tk_bad':>9}"
    )
    for e in summary["episodes"]:
        bad = e["tickers"] - e["tickers_subject"]
        pct = (100 * bad / e["tickers"]) if e["tickers"] else 0.0
        print(
            f"  {str(e.get('label',''))[:45]:<46}{str(e.get('kind','')):<9}"
            f"{e['theses']:>4}{e['subject']:>6}{e['other']:>5}{e['indeterminate']:>5}"
            f"{e['tickers']:>5}{e['tickers_subject']:>6}{pct:>8.0f}%"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pass1", type=Path, default=PASS1_DIR)
    parser.add_argument("--pass2", type=Path, default=PASS2_DIR)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(argv)
    # Accept relative paths from the shell; every downstream use assumes absolute.
    args.pass1 = args.pass1.resolve()
    args.pass2 = args.pass2.resolve()
    args.out = args.out.resolve()

    p1, ep1 = load_pass(args.pass1)
    p2, ep2 = load_pass(args.pass2)
    print(f"pass1: {len(p1)} theses / {len(ep1)} episodes  ({args.pass1})")
    print(f"pass2: {len(p2)} theses / {len(ep2)} episodes  ({args.pass2})")
    if p1.keys() != p2.keys():
        only1, only2 = sorted(p1.keys() - p2.keys()), sorted(p2.keys() - p1.keys())
        print(f"  WARNING: key mismatch — {len(only1)} only in pass1, {len(only2)} only in pass2")
        for k in (only1 + only2)[:10]:
            print(f"    {k}")

    records = reconcile(p1, p2)
    summary = summarise(records, {**ep2, **ep1})
    print_report(summary)

    args.out.write_text(
        json.dumps(
            {
                "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "pass1_dir": _relpath(args.pass1),
                "pass2_dir": _relpath(args.pass2),
                "rule": "two-of-two agreement; disagreement resolves to indeterminate",
                "summary": summary,
                "attributions": records,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n  -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
