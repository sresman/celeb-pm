# Transcripts Workstream — Decisions

> Companion to `workstreams/transcripts.md`. Loaded on demand, not at startup.
> Append new decisions with dates; keep the workstream doc's summary lean.

---

## 2026-07-06 — Thesis audit + 13F AI-signal infrastructure + Excel workbook

Full per-decision detail lives in `docs/implementation_notes/13f_signal_triggers_implementation_notes.md`
(SD-TRIG-1…18) and `docs/implementation_notes/thesis_audit_implementation_notes.md` (SD-AUDIT-1…5).
Key decisions, condensed:

- **AI classification source of truth** = `analysis/ai_basket_reclassification.json` (operator-authored,
  per-ticker `{ai, bucket}`; NTNX date-segmented at 2024-01-01 → not-AI before, AI after). Supersedes the
  hardcoded theme lists. `resolve_ai(reclass, ticker, filing_date, theme_col)` in `generate_13f_triggers.py`;
  fallback for tickers absent from the file = theme column startswith `AI/`/`Semiconductor`.
- **Digit-prefixed ticker fix:** the pipeline emits variants like `1CFLT`/`0JPHL`; `resolve_ai` retries the
  lookup with leading digits stripped, so Confluent's explicit `ai:false` exclusion isn't dodged. Removed a
  phantom AI/Data-Infrastructure sub-theme and shrank two ramp events.
- **Narrow ramp basket (Trigger 1 only):** AI *and* bucket ∉ {AI/Hyperscaler, AI/EV}. Feb-2022 ramp fell
  ~+20pt→+9.7pt once AMZN/TSLA excluded. Triggers 2/2b/3 use the full AI classification.
- **Clean separation:** triggers file carries NO returns; returns live in
  `filing_to_filing_returns_universal.csv` (every COMMON ticker + SMH + SPY × 24 filing-to-filing periods).
  `build_13f_analysis.py` is the canonical builder (default builds all 3 layers; `--skip-universal` for
  fast trigger-only reruns). `generate_13f_triggers.py` + `add_trigger_returns.py` retained but superseded.
- **Locked baskets, single-period, filing-anchored:** basket returns are equal-weight of constituents locked
  at the signal date (drop NO_DATA/PRE_IPO for a period); never rebalanced; never compounded in the workbook.
- **Excel workbook:** cells are numeric fractions with percent number-formats (not text), so they stay
  sortable/colorable. RampBasket CW renormalizes among names with data that period (parallels EW);
  fixed-denominator dilution is the rejected alternative (easy switch).
- **Env:** installed `openpyxl` into `.venv` (mandated, was absent); openpyxl imports carry
  `# type: ignore[import-untyped]` (no stubs). All new builders `mypy --strict` clean.

---

## 2026-07-01 — Theme-basket return analysis (theme_returns.py / theme_returns_v2.py)

**Context:** Two one-shot enrichment tasks. v1 (`theme_returns.py`) filled return columns on a
pre-built event CSV. v2 (`theme_returns_v2.py`) is a clean regeneration of the events themselves
from `thesis_timeline.json` + `theme_baskets_v2.json`, then the same return math. Both are
standalone of `src/celebpm` (operator constraint) and load `EODHD_API_KEY` from `.env` with dotenv
`override=True` (the `extract_theses.py` pattern).

### Return engine (shared by both scripts)
- **SPY is the master trading calendar.** N-trading-days-forward is measured on SPY's continuous
  US market index (2020→today); basket/SMH closes are looked up on those exact dates. A ticker
  absent on a date (pre-IPO / delisted) is excluded from that interval's equal-weight average.
- **Horizons** = 1m/1q/1y/2y ≙ 21/63/252/504 forward trading days. End index past the last SPY day
  → `INSUFFICIENT_DATA`. No priced ticker at either endpoint → `NO_DATA` (v2) / `PRE_IPO` (v1).
- **Direction:** LONG raw; SHORT negates the basket return (decline = positive signal); MIXED raw.
  `excess = direction-adjusted-basket − SMH`. SMH is computed for every event regardless of basket
  (including `NO_BASKET` events, where `ret_*`/`excess_*` = `NO_BASKET` but `smh_*` is numeric).
- **`theme_baskets*.json` is authoritative for baskets**, superseding any pre-filled `basket` column
  in the input CSV (which was stale — e.g. a row said `NO_BASKET` where the JSON resolves a basket).

### Date-segment resolution (operator-confirmed)
- **Chronological breakpoint, NOT literal "last match wins."** Walk segments in order; the first
  `before` whose bound exceeds the event date wins; fall through to the `after` segment if none.
  **Why:** the space themes have multiple overlapping `before` bounds — literal last-match would give
  a 2022 event the 2024–2026 basket (LUNR/ASTS, not yet public). Breakpoint semantics matches intent.

### v2 clustering + event state machine
- **Clustering uses `re.search` on the regex `keys`/`exclude`** against the lowercased summary — NOT
  substring `in`, and NOT the thesis `themes` tag list (too fragmented). A thesis may map to multiple
  themes (intentional). Unclustered theses are counted and reported, never fatal.
