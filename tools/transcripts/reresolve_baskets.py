"""Second-pass basket re-resolution over the existing 241 signal events (REVIEW ONLY).

Sends each row of analysis/step4_signal_events_v6_with_returns_extended.csv to
claude-opus-4-6 with a tighter prompt that (1) decides whether the thesis is
actually a trade recommendation (vs. structural observation / market commentary /
private-company talk) and (2) if so, names the precise tickers. Writes a review
artifact — analysis/basket_reresolution.csv — and APPLIES NOTHING. It does not
touch manual_overrides.json, theme_baskets_v3.json, or re-run any pipeline.

One API call per thesis (max per-row attention), run concurrently. Structured
output via output_config.format (json_schema). Adaptive thinking on for the
is-this-a-trade judgment. tickers_implied is enriched from thesis_timeline_v2_flat.

Usage:
    python -m tools.transcripts.reresolve_baskets [--limit N] [--workers K]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import anthropic
import dotenv

from . import targets

MODEL = "claude-opus-4-6"  # operator-chosen ("use opus 4.6")
MAX_TOKENS = 4096
INPUT_COST_PER_MTOK = 5.0
OUTPUT_COST_PER_MTOK = 25.0

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
INPUT_CSV = ANALYSIS_DIR / "step4_signal_events_v6_with_returns_extended.csv"
TIMELINE_FLAT = ANALYSIS_DIR / "thesis_timeline_v2_flat.json"
OUTPUT_CSV = ANALYSIS_DIR / "basket_reresolution.csv"

OUTPUT_FIELDS = [
    "date", "theme", "mention_number",
    "old_basket", "old_source", "old_direction",
    "new_basket", "new_source", "new_direction", "new_reasoning",
    "changed", "override_exists",
]

SYSTEM_PROMPT = """\
You are reviewing a thesis statement made by hedge fund manager Gavin Baker in a public \
appearance. Your job is to determine two things.

1. IS THIS A TRADE RECOMMENDATION?

A thesis is a trade recommendation ONLY if Baker is arguing that a specific stock or set of \
stocks should be bought or sold, or if the clear implication of his argument is that specific \
companies will benefit or suffer and an investor should act.

A thesis is NOT a trade recommendation if it is:
- A structural observation about the industry ("only three chip architectures have been used for training")
- A market-level opinion ("AI is not a bubble", "scaling laws are intact", "capex will have positive ROI")
- A risk warning or concern without a directional trade ("Microsoft flinched on capex")
- Commentary on private companies with no public ticker (xAI, OpenAI, Anthropic, SpaceX before its IPO)
- A prediction about technology trends without naming beneficiaries
- An observation that could support either long or short positions equally

If it is not a trade recommendation: is_trade=false, basket="NO_BASKET", direction="NONE", source="NONE".

2. IF IT IS A TRADE RECOMMENDATION, WHAT ARE THE TICKERS?

Include every ticker that Baker named explicitly OR that is the only reasonable public expression \
of his argument. Do not add tickers he did not name or imply just because they are in the same sector.

Rules:
- If he names tickers, use exactly those tickers. Do not add extras, do not subtract any.
- If he names a company by name but not ticker, resolve to the ticker.
- If he describes a category with only one or two public companies that fit, those are implied \
(e.g., "semicap equipment" = ASML, LRCX, AMAT, KLAC; "neoclouds" = CRWV, NBIS).
- If the thesis is bullish on a category with many possible names and he doesn't narrow it, the \
thesis is too vague to resolve. Return NO_BASKET.
- If the thesis names both winners and losers, it is a PAIR_TRADE. Set direction="PAIR_TRADE" and \
write the basket string as "LONG <tickers> / SHORT <tickers>".
- Google TPUs: if the thesis is about Google's TPU advantage, the beneficiary is GOOGL, not NVDA.
- "AI infrastructure beneficiaries" without specifics = NO_BASKET (too broad).
- "Nvidia's CUDA moat" = NVDA. "GPU demand" without naming Nvidia = NO_BASKET.

