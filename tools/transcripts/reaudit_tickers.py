"""Stricter, removal-only SECOND-pass ticker audit of contaminated theses.

The first pass (audit_theses.py) was too lenient: it left mega-cap tickers in
``tickers_direct`` that Baker mentioned somewhere in the same transcript but not
specifically in connection with a given thesis. On general structural theses this
bleeds a whole sector's worth of tickers in, misfiring the FIRST_MENTION_WITH_TICKERS
signal events downstream.

This pass re-audits ONLY the contaminated theses with a much stricter prompt and
REMOVES (never adds) tickers. It updates all three on-disk representations so they
stay consistent:
  - analysis/thesis_timeline_v2.json + _flat.json  (rewritten in place)
  - analysis/thesis_audits/*.json                  (the source-of-truth that
    audit_theses.rebuild_timelines() reassembles from — patched so a future rebuild
    reproduces the cleaned timelines rather than silently reverting this pass)
  - analysis/thesis_reaudits/*.json                (per-thesis re-audit record)

Re-audit set = A OR B OR C:
  A: len(tickers_direct) >= 5
  B: >= 2 mega-cap tickers in tickers_direct whose symbol AND name-variants are
     absent from summary + summary_extended (case-insensitive)
  C: any ETF ticker (SMH/SOXX/QQQ/XLK) in tickers_direct

Model: claude-sonnet-4-6, output enforced against REAUDIT_SCHEMA. Mirrors the
audit_theses.py conventions (.env override loader, one manual 30s retry, 2s pacing,
cost tracking, a _reaudit_log.json summary).

Usage:
    python -m tools.transcripts.reaudit_tickers [--force] [--limit N] [--single IDX]

Options:
    --force     Re-call the model even if the per-thesis reaudit JSON already exists
    --limit N   Process only the first N theses of the re-audit set
    --single    Process one thesis by its 0-based index into the FLAT timeline
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import anthropic
import dotenv

from . import targets
from .common import relpath

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 2048
SLEEP_BETWEEN = 2.0  # seconds, polite pacing on top of SDK auto-retry
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0

# --- Paths -------------------------------------------------------------------
ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
AUDITS_DIR = ANALYSIS_DIR / "thesis_audits"
REAUDITS_DIR = ANALYSIS_DIR / "thesis_reaudits"
TIMELINE_V2 = ANALYSIS_DIR / "thesis_timeline_v2.json"
TIMELINE_V2_FLAT = ANALYSIS_DIR / "thesis_timeline_v2_flat.json"
LOG_PATH = ANALYSIS_DIR / "_reaudit_log.json"

# --- Re-audit set selection --------------------------------------------------
CRITERION_A_MIN_DIRECT = 5
CRITERION_B_MIN_ABSENT_MEGA = 2

# Mega-cap symbol -> lowercase name variants to look for in the thesis text.
MEGA_CAPS: dict[str, tuple[str, ...]] = {
    "NVDA": ("nvidia",),
    "AMD": ("amd", "advanced micro"),
    "INTC": ("intel",),
    "GOOGL": ("google", "alphabet"),
    "AMZN": ("amazon",),
    "MSFT": ("microsoft",),
    "META": ("meta", "facebook"),
    "AAPL": ("apple",),
    "TSM": ("tsmc", "taiwan semi"),
    "ASML": ("asml",),
    "AVGO": ("broadcom",),
    "TSLA": ("tesla",),
    "NFLX": ("netflix",),
    "CRM": ("salesforce",),
    "ORCL": ("oracle",),
}

# ETFs are never a direct subject/beneficiary of a specific thesis (Criterion C).
ETF_TICKERS: frozenset[str] = frozenset({"SMH", "SOXX", "QQQ", "XLK"})

TANGENTIAL = "TANGENTIAL"


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


# ---------------------------------------------------------------------------
# Prompt + schema (strict, removal-only)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are performing a STRICT ticker audit on an investment thesis extracted from a transcript of Gavin Baker (Atreides Management).

The previous audit was too lenient — it left tickers in tickers_direct that Baker mentioned in the same interview but NOT specifically in connection with this particular thesis. Your job is to be aggressive about removing these.

THE CRITICAL TEST for each ticker: Did Baker specifically say THIS TICKER benefits from or is affected by THIS SPECIFIC THESIS? Not "he mentioned it in the same interview." Not "it's in the same sector." Not "it's an obvious beneficiary of the general theme." He must have SPECIFICALLY CONNECTED this ticker to this exact claim.

Rules:
- If the thesis is a GENERAL STRUCTURAL VIEW (e.g., "semiconductor intensity is increasing," "AI capex ROI is positive," "scaling laws are intact"), tickers_direct should be EMPTY unless Baker specifically named companies as beneficiaries of that exact structural claim.
- If Baker said "Nvidia" while discussing DRAM bottlenecks, Nvidia is TANGENTIAL to the DRAM thesis — it's a GPU company, not a memory company. Remove it.
- If Baker said "Google, Meta, Microsoft, Amazon" while discussing hyperscaler capex ROI, those ARE the subject — keep them.
- ETF tickers (SMH, SOXX, QQQ) are NEVER direct subjects or beneficiaries of a specific thesis. Always TANGENTIAL.
- Non-US tickers (000660.KS, HXSCL, SNE, NTDOY) should be kept ONLY if they are the genuine subject of the thesis.
- "DIRECT_BENEFICIARY" means the company's REVENUE OR STOCK PRICE would specifically move because of this thesis, not just that they're in a related industry.

When in doubt, REMOVE. A false negative (missing a legitimately connected ticker) is far less harmful than a false positive (a contaminated ticker misfiring a signal event).

Output valid JSON matching the schema. No preamble."""

