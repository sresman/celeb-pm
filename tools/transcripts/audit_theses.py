"""Audit each extracted thesis: expand the summary, clean the ticker set, recover
the dropped detail fields, and emit thesis_timeline_v2.json + _flat.json.

Model: claude-sonnet-4-6. Output is enforced against AUDIT_SCHEMA via the Messages
API `output_config.format`, so each response is guaranteed valid JSON. Mirrors the
conventions of extract_theses.py (`.env` override loader, one manual retry after
30s on top of SDK auto-retry, 2s pacing, cost tracking, a _log.json summary).

The per-transcript extraction JSONs in analysis/thesis_extractions/ are the source
of truth for detail / confidence_evidence / quote_fragment / time_horizon /
contrarian — fields that aggregate_theses.py dropped from thesis_timeline.json.

Usage:
    python -m tools.transcripts.audit_theses [--force] [--limit N] [--single IDX]

Options:
    --force     Re-audit even if the per-thesis audit JSON already exists
    --limit N   Process only the first N theses (chronological)
    --single    Process one thesis by its 0-based index in the sorted timeline
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import anthropic
import dotenv

from . import targets
from .audit_prompt import AUDIT_SCHEMA, SYSTEM_PROMPT, USER_TEMPLATE
from .common import relpath

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
SLEEP_BETWEEN = 2.0  # seconds, polite pacing on top of SDK auto-retry
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0

DIRECT_CLASSES = ("DIRECT_SUBJECT", "DIRECT_BENEFICIARY")

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
EXTRACTIONS_DIR = ANALYSIS_DIR / "thesis_extractions"
AUDITS_DIR = ANALYSIS_DIR / "thesis_audits"
TIMELINE_V1 = ANALYSIS_DIR / "thesis_timeline.json"
TIMELINE_V2 = ANALYSIS_DIR / "thesis_timeline_v2.json"
TIMELINE_V2_FLAT = ANALYSIS_DIR / "thesis_timeline_v2_flat.json"
LOG_PATH = ANALYSIS_DIR / "_audit_log.json"


def load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from .env with override (shell var is a placeholder)."""
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key.startswith("sk-ant-"):
        raise SystemExit(
            "ANTHROPIC_API_KEY missing or not a real key (got "
            f"{key[:8]!r}...). The real key must be in .env (sk-ant-...)."
        )
    return key


def _source_label(stem: str, date: str) -> str:
    """Extraction filename stem with the leading '{date}_' stripped."""
    prefix = f"{date}_"
    return stem[len(prefix):] if stem.startswith(prefix) else stem


def _thesis_sort_key(row: dict[str, Any]) -> tuple[str, str, int]:
    """Sort by date, then source, then numeric thesis id (T1 < T2 < T10)."""
    tid = str(row.get("thesis_id") or "")
    num = int(tid[1:]) if tid[1:].isdigit() else 0
    return (row.get("date") or "", row.get("source") or "", num)


def load_source_theses() -> list[dict[str, Any]]:
    """Flatten all extraction JSONs into per-thesis rows with source metadata."""
    rows: list[dict[str, Any]] = []
    for path in sorted(EXTRACTIONS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        meta = data.get("metadata", {})
        date = meta.get("date", "")
        src = meta.get("source", "")
        topic = meta.get("topic", "")
        source = f"{src} — {topic}" if topic else src
        source_label = _source_label(path.stem, date)
        for t in data.get("theses", []):
            rows.append({
                "date": date,
                "source": source,
                "source_label": source_label,
                "thesis": t,
            })
    rows.sort(key=lambda r: _thesis_sort_key(
        {"date": r["date"], "source": r["source"], "thesis_id": r["thesis"].get("id")}
    ))
    return rows


def _audit_path(row: dict[str, Any]) -> Path:
    tid = row["thesis"].get("id", "T?")
    return AUDITS_DIR / f"{row['date']}_{row['source_label']}_{tid}.json"


def _call(client: anthropic.Anthropic, user_content: str) -> Any:
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": AUDIT_SCHEMA}},
    )


