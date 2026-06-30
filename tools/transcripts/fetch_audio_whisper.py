"""Step 5 (OPTIONAL / general-purpose) -- audio-only podcasts -> Whisper.

NOT required for the current corpus: both originally-targeted audio-only episodes
(On The Tape "Fear is the Market Killer"; Thematic Investors "Sci-fi/History")
were found as YouTube mirrors during Gate-2 discovery and are already covered by
Step 1. This script is kept as ready-to-run tooling for any FUTURE audio-only
appearance that has no YouTube mirror.

Running it requires extra installs not present by default:
    pip install openai-whisper        # pulls in torch (~2-3 GB)
    # ffmpeg is already available on this machine

Flow per RSS_TARGETS entry: iTunes lookup -> RSS feed -> match episode ->
download enclosure MP3 -> whisper --model medium -> transcripts/whisper/.

Usage:
    python -m tools.transcripts.fetch_audio_whisper [--model medium] [--force]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from . import targets
from .common import make_session, relpath, write_step_manifest


def _resolve_feed_url(session: Any, itunes_id: str) -> str | None:
    resp = session.get(
        "https://itunes.apple.com/lookup",
        params={"id": itunes_id, "entity": "podcast"},
        timeout=targets.REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0].get("feedUrl") if results else None


def _find_enclosure(session: Any, feed_url: str, match: str) -> str | None:
    resp = session.get(feed_url, timeout=targets.REQUEST_TIMEOUT)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    for item in root.iter("item"):
        title_el = item.find("title")
        title = title_el.text or "" if title_el is not None else ""
        if match.lower() in title.lower():
            enc = item.find("enclosure")
            if enc is not None:
                return enc.get("url")
    return None


def fetch_one(target: targets.RssTarget, session: Any, model: str, *, force: bool) -> dict[str, Any]:
    out_path = targets.DIR_WHISPER / f"{target['date']}_{target['label']}.txt"
    row: dict[str, Any] = {
        "label": target["label"], "date": target["date"], "source": target["source"],
        "host": target["host"], "topic": target["topic"],
        "filepath": relpath(out_path), "quality": f"whisper_{model}", "status": "",
        "url": None,
    }
    if out_path.exists() and not force:
        row["status"] = "skipped_exists"
        return row
    if shutil.which("whisper") is None:
        row["status"] = "whisper_not_installed (pip install openai-whisper)"
        return row

    try:
        feed_url = _resolve_feed_url(session, target["itunes_id"])
        if not feed_url:
            row["status"] = "no_feed_url"
            return row
        mp3_url = _find_enclosure(session, feed_url, target["episode_match"])
        if not mp3_url:
            row["status"] = "episode_not_found_in_feed"
            return row
        row["url"] = mp3_url

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            mp3_path = tmp_dir / "episode.mp3"
            with session.get(mp3_url, stream=True, timeout=300) as audio:
                audio.raise_for_status()
                with mp3_path.open("wb") as fh:
                    for chunk in audio.iter_content(chunk_size=1 << 16):
                        fh.write(chunk)
            subprocess.run(
                ["whisper", str(mp3_path), "--model", model, "--language", "en",
                 "--output_format", "txt", "--output_dir", str(tmp_dir)],
                check=True, capture_output=True, text=True,
            )
            produced = next(tmp_dir.glob("*.txt"), None)
            if produced is None:
                row["status"] = "whisper_no_output"
                return row
            out_path.parent.mkdir(parents=True, exist_ok=True)
            header = (
                f"# label: {target['label']}\n# source: {target['source']}\n"
                f"# date: {target['date']}\n# url: {mp3_url}\n"
                f"# quality: whisper_{model}\n\n"
            )
            out_path.write_text(header + produced.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        row["status"] = f"error: {exc}"
        return row

    row["status"] = "ok"
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transcribe audio-only podcasts with Whisper")
    parser.add_argument("--model", default="medium", help="whisper model (default medium)")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    targets.DIR_WHISPER.mkdir(parents=True, exist_ok=True)
    session = make_session()
    rows = [fetch_one(t, session, args.model, force=args.force) for t in targets.RSS_TARGETS]
    for r in rows:
        print(f"{r['status']:<48} {r['label']}")
    write_step_manifest(targets.DIR_WHISPER, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