USER_TEMPLATE = """\
Thesis to re-audit:

Date: {date}
Source: {source}
Summary: {summary}
Summary Extended: {summary_extended}

Current tickers_direct: {tickers_direct}
Current tickers_subject: {tickers_subject}
Current ticker_audit (from first pass): {ticker_audit}

For each ticker currently in tickers_direct, classify as:
- KEEP: Baker specifically connected this ticker to this exact thesis
- REMOVE: Ticker was mentioned in the same interview but not specifically connected to this thesis

Do NOT add new tickers. This is a removal-only pass."""


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    """Object schema with all keys required + additionalProperties false."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


REAUDIT_SCHEMA: dict[str, Any] = _obj({
    "tickers_audited": {"type": "array", "items": _obj({
        "ticker": {"type": "string"},
        "action": {"type": "string", "enum": ["KEEP", "REMOVE"]},
        "reasoning": {"type": "string"},
    })},
})


# ---------------------------------------------------------------------------
# Re-audit set selection
# ---------------------------------------------------------------------------
def _text_blob(entry: dict[str, Any]) -> str:
    return f"{entry.get('summary') or ''} {entry.get('summary_extended') or ''}".lower()


def _mega_absent(ticker: str, blob: str) -> bool:
    """True if a mega-cap's symbol AND all its name-variants are absent from the text."""
    if ticker.lower() in blob:
        return False
    return not any(v in blob for v in MEGA_CAPS.get(ticker, ()))


def selection_reason(entry: dict[str, Any]) -> str | None:
    """Return a '+'-joined reason string if the thesis is in the re-audit set, else None."""
    direct = entry.get("tickers_direct") or []
    reasons: list[str] = []
    if len(direct) >= CRITERION_A_MIN_DIRECT:
        reasons.append("A")
    blob = _text_blob(entry)
    absent_mega = [t for t in direct if t in MEGA_CAPS and _mega_absent(t, blob)]
    if len(absent_mega) >= CRITERION_B_MIN_ABSENT_MEGA:
        reasons.append("B")
    if set(direct) & ETF_TICKERS:
        reasons.append("C")
    return "+".join(reasons) if reasons else None


# ---------------------------------------------------------------------------
# Matching flat entries back to their thesis_audits/*.json source files
# ---------------------------------------------------------------------------
def _content_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    """Stable key over fields this pass never mutates (unique across all 319)."""
    return (
        entry.get("date") or "",
        entry.get("source") or "",
        str(entry.get("thesis_id") or ""),
        (entry.get("summary") or "")[:60],
    )


