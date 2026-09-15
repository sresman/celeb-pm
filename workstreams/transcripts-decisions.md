# Transcripts Workstream — Decisions

> Companion to `workstreams/transcripts.md`. Loaded on demand, not at startup.
> Append new decisions with dates; keep the workstream doc's summary lean.

---

## 2026-08-10 — 2 new appearances → v8; targeted regex word-boundary fix → v9

### 2 new appearances (SD-2NEW)
- **SD-2NEW-1: source = fomo-fund-monitor triage.** 25 YouTube IDs triaged there; operator confirmed
  exactly 2 genuine new Baker appearances (ILTB `NGsi2PC4y68` 2026-08-04; Aria `MmNWwIYFBeI` 2026-04-16).
  Both **solo Baker** → full attribution, no co-guest/interviewer split (contrast Heller House SD-6NEW-1).
- **SD-2NEW-2: curation-gate decisions.** (1) Null 4 substring-false-positive clusters (see SD-REGEX-2).
  (2) Leave high-conviction *unclustered* theses as noise — T4 (hyperscaler OCF / $700B Blackwell-Rubin
  credit gap) is a macro framework call, not a ticker thesis; T7/T9 NVDA views are already well-captured
  corpus-wide; targeted overrides = maintenance surface without added signal; they'll cluster naturally if
  repeated. (3) No new themes for regulatory tail-risk (T19) / token-for-labor (T17) — one-off framings,
  no investable basket.
- **SD-2NEW-3: reaudit no-op is verified, not assumed.** 0 of 27 new theses met reaudit A/B/C (max 4
  tickers < 5; no ETFs; T3/T4 mega-caps are named in-text so not orphan-B) — checked via the tool's own
  `selection_reason`.

### Regex word-boundary fix (SD-REGEX)
- **SD-REGEX-1: targeted, NOT blanket.** Dry-run re-clustered all 589 theses with `\b`-anchored keys:
  blanket anchoring removes 133 matches but ~94 are legitimate stem/prefix matches (disaggregat→
  disaggregation, distill→distillation, scaling law→scaling laws, stablecoin→stablecoins, export
  control→export controls, …). It would drop 27 events / 20 material / 7 meets-criteria — mostly
  regressions. Rejected. See `analysis/regex_word_boundary_audit.md`.
- **SD-REGEX-2: fix = 4 collision keys only.** `dram`→`\bdram\b` (kills "dramatically"; needs BOTH
  bounds since the word starts at a boundary), `cien`→`\bcien` (efficient/efficiency), `lite`→`\blite`
  (satellites), `tpu`→`\btpu` (output). Leading-`\b` keeps plurals (tpus, ciena). `tpu.*v8`/`tpu.*cost`
  verified to have no residual "output" FP → left as-is. All stem/prefix keys untouched.
- **SD-REGEX-3: v9 is a correction that MOVES historical stats — needed sign-off.** Removed 2 spurious
  Optical events; 2023-04-21 was a meets-criteria "winner" (+13.5% 1y) that was really an All-In
  Starlink/satellites thesis (`lite`←"satellites"). Removing a below-average winner RAISED the signal
  mean (240.5%→257.8%). 0 return changes on shared rows; 3 Optical mentions renumbered (mention_number only).

### Open / flagged (2026-08-10)
- **PIPELINE_MAP "minimal re-run" recipe is unsafe.** `fetch_youtube <ids>` overwrites
  `youtube/_manifest.json` with only the passed IDs; `build_manifest` then truncated
  `_master_manifest.json` 45→16. Recovered by re-running `fetch_youtube` with no args. Fix:
  make `write_step_manifest` merge-by-id, or amend the doc to always fetch full-corpus before build.
- **3 redundant cluster_overrides** (tpu/dram/cien from the v8 task) now subsumed by SD-REGEX-2;
  harmless/idempotent, left in place. The `compute.*scale`→"hyperscaler" override on ILTB T3 is NOT a
  substring collision (real words) and is still needed.
- **`coherent` key over-matches** semantically ("coherent cluster" xAI theses land in Optical) — not a
  word-boundary issue; handled per-thesis via existing overrides.

---

## 2026-08-01 — 6 new appearances added → signal events v7

Full detail: `analysis/six_new_appearances_implementation_notes.md` (SD-6NEW-1…3),
`analysis/six_new_appearances_curation_gate.md`, `analysis/v6_to_v7_changelog.md`. Committed as `17b1488`.