- **`mention_number` / `total_theme_mentions` are unique-date based** (1-based index of the event's
  date within the theme's distinct dates / count of distinct dates), not per-thesis.
- **First-date event:** `FIRST_MENTION_AND_HC` if *any* thesis on the theme's first unique date is
  `high_conviction`, else `FIRST_MENTION`.
- **Dedup key is `(date, theme, event_type)`** — multiple distinct theses on one date can legitimately
  trigger different event types (e.g. `FIRST_MENTION_WITH_TICKERS` + `FIRST_SMID_TICKER` same row);
  those are not duplicates.
- **THESIS_REVERSAL light guard (operator-confirmed):** flag a LONG-theme thesis whose summary holds a
  bearish keyword (losing/lost/risk/mistake/bubble/worst/flinched/break down), BUT skip a match when
  that keyword also appears in the theme's own `keys` patterns. **Why:** anti-bubble/bullish themes
  ("AI bubble not happening") contain "bubble" in nearly every summary — verbatim matching floods the
  output with self-referential false reversals. The guard suppresses those while keeping genuine
  off-keyword tonal turns (11 reversal events, not flooded).

### Data / repo hygiene
- **`analysis/eod_prices/` is gitignored** (9.3M, regenerable from EODHD), mirroring the existing
  `data/price_cache/` convention. Scripts are idempotent: cached tickers are not re-fetched unless
  `--force-refetch`; only the 12 v2-new tickers (ASML/CCJ/DISH/EA/MA/META/MSTR/ORCL/RBLX/TGT/TTWO/V)
  hit the API on the v2 run.
- **Ticker → EODHD symbol** = append `.US`; `adjusted_close` (split-adjusted) is the price field;
  bad/≤0 closes are dropped per-bar. No class-share edge cases in this universe.

---

## 2026-07-14 — Corpus audit, gap-fill, re-score, durable overrides, basket re-resolution

**Data-integrity: verify dates via `yt-dlp` upload date, not the corpus.** Five files were mis-dated.
For same-day-upload sources (podcasts), upload date = episode date, so a mismatch is a real error. Two
"2024-06-15" All-In files were actually June 2026; TBPN "2025-11-15" was 2026-06-15; Aleph "2024-02-14"
was 2025-10-22 (content confirms: DeepSeek R1 / Lip-Bu Tan / Intel gov't stake — all 2025); iConnections
"2024" was Global Alts Miami **2026**. Fixed at ALL layers (targets.py is the source of truth for `date`;
manifest/transcript/extraction propagate) because a partial fix creeps back on rebuild. **Why:** the
project anchors signals on appearance date; a wrong date misplaces the signal by up to 2 years.

**Fetch pipeline is YouTube-caption-centric; Whisper is the fallback.** Colossus renders client-side
(use YT mirrors); CNBC has no captions; pre-2025 ILTB episodes are podcast-audio-only. `fetch_audio_whisper`
(small model, CPU — `medium`/MPS tested *slower*) covered CNBC + 4 ILTB. **`fetch_prices` now tolerates
404** (invalid/private tickers like CRSO/Crusoe → cached empty → NO_DATA) instead of crashing the run.

**Durable manual-override layer (`analysis/manual_overrides.json`).** Applied AFTER clustering + basket
resolution, immediately BEFORE returns, so it survives every rebuild. Two kinds: **cluster_overrides**
(re-theme a thesis) run pre-event-generation; **event_overrides** (basket/source/direction + flags) run
post-resolve. Shared helpers (`load_overrides`/`apply_cluster_overrides`/`find_event_override`/
`apply_event_override`) live in `theme_returns_v2.py` and are imported by `build_repeat_mention_events.py`
so both grains stay consistent. Match keys: theme / date / mention_number / summary_contains. **Why a
layer, not edits to theme_baskets:** basket corrections that generalize live in `theme_baskets_v3.json`
(the `"CORRECTED:"` notes); per-mention/per-thesis exceptions that clustering can't express live in the
override file. Overrides win over clustering by design.

**Event grain restructured for the noise-vs-criteria test (`build_repeat_mention_events.py`, NEW).**
`theme_returns_v2` emits one row per criterion-triggered event; the operator wanted one row per
(theme, mention) with `is_repeat_mention` (mention ≥ 2) as the broad superset and the 4 existing criteria
(`is_third_within_1yr`, `is_first_hc_not_first_mention`, `is_first_with_tickers`, `is_hc_high_profile_venue`)
as separate booleans → the `slice_summary` 3-way (all repeats / criteria-met / control). Same-date
flywheel/compute-demand conflicts resolved by **override-aware representative-thesis selection**.

**THESIS_REVERSAL guard tightened (Part 4).** Old detector fired on bearish keywords (17 fires, mostly
false). New guard (`is_stance_reversal`) requires a self-stance-change phrase (no-longer / used-to /
was-wrong / lost-its-leadership) on the **summary only** (matching summary_extended over-fired on audit
prose). Now 2 fires: genuine Google-TPU 2026-05-20 + a defensible Intel-2020 "lost its 50-year lead"
(cosmetic — doesn't change basket/stats). DRAM/TSMC/SpaceX false positives eliminated.

**New themes must not collide (7 added, 52→59).** Bare `world model` / `terrestrial data center` /
`ev/net pp&e` / `cooling` all collide with existing or sibling themes; used specific phrases
(`unity software`, `never be decommissioned` / `installed physical asset` / `hope diamond`,
`cooling ecosystem`) and collision-tested against all 507 theses (each captures exactly its targets,
Unity∩gaming = 0).

**Basket re-resolution is a REVIEW artifact, not an applied change (`reresolve_baskets.py`, opus-4-6).**
Per the operator's workflow rule (analysis → verify → then apply), the second-opinion pass writes
`basket_reresolution.csv` and touches nothing. One API call per thesis (max attention over
batch-multiple-per-call), adaptive thinking, structured output via `output_config.format`. **Model:
`claude-opus-4-6`** — operator explicitly said "opus 4.6" (a real active model; `claude-opus-4-8` is the
current top Opus at the same price if ever preferred). **Finding:** useful but noisy second opinion —
NO_BASKET-aggressive (100 flips) and multi-ticker-overeager (adds unnamed peers, hallucinated `CBRS`);
disagreeing with 35/41 overrides mostly reflects that aggression, not that the overrides are wrong.
Treat as triage input, not ground truth.
