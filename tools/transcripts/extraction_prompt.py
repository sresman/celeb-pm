"""Prompt + schema for structured thesis extraction (separated for easy iteration).

SYSTEM_PROMPT / USER_TEMPLATE are the operator-authored extraction prompt.
EXTRACTION_SCHEMA is the same JSON shape, expressed as a JSON Schema so it can be
enforced via the Messages API `output_config.format` (guaranteeing valid output).

JSON-Schema notes for structured outputs: every object sets
`additionalProperties: false` and lists all properties in `required`; nullable
fields use a `["...", "null"]` type union. No numeric/length constraints are used
(unsupported by structured outputs and unnecessary here).
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are a senior equity research analyst extracting structured investment intelligence from a transcript of Gavin Baker, CIO of Atreides Management (~$7B crossover fund focused on technology). Baker is one of the most respected technology investors alive — he ran Fidelity's $17B OTC fund for 8 years, compounding at 19%+ annually.

Your job is to extract every distinct investment thesis, recommendation, structural view, and forward-looking catalyst from this transcript. Baker's alpha-relevant commentary is often structural and thematic rather than ticker-specific. Pay close attention to:

- Structural views on supply chains, bottlenecks, and industry dynamics (e.g., "DRAM will be 30-40% of hyperscale capex by 2027")
- Implied beneficiaries even when no ticker is named (e.g., "the three HBM producers" = SK Hynix, Samsung, Micron)
- Relative rankings between sectors, themes, or investment approaches
- Views he explicitly frames as contrarian or against consensus
- Specific timelines or catalysts he identifies
- Shifts in his thinking vs. prior known positions

Do NOT:
- Summarize the transcript narratively — extract discrete, structured data points
- Infer tickers he didn't mention or imply — if he says "memory producers" without specifying, say "memory producers (implied: SK Hynix, Samsung, Micron)" only if the context makes it unambiguous
- Inflate confidence levels — "interesting" is not "high conviction"
- Include filler, pleasantries, or meta-commentary about the interview itself

Output valid JSON only. No markdown fences, no preamble."""

USER_TEMPLATE = """\
Transcript metadata:
- Source: {source}
- Date: {date}
- Host: {host}
- Topic: {topic}
- Quality: {quality} (youtube_auto transcripts may have garbled proper nouns — infer from context)

--- TRANSCRIPT START ---
{transcript_text}
--- TRANSCRIPT END ---

Extract the data points defined by the response schema. Theses ids are sequential within this transcript (T1, T2, ...). Map each thesis to investment themes (e.g. 'AI datacenter infrastructure', 'semiconductor supply chain', 'power/energy', 'robotics', 'space/orbital compute'). The quote_fragment is a short identifying phrase (under 15 words) from the transcript that anchors the thesis."""


def _arr_str() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


_CONFIDENCE = ["high_conviction", "moderate", "speculative", "passing_mention"]
_REC_CONFIDENCE = ["high_conviction", "moderate", "speculative"]
_TIME_HORIZON = ["near_term", "medium_term", "long_term", "not_specified"]
_DIRECTION = ["buy", "sell", "avoid", "hold"]
_RISK_NATURE = ["overvalued", "overhyped", "structural_risk", "regulatory", "geopolitical", "timing"]


def _obj(properties: dict[str, Any]) -> dict[str, Any]:
    """Object schema with all keys required + additionalProperties false (structured-output rules)."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


EXTRACTION_SCHEMA: dict[str, Any] = _obj({
    "metadata": _obj({
        "source": {"type": "string"},
        "date": {"type": "string"},
        "host": {"type": "string"},
        "topic": {"type": "string"},
        "duration_estimate_min": {"type": ["number", "null"]},
    }),
    "theses": {"type": "array", "items": _obj({
        "id": {"type": "string"},
        "summary": {"type": "string"},
        "detail": {"type": "string"},
        "confidence": {"type": "string", "enum": _CONFIDENCE},
        "confidence_evidence": {"type": "string"},
        "tickers_named": _arr_str(),
        "tickers_implied": _arr_str(),
        "themes": _arr_str(),
        "time_horizon": {"type": "string", "enum": _TIME_HORIZON},
        "contrarian": {"type": "boolean"},
        "quote_fragment": {"type": "string"},
    })},
    "explicit_recommendations": {"type": "array", "items": _obj({
        "direction": {"type": "string", "enum": _DIRECTION},
        "target": {"type": "string"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "string", "enum": _REC_CONFIDENCE},
    })},
    "sector_rankings": {"type": "array", "items": _obj({
        "preferred": {"type": "string"},
        "over": {"type": "string"},
        "reasoning": {"type": "string"},
    })},
    "risk_warnings": {"type": "array", "items": _obj({
        "target": {"type": "string"},
        "nature": {"type": "string", "enum": _RISK_NATURE},
        "detail": {"type": "string"},
    })},
    "catalysts": {"type": "array", "items": _obj({
        "event": {"type": "string"},
        "timing": {"type": "string"},
        "impact": {"type": "string"},
        "beneficiaries": _arr_str(),
        "losers": _arr_str(),
    })},
    "meta_views": {"type": "array", "items": _obj({
        "topic": {"type": "string"},
        "view": {"type": "string"},
        "detail": {"type": "string"},
    })},
})