**Ingestion**
- Corpus 39 → **45** transcripts, 507 → **562** theses. 3 YouTube (yt-dlp), 2 CNBC via **local Whisper
  `small`** (HLS `hls-264` audio → mp3 → whisper; CNBC has no captions), 1 Sohn AU 2021 as a labeled
  **`secondary_coverage`** web transcript (primary gated/404, no YT mirror; assembled from Sohn H&M +
  AFR write-ups with reported quotes — NOT verbatim).
- **Pipeline gotcha (logged):** `fetch_youtube <ids>` OVERWRITES `youtube/_manifest.json` with only the
  passed IDs (transcript files untouched). Always re-run `fetch_youtube` with NO args before
  `build_manifest` so the step-manifest is complete. Missing this dropped the master manifest 45→17 once.

**SD-6NEW-1 — Heller House reversal.** `jOgbqt04eUk` (Baker *interviews* SpaceX CFO Johnsen) was re-added
after its 2026-07-08 red-herring removal, then — per operator at the gate — **all 11 theses removed from
scoring** (they're the CFO's operational claims, not Baker's views; they clustered into tradeable
AI/space baskets). Mechanism: 15 `cluster_override` null removals (one per theme membership), extractions
retained on disk. Confirmed 0 Heller rows in v7.

**SD-6NEW-2 — new theme + keys (operator-approved, blast-radius reviewed).**
- New theme `Crypto / Coinbase (COIN)` LONG `[COIN]`; `COIN` added to `theme_returns_v2.UNIVERSE`.
- 3 keys added, each ticker/basket-connected: `lowest.?cost token` (Inference economics),
  `electricity generation` (Power/watts), `structurally short (of )?compute` (Reasoning/inference-time).
- **Declined** `blackwell`/`hopper` keys — 15/4-thesis blast radius (re-clusters many already-clustered
  theses). Consequence: All-In-tariffs T5/T6 stay NO_BASKET by choice.

**SD-6NEW-3 — event overrides are now DATE-ANCHORED.** Renumbering (inserting earlier-dated appearances)
silently broke event-overrides keyed by `(date, mention_number)` — stale mention numbers stopped matching
→ 9 SpaceX events reverted baskets. Root cause: `mention_number` is a fragile derived key; `(theme,date)`
is unique in the mention grain. **Fix:** stripped `mention_number` from all 73 dated event-overrides
(0 used it without a date → lossless). Immunizes the file against future renumbering; also activated
3 dormant DRAM overrides (`MU` → `MU, 000660.KS`, 0 return impact — SK Hynix is NO_DATA on EODHD).
**Rule going forward:** never key an override on `mention_number`; use `theme`+`date`(+`summary_contains`).

**Deliverable versioning.** `build_repeat_mention_events.py` output bumped v6 → **v7**
(`step4_signal_events_v7_with_returns_extended.{csv,xlsx}`); v6 kept for the diff. `theme_returns_v2.py`
still writes `step4_signal_events_v5.csv` (criterion grain). v6→v7: +15 events, 0 removed, 0 basket/return
changes on pre-existing rows, 21 pure mention renumbers.

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

---

## 2026-07-22 — Basket resolutions applied + 13F net-buying ramp + Unity

### Baker thesis-scoring (manual_overrides.json + theme_returns_v2.py)
- **cluster_overrides now support removal.** `to_theme`/`new_theme` = null/"unclustered" drops the
  matched thesis from `from_theme` (no re-add) → generates no event, doesn't affect any theme's mention
  numbering. Match keys gained `thesis_id` (per-date ordinal). Removal is `from_theme`-scoped so a
  multi-clustered thesis survives in its correct theme (e.g. 2026-05-22 T15 removed from NVDA-moat but
  kept in China as NO_BASKET). WHY: sequential review found ~42 keyword-collision misclusters.
- **Matched removals by CONTENT, not the task's `Tn` labels** — the operator's thesis_id labels were
  inconsistent with the timeline (~13/29 wrong); resolved each against the theses actually clustered in
  the theme. Validated against operator's target mention counts.
- **Two macro themes are theme-level NO_BASKET** ("AI capex ROI positive", "Broad AI bullish / early
  innings") — never-a-trade regardless of mention number. This SUPERSEDED an earlier v4 CHANGE (AI-capex
  m4 2025-03-29 → NVDA); latest review wins.