Also determine:
- direction: LONG, SHORT, MIXED, PAIR_TRADE, or NONE
- source: BAKER_NAMED (he said specific tickers/company names), OBVIOUS_UNIVERSE (he described a \
category with a small, obvious set of public companies), CONSTRUCTED (you inferred tickers from a \
broader theme description -- use sparingly, and it means a human should review), or NONE.

Use confidence as a prior (moderate theses are more likely to be commentary; high-conviction theses \
with named tickers are almost always real trades), but let the summary content decide.

Return the basket as a comma-separated ticker string (e.g., "ASML, LRCX, AMAT, KLAC"), or "NO_BASKET", \
or the "LONG .. / SHORT .." form for a pair trade. Put your justification in reasoning."""

USER_TEMPLATE = """\
THEME (pipeline cluster): {theme}
DATE: {date}
VENUE/SOURCE: {venue}
CONFIDENCE: {confidence}
CURRENT (pipeline) basket_direction: {basket_direction}

SUMMARY: {summary}

EXPANDED SUMMARY: {summary_extended}

TICKERS the pipeline tagged as directly named: {tickers_direct}
TICKERS the pipeline tagged as implied: {tickers_implied}

Decide is_trade, basket, direction, source, reasoning."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "is_trade": {"type": "boolean"},
        "basket": {"type": "string"},
        "direction": {"type": "string",
                      "enum": ["LONG", "SHORT", "MIXED", "PAIR_TRADE", "NONE"]},
        "source": {"type": "string",
                   "enum": ["BAKER_NAMED", "OBVIOUS_UNIVERSE", "CONSTRUCTED", "NONE"]},
        "reasoning": {"type": "string"},
    },
    "required": ["is_trade", "basket", "direction", "source", "reasoning"],
    "additionalProperties": False,
}

_print_lock = threading.Lock()


def load_api_key() -> str:
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key.startswith("sk-ant-"):
        raise SystemExit(f"ANTHROPIC_API_KEY missing/invalid (got {key[:8]!r}...).")
    return key


def _norm_basket(s: str) -> str:
    """Normalize a basket string to a comparable key (sorted upper tickers)."""
    s = (s or "").strip()
    if not s or s.upper() in {"NO_BASKET", "NONE", ""}:
        return "NO_BASKET"
    if "/" in s or s.upper().startswith("LONG") or "SHORT" in s.upper():
        return "PAIR:" + " ".join(s.upper().split())
    parts = [p.strip().upper() for p in s.replace(";", ",").split(",") if p.strip()]
    return ",".join(sorted(parts))


def build_implied_lookup() -> dict[tuple[str, str], list[str]]:
    """(date, summary) -> tickers_implied_original, from the audited timeline."""
    tl = json.loads(TIMELINE_FLAT.read_text())
    out: dict[tuple[str, str], list[str]] = {}
    for e in tl:
        key = (str(e.get("date", "")), str(e.get("summary", "")))
        if key not in out:
            out[key] = list(e.get("tickers_implied_original", []) or [])
    return out


