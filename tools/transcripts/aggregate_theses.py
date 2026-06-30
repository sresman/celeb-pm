"""Combine per-transcript extractions into aggregate views.

Reads analysis/thesis_extractions/*.json and writes:
  - analysis/all_summaries.json   : one entry per transcript (full data + counts)
  - analysis/thesis_timeline.json : flat, date-sorted list of every thesis

Usage:
    python -m tools.transcripts.aggregate_theses [--generated ISO_TIMESTAMP]
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from . import targets
from .common import relpath

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
EXTRACTIONS_DIR = ANALYSIS_DIR / "thesis_extractions"
ALL_SUMMARIES = ANALYSIS_DIR / "all_summaries.json"
THESIS_TIMELINE = ANALYSIS_DIR / "thesis_timeline.json"


def _load_extractions() -> list[tuple[str, dict[str, Any]]]:
    files = sorted(p for p in EXTRACTIONS_DIR.glob("*.json"))
    out: list[tuple[str, dict[str, Any]]] = []
    for path in files:
        out.append((path.name, json.loads(path.read_text(encoding="utf-8"))))
    return out


def build(generated: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    extractions = _load_extractions()

    transcripts: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []

    for filename, data in extractions:
        meta = data.get("metadata", {})
        date = meta.get("date", "")
        source = meta.get("source", "")
        theses = data.get("theses", [])
        transcripts.append({
            "file": filename,
            "date": date,
            "source": source,
            "thesis_count": len(theses),
            "data": data,
        })
        topic = meta.get("topic", "")
        source_label = f"{source} — {topic}" if topic else source
        for t in theses:
            timeline.append({
                "date": date,
                "source": source_label,
                "thesis_id": t.get("id"),
                "summary": t.get("summary"),
                "confidence": t.get("confidence"),
                "themes": t.get("themes", []),
                "tickers_named": t.get("tickers_named", []),
                "tickers_implied": t.get("tickers_implied", []),
            })

    transcripts.sort(key=lambda r: (r["date"], r["file"]))
    timeline.sort(key=lambda r: (r["date"] or "", r["thesis_id"] or ""))

    all_summaries = {
        "generated": generated,
        "transcript_count": len(transcripts),
        "thesis_count": len(timeline),
        "transcripts": transcripts,
    }
    return all_summaries, timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate per-transcript thesis extractions")
    parser.add_argument("--generated", default="", help="ISO timestamp to stamp into output")
    args = parser.parse_args(argv)

    all_summaries, timeline = build(args.generated)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    ALL_SUMMARIES.write_text(json.dumps(all_summaries, indent=2) + "\n", encoding="utf-8")
    THESIS_TIMELINE.write_text(json.dumps(timeline, indent=2) + "\n", encoding="utf-8")

    print(f"Aggregated {all_summaries['transcript_count']} transcripts, "
          f"{all_summaries['thesis_count']} theses")
    print(f"  -> {relpath(ALL_SUMMARIES)}")
    print(f"  -> {relpath(THESIS_TIMELINE)}")
    # Surface any zero-thesis transcripts for the verification step.
    empty = [t["file"] for t in all_summaries["transcripts"] if t["thesis_count"] == 0]
    if empty:
        print(f"  NOTE: {len(empty)} transcript(s) with 0 theses (expected for sparse/paywalled): "
              + ", ".join(empty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
