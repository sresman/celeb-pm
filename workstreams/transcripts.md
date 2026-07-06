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

1. **Cross-reference transcript theses ↔ 13F signals** — the two halves now exist
   (`analysis/thesis_timeline_v2_flat.json` + `analysis/13f_signal_triggers_clean.csv` /
   `filing_to_filing_returns_universal.csv`). Join Baker's stated theses to his actual
   13F trigger events on ticker+date to see which stated views he backed with capital.
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
