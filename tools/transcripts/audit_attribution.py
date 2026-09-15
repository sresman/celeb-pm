"""Second-order audit: WHO SAID IT. Attribute each thesis to Baker or a co-speaker.

WHY THIS EXISTS. ``extract_theses`` receives an undifferentiated transcript. YouTube
auto-captions carry ``>>`` turn markers but NO speaker names, the extraction prompt
frames the whole file as "a transcript of Gavin Baker" and asks for "Baker's
alpha-relevant commentary", and the thesis schema has no speaker field. On a solo
interview that is harmless. On a panel it is not: a co-host's stock call is
indistinguishable from Baker's, and it flows downstream into ``tickers_named`` and
therefore into the BAKER_NAMED population whose alpha the strategy rests on.

Confirmed instance (All-In 2026-08-14, T15, ``AMZN``): "I'm not a proponent of
socialism, but... So that's my message as a long-term shareholder in Amazon. I have
a very big position in Amazon and I keep increasing it every year." That is Jason
Calacanis, not Baker. It passes a naive holdings check because Atreides does hold
AMZN (2.07% of equity, 2026-06-30).

STRICTLY NON-DESTRUCTIVE. This module NEVER writes to ``thesis_timeline_v2*.json``,
``thesis_extractions/`` or ``thesis_audits/``. Every result goes to a parallel tree,
``analysis/attribution_audit/``, so the audit can be re-run, discarded, or ignored
without touching the corpus. Nothing downstream reads it until you decide it should.

METHOD. One API call per EPISODE, not per thesis. The model sees the episode's known
participants plus, for each thesis, a window of the transcript around its
``quote_fragment`` — the containing speaker turn plus the preceding turns, which is
where the handoff cues live ("How are you doing, Gavin?" -> the next turn is Baker).
Batching per episode is both cheaper and MORE accurate than per-thesis calls: the
model can track turn alternation across the whole set.

Quote location is garble-tolerant. Auto-captions mangle proper nouns ("ampiers" for
Ampere, "Grock" for Grok), so an exact match fails on roughly a third of quotes; the
locator falls back to progressively shorter word-shingles, then to a difflib sweep.
A quote that still cannot be placed is reported ``indeterminate`` with
``quote_not_located`` rather than guessed at.

Usage::

    python -m tools.transcripts.audit_attribution --dry-run   # select + locate only
    python -m tools.transcripts.audit_attribution             # panel + unknown-host
    python -m tools.transcripts.audit_attribution --all       # every appearance
    python -m tools.transcripts.audit_attribution --dates 2026-08-14
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable

import dotenv

from tools.transcripts import targets
from tools.transcripts.audit_theses import load_api_key

ANALYSIS_DIR = targets.REPO_ROOT / "analysis"
OUT_DIR = ANALYSIS_DIR / "attribution_audit"
LOG_PATH = ANALYSIS_DIR / "_attribution_audit_log.json"
TIMELINE_FLAT = ANALYSIS_DIR / "thesis_timeline_v2_flat.json"
EXTRACTION_DIR = ANALYSIS_DIR / "thesis_extractions"
MASTER_MANIFEST = targets.REPO_ROOT / "transcripts" / "_master_manifest.json"

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
SLEEP_BETWEEN = 2.0
# Explicit per-request timeout. Without one, pass 2 of 2026-09-08 sat on a single
# stalled request for 55 minutes with the process alive and no output — the SDK
# default is generous and the manual retry below doubles it. 180s is well clear of
# the slowest observed episode (a16z 2026-08-31, 543 turns, ~40s).
API_TIMEOUT_SECONDS = 180.0

# Quote-location tuning. Pass 3 scores a quote against windows of each turn using
# character n-grams; NGRAM_N=4 is short enough to survive a garbled word and long
# enough not to match on noise. LOCATE_MIN_SCORE is calibrated against the quotes
# that pass 1 can place exactly — see the calibration note in the implementation
# notes (2026-09-08).
NGRAM_N = 4
MIN_MATCH_WINDOW_CHARS = 160
MIN_SHINGLE_CHARS = 12
LOCATE_MIN_SCORE = 0.70  # calibrated: worst cross-episode false positive scored
#                          0.66; true positives under 35% simulated caption
#                          garbling bottomed out at 0.81 (5th pct). 0.70 is the gap.
INPUT_COST_PER_MTOK = 3.0
OUTPUT_COST_PER_MTOK = 15.0

# Turns of transcript to include before the one containing the quote. The handoff
# cue that identifies a speaker usually sits in the PRECEDING turn, not the current
# one, so this is deliberately generous.
TURNS_BEFORE = 3
TURNS_AFTER = 1
# Hard cap per window so one rambling turn cannot dominate the prompt.
WINDOW_MAX_CHARS = 2600

# A host string implying more than one voice. Matches the co-host names that recur
# across this corpus plus the generic separators.
PANEL_HINT = re.compile(
    r",|&| and |guest|bestie|panel|chamath|jason|sacks|friedberg|gurley|gerstner|gracias",
    re.IGNORECASE,
)

ATTRIBUTION_VALUES = ("baker", "other", "indeterminate")

AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "attributions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "thesis_id": {"type": "string"},
                    "speaker_attribution": {"type": "string", "enum": list(ATTRIBUTION_VALUES)},
                    "attribution_confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "likely_speaker": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "thesis_id",
                    "speaker_attribution",
                    "attribution_confidence",
                    "likely_speaker",
                    "evidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["attributions"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """\