def build_audit_index() -> dict[tuple[str, str, str, str], Path]:
    """Map each on-disk audit file's content-key to its path (for consistent writeback)."""
    index: dict[tuple[str, str, str, str], Path] = {}
    for p in sorted(AUDITS_DIR.glob("*.json")):
        entry = json.loads(p.read_text(encoding="utf-8"))
        key = _content_key(entry)
        if key in index:
            raise SystemExit(f"Duplicate content-key {key} in audits — cannot match uniquely.")
        index[key] = p
    return index


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------
def _call(client: anthropic.Anthropic, user_content: str) -> Any:
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": REAUDIT_SCHEMA}},
    )


def _reaudit_the_thesis(
    client: anthropic.Anthropic, entry: dict[str, Any], log: dict[str, Any]
) -> list[dict[str, Any]] | None:
    """Call the model for one thesis. Returns the tickers_audited list, or None on error."""
    user_content = USER_TEMPLATE.format(
        date=entry.get("date", ""),
        source=entry.get("source", ""),
        summary=entry.get("summary", ""),
        summary_extended=entry.get("summary_extended", ""),
        tickers_direct=", ".join(entry.get("tickers_direct", [])) or "(none)",
        tickers_subject=", ".join(entry.get("tickers_subject", [])) or "(none)",
        ticker_audit=json.dumps(entry.get("ticker_audit", []), ensure_ascii=False),
    )

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
            return None

    assert resp is not None
    log["input_tokens"] = resp.usage.input_tokens
    log["output_tokens"] = resp.usage.output_tokens

    if resp.stop_reason == "refusal":
        log["status"] = "refusal"
        return None

    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        log["status"] = f"json_parse_error: {exc}"
        return None

    if resp.stop_reason == "max_tokens":
        log.setdefault("warnings", []).append("hit max_tokens")
    return list(parsed.get("tickers_audited", []))