- **theme_returns_v2 OUTPUT_FIELDS bug fixed** — added `override_note` + the 4 override-flag columns;
  `apply_event_override` set them but the DictWriter fieldnames omitted them → `ValueError` on any
  overridden row (was masked in prior runs by piping through `tail`). `step4_signal_events_v3.csv`/`_v5.csv`
  are its outputs (not the deliverable; the deliverable xlsx comes from build_repeat_mention_events).
- **UNIVERSE extended** (theme_returns_v2) with WMT/HD/LOW/COST/KR/000660.KS for the v4 retail + DRAM
  baskets; 000660.KS (SK Hynix) 404s on EODHD → graceful NO_DATA, DRAM still scores via MU.

### 13F AI-signal layer (build_13f_analysis.py + build_trigger_workbook.py)
- **Unity U → "AI/World Models"** in `ai_basket_reclassification.json`; RBLX deliberately NOT AI (gaming
  in Baker's framing). Ramp membership is exclusion-based (`_in_ramp`: is_ai & not Hyperscaler/EV), so U
  auto-flows; `RAMP_INCLUDED_BUCKETS` is only the definition-doc list.
- **Ramp trigger = net buying, not weight drift.** `compute_net_buying` reads `positions.json` share
  deltas for the narrow AI basket: Δshares×current price (buys/sells) + new-position value; net as % of
  total portfolio value; fires ≥5%. WHY: weight can rise on price alone (May-2026 "ramp" +13.7pt while a
  net seller of ~$109M).
- **DEVIATION (documented, toggle `COUNT_EXITS`): full exits are NOT counted as selling.** Spec text said
  count them, but that gave May-2025 +$381M / May-2026 −$402M; excluding exits reproduces the operator's
  stated targets exactly (May-2025 +$561,990,623 ≈ $562M). The fire/no-fire verdicts hold either way.
- **value_reported units normalized per filing** — $thousands pre-2023-Q4, whole-$ after (detected via
  max implied price/share ≥$15 → dollars, else ×1000). Applied to all $ outputs so net_buying_dollars &
  the `+$NNM` ticker detail read as real dollars across eras. Percent columns are ratios (unit-safe).

### Open / flagged
- **DRAM = 9 mentions, not the requested 7** — all 9 are genuine HBM/DRAM theses; target predates recent
  corpus gap-fill. Operator to say which 2 (if any) to drop.
- **Unity NewPosition**: enters at 1.88% equity weight (< 2% threshold) so no NEW_AI_POSITION_2PCT event;
  captured as NEW_AI_SUBTHEME. Operator's 2.7%/6.7% figures are a different basis than 13F equity-only.
- **Minor**: the `15.0`/`1000.0` units-detection constants in `compute_net_buying` are inline magic
  numbers (documented); could be promoted to module constants.

---

## 2026-09-08 — Speaker attribution

### SD-ATTR-1 — The problem, and why nothing caught it

`extract_theses` receives an undifferentiated transcript. YouTube auto-captions
mark a speaker change with `>>` but never name anyone, and 19 of 47 transcripts
carry no markers at all — a panel arrives as one prose block. The prompt opened
"a transcript of Gavin Baker" and asked for "Baker's alpha-relevant commentary",
actively priming attribution to him, and the thesis schema had no speaker field.
Three layers with no way to represent "someone else said this".

Measured over all 47 appearances: **73% of named-ticker slots attribute to Baker,
11% to another speaker, 16% indeterminate.** Panel episodes: 44% contamination.
Solo episodes were NOT clean either — 21% — because an interviewer with
substantive views (or a co-guest) reads the same as the subject.

Canonical case: All-In 2026-08-14 T14, `AMZN`, *"I have a very big position in
Amazon and I keep increasing it every year"* → Jason Calacanis. It survives a
naive "does Baker hold AMZN?" check because Atreides does hold AMZN (2.07% of
equity, 2026-06-30). The tell is rhetorical register, not holdings.

### SD-ATTR-2 — Attribution goes in a separate pass, NOT the extraction schema

**Decision: `audit_attribution.py`, a non-destructive second pass. Extraction is
untouched.**

The obvious design — add `speaker_attribution` to `EXTRACTION_SCHEMA` and teach
the prompt about multi-speaker transcripts — was tried across five prompt
revisions and **collapsed extraction yield on roughly half the corpus**
(2024-08-27: 20 theses → 1; 2024-12-07: 17 → 1; 2022-01-25: 17 → 1). A bisect
isolated it:

    original prose + original schema    -> 20 theses
    original prose + attribution fields -> 21 theses   (schema change is free)
    rewritten prose + same fields       ->  1 thesis   (prose was the cause)

but a subsequent 22-episode run showed ~50% collapse even on the "good" config,
so the schema route was abandoned entirely and the corpus restored from git.

The audit pass gets the same result for ~$1.32, keys per thesis on a focused
transcript window, writes only to `analysis/attribution_audit/`, and cannot
damage the corpus. It caught both canonical cases (Calacanis on AMZN; Johnsen on
Heller House) with cited cues.

### SD-ATTR-3 — `indeterminate` does not count as Baker

Operator decision. Theses stay in the corpus tagged (so it is reversible), but
the filtering layer treats **only `subject`** as Baker. Rationale: BAKER_NAMED's
alpha rests on Baker's specificity, so "probably him" is not good enough. Cost:
16% of named-ticker slots.

### SD-ATTR-4 — Two-of-two agreement test

Operator decision. Run the audit twice; disagreement between passes →
`indeterminate`. Motivated by observed per-thesis instability: the same config
attributed the AMZN thesis to Calacanis in one draw and did not flag it in the
next. Inline attribution reliably reduces contamination but does not reliably
catch any SPECIFIC instance.

### SD-ATTR-5 — Two appearances are not appearances

- **Limitless/Bankless 2026-05-28 — REMOVED.** Baker is not on it. Title "What
  The Best AI Investors Are Buying Right Now"; opens "Gavin Baker is one of the
  most prolific AI investors that almost no one has heard of. He spent the last
  20 years..." — third person throughout, two hosts, and it garbles Atreides as
  "a Trade Desk Management". Audit: 14/14 theses `other`, 19/19 tickers.
- **Heller House 2026-06-08 — REMOVED.** Baker is the interviewer. 97 turns, 6
  question-shaped (367 words) vs 91 answer-shaped (8,297) → 96% Johnsen;
  questions span turn 2..83 of 96; corporate "we/our/us" 228 in answers vs 10 in
  questions. Cost: 4 of 11 theses were genuinely Baker's framing claims
  (TMUS/T/VZ, NVDA) and went with it.
  **PRIOR ART:** the operator had already caught this in the 6-new task via 15
  `cluster_overrides` (2026-07-22, note "Heller House = Baker interviewing SpaceX
  CFO Johnsen") nulling each thesis's theme. Those overrides are now orphaned on
  a date that no longer exists — left in place deliberately as a record of the
  decision.

### SD-ATTR-6 — Only `theses` is consumed downstream

`explicit_recommendations`, `catalysts`, `sector_rankings`, `risk_warnings` and
`meta_views` are written by `extract_theses` and read by NOTHING. Pre-existing,
not introduced. Consequence: a claim routed to `meta_views` instead of `theses`
is functionally deleted, which is what made the failed prompt rewrites so
damaging.

`explicit_recommendations` holds **154 items across 42 of 48 appearances**, and
on unmodified episodes **76% name a ticker the theses do not**. It is directional
("buy Nvidia, high_conviction"; "avoid Apple") — arguably stronger signal than a
ticker inside a structural argument. Wiring it up is ADDITIVE (new events), not
corrective, so it belongs after returns unblock; it also needs ticker resolution
for the free-text `target` field and a `direction` concept the event model lacks.

### SD-ATTR-7 — Keying rules (learned the hard way, three times)

- **Never key on `date`.** Not unique: 2026-05-12 holds two records of one Sohn
  event (the YouTube talk and Khaira's write-up). A date-keyed map silently drops
  one, which invalidated one appearance in the first audit run.
- **Never key on a `host` string.** All-In host strings are byte-identical across
  episodes, so `replace(count=1)` hit the first occurrence every time and
  **shuffled rosters between episodes** (Travis Kalanick landed on 2025-03-29).
- **Never key on `label` with `str.find`** where labels repeat across lists: the
  ILTB labels exist in both `COLOSSUS_EPISODES` and `RSS_TARGETS`, which produced
  duplicate `subject_role` keys on six Colossus entries.
- Key on the entry's dict key, or on `label` scoped to one list.

### SD-ATTR-8 — Metadata sources

`targets.py` has **five** target lists (`YOUTUBE_VIDEOS`, `RSS_TARGETS`,
`COLOSSUS_EPISODES`, `TEXT_TARGETS`, `WEB_TARGETS`) plus `CNBC_TARGET`, plus the
new `SUPPLEMENTARY_METADATA` for three appearances acquired outside all of them
(`sohn_australia_2021_coinbase`, `cnbc_squawk_spacex_debut_2026jun`,
`cnbc_spacex_drawdown_2026jul`). Reading only the first two — as the audit
originally did — hands 15 appearances an empty participants field, the exact
condition that degrades attribution. Use `audit_attribution.metadata_by_label()`.

`host` was wrong across the corpus: All-In 2026-08-14 listed Chamath and
Friedberg, who are **never mentioned once** in the transcript ("David Saxs and
Gavin Baker are with us this week... we got a short crew"). Rosters re-derived
from transcript openings via `fix_participants.py`; roles normalised by a
deterministic rule (co-speaker count) because the model's own role calls were
inconsistent across episodes of the same show.

### SD-ATTR-9 — Validation sample size

Operator standing note, recorded because it cost a full corpus re-extract:
**validate on a sample large enough to see the failure you are testing for.** Two
episodes cannot detect a 50% collapse rate. Every "fix confirmed" in this session
that rested on one or two episodes was later falsified by a 19-22 episode run.

### SD-ATTR-10 — The attribution audit is keyed on `label`, never `date`

SD-ATTR-7 recorded the keying rule; the audit itself still broke it. Its episode
selection, transcript lookup and output filename were all date-keyed, with an
unused `transcript_by_label()` sitting beside them. 2026-05-12 holds two
appearances of one Sohn NY event (Khaira write-up, 4 theses; YouTube fireside, 8)
whose thesis_ids collide on T1..T4 — so 12 theses went into one call against one
transcript and produced one unjoinable output file. Fixed before either pass was
paid for. **The rule is not enforced anywhere; check it by hand in any new module
that touches the corpus.**

### SD-ATTR-11 — Attribution is overlaid at timeline rebuild, not stored in the audits

`rebuild_timelines()` reassembles the timeline from the 614 per-thesis files in
`analysis/thesis_audits/`, not from `_build_v2_entry()`. Fields added to that
function therefore only reach the timeline for theses re-audited afterwards —
which is why last session's `speaker_attribution` never appeared. The fix loads
`attribution_resolved.json` and merges at rebuild time. Consequence, deliberate:
re-running the ~$2.50 attribution audit never triggers the ~$2.29 thesis audit,
and the per-thesis audit files stay untouched. Also added `appearance_label` to
every timeline row and a `--rebuild-only` flag.

### SD-ATTR-12 — The filter ships defaulted OFF

`--attribution {all,subject}` on both `theme_returns_v2` and
`build_repeat_mention_events`, defaulting to `all`. The operator's rule is
`subject`-only, but the workflow rule (2026-07-14) is analysis → operator
verifies → only then deliverables. A filter that changes v9/v10 the moment
anyone re-runs the pipeline would violate that, so the default stays at the
pre-attribution behaviour until sign-off. Filtered runs write `_subject`-suffixed
files so the two can coexist. Flipping the default is one word in each module.

### SD-ATTR-13 — Vocabulary is translated once, in the reconciler

`audit_attribution` emits `baker`; the corpus and the filtering layer speak
`subject`/`other`/`indeterminate`. The map lives in
`reconcile_attribution.VERDICT_MAP` and nowhere else, keeping the investor-
specific word out of everything downstream of the audit (CLAUDE.md's
investor-agnostic rule).

### SD-ATTR-14 — Every API client in this tree needs an explicit timeout

`audit_attribution` built its client with `max_retries=3` and no `timeout`, and
wraps a bare `except Exception` around a second attempt. Pass 2 sat on one
stalled request for **55 minutes** with the process alive and no output. Added
`API_TIMEOUT_SECONDS = 180.0`. Recovery cost nothing because the module is
idempotent — re-running **without** `--force` skipped the 41 finished episodes
and still produced a complete summary.

Two corollaries worth generalising:
- **Always run these with `python -u`.** Stdout redirected to a file is
  block-buffered, so a long run shows nothing until it exits and a hang is
  indistinguishable from slowness.
- `audit_theses.py` has the same un-timed client construction. Not changed this
  session (out of scope), but it will hang the same way.

### SD-ATTR-15 — Two-of-two agreement came in at 95%, and the disagreement is harmless

583 of 614 agreed. Critically, `subject`→`subject` held 416 of pass 1's 422 calls
(98.6%): when a pass says the subject spoke, that is stable. The churn is
`other`↔`indeterminate` (17 of 31 disagreements), a distinction the filter does
not act on since both are excluded. So the rule costs 6 theses / 10 named tickers
and buys a defensible floor — a good trade. The rule does **not** protect against
correlated error: the 5 cold-open false positives are seen identically by both
passes.
