# Transcripts Workstream

> Living doc. Gavin Baker public-appearance transcript corpus + NLP signal extraction.
> Standalone of the 13F pipeline (`workstreams/main.md`). `/resume transcripts` reads this.

---

## What this is

A corpus of Gavin Baker (Atreides Management) public-appearance transcripts and a
structured-thesis extraction layer over it, for later cross-referencing of his stated
investment theses against his 13F filings. All code in `tools/transcripts/`; all data in
`transcripts/` + `analysis/`. Independent of `src/celebpm`.

Branch: **`gavin-baker-transcript-corpus`** (not yet merged to main).

---

## Current State (as of 2026-07-14)

**Corpus audit → gap-fill → re-score → durable overrides COMPLETE; basket re-resolution is a
pending operator review.** This session cleaned and expanded the Baker corpus and rebuilt the
whole thesis-scoring stack on the corrected data. In order:

- **Corpus audit** (`analysis/corpus_audit.md`): removed 1 red herring (Heller House — a SpaceX-CFO
  reporter segment, not Baker), built a master appearance list via web search, diffed vs corpus.
- **Gap-fill** (`analysis/corpus_gap_fill_report.md`): corrected **5 mis-dated files** at all layers
  (targets.py → transcript → manifest → extraction JSON) — Aleph 2024-02-14→**2025-10-22**, two All-In
  files mislabeled "2024-06-15" → **2026-06-07 / 2026-06-27**, TBPN 2025-11-15→**2026-06-15**,
  iConnections "2024"→**2026-02-24**; all found by verifying `yt-dlp` upload dates. Fetched + extracted
  **13 new appearances** (incl. the Limitless/Bankless Unity "world-model builder" thesis, the audit's
  target). CNBC + 4 podcast-only ILTB episodes came via **Whisper** (`fetch_audio_whisper`, small model);
  `fetch_prices` hardened to tolerate 404 tickers. Corpus: 26 → **39 files / 507 theses / 2019-11-26 →
  2026-07-08**.
- **Re-score** (`analysis/rescore_diff_summary.md`): `aggregate_theses` → `audit_theses` (258 re-audited,
  ~$2.29) → `theme_returns_v2` → **`build_repeat_mention_events.py`** (NEW). Restructured the event grain
  to **one row per (theme, mention)** with `is_repeat_mention` + the 4 existing criteria as separate
  booleans → the 3-way noise-vs-criteria slice in `step4_signal_events_v6_with_returns_extended.xlsx`.
- **Durable overrides + 7 new themes + reversal fix** (`analysis/override_rerun_diff.md`): NEW
  `analysis/manual_overrides.json` (cluster + event overrides applied after clustering, before returns,
  in BOTH `theme_returns_v2` and `build_repeat_mention_events` via shared helpers) — survives rebuilds.
  15 event + 1 cluster override (41 rows changed). `theme_baskets_v3.json` +7 themes (52→59; Unity,
  datacenter-physical-assets, gaming-world-models, cooling-suppliers, CDN, uranium, stranded-power;
  collision-tested). `THESIS_REVERSAL` guard tightened to self-stance-change phrases (17→2 fires; genuine
  TPU 2026-05-20 fires, DRAM/TSMC/SpaceX false positives gone). Added `is_derisk_signal`. UNIVERSE +25
  tickers. All gates pass; all touched scripts `mypy --strict` clean.
- **Basket re-resolution — REVIEW ARTIFACT, nothing applied** (`analysis/basket_reresolution.csv`,
  `reresolve_baskets.py`, **claude-opus-4-6**): a per-thesis second-opinion pass over all 241 events
  (is-this-a-trade + precise tickers). 207/241 changed, **disagrees with 35/41 manual overrides**.
  Findings: strong at catching structural-observations-scored-as-trades (its NO_BASKET calls + the
  "three chip architectures" case), but overeager on NO_BASKET (100 flips) and overreaches on
  multi-ticker (added unnamed sector peers; invented a bogus `CBRS` ticker). **Do not bulk-apply** —
  operator triages which rows fold into `manual_overrides.json`.

**Workflow rule (operator, 2026-07-14):** analysis first → operator verifies numbers + data → only
THEN presentation edits. Do not touch deliverables/HTML until the analysis is signed off.

## Current State (as of 2026-07-06)

**Thesis audit + 13F AI-signal infrastructure COMPLETE.** A clean-separated analysis stack now
sits on top of the 13F pipeline views (Atreides, CIK 0001777813). Pieces, in order built:
- **Thesis audit** (`audit_theses.py` + `audit_prompt.py`, sonnet-4-6, ~$2.93): expanded every
  summary (134→1029 chars), cleaned contaminated tickers, recovered dropped `detail`/etc. →
  `analysis/thesis_timeline_v2.json` (+`_flat`) + per-thesis `analysis/thesis_audits/`.
