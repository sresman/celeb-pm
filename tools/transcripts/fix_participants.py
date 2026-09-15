"""Derive the participant roster and the subject's role from each transcript.

The ``host`` field in ``targets.py`` is operator-maintained and drifted. For
All-In 2026-08-14 it listed "Chamath, Jason, Sacks, Friedberg" while the episode
opens "David Saxs and Gavin Baker are with us this week... we got a short crew" —
Chamath and Friedberg are not on it. The extraction prompt CONSUMES that field,
so a wrong roster actively misinforms attribution.

This reads the opening of each transcript (where podcasts announce their lineup)
plus the title, and asks the model for the roster and the subject's role. Output
is a PROPOSAL file for review; ``--apply`` then rewrites ``host`` and adds
``subject_role`` in targets.py. Never guesses: an opening that does not name the
participants yields role "unknown" and an empty roster rather than an invention.

Roles: guest (one interviewer) | panelist (several substantive voices) |
interviewer (the subject is asking) | absent (third parties discussing them).

Usage::

    python -m tools.transcripts.fix_participants            # propose
    python -m tools.transcripts.fix_participants --apply    # write targets.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import dotenv

from tools.transcripts import targets
from tools.transcripts.audit_theses import load_api_key

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
OPENING_CHARS = 3000
PROPOSAL_PATH = targets.REPO_ROOT / "analysis" / "participant_proposals.json"
MASTER = targets.REPO_ROOT / "transcripts" / "_master_manifest.json"
# Investor-specific value lives in config (project rule), not inline here.
SUBJECT = targets.SUBJECT_DESCRIPTION

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "participants": {"type": "array", "items": {"type": "string"}},
        "subject_role": {
            "type": "string",
            "enum": ["guest", "panelist", "interviewer", "absent", "unknown"],
        },
        "evidence": {"type": "string"},
    },
    "required": ["participants", "subject_role", "evidence"],
    "additionalProperties": False,
}

SYSTEM = f"""\
You identify who is present on a recording and what role the SUBJECT plays.
SUBJECT = {SUBJECT}.

You are given the title and the OPENING of a transcript — podcasts and panels
almost always announce their lineup in the first minute.

participants: every person audibly present, by name, EXCLUDING the subject. Use
the names as spoken. If the opening does not name them, return an empty list —
do not infer a roster from the show's usual cast, because the usual cast is
exactly what has been wrong before.

subject_role:
  "guest"       - one interviewer/host asking; the subject is the interviewee
  "panelist"    - several voices with their own substantive views, subject among them
  "interviewer" - the SUBJECT is the one asking; someone else is the interviewee
  "absent"      - third parties discussing the subject in the third person; not present
  "unknown"     - the opening gives no reliable signal

