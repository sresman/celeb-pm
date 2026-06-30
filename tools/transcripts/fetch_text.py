"""Step 4 -- written interviews (themarket.ch HTML + Graham & Doddsville PDF).

themarket.ch hard-paywalls its interviews; only a short public lede is
retrievable, which we save tagged as `paywalled_lede`. Graham & Doddsville is a
public PDF newsletter -- we extract just the Gavin Baker interview pages.

Usage:
    python -m tools.transcripts.fetch_text [--force]
"""

from __future__ import annotations

import argparse
import io
from typing import Any

from bs4 import BeautifulSoup
from pypdf import PdfReader

from . import targets
from .common import make_session, relpath, write_step_manifest, write_transcript

# A real (non-paywalled) article clears this; below it we have only the lede.
FULL_ARTICLE_CHARS = 1500
MIN_SAVE_CHARS = 100


def _extract_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "aside"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body
    if node is None:
        return ""
    paras = [p.get_text(" ", strip=True) for p in node.find_all(["p", "h1", "h2", "h3", "li"])]
    return "\n\n".join(p for p in paras if p)


def _extract_pdf_baker_section(data: bytes) -> str:
    """Extract only the Gavin Baker interview pages from the G&D newsletter.

    Heuristic tuned for Issue 43: his interview carries the running header
    'Gavin Baker, Atreides Management' and runs after the cover/TOC (page
    index >= 3). We keep those pages in order.
    """
    reader = PdfReader(io.BytesIO(data))
    kept: list[str] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if idx >= 3 and "gavin baker" in text.lower():
            kept.append(text.strip())
    return "\n\n".join(kept)


def fetch_one(target: targets.SearchTarget, session: Any, *, force: bool) -> dict[str, Any]:
    out_path = targets.DIR_TEXT / f"{target['date']}_{target['label']}.txt"
    row: dict[str, Any] = {
        "label": target["label"], "date": target["date"], "source": target["source"],
        "host": target["host"], "topic": target["topic"], "url": target["url"],
        "filepath": relpath(out_path), "quality": "", "status": "",
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

    if target["kind"] == "pdf":
        text = _extract_pdf_baker_section(resp.content)
        quality = "pdf_extracted"
    else:
        text = _extract_html(resp.text)
        quality = "article_full" if len(text) >= FULL_ARTICLE_CHARS else "paywalled_lede"

    row["chars"] = len(text)
    row["quality"] = quality
    if len(text) < MIN_SAVE_CHARS:
        row["status"] = "no_public_content"
        return row

    note = "themarket.ch is paywalled; public lede only" if quality == "paywalled_lede" else \
        ("Graham & Doddsville Issue 43 -- Baker interview pages" if quality == "pdf_extracted" else "")
    write_transcript(
        out_path,
        label=target["label"], source=target["source"], date=target["date"],
        url=target["url"], body=text,
        extra_header={"note": note} if note else None,
    )
    row["status"] = "ok"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch written interviews (themarket + G&D PDF)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    targets.DIR_TEXT.mkdir(parents=True, exist_ok=True)
    session = make_session()
    rows = [fetch_one(t, session, force=args.force) for t in targets.TEXT_TARGETS]
    for r in rows:
        print(f"{r['status']:<20} {r['quality']:<16} {r['label']}  ({r.get('chars', '?')} chars)")
    manifest = write_step_manifest(targets.DIR_TEXT, rows)
    ok = sum(1 for r in rows if r["status"] in ("ok", "skipped_exists"))
    print(f"\nText interviews: {ok}/{len(rows)} -> {relpath(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