- **AI classification** is authoritative from `analysis/ai_basket_reclassification.json` (operator
  file; per-ticker `{ai,bucket}`, NTNX date-segmented). `resolve_ai()` in `generate_13f_triggers.py`
  (retries digit-stripped ticker → fixes the `1CFLT` variant that dodged CFLT's exclusion).
- **Triggers** (`generate_13f_triggers.py` → `add_trigger_returns.py` → **`build_13f_analysis.py`**,
  the current canonical builder): 3 clean layers — `analysis/filing_to_filing_returns_universal.csv`
  (216 tickers × 24 filing-to-filing periods), `analysis/13f_signal_triggers_clean.csv` (102 events,
  NO returns), `analysis/ai_basket_definition.json`. Trigger types: AI_BASKET_RAMP (narrow
  picks-and-shovels basket, excl. AI/Hyperscaler+AI/EV), NEW_AI_SUBTHEME, AI_SUBTHEME_ACTIVE_CROSS_2/4PCT,
  NEW_AI_POSITION_2PCT.
- **Excel workbook** (`build_trigger_workbook.py`, openpyxl): `analysis/trigger_analysis.xlsx`, 6
  sheets (Ramp/NewSubtheme/NewPosition/Cross4pct/Cross2pct/RampBasket), single-period returns, locked
  baskets, EW/CW/SMH, green-red shading. All builders `mypy --strict` clean.
- **Also in tree (operator/other-session):** `reaudit_tickers.py` + `recompute_returns_*.py` +
  `step4_signal_events_v4/v5/v6*` outputs; `theme_returns_v2.py` was trimmed (14+/28-). Committed
  together as the analysis layer. Full decision log: SD-TRIG-1…18 + SD-AUDIT-1…5 in the impl notes
  (`docs/implementation_notes/13f_signal_triggers_implementation_notes.md`,
  `.../thesis_audit_implementation_notes.md`).

**Theme-basket return analysis COMPLETE (v3).** `tools/transcripts/theme_returns_v2.py` regenerates
signal events from scratch and computes forward returns. It (1) clusters the 319 theses into 52 themes
via the regex `keys`/`exclude` patterns in `analysis/theme_baskets_v2.json` (multi-assign; 207 clustered,
112 unclustered — expected for philosophy/meta theses), (2) runs an 8-type signal-event state machine
→ **137 events**, (3) resolves each event's date-aware basket, (4) pulls/caches EODHD adjusted closes for
a 46-ticker universe (cache `analysis/eod_prices/`, 0.5s pacing, only-new-tickers-fetched), (5) computes
equal-weight basket + SMH + excess returns at 1m/1q/1y/2y, and (6) writes `analysis/step4_signal_events_v3.csv`
+ summary stats (events-by-type, clustered/unclustered, avg return & win-rate by type/source). Spot-checks
pass (Optical 1y +82.57%, DRAM/HBM MU 1y +43.86%, SaaS SHORT sign-inverted, TGT run-then-fade; corrected
baskets verified: TSMC=NVDA/AVGO/MU, Custom-ASIC=GOOGL/AMZN, capex-ROI=AMZN/MSFT/GOOGL/META). An earlier
one-shot `theme_returns.py` (v1, event CSV as input rather than regenerated) is retained; its output is
`analysis/step4_signal_events_with_returns.csv`. `analysis/eod_prices/` is gitignored (regenerable, mirrors
the `data/price_cache/` convention). Decisions: `workstreams/transcripts-decisions.md`.

**Corpus COMPLETE — 27 transcripts** (`transcripts/`, `_master_manifest.json`). Built via
yt-dlp (auto-captions, not youtube-transcript-api), bs4 scrapes, and a PDF extract. Tiers:
21 `youtube_auto`, 1 `pdf_extracted` (Graham & Doddsville Issue 43), 2 `writeup_public_portion`
(HedgeFundAlpha), 3 `paywalled_lede` (themarket.ch). Spans Nov 2019 → Jun 2026.

**Thesis extraction COMPLETE — 27/27, 319 theses** (`analysis/`). `claude-sonnet-4-6` with the
operator's prompt, schema enforced via Messages API `output_config.format` (guaranteed-valid JSON).
Per-transcript JSON in `analysis/thesis_extractions/`, plus `all_summaries.json` and the flat
date-sorted `thesis_timeline.json` (the join-ready shape for the 13F cross-reference). Total run
~$3.36 (~550K in + 114K out tokens). `mypy` clean on the three new modules.

---

## Active specs in use

_No active specs._ — Both tasks were prompt-driven (no spec file). The operator's extraction
prompt + schema live in `tools/transcripts/extraction_prompt.py`.

---

## Immediate Next Steps

1. **Operator reviews `analysis/basket_reresolution.csv`** (207/241 re-resolutions changed; disagrees
   with 35/41 overrides). Triage which rows to accept; the accepted ones fold into
   `analysis/manual_overrides.json`, then re-run `theme_returns_v2` + `build_repeat_mention_events`
   (overrides auto-apply). **Caveat:** the opus-4-6 pass is NO_BASKET-aggressive and multi-ticker-overeager
   (added unnamed peers, one bogus `CBRS`) — do not bulk-apply. Optional helpers offered: filter the CSV
   to the high-signal subset, or add an agreement-vs-override column.
2. **Verify the SpaceX Nov-2021 override** — the re-resolver read the expanded summary as "Baker does not
   name specific short targets," contradicting the `VSAT/SATS/LUMN SHORT` override. Check the transcript.
3. **Bring Unity into signal scoring if wanted** — U is in the timeline + has its own theme now, but the
   thesis clustered fine; confirm the basket flows through (it does). Deferred: refresh the 13f_signal /
   returns cross-reference + any presentation deliverables ONLY after analysis sign-off (workflow rule).
4. **Cross-reference transcript theses ↔ 13F signals** (was #1) — join `thesis_timeline_v2_flat.json` to
   `13f_signal_triggers_clean.csv` on ticker+date once basket resolutions are settled.
2. **34 universal-returns tickers are all-`NO_DATA`** (CUSIP placeholders + foreign/odd EODHD
   symbols, all non-AI) — if price coverage for those is wanted, add a CUSIP→ticker map. (Flag only.)
3. **RampBasket CW missing-data** renormalizes among available names (parallels EW); switch to a
   fixed denominator if dilution-on-dropout is preferred (SD-TRIG-18, one-line change).
4. **(Optional)** proper-noun cleanup on youtube_auto transcripts; close 4 older ILTB corpus gaps.

---

## Key Files

**Corpus (`tools/transcripts/`):** `targets.py` (single source of truth: IDs/URLs/queries/paths/UA)
· `common.py` (UA session, json3→`[MM:SS]` converter, writers, manifest helpers) · `fetch_youtube.py`
· `discover_youtube.py` · `fetch_colossus.py` · `fetch_web.py` · `fetch_text.py` · `fetch_cnbc.py`
· `fetch_audio_whisper.py` (optional/unused — both targets covered via YouTube) · `build_manifest.py`
· `run_all.py` · `README.md`.

**Extraction (`tools/transcripts/`):** `extraction_prompt.py` (SYSTEM_PROMPT/USER_TEMPLATE/EXTRACTION_SCHEMA)
· `extract_theses.py` (sonnet-4-6 runner; `--force`/`--limit`/`--single`) · `aggregate_theses.py`.

**Returns analysis (`tools/transcripts/`):** `theme_returns_v2.py` (v3 regeneration: cluster → events →
baskets → EODHD prices → returns → `step4_signal_events_v3.csv`; `--force-refetch`) · `theme_returns.py`
(v1, CSV-driven precursor → `step4_signal_events_with_returns.csv`). Inputs: `analysis/theme_baskets_v2.json`
(52 themes, regex keys/exclude), `analysis/thesis_timeline.json`. Cache: `analysis/eod_prices/` (gitignored).

**Data:** `transcripts/{youtube,colossus,web,text,whisper}/` + `transcripts/_master_manifest.json` ·
`analysis/thesis_extractions/*.json` + `analysis/all_summaries.json` + `analysis/thesis_timeline.json`
+ `analysis/_extraction_log.json`.

---

## Settled Decisions (key rules)

1. **YouTube via `yt-dlp`**, not `youtube-transcript-api` (latter uninstalled + IP-block-prone).
2. **Structured outputs enforce the schema** (`output_config.format`) → guaranteed-valid JSON; the
   prompt-only `.raw` fallback is a near-dead safety net.
3. **Model `claude-sonnet-4-6`** is operator-chosen (cheap/fast structured extraction); constants
   (model, max_tokens, costs, paths) live at the top of `extract_theses.py` / in `targets.py`.
4. **Real API key loads from `.env` with `override=True`** — the shell `ANTHROPIC_API_KEY` is a
   placeholder; the loader asserts `sk-ant-` prefix and fails fast otherwise.
5. **Pragmatic rigor** (operator-approved): type hints + clean structure, no mocked-network pytest
   suite. Verification = manifests + spot-checks. Corpus is committed to git.
6. **Idempotent runs** — every fetcher and the extractor skip existing outputs unless `--force`.
