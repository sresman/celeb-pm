"""Step 6 -- CNBC Sharpe Angle video.

The CNBC video exposes no caption track (verified via yt-dlp), so without Whisper
there is no verbatim transcript. We fall back to saving the article text that
accompanies the video page, tagged as a partial/summary. Low priority.

Usage:
    python -m tools.transcripts.fetch_cnbc [--force]
"""

from __future__ import annotations

import argparse
from typing import Any

from bs4 import BeautifulSoup

from . import targets
from .common import make_session, relpath, write_step_manifest, write_transcript

MIN_CHARS = 150


def _extract(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body
    if node is None:
        return ""
    paras = [p.get_text(" ", strip=True) for p in node.find_all(["p", "li", "h1", "h2"])]
    return "\n\n".join(p for p in paras if p)


def fetch_one(target: targets.ScrapeTarget, session: Any, *, force: bool) -> dict[str, Any]:
    out_path = targets.DIR_TEXT / f"{target['date']}_{target['label']}.txt"
    row: dict[str, Any] = {
        "label": target["label"], "date": target["date"], "source": target["source"],
        "host": target["host"], "topic": target["topic"], "url": target["url"],
        "filepath": relpath(out_path), "quality": "article_summary_no_captions", "status": "",
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
    if len(text) < MIN_CHARS:
        row["status"] = "no_text (video has no captions)"
        return row

    write_transcript(
        out_path,
        label=target["label"], source=target["source"], date=target["date"],
        url=target["url"], body=text,
        extra_header={"note": "CNBC video has no captions; article text only"},
    )
    row["status"] = "ok"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch CNBC Sharpe Angle article text")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    targets.DIR_TEXT.mkdir(parents=True, exist_ok=True)
    session = make_session()
    row = fetch_one(targets.CNBC_TARGET, session, force=args.force)
    print(f"{row['status']:<32} {row['label']}  ({row.get('chars', '?')} chars)")
    write_step_manifest(targets.DIR_TEXT, [row], name="_manifest_cnbc.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