# ---------------------------------------------------------------------------
# Apply removals (removal-only, in place)
# ---------------------------------------------------------------------------
def apply_removals(entry: dict[str, Any], audited: list[dict[str, Any]]) -> list[str]:
    """Remove REMOVE-marked tickers from tickers_direct/subject; retag ticker_audit. Idempotent."""
    remove_reason = {
        a["ticker"]: a.get("reasoning", "")
        for a in audited if a.get("action") == "REMOVE"
    }
    if not remove_reason:
        return []

    entry["tickers_direct"] = [t for t in entry.get("tickers_direct", []) if t not in remove_reason]
    entry["tickers_subject"] = [t for t in entry.get("tickers_subject", []) if t not in remove_reason]

    for a in entry.get("ticker_audit", []):
        tk = a.get("ticker")
        if tk in remove_reason and a.get("classification") != TANGENTIAL:
            a["classification"] = TANGENTIAL
            base = (a.get("reasoning") or "").rstrip()
            a["reasoning"] = f"{base} [RE-AUDIT: {remove_reason[tk]}]".strip()
    return list(remove_reason)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-audit contaminated tickers_direct")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--single", type=int, default=None,
        help="0-based index into the flat timeline",
    )
    args = parser.parse_args(argv)

    REAUDITS_DIR.mkdir(parents=True, exist_ok=True)
    flat: list[dict[str, Any]] = json.loads(TIMELINE_V2_FLAT.read_text(encoding="utf-8"))
    audit_index = build_audit_index()

    # Build the re-audit set (indices into the flat list).
    if args.single is not None:
        if not 0 <= args.single < len(flat):
            raise SystemExit(f"--single {args.single} out of range 0..{len(flat) - 1}")
        selected_idx = [args.single]
    else:
        selected_idx = [i for i, e in enumerate(flat) if selection_reason(e) is not None]
        if args.limit:
            selected_idx = selected_idx[: args.limit]

    print(f"Loaded {len(flat)} theses; re-audit set = {len(selected_idx)}.")

    client = anthropic.Anthropic(api_key=load_api_key(), max_retries=3)

    logs: list[dict[str, Any]] = []
    total_in = total_out = 0
    total_removed = total_kept = 0

    for n, idx in enumerate(selected_idx, 1):
        entry = flat[idx]
        key = _content_key(entry)
        audit_path = audit_index.get(key)
        stem = audit_path.stem if audit_path else f"idx{idx}_{entry.get('thesis_id')}"
        reaudit_path = REAUDITS_DIR / f"{stem}.json"

        before = list(entry.get("tickers_direct", []))
        log: dict[str, Any] = {
            "index": idx, "date": entry.get("date"), "thesis_id": entry.get("thesis_id"),
            "criteria": selection_reason(entry), "output": relpath(reaudit_path),
            "status": "", "input_tokens": 0, "output_tokens": 0,
            "n_before": len(before),
        }

        if reaudit_path.exists() and not args.force:
            # Re-apply the stored decision so the timeline write is deterministic
            # even if a prior run crashed mid-write. Idempotent.
            record = json.loads(reaudit_path.read_text(encoding="utf-8"))
            audited = record.get("tickers_audited", [])
            log["status"] = "skipped_exists"
        else:
            audited = _reaudit_the_thesis(client, entry, log)
            if audited is None:
                logs.append(log)
                print(f"[{n}/{len(selected_idx)}] idx{idx} {entry.get('thesis_id')} — {log['status']}")
                total_in += log["input_tokens"]
                total_out += log["output_tokens"]
                continue
            reaudit_path.write_text(json.dumps({
                "date": entry.get("date"), "source": entry.get("source"),
                "thesis_id": entry.get("thesis_id"), "summary": entry.get("summary"),
                "criteria": log["criteria"], "tickers_direct_before": before,
                "tickers_audited": audited,
            }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            log["status"] = "ok"

        removed = apply_removals(entry, audited)

        # Keep the on-disk audit source file consistent with the mutated entry so a
        # future audit_theses.rebuild_timelines() reproduces (not reverts) this pass.
        if audit_path is not None:
            audit_path.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
        else:
            log.setdefault("warnings", []).append("no matching thesis_audits file")

        log["n_after"] = len(entry.get("tickers_direct", []))
        log["removed"] = removed
        total_removed += len(removed)
        total_kept += log["n_after"]
        total_in += log["input_tokens"]
        total_out += log["output_tokens"]
        logs.append(log)
        print(f"[{n}/{len(selected_idx)}] idx{idx} {entry.get('thesis_id')} "
              f"[{log['criteria']}] — {log['status']}: {log['n_before']}->{log['n_after']} "
              f"({len(removed)} removed)")
        if log["status"] != "skipped_exists":
            time.sleep(SLEEP_BETWEEN)

    # Rewrite both timeline files from the mutated flat list (identical content).
    payload = json.dumps(flat, indent=2, ensure_ascii=False) + "\n"
    TIMELINE_V2_FLAT.write_text(payload, encoding="utf-8")
    TIMELINE_V2.write_text(payload, encoding="utf-8")

    cost = total_in / 1e6 * INPUT_COST_PER_MTOK + total_out / 1e6 * OUTPUT_COST_PER_MTOK
    n_ok = sum(1 for r in logs if r["status"] == "ok")
    n_skipped = sum(1 for r in logs if r["status"] == "skipped_exists")
    errors = [r for r in logs if r["status"] not in ("ok", "skipped_exists")]

    summary = {
        "model": MODEL,
        "theses_reaudited": len(selected_idx),
        "ok": n_ok,
        "skipped": n_skipped,
        "errors": errors,
        "tickers_removed": total_removed,
        "tickers_kept": total_kept,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "estimated_cost_usd": round(cost, 4),
        "rows": logs,
    }
    LOG_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\nDone: {n_ok} ok, {n_skipped} skipped, {len(errors)} errors")
    print(f"Tickers: {total_removed} removed, {total_kept} kept across re-audited theses")
    print(f"Timelines rewritten -> {relpath(TIMELINE_V2)} + _flat")
    print(f"Tokens: {total_in:,} in + {total_out:,} out  ~${cost:.2f}  -> {relpath(LOG_PATH)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
