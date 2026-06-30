"""Step 1 -- YouTube auto-transcripts via yt-dlp.

Uses yt-dlp (not youtube-transcript-api) because it is installed, works from
this network, and is far less prone to IP blocking. For each known video we
download the English auto-caption track in json3 format, convert it to
'[MM:SS] text' lines, and write transcripts/youtube/<date>_<label>_<id>.txt.

Usage:
    python -m tools.transcripts.fetch_youtube              # batch all known IDs
    python -m tools.transcripts.fetch_youtube <id> [<id>]  # only these IDs
    python -m tools.transcripts.fetch_youtube --force      # re-download existing
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from . import targets
from .common import json3_to_text, relpath, write_step_manifest, write_transcript

# Candidate sub-language tags to try, in order. YouTube auto-captions are
# usually 'en'; some videos expose 'en-orig' or a manual 'en' track instead.
SUB_LANG_CANDIDATES = ["en", "en-orig", "en-US", "en-GB"]


def _output_path(vid_id: str, meta: targets.YoutubeTarget) -> Path:
    return targets.DIR_YOUTUBE / f"{meta['date']}_{meta['label']}_{vid_id}.txt"


def _fetch_metadata(vid_id: str) -> dict[str, Any]:
    """Return yt-dlp's JSON metadata for a video (title, uploader, etc.)."""
    proc = subprocess.run(
        [
            "yt-dlp", "--skip-download", "--no-warnings", "--dump-single-json",
            f"https://www.youtube.com/watch?v={vid_id}",
        ],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip()[:400] or "yt-dlp metadata failed")
    data: dict[str, Any] = json.loads(proc.stdout)
    return data


def _download_caption(vid_id: str, sub_lang: str, dest_dir: Path) -> str | None:
    """Download one auto-caption track as json3. Return raw json3 or None."""
    proc = subprocess.run(
        [
            "yt-dlp", "--skip-download", "--no-warnings",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", sub_lang, "--sub-format", "json3",
            "-o", str(dest_dir / "%(id)s.%(ext)s"),
            f"https://www.youtube.com/watch?v={vid_id}",
        ],
        capture_output=True, text=True, timeout=180,
    )
    # yt-dlp returns 0 even when no subs in the requested lang exist; detect the
    # written file rather than trusting the return code.
    matches = list(dest_dir.glob(f"{vid_id}.*.json3"))
    if matches:
        return matches[0].read_text(encoding="utf-8")
    if proc.returncode != 0 and "Sign in to confirm" in proc.stderr:
        raise RuntimeError("bot_wall")  # surfaced to caller for cookie fallback
    return None


def fetch_one(vid_id: str, meta: targets.YoutubeTarget, *, force: bool) -> dict[str, Any]:
    """Fetch a single video's transcript. Returns a manifest row."""
    out_path = _output_path(vid_id, meta)
    row: dict[str, Any] = {
        "id": vid_id, "label": meta["label"], "date": meta["date"],
        "source": meta["source"], "host": meta["host"], "topic": meta["topic"],
        "filepath": relpath(out_path), "quality": "youtube_auto", "status": "",
        "actual_title": None,
    }

    if out_path.exists() and not force:
        row["status"] = "skipped_exists"
        return row

    # Verify the video resolves and capture its real title (so a mislabeled ID
    # is flagged, not silently trusted).
    try:
        md = _fetch_metadata(vid_id)
        row["actual_title"] = md.get("title")
        if md.get("upload_date"):  # YYYYMMDD
            d = md["upload_date"]
            row["actual_upload_date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    except Exception as exc:  # noqa: BLE001 -- best-effort, recorded in manifest
        row["status"] = f"metadata_error: {exc}"
        return row

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        raw_json3: str | None = None
        used_lang: str | None = None
        for lang in SUB_LANG_CANDIDATES:
            try:
                raw_json3 = _download_caption(vid_id, lang, tmp_dir)
            except RuntimeError as exc:
                if str(exc) == "bot_wall":
                    row["status"] = "bot_wall (retry with --cookies-from-browser)"
                    return row
                raise
            if raw_json3:
                used_lang = lang
                break

        if not raw_json3:
            row["status"] = "no_captions"
            return row

        body = json3_to_text(raw_json3)
        if not body.strip():
            row["status"] = "empty_captions"
            return row

    write_transcript(
        out_path,
        label=meta["label"], source=meta["source"], date=meta["date"],
        url=f"https://www.youtube.com/watch?v={vid_id}", body=body,
        extra_header={
            "youtube_id": vid_id,
            "sub_lang": used_lang or "",
            "actual_title": row["actual_title"] or "",
        },
    )
    row["status"] = "ok"
    row["lines"] = body.count("\n") + 1
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fetch YouTube auto-transcripts via yt-dlp")
    parser.add_argument("ids", nargs="*", help="specific video IDs (default: all known)")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    args = parser.parse_args(argv)

    targets.DIR_YOUTUBE.mkdir(parents=True, exist_ok=True)

    if args.ids:
        selected = {vid: targets.YOUTUBE_VIDEOS[vid] for vid in args.ids
                    if vid in targets.YOUTUBE_VIDEOS}
        unknown = [vid for vid in args.ids if vid not in targets.YOUTUBE_VIDEOS]
        for vid in unknown:
            print(f"WARN: {vid} not in targets.YOUTUBE_VIDEOS -- skipping", file=sys.stderr)
    else:
        selected = targets.YOUTUBE_VIDEOS

    rows: list[dict[str, Any]] = []
    for vid_id, meta in selected.items():
        row = fetch_one(vid_id, meta, force=args.force)
        rows.append(row)
        flag = ""
        if row.get("actual_title") and meta["label"].split("_")[0] not in (row["actual_title"] or "").lower():
            flag = f"  [title: {row['actual_title']!r}]"
        print(f"{row['status']:<28} {meta['label']}{flag}")

    manifest = write_step_manifest(targets.DIR_YOUTUBE, rows)
    ok = sum(1 for r in rows if r["status"] in ("ok", "skipped_exists"))
    print(f"\nYouTube: {ok}/{len(rows)} available -> {relpath(manifest)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
