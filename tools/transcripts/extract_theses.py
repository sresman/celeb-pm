"""Send each transcript to Claude for structured thesis extraction.

Model: claude-sonnet-4-6. Output is enforced against EXTRACTION_SCHEMA via the
Messages API `output_config.format`, so each response is guaranteed valid JSON.

Usage:
    python -m tools.transcripts.extract_theses [--force] [--limit N] [--single PATH]

Options:
    --force     Re-extract even if output JSON already exists
    --limit N   Process only the first N transcripts (chronological)
    --single    Process one specific transcript file (path), ignore the manifest order

Note: a 50%-cheaper Batch API path exists, but with 27 small calls (~$2) the
synchronous per-file flow (with progress + cost tracking) is simpler.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import anthropic
import dotenv

from . import targets
from .common import relpath
from .extraction_prompt import EXTRACTION_SCHEMA, SYSTEM_PROMPT, USER_TEMPLATE

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_TOKENS_RETRY = 16000
MAX_TRANSCRIPT_CHARS = 150_000
SLEEP_BETWEEN = 2.0  # seconds, polite pacing on top of SDK auto-retry
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
EXTRACTIONS_DIR = ANALYSIS_DIR / "thesis_extractions"
LOG_PATH = ANALYSIS_DIR / "_extraction_log.json"


def load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from .env with override (shell var is a placeholder)."""
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    import os

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key.startswith("sk-ant-"):
        raise SystemExit(
            "ANTHROPIC_API_KEY missing or not a real key (got "
            f"{key[:8]!r}...). The real key must be in .env (sk-ant-...)."
        )
    return key


def _strip_header(text: str) -> str:
    """Drop the leading '# ...' comment header block; return the transcript body."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("#") or lines[i].strip() == ""):
        i += 1
    return "\n".join(lines[i:]).strip()


def _counts(data: dict[str, Any]) -> str:
    return (
        f"{len(data.get('theses', []))} theses, "
        f"{len(data.get('explicit_recommendations', []))} recommendations, "
        f"{len(data.get('catalysts', []))} catalysts"
    )


def _call(client: anthropic.Anthropic, user_content: str, max_tokens: int) -> Any:
    return client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
    )


def extract_one(
    client: anthropic.Anthropic, entry: dict[str, Any], *, force: bool
) -> dict[str, Any]:
    """Extract one transcript. Returns a log row."""
    date = entry["date"]
    label = entry["label"]
    out_path = EXTRACTIONS_DIR / f"{date}_{label}.json"
    row: dict[str, Any] = {
        "label": label, "date": date, "source": entry.get("source"),
        "filepath": entry.get("filepath"), "output": relpath(out_path), "status": "",
        "input_tokens": 0, "output_tokens": 0,
    }

    if out_path.exists() and not force:
        row["status"] = "skipped_exists"
        return row

    src_path = targets.REPO_ROOT / entry["filepath"]
    if not src_path.exists():
        row["status"] = "source_missing"
        return row

    body = _strip_header(src_path.read_text(encoding="utf-8"))
    if len(body) > MAX_TRANSCRIPT_CHARS:
        body = body[:MAX_TRANSCRIPT_CHARS] + "\n\n[TRANSCRIPT TRUNCATED FOR LENGTH]"
        row["truncated"] = True

    user_content = USER_TEMPLATE.format(
        source=entry.get("source", ""), date=date, host=entry.get("host", ""),
        topic=entry.get("topic", ""), quality=entry.get("quality", ""),
        transcript_text=body,
    )

    # API call with one extra manual retry after 30s (SDK already retries 429/5xx).
    resp = None
    for attempt in range(2):
        try:
            resp = _call(client, user_content, MAX_TOKENS)
            if resp.stop_reason == "max_tokens":
                resp = _call(client, user_content, MAX_TOKENS_RETRY)
            break
        except anthropic.APIError as exc:
            if attempt == 0:
                row.setdefault("warnings", []).append(f"retry after error: {exc}")
                time.sleep(30)
                continue
            row["status"] = f"api_error: {exc}"
            return row

    assert resp is not None
    row["input_tokens"] = resp.usage.input_tokens
    row["output_tokens"] = resp.usage.output_tokens

    if resp.stop_reason == "refusal":
        row["status"] = "refusal"
        _save_raw(out_path, resp)
        return row

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        row["status"] = f"json_parse_error: {exc}"
        _save_raw(out_path, resp, text=text)
        return row

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    row["status"] = "ok"
    row["counts"] = _counts(data)
    if resp.stop_reason == "max_tokens":
        row.setdefault("warnings", []).append("hit max_tokens even after retry")
    return row


def _save_raw(out_path: Path, resp: Any, text: str | None = None) -> None:
    raw_path = out_path.with_suffix(".raw.txt")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    content = text if text is not None else "\n".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    )
    raw_path.write_text(content or "(no text content)", encoding="utf-8")


def _load_manifest() -> list[dict[str, Any]]:
    data = json.loads(targets.MASTER_MANIFEST.read_text(encoding="utf-8"))
    return sorted(data, key=lambda r: (r.get("date") or "", r.get("label") or ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract structured theses from transcripts")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--single", type=str, default=None, help="path to one transcript .txt")
    args = parser.parse_args(argv)

    client = anthropic.Anthropic(api_key=load_api_key(), max_retries=3)
    EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

    entries = _load_manifest()
    if args.single:
        target = str(Path(args.single))
        entries = [e for e in entries if e["filepath"] == target
                   or e["filepath"].endswith(Path(args.single).name)]
        if not entries:
            raise SystemExit(f"No manifest entry matches {args.single}")
    if args.limit:
        entries = entries[: args.limit]

    rows: list[dict[str, Any]] = []
    total_in = total_out = 0
    for idx, entry in enumerate(entries, 1):
        row = extract_one(client, entry, force=args.force)
        rows.append(row)
        total_in += row["input_tokens"]
        total_out += row["output_tokens"]
        detail = row.get("counts", row["status"])
        print(f"[{idx}/{len(entries)}] {row['date']}_{row['label']} — {detail}")
        if row["status"] not in ("skipped_exists",):
            time.sleep(SLEEP_BETWEEN)

    cost = total_in / 1e6 * INPUT_COST_PER_MTOK + total_out / 1e6 * OUTPUT_COST_PER_MTOK
    n_ok = sum(1 for r in rows if r["status"] == "ok")
    n_skipped = sum(1 for r in rows if r["status"] == "skipped_exists")
    errors = [r for r in rows if r["status"] not in ("ok", "skipped_exists")]
    summary = {
        "model": MODEL,
        "transcripts_processed": len(rows),
        "ok": n_ok,
        "skipped": n_skipped,
        "errors": errors,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "estimated_cost_usd": round(cost, 4),
        "rows": rows,
    }
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"\nDone: {n_ok} ok, {n_skipped} skipped, {len(errors)} errors")
    print(f"Tokens: {total_in:,} in + {total_out:,} out  ~${cost:.2f}  -> {relpath(LOG_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