You are auditing WHO SPOKE each investment thesis extracted from a podcast or panel \
transcript. The transcript is a YouTube auto-caption: `>>` marks a change of speaker \
but NEVER names them. Your job is attribution only — do not re-judge the thesis.

The target speaker is GAVIN BAKER, founding partner and CIO of Atreides Management. \
Other participants are hosts, co-guests or interviewers.

For each thesis you are given a quote and the surrounding turns. Decide:
  "baker"         — the quoted words are Baker's
  "other"         — the quoted words are a different participant's
  "indeterminate" — genuinely cannot tell from the window given

Evidence to use, strongest first:
  1. Direct address in a nearby turn ("How are you doing, Gavin?" -> the reply is Baker).
  2. Self-identification ("at Atreides we...", "my fund", "when I ran the OTC fund").
  3. Role register. Baker is a fund CIO discussing positioning, sizing and portfolio \
construction. A host running the show does intros, transitions, reads ads, addresses \
the audience, and editorialises politically. A retail-investor framing of a personal \
holding ("I have a very big position and I keep increasing it every year") is much \
more typical of a host than of a CIO describing a fund position.
  4. Turn alternation across the window.

Do NOT infer "baker" merely because the thesis is investment-flavoured or because the \
ticker is one Baker is known to hold — co-hosts discuss the same names. Absent real \
evidence, answer "indeterminate". Over-attributing to Baker is the specific failure \
this audit exists to detect, so bias toward "indeterminate" when the window is thin.

