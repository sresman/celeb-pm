"""Prompt + schema for the thesis audit pass (separated for easy iteration).

SYSTEM_PROMPT / USER_TEMPLATE are the operator-authored audit prompt. AUDIT_SCHEMA
is the operator's output shape expressed as a JSON Schema so it can be enforced via
the Messages API `output_config.format` (guaranteeing valid output).

JSON-Schema notes for structured outputs (same rules as extraction_prompt.py):
every object sets `additionalProperties: false` and lists all properties in
`required`. No numeric/length constraints (unsupported and unnecessary here).
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are auditing investment thesis extractions from transcripts of Gavin Baker (Atreides Management). For each thesis, you must do three things:

1. EXPAND THE SUMMARY to 3-5 sentences that capture:
   - The specific claim or structural view (not vague — what exactly is he saying?)
   - The reasoning or evidence he presented (why does he believe this?)
   - The investment implication (what should you buy, sell, or watch?)
   - Any specific numbers, timeframes, or comparisons he cited

   Write in third person ("Baker argues..."). Be precise and specific. A reader should understand the full thesis from the summary alone without reading the transcript.

2. AUDIT EVERY TICKER in tickers_named and tickers_implied. For each ticker, classify it as:
   - DIRECT_SUBJECT: This thesis is specifically about this company (e.g., "INTC" in a thesis about Intel's foundry failure)
   - DIRECT_BENEFICIARY: This company directly benefits from the thesis even if not the subject (e.g., "MU" in a thesis about DRAM shortage — MU benefits from the shortage)
   - TANGENTIAL: This ticker was mentioned in the same transcript segment but is not the subject of or a beneficiary of THIS specific thesis. REMOVE these.

3. ADD any tickers Baker clearly implied but the extraction missed. Rules for adding:
   - Only add if the thesis makes the beneficiary UNAMBIGUOUS (e.g., "the three HBM producers" → MU is the only US-listed one)
   - Only add US-listed equities (no Korean, Japanese, or Taiwan-listed stocks)
   - Classify added tickers as DIRECT_SUBJECT or DIRECT_BENEFICIARY
   - Do NOT add tickers just because they are loosely related to the theme

Common contamination patterns to watch for:
- NVDA, AMD, INTC, ASML appearing in memory/DRAM theses (tangential unless the thesis is specifically about them)
- Multiple mega-caps appearing in a thesis that is really about one specific company
- Tickers from adjacent theses in the same transcript bleeding into this one
- Implied tickers that are too loosely connected (e.g., "AI will transform healthcare" does not imply any specific ticker)

Output valid JSON matching the schema. No preamble, no markdown fences."""

USER_TEMPLATE = """\
Thesis to audit:

Source: {source}
Date: {date}
Original Summary: {summary}
Detail: {detail}
Confidence: {confidence}
Confidence Evidence: {confidence_evidence}
Quote Fragment: {quote_fragment}
Themes: {themes}
Time Horizon: {time_horizon}
Contrarian: {contrarian}

Current tickers_named: {tickers_named}
Current tickers_implied: {tickers_implied}

Audit this thesis. Expand the summary, classify each ticker, remove tangential ones, and add any clearly implied beneficiaries that are missing."""


_CLASSIFICATION = ["DIRECT_SUBJECT", "DIRECT_BENEFICIARY", "TANGENTIAL"]


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    """Object schema with all keys required + additionalProperties false (structured-output rules)."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


AUDIT_SCHEMA: dict[str, Any] = _obj({
    "summary_extended": {
        "type": "string",
        "description": (
            "3-5 sentence expanded summary capturing claim, reasoning, "
            "implication, and specifics"
        ),
    },
    "tickers_audited": {"type": "array", "items": _obj({
        "ticker": {"type": "string"},
        "classification": {"type": "string", "enum": _CLASSIFICATION},
        "was_original": {
            "type": "boolean",
            "description": (
                "true if this ticker was in the original tickers_named or "
                "tickers_implied"
            ),
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of why this classification",
        },
    })},
})
