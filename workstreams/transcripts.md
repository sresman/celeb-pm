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

## Current State (as of 2026-07-01)

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

1. **Second-pass analysis** — cross-reference `analysis/thesis_timeline.json` (each thesis tagged
   with date/source/confidence/themes/tickers_named/tickers_implied) against the 13F position
   data from `src/celebpm` (CIK 0001777813, Atreides). The timeline is the intended input shape.
2. **(Optional) proper-noun cleanup pass** on the youtube_auto transcripts (TSMC→"TSM C",
   Trainium→"training him") before any re-extraction — noted in `tools/transcripts/README.md`.
3. **(Optional) close corpus gaps** — 4 older ILTB episodes (2019–2022) have no YouTube mirror and
   Colossus is JS-gated; CNBC video has no captions. See README "Known gaps".

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