Set likely_speaker to a name when you can (e.g. "Jason Calacanis"), otherwise "" for \
baker/indeterminate or a role ("host") for other. evidence: one short sentence citing \
the specific cue. Output valid JSON only."""


# --------------------------------------------------------------------------- #
# Transcript handling
# --------------------------------------------------------------------------- #


def _strip_timestamps(raw: str) -> list[str]:
    out: list[str] = []
    for line in raw.splitlines():
        if line.startswith("#"):
            continue
        out.append(re.sub(r"^\[\d+:\d+\]\s*", "", line).rstrip())
    return out


def split_turns(lines: list[str]) -> list[str]:
    """Group caption lines into speaker turns on the `>>` marker.

    A transcript with no markers at all yields a single turn, which is the correct
    representation of a monologue or an un-marked caption track.
    """
    turns: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.lstrip().startswith(">>"):
            if current:
                turns.append(" ".join(current).strip())
            current = [line.lstrip()[2:].strip()]
        else:
            current.append(line.strip())
    if current:
        turns.append(" ".join(current).strip())
    return [t for t in turns if t]


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower())


def _squash(text: str) -> str:
    """Collapse whitespace runs. Matching-only — never use where offsets matter.

    ``_norm`` substitutes each punctuation character with a single space and is
    deliberately LENGTH-PRESERVING, because ``_char_window`` maps a position found
    in the normalised string back onto the raw one. That leaves runs of spaces
    wherever the quote had punctuation the caption track does not, which silently
    broke exact substring matching: "Nvidia, and AMD" normalises to
    "nvidia  and amd" (two spaces) and will not match "nvidia and amd".
    """
    return " ".join(text.split())


def _char_ngrams(text: str, n: int = NGRAM_N) -> set[str]:
    """Character n-grams. Garble-tolerant: a mangled proper noun costs only the
    handful of n-grams spanning it, not the whole match."""
    if len(text) < n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def _window_containment(q_grams: set[str], text: str, win: int) -> float:
    """Best fraction of ``q_grams`` found in any ``win``-sized window of ``text``.

    Windowing is the point. Plain containment over a whole turn lets a long
    rambling turn score highly just by containing a lot of everything, which is
    how the previous difflib sweep placed quotes on plausible-but-wrong turns. A
    window sized to the quote can only score high if the quote's material is
    actually concentrated somewhere in the turn.
    """
    if not q_grams:
        return 0.0
    if len(text) <= win:
        return len(q_grams & _char_ngrams(text)) / len(q_grams)
    best = 0.0
    step = max(1, win // 2)
    for start in range(0, len(text) - win + step, step):
        seg = text[start : start + win]
        score = len(q_grams & _char_ngrams(seg)) / len(q_grams)
        if score > best:
            best = score
            if best >= 0.999:
                break
    return best


def locate_turn(turns: list[str], quote: str) -> int | None:
    """Index of the turn containing ``quote``, or None.

    Three passes, loosening each time, because auto-captions garble proper nouns
    ("ampiers" for Ampere, "Grock" for Grok) and the extracted quote is often
    re-punctuated relative to the caption track.

    1. exact squashed-normalised substring — perfect precision when it fires;
    2. the longest word-shingle occurring in exactly one turn;
    3. windowed character-n-gram containment, which tolerates garbling.

    Returning None is a valid, LOUD answer: the caller reports the thesis as
    ``indeterminate`` with ``quote_not_located`` rather than guessing. That is
    strictly better than a confident placement on the wrong turn, which produces
    an ``indeterminate`` verdict that looks like genuine ambiguity but is really
    bad input — the failure mode that dominated the 2026-09-08 audit.
    """
    if not quote.strip():
        return None
    normed = [_squash(_norm(t)) for t in turns]
    q = _squash(_norm(quote))
    if not q:
        return None

    # Pass 1 — exact substring.
    for i, t in enumerate(normed):
        if q in t:
            return i

    # Pass 2 — longest word-shingle that occurs exactly once across all turns.
    words = [w for w in q.split() if len(w) > 2]
    for size in (8, 6, 5, 4, 3):
        if len(words) < size:
            continue
        for start in range(len(words) - size + 1):
            shingle = " ".join(words[start : start + size])
            if len(shingle) < MIN_SHINGLE_CHARS:
                continue
            hits = [i for i, t in enumerate(normed) if shingle in t]
            if len(hits) == 1:
                return hits[0]

    # Pass 3 — windowed character-n-gram containment.
    q_grams = _char_ngrams(q)
    if not q_grams:
        return None
    win = max(2 * len(q), MIN_MATCH_WINDOW_CHARS)
    best_score, best_idx = 0.0, None
    for i, t in enumerate(normed):
        score = _window_containment(q_grams, t, win)
        if score > best_score:
            best_score, best_idx = score, i
    return best_idx if best_score >= LOCATE_MIN_SCORE else None


def _char_window(text: str, quote: str) -> str:
    """Slice +/- WINDOW_MAX_CHARS around ``quote`` inside one oversized block.

    Needed because MOST transcripts in this corpus carry no `>>` markers at all —
    19 of the 26 audited episodes are a single undifferentiated block. Turn-based
    windowing degenerates to "send the whole file" there, so fall back to a
    character window centred on the quote. Attribution is weaker without turn
    boundaries, which is exactly why the prompt is told to prefer
    "indeterminate" over a guess.
    """
    pos = _norm(text).find(_norm(quote)[:60])
    if pos < 0:
        words = [w for w in _norm(quote).split() if len(w) > 3]
        for size in (5, 4, 3):
            if len(words) >= size:
                pos = _norm(text).find(" ".join(words[:size]))
                if pos >= 0:
                    break
    if pos < 0:
        pos = 0
    lo = max(0, pos - WINDOW_MAX_CHARS)
    hi = min(len(text), pos + WINDOW_MAX_CHARS)
    prefix = "… " if lo > 0 else ""
    suffix = " …" if hi < len(text) else ""
    return f"{prefix}{text[lo:hi]}{suffix}"


def build_window(turns: list[str], idx: int, quote: str = "") -> str:
    """Render the turns around ``idx``, marking the one holding the quote.

    When the containing turn is itself oversized — i.e. the transcript has no
    usable `>>` structure — fall back to a character window around the quote so a
    single 90 KB block cannot be pasted wholesale into the prompt.
    """
    if len(turns[idx]) > WINDOW_MAX_CHARS:
        return (
            "[no speaker markers in this transcript — character window only]\n"
            + _char_window(turns[idx], quote)
        )
    lo = max(0, idx - TURNS_BEFORE)
    hi = min(len(turns), idx + TURNS_AFTER + 1)
    parts: list[str] = []
    for i in range(lo, hi):
        body = turns[i]
        if len(body) > WINDOW_MAX_CHARS:
            body = _char_window(body, quote if i == idx else "")
        marker = "  <-- QUOTE IS IN THIS TURN" if i == idx else ""
        parts.append(f"[turn {i}]{marker}\n{body}")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- #
# Episode selection
# --------------------------------------------------------------------------- #


def metadata_by_label() -> dict[str, tuple[str, str]]:
    """label -> (host, subject_role), covering EVERY appearance.

    targets.py splits appearances across FIVE lists plus a standalone CNBC dict,
    and three appearances (sohn_australia_2021_coinbase,
    cnbc_squawk_spacex_debut_2026jun, cnbc_spacex_drawdown_2026jul) are acquired
    outside all of them. An earlier version of this module read only
    YOUTUBE_VIDEOS and RSS_TARGETS, so 15 appearances silently received an EMPTY
    participants field — the exact condition that produces bad attribution — and
    I mis-reported the gap twice as a result. Read every list, then fall back to
    the master manifest, which carries a host for all 48.
    """
    out: dict[str, tuple[str, str]] = {}
    for name in (
        "YOUTUBE_VIDEOS", "RSS_TARGETS", "COLOSSUS_EPISODES",
        "TEXT_TARGETS", "WEB_TARGETS",
    ):
        container = getattr(targets, name, None)
        if container is None:
            continue
        rows = container.values() if isinstance(container, dict) else container
        for row in rows:
            label = str(row.get("label", ""))
            if label:
                out[label] = (str(row.get("host", "")), str(row.get("subject_role", "unknown")))
    cnbc = getattr(targets, "CNBC_TARGET", None)
    if isinstance(cnbc, dict) and cnbc.get("label"):
        out[str(cnbc["label"])] = (
            str(cnbc.get("host", "")), str(cnbc.get("subject_role", "unknown"))
        )
    for label, row in getattr(targets, "SUPPLEMENTARY_METADATA", {}).items():
        out[str(label)] = (str(row.get("host", "")), str(row.get("subject_role", "unknown")))
    # Fallback for appearances acquired outside targets.py entirely.
    for row in json.loads(MASTER_MANIFEST.read_text(encoding="utf-8")):
        label = str(row.get("label", ""))
        if label and label not in out:
            role = row.get("subject_role") or "unknown"
            out[label] = (str(row.get("host", "")), str(role))
    return out


def label_by_date_source() -> dict[tuple[str, str], str]:
    """(date, timeline-source) -> label, built from the extraction files.

    The flat timeline carries no ``label``, only ``date`` and a composed
    ``source`` of the form ``"{metadata.source} — {metadata.topic}"`` (see
    ``audit_theses``). The extraction JSONs carry both halves plus the label in
    their filename, so this reconstructs the join. Verified 47/47 against the
    614-thesis timeline.
    """
    out: dict[tuple[str, str], str] = {}
    for path in sorted(EXTRACTION_DIR.glob("*.json")):
        meta = json.loads(path.read_text(encoding="utf-8")).get("metadata", {})
        source = str(meta.get("source", "") or "")
        topic = str(meta.get("topic", "") or "")
        composed = f"{source} — {topic}" if topic else source
        out[(str(meta.get("date", ""))[:10], composed)] = path.stem[11:]
    return out


def transcript_by_label() -> dict[str, tuple[str, str]]:
    """label -> (date, transcript path). ``label`` IS unique across the corpus."""
    rows = json.loads(MASTER_MANIFEST.read_text(encoding="utf-8"))
    return {
        str(r["label"]): (str(r["date"]), str(r["filepath"]))
        for r in rows
        if isinstance(r, dict) and r.get("filepath") and r.get("label")
    }


def classify(host: str) -> str:
    if not host:
        return "unknown"
    return "panel" if PANEL_HINT.search(host) else "solo"


def select_episodes(
    mode: str, only: Iterable[str] | None
) -> list[tuple[str, str, str, str, str]]:
    """Return (label, date, source, host, kind) for the episodes to audit.

    Keyed on ``label``, never on ``date``. 2026-05-12 holds TWO appearances of
    the one Sohn NY event — Khaira's write-up (4 theses) and the YouTube
    fireside (8) — whose thesis_ids collide on T1..T4. A date-keyed pass bundled
    all 12 into a single call against whichever transcript the date map happened
    to keep, so up to 8 quotes could not be located and the output file could not
    be joined back to an appearance. ``--dates`` still filters on date and now
    selects both appearances that share one.
    """
    meta = metadata_by_label()
    labels = label_by_date_source()
    timeline = json.loads(TIMELINE_FLAT.read_text(encoding="utf-8"))

    groups: dict[tuple[str, str], None] = {}
    for row in timeline:
        groups[(str(row.get("date", ""))[:10], str(row.get("source", "")))] = None

    picked: list[tuple[str, str, str, str, str]] = []
    for date, source in sorted(groups):
        if only is not None and date not in set(only):
            continue
        label = labels.get((date, source), "")
        if not label:
            print(f"  WARNING: no label for ({date}, {source[:50]}) — skipped")
            continue
        host, _role = meta.get(label, ("", "unknown"))
        kind = classify(host)
        if mode == "all" or kind in ("panel", "unknown"):
            picked.append((label, date, source, host, kind))
    return picked


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #


def build_user_content(
    date: str, source: str, host: str, kind: str, items: list[dict[str, Any]]
) -> str:
    parts = [
        f"Episode date: {date}",
        f"Source: {source}",
        f"Known participants: {host or 'UNKNOWN — infer from the transcript itself'}",
        f"Episode kind (from metadata, may be wrong): {kind}",
        "",
        "NOTE: the participant metadata above has been wrong before. Trust the "
        "transcript over it.",
        "",
        f"{len(items)} theses to attribute:",
    ]
    for item in items:
        parts += [
            "",
            "=" * 70,
            f"thesis_id: {item['thesis_id']}",
            f"thesis: {item['summary'][:280]}",
            f"tickers_named: {item['tickers'] or '(none)'}",
            f"quote_fragment: \"{item['quote']}\"",
            "",
            "transcript window:",
            item["window"],
        ]
    return "\n".join(parts)


def call_api(client: Any, user_content: str) -> Any:
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": AUDIT_SCHEMA}},
    )


def response_text(resp: Any) -> str:
    return "".join(
        b.text for b in resp.content if getattr(b, "type", "") == "text"
    )


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


def summarise(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate + per-episode rates, counted BOTH by thesis and by named ticker.

    The ticker cross-tab is the one that matters operationally: BAKER_NAMED is
    populated from ``tickers_named``, so a contaminated thesis carrying five
    tickers does five times the damage of one carrying none.
    """
    def blank() -> dict[str, int]:
        return {
            "theses": 0,
            "baker": 0,
            "other": 0,
            "indeterminate": 0,
            "tickers": 0,
            "tickers_baker": 0,
            "tickers_other": 0,
            "tickers_indeterminate": 0,
        }

    total = blank()
    per_episode: list[dict[str, Any]] = []
    for ep in episodes:
        row = blank()
        for r in ep["results"]:
            verdict = r["speaker_attribution"]
            n_tickers = len(r.get("tickers") or [])
            row["theses"] += 1
            row[verdict] += 1
            row["tickers"] += n_tickers
            row[f"tickers_{verdict}"] += n_tickers
        for k, v in row.items():
            total[k] += v
        contaminated = row["other"] + row["indeterminate"]
        per_episode.append(
            {
                "label": ep.get("label", ""),
                "date": ep["date"],
                "source": ep["source"],
                "kind": ep["kind"],
                "host": ep["host"],
                **row,
                "pct_not_baker": round(100 * contaminated / row["theses"], 1)
                if row["theses"]
                else 0.0,
                "pct_tickers_not_baker": round(
                    100 * (row["tickers_other"] + row["tickers_indeterminate"]) / row["tickers"], 1
                )
                if row["tickers"]
                else 0.0,
            }
        )
    return {"total": total, "episodes": per_episode}