def reresolve_one(
    client: anthropic.Anthropic, row: dict[str, str], implied: list[str]
) -> dict[str, Any]:
    user = USER_TEMPLATE.format(
        theme=row["theme"], date=row["date"], venue=row.get("source", ""),
        confidence=row.get("confidence", ""), basket_direction=row.get("basket_direction", ""),
        summary=row.get("summary", ""), summary_extended=row.get("summary_extended", ""),
        tickers_direct=row.get("tickers_direct", "") or "(none)",
        tickers_implied=", ".join(implied) or "(none)",
    )
    resp = client.messages.create(
        model=MODEL, max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    verdict = json.loads(text)
    usage = (resp.usage.input_tokens, resp.usage.output_tokens)

    old_basket, old_source, old_dir = (
        row.get("resolved_basket", ""), row.get("basket_source", ""),
        row.get("basket_direction", ""),
    )
    new_basket = verdict["basket"] if verdict["is_trade"] else "NO_BASKET"
    new_source, new_dir = verdict["source"], verdict["direction"]
    changed = (
        _norm_basket(new_basket) != _norm_basket(old_basket)
        or new_source != old_source or new_dir != old_dir
    )
    return {
        "row": {
            "date": row["date"], "theme": row["theme"],
            "mention_number": row.get("mention_number", ""),
            "old_basket": old_basket, "old_source": old_source, "old_direction": old_dir,
            "new_basket": new_basket, "new_source": new_source, "new_direction": new_dir,
            "new_reasoning": verdict["reasoning"],
            "changed": "YES" if changed else "NO",
            "override_exists": "YES" if (row.get("override_note") or "").strip() else "NO",
        },
        "usage": usage,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    client = anthropic.Anthropic(api_key=load_api_key(), max_retries=4)
    implied_lookup = build_implied_lookup()
    rows = list(csv.DictReader(INPUT_CSV.open()))
    if args.limit:
        rows = rows[: args.limit]
    print(f"Re-resolving {len(rows)} events with {MODEL} ({args.workers} workers)...")

    results: dict[int, dict[str, str]] = {}
    errors: list[str] = []
    tot_in = tot_out = 0
    done = 0

    def work(i: int, row: dict[str, str]) -> tuple[int, dict[str, Any] | None, str | None]:
        implied = implied_lookup.get((row["date"], row.get("summary", "")), [])
        try:
            return i, reresolve_one(client, row, implied), None
        except Exception as exc:  # noqa: BLE001 — record per-row, don't kill the batch
            return i, None, f"{exc.__class__.__name__}: {exc}"

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, i, r) for i, r in enumerate(rows)]
        for fut in as_completed(futs):
            i, res, err = fut.result()
            done += 1
            if res is None:
                errors.append(f"row {i} ({rows[i]['date']} {rows[i]['theme']}): {err}")
                results[i] = {
                    "date": rows[i]["date"], "theme": rows[i]["theme"],
                    "mention_number": rows[i].get("mention_number", ""),
                    "old_basket": rows[i].get("resolved_basket", ""),
                    "old_source": rows[i].get("basket_source", ""),
                    "old_direction": rows[i].get("basket_direction", ""),
                    "new_basket": "ERROR", "new_source": "ERROR", "new_direction": "ERROR",
                    "new_reasoning": err or "", "changed": "ERROR",
                    "override_exists": "YES" if (rows[i].get("override_note") or "").strip() else "NO",
                }
            else:
                results[i] = res["row"]
                tot_in += res["usage"][0]
                tot_out += res["usage"][1]
            if done % 20 == 0 or done == len(rows):
                with _print_lock:
                    print(f"  [{done}/{len(rows)}] ~${tot_in/1e6*INPUT_COST_PER_MTOK + tot_out/1e6*OUTPUT_COST_PER_MTOK:.2f}")

    # changed=YES first, then by date
    ordered = sorted(
        (results[i] for i in range(len(rows))),
        key=lambda r: (0 if r["changed"] == "YES" else (2 if r["changed"] == "ERROR" else 1), r["date"]),
    )
    with OUTPUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        w.writeheader()
        w.writerows(ordered)

    n_changed = sum(1 for r in ordered if r["changed"] == "YES")
    cost = tot_in / 1e6 * INPUT_COST_PER_MTOK + tot_out / 1e6 * OUTPUT_COST_PER_MTOK
    print(f"\nDone: {len(rows)} rows, {n_changed} changed, {len(errors)} errors.")
    print(f"Tokens: {tot_in:,} in + {tot_out:,} out  ~${cost:.2f}  -> {OUTPUT_CSV}")
    if errors:
        print("Errors:")
        for e in errors[:20]:
            print(f"  {e}")


if __name__ == "__main__":
    main()