evidence: one short sentence quoting the cue you used. Output valid JSON only."""


def opening_of(path: Path) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title_m = re.search(r"^# actual_title: (.*)$", raw, re.M)
    title = title_m.group(1).strip() if title_m else ""
    body = re.sub(r"^#.*$", "", raw, flags=re.M)
    body = re.sub(r"\[\d+:\d+\]", " ", body)
    return title, re.sub(r"\s+", " ", body).strip()[:OPENING_CHARS]


def entries_by_date() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for vid, v in targets.YOUTUBE_VIDEOS.items():
        out[str(v["date"])] = {"key": vid, "kind": "youtube", **v}
    for r in targets.RSS_TARGETS:
        out.setdefault(str(r["date"]), {"key": r.get("label", ""), "kind": "rss", **r})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    dotenv.load_dotenv(targets.REPO_ROOT / ".env", override=True)

    if args.apply:
        return apply_proposals()

    import anthropic

    client = anthropic.Anthropic(api_key=load_api_key(), max_retries=3)
    paths = {
        str(r["date"]): str(r["filepath"])
        for r in json.loads(MASTER.read_text(encoding="utf-8"))
        if r.get("filepath")
    }
    entries = entries_by_date()
    props: dict[str, Any] = {}
    tin = tout = 0
    for n, (date, entry) in enumerate(sorted(entries.items()), 1):
        rel = paths.get(date)
        if not rel or not (targets.REPO_ROOT / rel).exists():
            print(f"[{n}/{len(entries)}] {date} — no transcript; skipped")
            continue
        title, opening = opening_of(targets.REPO_ROOT / rel)
        user = (
            f"Source: {entry.get('source','')}\nDate: {date}\nTitle: {title}\n"
            f"Currently recorded participants (MAY BE WRONG): {entry.get('host','')}\n\n"
            f"--- OPENING ---\n{opening}"
        )
        resp = client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, temperature=0, system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        tin += resp.usage.input_tokens
        tout += resp.usage.output_tokens
        parsed = json.loads(
            "".join(
                str(getattr(b, "text", ""))
                for b in resp.content
                if getattr(b, "type", "") == "text"
            )
        )
        props[date] = {
            "key": entry["key"], "kind": entry["kind"], "label": entry.get("label", ""),
            "source": entry.get("source", ""), "current_host": entry.get("host", ""),
            **parsed,
        }
        changed = "" if parsed["participants"] and all(
            p.split()[-1].lower() in entry.get("host", "").lower() for p in parsed["participants"]
        ) else "  <-- CHANGED"
        print(
            f"[{n}/{len(entries)}] {date} {parsed['subject_role']:<12}"
            f"{', '.join(parsed['participants'])[:46]:<48}{changed}"
        )
    PROPOSAL_PATH.write_text(json.dumps(props, indent=2) + "\n", encoding="utf-8")
    cost = tin / 1e6 * 3.0 + tout / 1e6 * 15.0
    print(f"\n{len(props)} proposals -> {PROPOSAL_PATH}   ~${cost:.2f}")
    print("Review, then re-run with --apply.")
    return 0


def _normalise_roles(props: dict[str, Any]) -> None:
    """Take the ROSTER from the model but the ROLE from a rule.

    The model's role calls were internally inconsistent: All-In episodes came back
    "guest" or "panelist" depending on the episode, and a16z one-on-ones came back
    "panelist". Role is really a function of how many substantive co-speakers
    there are, which the roster already answers, so derive it:

      interviewer / absent  -> keep the model's call (title- or third-person-driven,
                               and it got both of those right)
      >= 2 co-speakers      -> panelist
      1 co-speaker          -> guest
      0 co-speakers         -> unknown  (do not guess)
    """
    for p in props.values():
        if p["subject_role"] in ("interviewer", "absent"):
            continue
        n = len(p["participants"])
        p["subject_role"] = "panelist" if n >= 2 else ("guest" if n == 1 else "unknown")


def apply_proposals() -> int:
    """Rewrite host + insert subject_role in targets.py, keyed per ENTRY.

    Keyed on the entry's dict key (YouTube video id) or, for RSS rows, its label —
    NOT on the existing host string. All-In episodes share byte-identical host
    strings ("Chamath, Jason, Sacks, Friedberg"), so a host-string replace with
    count=1 hits the first occurrence every time and shuffles rosters between
    episodes. That happened once; this keys on something unique instead.
    """
    props = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    _normalise_roles(props)
    path = targets.REPO_ROOT / "tools" / "transcripts" / "targets.py"
    src = path.read_text(encoding="utf-8")
    applied = 0
    for date, p in sorted(props.items()):
        roster = ", ".join(p["participants"])
        role = p["subject_role"]
        if role == "interviewer":
            host = f"{roster or 'unnamed interviewee'} (Gavin Baker interviewing)"
        elif role == "absent":
            host = f"{roster or 'unnamed'} (Gavin Baker NOT present)"
        elif roster:
            host = f"{roster} (Gavin Baker {role})"
        else:
            host = f"unnamed (Gavin Baker {role})"

        # Anchor on the unique entry key, then rewrite host/subject_role inside
        # that entry's block only (up to its closing brace).
        anchor = f'"{p["key"]}": {{' if p["kind"] == "youtube" else f'"label": "{p["label"]}"'
        start = src.find(anchor)
        if start < 0:
            print(f"  {date}: anchor {anchor!r} not found; skipped")
            continue
        end = src.find("\n    },", start)
        if end < 0:
            end = src.find("},", start)
        block = src[start:end]
        new_block = re.sub(
            r'"host":\s*"[^"]*"(,\s*"subject_role":\s*"[^"]*")?',
            f'"host": "{host}", "subject_role": "{role}"',
            block,
            count=1,
        )
        if new_block == block:
            print(f"  {date}: no host field in block; skipped")
            continue
        src = src[:start] + new_block + src[end:]
        applied += 1
    path.write_text(src, encoding="utf-8")
    print(f"applied {applied}/{len(props)} entries -> targets.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
