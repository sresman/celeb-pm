"""Step 2 -- Colossus / Invest Like the Best transcripts.

Colossus renders its full transcripts client-side; the static HTML exposes only
a short intro teaser (~130 words). We therefore attempt extraction and save ONLY
when the recovered text clears a length threshold that distinguishes a real
transcript from the teaser. Otherwise we record a coverage gap so the operator
can see which episodes need the YouTube mirror (Step 1) or a JS-rendered pull.

Usage:
    python -m tools.transcripts.fetch_colossus [--force]
"""

from __future__ import annotations

import argparse
from typing import Any

from bs4 import BeautifulSoup

from . import targets
from .common import (
    make_session, relpath, slugify, write_step_manifest, write_transcript,
)

# Below this many characters the recovered text is the static teaser, not a
# real transcript -- don't save it as one.
MIN_TRANSCRIPT_CHARS = 3000


def _extract(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    node = soup.find("div", class_="transcript__content") or soup.find(
        "article", class_="transcript"
    )
    if node is None:
        return ""
    return node.get_text(" ", strip=True)


def fetch_one(target: targets.ScrapeTarget, session: Any, *, force: bool) -> dict[str, Any]:
    out_path = targets.DIR_COLOSSUS / f"{target['date']}_{target['label']}.txt"
    row: dict[str, Any] = {
        "label": target["label"], "date": target["date"], "source": target["source"],
        "host": target["host"], "topic": target["topic"], "url": target["url"],
        "filepath": relpath(out_path), "quality": "colossus_edited", "status": "",
    }
    if out_path.exists() and not force:
        row["status"] = "skipped_exists"
        return row
    try:
        resp = session.get(target["url"], timeout=targets.REQUEST_TIMEOUT)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        row["status"] = f"http_error: {exc}"
        return row

    text = _extract(resp.text)
    row["chars"] = len(text)
    if len(text) < MIN_TRANSCRIPT_CHARS:
        # Static page only carries a teaser; the full transcript is JS-gated.
        row["status"] = "needs_fallback_js_or_youtube"
        return row

    write_transcript(
        out_path,
        label=target["label"], source=target["source"], date=target["date"],
        url=target["url"], body=text,
    )
    row["status"] = "ok"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch Colossus / ILTB transcripts")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    targets.DIR_COLOSSUS.mkdir(parents=True, exist_ok=True)
    session = make_session()
    rows = [fetch_one(t, session, force=args.force) for t in targets.COLOSSUS_EPISODES]
    for r in rows:
        print(f"{r['status']:<32} {r['label']}  ({r.get('chars', '?')} chars)")
    manifest = write_step_manifest(targets.DIR_COLOSSUS, rows)
    ok = sum(1 for r in rows if r["status"] in ("ok", "skipped_exists"))
    print(f"\nColossus: {ok}/{len(rows)} full transcripts -> {relpath(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
