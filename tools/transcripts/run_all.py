"""Orchestrate the transcript corpus build end-to-end.

Runs Step 1 (YouTube) -> Step 2 (Colossus) -> Step 3 (web) -> Step 4 (text) ->
Step 6 (CNBC) -> master manifest. Step 5 (Whisper) is skipped by default because
both of its episodes are covered via YouTube mirrors; pass --whisper to include
it (requires `pip install openai-whisper`).

All fetchers are idempotent: existing files are skipped unless --force. Discovery
of new YouTube IDs is intentionally NOT part of this runner -- it is a reviewed
step (see discover_youtube.py).

Usage:
    python -m tools.transcripts.run_all [--force] [--whisper]
"""

from __future__ import annotations

import argparse

from . import (
    build_manifest, fetch_cnbc, fetch_colossus, fetch_text, fetch_web, fetch_youtube,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the full Gavin Baker transcript corpus")
    parser.add_argument("--force", action="store_true", help="re-download existing files")
    parser.add_argument("--whisper", action="store_true", help="also run Step 5 (Whisper)")
    args = parser.parse_args(argv)

    force = ["--force"] if args.force else []

    print("\n##### Step 1: YouTube #####")
    fetch_youtube.main(force)
    print("\n##### Step 2: Colossus #####")
    fetch_colossus.main(force)
    print("\n##### Step 3: Web writeups #####")
    fetch_web.main(force)
    print("\n##### Step 4: Text interviews #####")
    fetch_text.main(force)
    print("\n##### Step 6: CNBC #####")
    fetch_cnbc.main(force)

    if args.whisper:
        from . import fetch_audio_whisper
        print("\n##### Step 5: Whisper (audio-only) #####")
        fetch_audio_whisper.main(force)

    print("\n##### Master manifest #####")
    build_manifest.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
