"""Shared helpers for the transcript fetchers.

Kept deliberately small: an HTTP session with a browser UA, a json3->text
converter for yt-dlp auto-subs, a slugifier, a uniform transcript-file writer
(header + body), and per-step manifest read/write helpers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import requests

from . import targets


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def make_session() -> requests.Session:
    """A requests session that presents a normal browser User-Agent."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": targets.USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


# --------------------------------------------------------------------------
# Text utilities
# --------------------------------------------------------------------------


def slugify(text: str) -> str:
    """Lowercase, ascii, hyphen-safe slug for filenames."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")


def _format_timestamp(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def json3_to_text(raw: str) -> str:
    """Convert a yt-dlp json3 auto-caption payload to '[MM:SS] text' lines.

    json3 events look like {"tStartMs": int, "segs": [{"utf8": str}, ...]}.
    Events with no segs (or only whitespace/newlines) are caption-timing
    artifacts and are skipped.
    """
    data = json.loads(raw)
    lines: list[str] = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(seg.get("utf8", "") for seg in segs)
        text = text.replace("\n", " ").strip()
        if not text:
            continue
        start = int(event.get("tStartMs", 0))
        lines.append(f"[{_format_timestamp(start)}] {text}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Transcript file writing
# --------------------------------------------------------------------------


def write_transcript(
    path: Path,
    *,
    label: str,
    source: str,
    date: str,
    url: str | None,
    body: str,
    extra_header: dict[str, str] | None = None,
) -> None:
    """Write a transcript file with a consistent comment header + body."""
    path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = [
        f"# label: {label}",
        f"# source: {source}",
        f"# date: {date}",
    ]
    if url:
        header_lines.append(f"# url: {url}")
    for key, value in (extra_header or {}).items():
        header_lines.append(f"# {key}: {value}")
    path.write_text("\n".join(header_lines) + "\n\n" + body + "\n", encoding="utf-8")


# --------------------------------------------------------------------------
# Manifest helpers
# --------------------------------------------------------------------------


def write_step_manifest(
    directory: Path, rows: list[dict[str, Any]], name: str = "_manifest.json"
) -> Path:
    """Write a per-step manifest JSON into `directory` (default _manifest.json)."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / name
    manifest_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def relpath(path: Path) -> str:
    """Repo-root-relative path string for manifests."""
    try:
        return str(path.relative_to(targets.REPO_ROOT))
    except ValueError:
        return str(path)
