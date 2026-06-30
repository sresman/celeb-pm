"""Discovery -- surface candidate YouTube IDs for operator review (Gate 2).

Runs each query in targets.SEARCHES via `yt-dlp ytsearch`, dedups against the
already-known IDs, and prints id | title | channel | upload_date | duration so
the operator can decide which (if any) to add to targets.YOUTUBE_VIDEOS before
a follow-up `fetch_youtube` run. This script never downloads transcripts.

Usage:
    python -m tools.transcripts.discover_youtube [--n 5]
"""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import Any

from . import targets


def _search(query: str, n: int) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "yt-dlp", f"ytsearch{n}:{query}", "--flat-playlist", "--no-warnings",
            "--print", "%(id)s\t%(title)s\t%(channel)s\t%(upload_date)s\t%(duration)s",
        ],
        capture_output=True, text=True, timeout=120,
    )
    rows: list[dict[str, Any]] = []
    for line in proc.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        vid_id, title, channel, upload_date, duration = parts[:5]
        rows.append({
            "id": vid_id, "title": title, "channel": channel,
            "upload_date": upload_date, "duration": duration,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover candidate Gavin Baker YouTube IDs")
    parser.add_argument("--n", type=int, default=5, help="results per query (default 5)")
    args = parser.parse_args(argv)

    known = set(targets.YOUTUBE_VIDEOS)
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []

    for query in targets.SEARCHES:
        print(f"\n=== {query} ===")
        for row in _search(query, args.n):
            vid_id = row["id"]
            tag = ""
            if vid_id in known:
                tag = "  [ALREADY KNOWN]"
            elif vid_id in seen:
                tag = "  [dup]"
            else:
                seen.add(vid_id)
                candidates.append({**row, "query": query})
            mins = ""
            if row["duration"] and row["duration"] != "NA":
                try:
                    mins = f"{int(float(row['duration'])) // 60}m"
                except ValueError:
                    mins = row["duration"]
            print(f"  {vid_id}  {row['upload_date']:<9} {mins:>5}  "
                  f"{row['channel']}: {row['title']}{tag}")

    print(f"\n{len(candidates)} new candidate(s) not already in targets.YOUTUBE_VIDEOS.")
    print("Review above, then add confirmed IDs to targets.py and re-run fetch_youtube.")
    # Emit machine-readable candidates for convenience.
    print("\n--- JSON candidates ---")
    print(json.dumps(candidates, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