def _save_raw(out_path: Path, resp: Any, text: str | None = None) -> None:
    raw_path = out_path.with_suffix(".raw.txt")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    content = text if text is not None else "\n".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    )
    raw_path.write_text(content or "(no text content)", encoding="utf-8")


def _build_v2_entry(row: dict[str, Any], audit: dict[str, Any]) -> dict[str, Any]:
    """Assemble the timeline_v2 object from the source thesis + audit result."""
    t = row["thesis"]
    audited: list[dict[str, Any]] = audit.get("tickers_audited", [])

    def _dedup(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    tickers_direct = _dedup(
        a["ticker"] for a in audited if a.get("classification") in DIRECT_CLASSES
    )
    tickers_subject = _dedup(
        a["ticker"] for a in audited if a.get("classification") == "DIRECT_SUBJECT"
    )
    return {
        "date": row["date"],
        "source": row["source"],
        "thesis_id": t.get("id"),
        "summary": t.get("summary"),
        "summary_extended": audit.get("summary_extended"),
        "detail": t.get("detail"),
        "confidence": t.get("confidence"),
        "confidence_evidence": t.get("confidence_evidence"),
        "themes": t.get("themes", []),
        "time_horizon": t.get("time_horizon"),
        "contrarian": t.get("contrarian"),
        "quote_fragment": t.get("quote_fragment"),
        "tickers_named_original": t.get("tickers_named", []),
        "tickers_direct": tickers_direct,
        "tickers_subject": tickers_subject,
        "tickers_implied_original": t.get("tickers_implied", []),
        "ticker_audit": audited,
    }


def audit_one(
    client: anthropic.Anthropic, row: dict[str, Any], *, force: bool
) -> dict[str, Any]:
    """Audit one thesis. Writes the per-thesis v2 entry and returns a log row."""
    t = row["thesis"]
    out_path = _audit_path(row)
    log: dict[str, Any] = {
        "date": row["date"], "source_label": row["source_label"],
        "thesis_id": t.get("id"), "output": relpath(out_path), "status": "",
        "input_tokens": 0, "output_tokens": 0,
    }

    if out_path.exists() and not force:
        log["status"] = "skipped_exists"
        return log

    user_content = USER_TEMPLATE.format(
        source=row["source"], date=row["date"],
        summary=t.get("summary", ""), detail=t.get("detail", ""),
        confidence=t.get("confidence", ""),
        confidence_evidence=t.get("confidence_evidence", ""),
        quote_fragment=t.get("quote_fragment", ""),
        themes=", ".join(t.get("themes", [])),
        time_horizon=t.get("time_horizon", ""),
        contrarian=t.get("contrarian", ""),
        tickers_named=", ".join(t.get("tickers_named", [])) or "(none)",
        tickers_implied=", ".join(t.get("tickers_implied", [])) or "(none)",
    )

    # API call with one extra manual retry after 30s (SDK already retries 429/5xx).
    resp = None
    for attempt in range(2):
        try:
            resp = _call(client, user_content)
            break
        except anthropic.APIError as exc:
            if attempt == 0:
                log.setdefault("warnings", []).append(f"retry after error: {exc}")
                time.sleep(30)
                continue
            log["status"] = f"api_error: {exc}"
            return log

    assert resp is not None
    log["input_tokens"] = resp.usage.input_tokens
    log["output_tokens"] = resp.usage.output_tokens

    if resp.stop_reason == "refusal":
        log["status"] = "refusal"
        _save_raw(out_path, resp)
        return log

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        audit = json.loads(text)
    except json.JSONDecodeError as exc:
        log["status"] = f"json_parse_error: {exc}"
        _save_raw(out_path, resp, text=text)
        return log

    entry = _build_v2_entry(row, audit)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    log["status"] = "ok"
    if resp.stop_reason == "max_tokens":
        log.setdefault("warnings", []).append("hit max_tokens")
    return log


def rebuild_timelines() -> int:
    """Reassemble thesis_timeline_v2.json + _flat.json from all on-disk audits."""
    entries = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(AUDITS_DIR.glob("*.json"))
    ]
    entries.sort(key=_thesis_sort_key)
    payload = json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
    # v2.json mirrors v1's flat chronological shape; _flat.json is the identical
    # flat list the signal-event generator consumes (same fields, per spec).
    TIMELINE_V2.write_text(payload, encoding="utf-8")
    TIMELINE_V2_FLAT.write_text(payload, encoding="utf-8")
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit extracted theses")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--single", type=int, default=None,
        help="0-based index into the sorted timeline",
    )
    args = parser.parse_args(argv)

    client = anthropic.Anthropic(api_key=load_api_key(), max_retries=3)
    AUDITS_DIR.mkdir(parents=True, exist_ok=True)

    rows = load_source_theses()

    # Cross-reference against the v1 timeline count (should be 319).
    if TIMELINE_V1.exists():
        v1_count = len(json.loads(TIMELINE_V1.read_text(encoding="utf-8")))
        if v1_count != len(rows):
            print(f"WARNING: {len(rows)} theses in extractions != {v1_count} in "
                  f"{relpath(TIMELINE_V1)} — proceeding with extractions as truth.")

    selected = rows
    if args.single is not None:
        if not 0 <= args.single < len(rows):
            raise SystemExit(f"--single {args.single} out of range 0..{len(rows) - 1}")
        selected = [rows[args.single]]
    elif args.limit:
        selected = rows[: args.limit]

    logs: list[dict[str, Any]] = []
    total_in = total_out = 0
    for idx, row in enumerate(selected, 1):
        log = audit_one(client, row, force=args.force)
        logs.append(log)
        total_in += log["input_tokens"]
        total_out += log["output_tokens"]
        print(f"[{idx}/{len(selected)}] {log['date']}_{log['source_label']}_"
              f"{log['thesis_id']} — {log['status']}")
        if log["status"] not in ("skipped_exists",):
            time.sleep(SLEEP_BETWEEN)

    total_entries = rebuild_timelines()

    # Length + ticker-audit stats over the theses processed this run.
    orig_lens: list[int] = []
    ext_lens: list[int] = []
    tangential = added = 0
    for row in selected:
        p = _audit_path(row)
        if not p.exists():
            continue
        e = json.loads(p.read_text(encoding="utf-8"))
        orig_lens.append(len(e.get("summary") or ""))
        ext_lens.append(len(e.get("summary_extended") or ""))
        for a in e.get("ticker_audit", []):
            if a.get("classification") == "TANGENTIAL":
                tangential += 1
            if not a.get("was_original", True):
                added += 1

    cost = total_in / 1e6 * INPUT_COST_PER_MTOK + total_out / 1e6 * OUTPUT_COST_PER_MTOK
    n_ok = sum(1 for r in logs if r["status"] == "ok")
    n_skipped = sum(1 for r in logs if r["status"] == "skipped_exists")
    errors = [r for r in logs if r["status"] not in ("ok", "skipped_exists")]
    avg_orig = sum(orig_lens) / len(orig_lens) if orig_lens else 0
    avg_ext = sum(ext_lens) / len(ext_lens) if ext_lens else 0

    summary = {
        "model": MODEL,
        "theses_selected": len(selected),
        "ok": n_ok,
        "skipped": n_skipped,
        "errors": errors,
        "tickers_removed_tangential": tangential,
        "tickers_added": added,
        "avg_summary_len": round(avg_orig, 1),
        "avg_summary_extended_len": round(avg_ext, 1),
        "timeline_v2_entries": total_entries,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "estimated_cost_usd": round(cost, 4),
        "rows": logs,
    }
    LOG_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(f"\nDone: {n_ok} ok, {n_skipped} skipped, {len(errors)} errors")
    print(f"Tickers: {tangential} tangential removed, {added} added")
    print(f"Summary length: {avg_orig:.0f} -> {avg_ext:.0f} chars (avg)")
    print(f"timeline_v2 entries: {total_entries}  -> {relpath(TIMELINE_V2)}")
    print(f"Tokens: {total_in:,} in + {total_out:,} out  ~${cost:.2f}  "
          f"-> {relpath(LOG_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
