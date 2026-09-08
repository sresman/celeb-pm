## Handoff -- transcripts -- 2026-09-08

**Session duration**: long (multi-day thread; this entry covers the attribution work)
**Workstream**: transcripts (Baker corpus + thesis extraction). The `src/celebpm`
13F pipeline was NOT touched. Separate repo `fomo-fund-monitor` was wrapped
independently — see its `handoffs/2026-09-03-monitor.md`.

### What was built

- **`tools/transcripts/audit_attribution.py`** (NEW) — non-destructive per-thesis
  speaker attribution (`subject` / `other` / `indeterminate`) from a focused
  transcript window. One API call per episode. Writes only to
  `analysis/attribution_audit/`; never touches the corpus. `metadata_by_label()`
  reads all five target lists + `CNBC_TARGET` + `SUPPLEMENTARY_METADATA`.
- **`tools/transcripts/fix_participants.py`** (NEW) — derives the participant
  roster and the subject's role from each transcript's opening; `--apply` writes
  `host` + `subject_role` into `targets.py`, keyed on the entry's dict key.
- **`tools/transcripts/targets.py`** — Bankless 2026-05-28 and Heller House
  2026-06-08 removed (dated comments explain why); a16z 2026-08-31 added;
  `SUBJECT_DESCRIPTION` and `SUPPLEMENTARY_METADATA` added; `host` corrected and
  `subject_role` added on all 50 entries.
- **`tools/transcripts/extract_theses.py`** — `low_yield` guard: flags an
  implausibly small thesis count (floor = chars/12k, min 3) as `status:
  low_yield` instead of `ok`.
- **`tools/transcripts/audit_theses.py`** — carries `speaker_attribution` /
  `speaker_name` / `attribution_evidence` into the timeline rows (defaults
  `indeterminate`). SOURCE still needs rewiring to the audit output.
- **`tools/transcripts/build_manifest.py`** — `subject_role` added to `FIELDS`
  (populates once the fetchers next run).
- Corpus: a16z 2026-08-31 ingested (20 theses); Bankless + Heller House removed;
  timeline rebuilt. **48 appearances, 614 theses, 705 named-ticker slots.**

### Decisions made

Full reasoning in `workstreams/transcripts-decisions.md` (SD-ATTR-1…9). The
load-bearing ones:

- **Attribution lives in a separate audit pass, never in `EXTRACTION_SCHEMA`.**
  The schema+prompt route was tried across five revisions and collapsed
  extraction yield on ~50% of episodes (2024-08-27: 20 theses → 1). Corpus was
  restored from git. The audit pass costs ~$1.32 and carries zero corpus risk.
- **`indeterminate` does not count as Baker** (operator). Theses stay tagged in
  the corpus so it is reversible; the filter treats only `subject` as Baker.
- **Two-of-two agreement test** (operator): run the audit twice, disagreement →
  `indeterminate`. Justified by observed per-thesis instability.
- **Bankless 2026-05-28 and Heller House 2026-06-08 are not Baker appearances**
  and were removed rather than re-extracted.
- **Only `theses` is consumed downstream** — five of six extraction sections are
  write-only, so misrouting is equivalent to deletion.

### Current state

Corpus coherent and restored: timeline 614 = extraction 614, `mypy` clean (45
files), extractor verified working. Metadata complete: 50 labels, zero empty
hosts, zero missing roles (30 guest / 16 panelist / 3 secondary / 1 unknown).

The attribution MEASUREMENT is done and trustworthy (73% subject / 11% other /
16% indeterminate on named-ticker slots; 44% panel contamination). The
attribution PLUMBING is not: nothing downstream filters on speaker, and
`audit_theses` still reads the field from extraction rather than from the audit.

**Returns are HELD. v10 is NOT regenerated.**

### Known issues

- `analysis/_attribution_audit_precorpus_restore/` — 46 audit files produced
  against the PRE-restore corpus. Stale; do not trust or commit as current.
- 15 orphaned `cluster_overrides` in `analysis/manual_overrides.json` matching
  `date: 2026-06-08` (deleted Heller House). Inert; left deliberately as a record
  of the operator's 2026-07-22 decision.
- Two Sohn write-ups are `subject_role: secondary` — Baker spoke at the events
  but the text is a third party's rendering. They carry 18 named tickers between
  them; whether they belong in BAKER_NAMED is unresolved.
- Several rosters are first-name-only or caption-garbled ("Foxy", "Jas", "Guy");
  one entry is `unknown` with an empty roster. Not invented.
- `explicit_recommendations` unwired: 154 items / 42 appearances, 76% naming
  tickers the theses do not. Needs ticker resolution for the free-text `target`
  and a `direction` concept the event model lacks.
- Extraction yield has real run-to-run spread even on the committed prompt. The
  `low_yield` guard makes it visible but does not fix it; no retry logic exists.
- Pre-existing uncommitted two-podcast corpus work (thesis_audits for 2026-07-14,
  `situational_awareness_q2_2026_liquidation_analysis.md`, v10 CSV/XLSX from
  2026-08-16) predates this session and is NOT part of these commits.

### Next step

Run `python -m tools.transcripts.audit_attribution --all --force` TWICE over the
current 614-thesis corpus, saving the passes separately (e.g. move
`analysis/attribution_audit/` to `..._pass1/` between runs). Then build the
cross-check: disagreement between passes → `indeterminate`. Then rewire
`audit_theses.py::_timeline_row` to read `speaker_attribution` from
`analysis/attribution_audit/<label>.json` instead of from `t.get(...)`.

### Parallel work available

- `fomo-fund-monitor` is fully wrapped and pushed; only operator actions remain
  there (flip repo to private, verify the Dwarkesh 403 is gone, watch one weekly
  heartbeat drain the digest queue).
- celeb-pm `main` workstream: View 4 (Exit Signals / Survivors) in `src/celebpm`,
  untouched all session.
- Merging `trigger-denominator-ex-spcx` to main is still an open operator call.

### Context to load

`workstreams/transcripts-decisions.md` (2026-09-08 section, SD-ATTR-1…9 — start
here), `tools/transcripts/audit_attribution.py` (module docstring explains the
method and why extraction was left alone), `analysis/_attribution_audit_log.json`
if a fresh pass has been run.
