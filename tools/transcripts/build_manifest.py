"""Final step -- build transcripts/_master_manifest.json + a coverage report.

Combines every per-step manifest, keeps the rows whose transcript file actually
exists on disk, normalizes the columns, and prints a coverage table so gaps are
explicit (never silently truncated).

Usage:
    python -m tools.transcripts.build_manifest
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from . import targets
from .common import relpath

MANIFEST_GLOB = "_manifest*.json"

# Columns surfaced in the master manifest.
# subject_role added 2026-09-08: the attribution audit needs the subject's role
# on each recording, and the manifest is the only place that covers ALL 48
# appearances — targets.py splits them across five lists (YOUTUBE_VIDEOS,
# RSS_TARGETS, COLOSSUS_EPISODES, TEXT_TARGETS, WEB_TARGETS + CNBC_TARGET), and
# three appearances (sohn_australia_2021_coinbase, cnbc_squawk_spacex_debut_2026jun,
# cnbc_spacex_drawdown_2026jul) are acquired outside those lists entirely.
# Reading role/host from the manifest instead of targets.py removes a whole class
# of "which list did I forget to check" bug.
FIELDS = ["date", "source", "label", "host", "topic", "filepath", "quality", "status", "url", "subject_role"]


def _load_step_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for directory in targets.ALL_DIRS:
        if not directory.exists():
            continue
        for manifest in sorted(directory.glob(MANIFEST_GLOB)):
            if manifest.name == targets.MASTER_MANIFEST.name:
                continue
            data = json.loads(manifest.read_text(encoding="utf-8"))
            rows.extend(data)
    return rows


def build() -> tuple[list[dict[str, Any]], Counter[str]]:
    rows = _load_step_rows()
    status_counts: Counter[str] = Counter()
    manifest: list[dict[str, Any]] = []

    for row in rows:
        status = row.get("status", "")
        status_counts[status] += 1
        filepath = row.get("filepath")
        # Only catalog rows whose file exists (ok / skipped_exists).
        if not filepath or not (targets.REPO_ROOT / filepath).exists():
            continue
        manifest.append({field: row.get(field) for field in FIELDS})

    manifest.sort(key=lambda r: (r.get("date") or "", r.get("label") or ""))
    return manifest, status_counts


def main() -> int:
    manifest, status_counts = build()
    targets.TRANSCRIPTS_ROOT.mkdir(parents=True, exist_ok=True)
    targets.MASTER_MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Master manifest: {len(manifest)} transcripts -> {relpath(targets.MASTER_MANIFEST)}\n")
    print("Coverage by status (all attempted targets):")
    for status, count in sorted(status_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}  {status}")

    print("\nObtained transcripts by quality tier:")
    quality_counts: Counter[str] = Counter(r["quality"] for r in manifest)
    for quality, count in sorted(quality_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>3}  {quality}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