def print_report(summary: dict[str, Any]) -> None:
    t = summary["total"]
    print("\n" + "=" * 96)
    print("ATTRIBUTION AUDIT — aggregate")
    print("=" * 96)
    if t["theses"]:
        print(
            f"  theses        {t['theses']:>4}   "
            f"baker {t['baker']:>4} ({t['baker']/t['theses']:.0%})   "
            f"other {t['other']:>3} ({t['other']/t['theses']:.0%})   "
            f"indet {t['indeterminate']:>3} ({t['indeterminate']/t['theses']:.0%})"
        )
    if t["tickers"]:
        print(
            f"  named tickers {t['tickers']:>4}   "
            f"baker {t['tickers_baker']:>4} ({t['tickers_baker']/t['tickers']:.0%})   "
            f"other {t['tickers_other']:>3} ({t['tickers_other']/t['tickers']:.0%})   "
            f"indet {t['tickers_indeterminate']:>3} "
            f"({t['tickers_indeterminate']/t['tickers']:.0%})"
        )
    print("\n" + "-" * 96)
    print("PER EPISODE — sorted by ticker contamination (the BAKER_NAMED-relevant rate)")
    print("-" * 96)
    print(
        f"  {'date':<12}{'kind':<9}{'th':>4}{'bkr':>5}{'oth':>5}{'ind':>5}"
        f"{'tk':>5}{'tk_o':>6}{'tk_i':>6}{'%tk_bad':>9}  source"
    )
    for e in sorted(
        summary["episodes"], key=lambda x: (-x["pct_tickers_not_baker"], -x["tickers"])
    ):
        print(
            f"  {e['date']:<12}{e['kind']:<9}{e['theses']:>4}{e['baker']:>5}"
            f"{e['other']:>5}{e['indeterminate']:>5}{e['tickers']:>5}"
            f"{e['tickers_other']:>6}{e['tickers_indeterminate']:>6}"
            f"{e['pct_tickers_not_baker']:>8.0f}%  {e['source'][:30]}"
        )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="audit every appearance")
    parser.add_argument("--dates", nargs="*", default=None)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="select episodes and locate quotes; make no API calls",
    )
    parser.add_argument("--force", action="store_true", help="re-audit existing outputs")
    parser.add_argument(
        "--out-dir", type=Path, default=None,
        help=f"write episode files here instead of {OUT_DIR.name}/",
    )
    parser.add_argument(
        "--only", type=Path, default=None,
        help="JSON list of [label, thesis_id] pairs. Audits ONLY those theses and "
             "MERGES them into the existing episode file, leaving every other "
             "verdict untouched. Implies --force for the selected theses.",
    )
    args = parser.parse_args()

    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)
    timeline = json.loads(TIMELINE_FLAT.read_text(encoding="utf-8"))
    paths = transcript_by_label()
    picked = select_episodes("all" if args.all else "risk", args.dates)

    by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in timeline:
        key = (str(row.get("date", ""))[:10], str(row.get("source", "")))
        by_group.setdefault(key, []).append(row)

    out_dir = (args.out_dir or OUT_DIR).resolve()
    only: dict[str, set[str]] | None = None
    if args.only is not None:
        only = {}
        for label, thesis_id in json.loads(args.only.read_text(encoding="utf-8")):
            only.setdefault(str(label), set()).add(str(thesis_id))
        print(
            f"targeted re-audit: {sum(len(v) for v in only.values())} theses "
            f"across {len(only)} episodes -> {out_dir}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    client = None
    if not args.dry_run:
        import anthropic

        client = anthropic.Anthropic(
            api_key=load_api_key(), max_retries=3, timeout=API_TIMEOUT_SECONDS
        )

    episodes: list[dict[str, Any]] = []
    total_in = total_out = 0
    unlocated = 0

    for n, (label, date, source, host, kind) in enumerate(picked, 1):
        rows = by_group.get((date, source), [])
        entry = paths.get(label)
        if entry is None:
            print(f"[{n}/{len(picked)}] {label} — no transcript on file; skipped")
            continue
        rel = entry[1]
        out_path = out_dir / f"{label}.json"
        if only is not None:
            wanted = only.get(label, set())
            rows = [r for r in rows if str(r.get("thesis_id")) in wanted]
            if not rows:
                continue
        elif out_path.exists() and not args.force and not args.dry_run:
            episodes.append(json.loads(out_path.read_text(encoding="utf-8")))
            print(f"[{n}/{len(picked)}] {label} — skipped_exists")
            continue

        turns = split_turns(_strip_timestamps((targets.REPO_ROOT / rel).read_text(encoding="utf-8")))
        items: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for row in rows:
            tickers = list(row.get("tickers_direct") or [])
            quote = str(row.get("quote_fragment") or "")
            idx = locate_turn(turns, quote)
            payload = {
                "thesis_id": str(row.get("thesis_id") or ""),
                "summary": str(row.get("summary") or ""),
                "tickers": tickers,
                "quote": quote,
            }
            if idx is None:
                unlocated += 1
                missing.append(payload)
            else:
                items.append({**payload, "window": build_window(turns, idx, quote)})

        print(
            f"[{n}/{len(picked)}] {label[:44]:<44} {kind:<8} theses={len(rows):>3} "
            f"located={len(items):>3} unlocated={len(missing):>2} turns={len(turns):>4}"
        )
        if args.dry_run:
            continue

        results: list[dict[str, Any]] = [
            {
                **m,
                "speaker_attribution": "indeterminate",
                "attribution_confidence": "low",
                "likely_speaker": "",
                "evidence": "quote_not_located in transcript",
            }
            for m in missing
        ]
        if items and client is not None:
            content = build_user_content(date, source, host, kind, items)
            try:
                resp = call_api(client, content)
            except Exception:
                time.sleep(30)
                resp = call_api(client, content)
            total_in += resp.usage.input_tokens
            total_out += resp.usage.output_tokens
            parsed = json.loads(response_text(resp))
            by_id = {a["thesis_id"]: a for a in parsed["attributions"]}
            for item in items:
                a = by_id.get(item["thesis_id"])
                results.append(
                    {
                        "thesis_id": item["thesis_id"],
                        "summary": item["summary"],
                        "tickers": item["tickers"],
                        "quote": item["quote"],
                        "speaker_attribution": a["speaker_attribution"] if a else "indeterminate",
                        "attribution_confidence": a["attribution_confidence"] if a else "low",
                        "likely_speaker": a["likely_speaker"] if a else "",
                        "evidence": a["evidence"] if a else "model returned no row",
                    }
                )
            time.sleep(SLEEP_BETWEEN)

        if only is not None and out_path.exists():
            # Merge: replace only the re-audited theses, preserve the file's order
            # and every verdict this run did not look at.
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            fresh = {str(r["thesis_id"]): r for r in results}
            merged = [fresh.pop(str(r["thesis_id"]), r) for r in existing.get("results", [])]
            merged.extend(fresh.values())
            record = {**existing, "results": merged}
        else:
            record = {
                "label": label,
                "date": date,
                "source": source,
                "host": host,
                "kind": kind,
                "model": MODEL,
                "results": results,
            }
        out_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        episodes.append(record)

    if args.dry_run:
        print(f"\nDRY RUN — {len(picked)} episode(s) selected, {unlocated} quote(s) unlocated.")
        return 0

    summary = summarise(episodes)
    print_report(summary)
    cost = total_in / 1e6 * INPUT_COST_PER_MTOK + total_out / 1e6 * OUTPUT_COST_PER_MTOK
    print(f"\nTokens: {total_in:,} in + {total_out:,} out  ~${cost:.2f}")
    LOG_PATH.write_text(
        json.dumps(
            {"model": MODEL, "input_tokens": total_in, "output_tokens": total_out,
             "cost_usd": round(cost, 4), **summary},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"  -> {LOG_PATH}\n  -> {out_dir}/<label>.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
