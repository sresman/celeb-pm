"""Step 3 -- free web writeups (HedgeFundAlpha conference notes).

These are article writeups, not verbatim transcripts. HedgeFundAlpha paywalls
the full text; we save the public portion and tag the quality accordingly.
(happyscribe was dropped -- it hard-blocks this network with a 403, and its
All-In episode is covered by the YouTube pull in Step 1.)

Usage:
    python -m tools.transcripts.fetch_web [--force]
"""

from __future__ import annotations

import argparse
from typing import Any

from bs4 import BeautifulSoup

from . import targets
from .common import make_session, relpath, write_step_manifest, write_transcript

MIN_CHARS = 200  # below this there's no usable public content


def _extract_article(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "form"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body
    if node is None:
        return ""
    # Paragraph-joined text keeps it readable for NLP.
    paras = [p.get_text(" ", strip=True) for p in node.find_all(["p", "li", "h1", "h2", "h3"])]
    text = "\n\n".join(p for p in paras if p)
    return text or node.get_text("\n", strip=True)


def fetch_one(target: targets.ScrapeTarget, session: Any, *, force: bool) -> dict[str, Any]:
    out_path = targets.DIR_WEB / f"{target['date']}_{target['label']}.txt"
    row: dict[str, Any] = {
        "label": target["label"], "date": target["date"], "source": target["source"],
        "host": target["host"], "topic": target["topic"], "url": target["url"],
        "filepath": relpath(out_path), "quality": "writeup_public_portion", "status": "",
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

    text = _extract_article(resp.text)
    row["chars"] = len(text)
    if len(text) < MIN_CHARS:
        row["status"] = "no_public_content"
        return row

    write_transcript(
        out_path,
        label=target["label"], source=target["source"], date=target["date"],
        url=target["url"], body=text,
        extra_header={"note": "writeup / public portion only (paywalled source)"},
    )
    row["status"] = "ok"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch HedgeFundAlpha writeups")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    targets.DIR_WEB.mkdir(parents=True, exist_ok=True)
    session = make_session()
    rows = [fetch_one(t, session, force=args.force) for t in targets.WEB_TARGETS]
    for r in rows:
        print(f"{r['status']:<24} {r['label']}  ({r.get('chars', '?')} chars)")
    manifest = write_step_manifest(targets.DIR_WEB, rows)
    ok = sum(1 for r in rows if r["status"] in ("ok", "skipped_exists"))
    print(f"\nWeb writeups: {ok}/{len(rows)} -> {relpath(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
