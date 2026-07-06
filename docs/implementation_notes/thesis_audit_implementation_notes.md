# Thesis Audit — Implementation Notes

Spec: operator prompt "Audit Thesis Tickers, Expand Summaries, Recover Detail Fields"
(no spec file; passed via `/resume`). Plan: `main-task-audit-pure-star.md`.
Code: `tools/transcripts/audit_theses.py` + `audit_prompt.py`.

## Decisions where the spec was ambiguous

### SD-AUDIT-1 — `source_label` for audit filenames (2026-07-01)
Spec filename is `{date}_{source_label}_{thesis_id}.json`. The extraction JSON
metadata has `source` ("All-In Podcast") + `topic` but no short label. Derived
`source_label` from the extraction filename stem with the leading `{date}_` stripped
(e.g. `allin_dram_bottleneck_2024mid`) — unique per transcript and filesystem-safe.

### SD-AUDIT-2 — `--single` takes a timeline index, not a thesis id (2026-07-01)
Spec usage line says `--single THESIS_ID`; the option help says "one specific thesis
by its timeline index". Thesis ids (`T1`…) repeat across transcripts, so an id alone
is ambiguous. Implemented `--single` as a 0-based index into the date/source/id-sorted
flat list.

### SD-AUDIT-3 — timeline_v2.json and _flat.json are identical flat lists (2026-07-01)
Spec describes `thesis_timeline_v2.json` as "same structure as v1" (v1 =
`thesis_timeline.json` is a flat chronological list) with a flat per-thesis object,
and `thesis_timeline_v2_flat.json` as "the flat chronological list … with the same
fields". Both are therefore flat lists of the identical per-thesis objects, so this
implementation writes the same payload to both files. **FLAG for operator:** if
`thesis_timeline_v2.json` was intended to be grouped-by-transcript (analogous to v1's
`all_summaries.json`) with only `_flat.json` flat, say so and it's a one-function
change. Left identical per the literal spec.

### SD-AUDIT-4 — per-thesis audit file == the timeline_v2 entry (2026-07-01)
The per-thesis file written to `analysis/thesis_audits/` is the fully-assembled
timeline_v2 object (not the raw API response). `rebuild_timelines()` then reads the
union of on-disk audit files and concatenates → both timeline files are rebuilt every
run, so partial/`--limit` runs still produce consistent output for what's done. This
makes the audit files the idempotency/skip unit (skip if exists unless `--force`) and
keeps rebuild a pure read (no re-derivation).

### SD-AUDIT-5 — sort key (2026-07-01)
Sort by `(date, source, numeric(thesis_id))`. `source` disambiguates same-date
transcripts (two 2024-06-15 All-In episodes have different `— topic` suffixes).
Numeric thesis id gives T1<T2<T10 (v1 sorted ids lexically; this is a deliberate minor
improvement, chronological within a transcript).

## Deviations from the working extract_theses.py pattern
- No `MAX_TOKENS_RETRY` escalation: audit outputs are small (one expanded summary +
  a short ticker array), `max_tokens=2048` is ample; a `max_tokens` stop is logged as
  a warning rather than retried at a higher cap.
- No prompt caching: the ~600-token system prompt is below Sonnet 4.6's 2,048-token
  cache minimum, so caching would never fire. Matches extract_theses.py (no caching).

## Cost note
Real run cost ≈ $3.0–3.5 (319 calls; ~600-tok system re-sent per call), above the
spec's "~$1.50 / ~$1–2" estimate. Small either way; flagged to operator.
