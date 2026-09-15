# Transcripts Workstream

> Living doc. Gavin Baker public-appearance transcript corpus + NLP signal extraction.
> Standalone of the 13F pipeline (`workstreams/main.md`). `/resume transcripts` reads this.

---

## What this is

A corpus of Gavin Baker (Atreides Management) public-appearance transcripts and a
structured-thesis extraction layer over it, for later cross-referencing of his stated
investment theses against his 13F filings. All code in `tools/transcripts/`; all data in
`transcripts/` + `analysis/`. Independent of `src/celebpm`.

Branch: **`main`**. `trigger-denominator-ex-spcx` fast-forwarded into it on
2026-09-15 and was deleted; all transcripts work now lands on `main` directly.

---

## Current State (as of 2026-09-15) — RETURNS UN-HELD; v10 REGENERATED ON SUBJECT

**The operator flipped the default to `subject` and unheld returns.** v10 is
regenerated off `main` with prices refreshed through 2026-09-14. This closes the
decision that had blocked the workstream since 2026-09-08.

- **`--attribution` now defaults to `subject`** in both `theme_returns_v2` and
  `build_repeat_mention_events` (`DEFAULT_ATTRIBUTION`). The filter keeps
  **467/614 theses** (105 indeterminate + 42 other excluded). Output paths are
  suffixed for any *non-default* mode, so `--attribution all` writes
  `_all`-suffixed files and a comparison run cannot overwrite the deliverable.
  Docstrings and `--help` were corrected — they still described the pre-flip
  polarity, including `_mode_path`'s claim that a filtered run must not
  overwrite the unfiltered deliverable, which is now backwards.
- **Branch resolved.** `trigger-denominator-ex-spcx` was a strict fast-forward of
  `main` (merge-base == `origin/main` tip, zero commits on main the branch
  lacked), so it landed as a ref update and the branch was deleted local +
  origin.
- **The run.** `theme_returns_v2 --force-refetch` (78 tickers, fresh through
  2026-09-14) → 139 events, 258 clustered / 209 unclustered. Then
  `build_repeat_mention_events` on the **warm cache** — it imports the same
  `fetch_prices` over the same `UNIVERSE`, so a second forced refetch would
  re-pull the identical 78 tickers (SD-ATTR-21). → 205 mention rows, 151 repeat
  mentions.
- **Deliverable: `analysis/step4_signal_events_v10_with_returns_extended.{csv,xlsx}`**
  (2 sheets: `signal_events` 205 rows, `slice_summary` 3). v9 and
  `step4_signal_events_v10_2026-08-16_preattribution.*` preserved.
- **What the fresh prices changed.** Row identity is identical to the
  cached-price run; 145 of 155 changed cells are `INSUFFICIENT_DATA` → a computed
  value, as the 2025-12-09 cohort crossed 9m and the 2026-06-11/12 cohorts
  crossed 1q. The other 10 are second-decimal adjusted-close revisions.

| slice | n | ret_1y | winrate_1y | 9m before → after |
| --- | ---: | ---: | ---: | --- |
| signal (meets criteria) | 38 | **228.53** | 100% | 107.99 → **100.14** (92.3% → 85.7%) |
| control (no criteria) | 112 | 29.68 | 47.1% | 13.59 → **23.38** (57.7% → 64.5%) |

**1y did not move.** The newly-computable 9m cohort narrows the signal-vs-control
gap at that horizon without closing it — quote 9m with that in mind.

**`000660.KS` (SK Hynix) returns `NO_DATA` from EODHD and always has.** The four
rows carrying it in `resolved_basket` have identical returns pre- and
post-refetch, so the forced refetch caused no regression and the equal-weight
basket simply drops it — but the three DRAM overrides adding it to `MU` have
never contributed anything, consistent with the "0 return impact" note from
2026-07-22. Needs a different symbol or a KRX-covering subscription tier to
actually participate. `CRSO` is `NO_DATA` by design (private).

Detail + SD-ATTR-20…21: `analysis/attribution_implementation_notes.md`.

---

## Current State (as of 2026-09-08, latest) — LOCATOR FIXED; FILTER COST ~15-19%

**The quote locator was the dominant cost of the attribution filter, not
contamination.** Fixed, corpus re-audited on the affected slice, comparison
regenerated. Default still NOT flipped — awaiting the operator.

- **`locate_turn` had two defects** (SD-ATTR-17). (a) `_norm` substitutes each
  punctuation char with a space without collapsing runs, so any quote with
  punctuation the caption lacks failed exact matching outright; fixed with a
  matching-only `_squash()` (`_norm` must stay length-preserving for
  `_char_window`). (b) the pass-3 fallback used `difflib.quick_ratio()` — an
  order-insensitive character-multiset *upper bound* — against only `t[:400]`,
  which is what placed quotes on plausible-but-wrong turns. Replaced with
  windowed character-4-gram containment, threshold **0.70** calibrated against
  simulated caption garbling (positives p05 = 0.81) and a cross-episode negative
  control (max 0.66).
  **Located rate 560/614 (91.2%) -> 599/614 (97.6%)**; 62 quotes silently
  relocated to a different turn.
- **Targeted re-audit** of the 119 window-changed theses (not just the 81 that
  merely looked broken — 32 of the rest carried decided verdicts formed on
  discredited windows). Run twice, merged into `*_v2` pass copies via new
  `--only` / `--out-dir`. Agreement 95.0% -> **96.2%**. $0.90 total.
- **Attribution now: 467 subject (76%) / 42 other (7%) / 105 indeterminate (17%)**
  on theses; **573 / 36 / 96** on the 705 named-ticker slots (81% subject, up
  from 70%). On the re-audited slice, 64% of named tickers resolved to subject.
- **Filter cost roughly halved**: named-ticker slots −18.7% (was −30.2%), scored
  rows −16.9% (was −29.6%), meets-criteria −14.0% (was −24.4%), themes lost 10 -> 7.
  26 of 61 themes are untouched. `TSMC capacity discipline` — the diagnostic case
  — is fully recovered, all three theses now `subject`.
- **Residual indeterminate is now mostly genuine**: placement failures fell from
  81 theses / 88 tickers to 34 / 25; 71 of the remaining 105 are real ambiguity,
  largely the 19 transcripts with no `>>` speaker markers.
- **`audit_theses.py` client timeout added** (SD-ATTR-19), matching
  `audit_attribution`.

**Reads as a stable signal with a bounded contamination haircut, not a materially
different corpus.** Returns still held; v10 not regenerated; default still `all`.

Detail: `analysis/attribution_implementation_notes.md`, SD-ATTR-17…19.

---

## Current State (as of 2026-09-08, mid-session) — ATTRIBUTION WIRED END-TO-END; RETURNS STILL HELD

**Both audit passes are run, reconciled, and wired into the timeline.** The
attribution plumbing described as missing below is now in place.

- **`audit_attribution` was keyed on `date`, not `label`** — fixed before
  spending. 2026-05-12 holds two appearances of one Sohn NY event whose
  thesis_ids collide on T1..T4; the date-keyed path bundled all 12 theses into
  one call against one transcript and wrote an unjoinable output file. Now
  label-keyed throughout (`select_episodes`, `label_by_date_source`,
  `{label}.json`).
- **Two passes, 95.0% agreement** (583/614). Resolved by the operator's
  two-of-two rule: **416 subject (68%) / 56 other (9%) / 142 indeterminate
  (23%)** on theses; **492 / 56 / 157** on the 705 named-ticker slots.
  `subject`→`subject` held 416 of 422 — the subject verdict is stable; the churn
  is `other`↔`indeterminate`, a distinction the filter does not act on.
  → `analysis/attribution_resolved.json`, `tools/transcripts/reconcile_attribution.py`.
- **Timeline rewired.** `audit_theses.rebuild_timelines()` overlays attribution
  from the resolved file (614/614 matched) and adds `appearance_label`. The
  overlay happens at rebuild, not in the per-thesis audit files, so re-running
  attribution never re-runs the expensive thesis audit. New `--rebuild-only`.
- **Filtering layer in** `theme_returns_v2` + `build_repeat_mention_events`:
  `--attribution {all,subject}`, **defaulting to `all`** so no deliverable moves
  before sign-off; filtered runs write `_subject`-suffixed outputs.
- **Aggregate comparison done** (`analysis/attribution_filter_comparison.md`,
  no returns computed): theses 614→416, mention rows 257→179, repeat mentions
  196→128, meets-criteria 86→65, scored rows 142→100, basket universe 71→61.
  **The "contamination is noise around a stable signal" hypothesis does not hold
  in aggregate — about a third goes away.** But the loss is non-uniform: the
  ticker-anchored themes are untouched (DRAM/HBM 10→10, Reasoning 7→7, Trainium
  5→5, Metaverse 5→5) while panel-narrative themes take the hit (SpaceX 17→10,
  Orbital 13→7, AI-bubble-not-happening 7→2). Ten themes vanish.

**AWAITING OPERATOR READ. Returns stay held; v10 not regenerated.**

Detail + decisions SD-ATTR-10…14: `analysis/attribution_implementation_notes.md`.

---

## Current State (as of 2026-09-08, earlier) — ATTRIBUTION AUDIT; CORPUS 614 THESES

**Found: the corpus attributed other speakers' claims to Baker.** `extract_theses`
reads an undifferentiated transcript (YouTube auto-captions mark speaker changes
with `>>` but never name anyone; 19 of 47 transcripts have no markers at all), the
prompt opened *"a transcript of Gavin Baker"* and asked for *"Baker's
alpha-relevant commentary"*, and the thesis schema had no speaker field. Nothing
in the pipeline could catch a co-host's claim being booked as Baker's.

**New tool: `tools/transcripts/audit_attribution.py`** — a non-destructive second
pass that attributes each thesis to `subject` / `other` / `indeterminate` from a
focused transcript window, writing to `analysis/attribution_audit/` only. Measured
over all 47 appearances (~$1.32): **73% of named-ticker slots attribute to Baker,
11% to another speaker, 16% indeterminate**; on panel episodes contamination ran
44%. Confirmed case — All-In 2026-08-14 T14, `AMZN`, *"I have a very big position
in Amazon and I keep increasing it every year"* → **Jason Calacanis**, which
passes a naive holdings check because Atreides does hold AMZN.

**Two appearances removed from the corpus** (dated comments in `targets.py`,
attribution records preserved outside the audit tree):
- Limitless/Bankless 2026-05-28 — **Baker is not on it**; two hosts discussing him
  in the third person. 14 theses / 19 ticker slots.
- Heller House 2026-06-08 — **Baker is the interviewer**; 96% of words are SpaceX
  CFO Bret Johnsen's, questions span turn 2..83 of 96. 11 theses. NOTE: the
  operator had already caught this in the 6-new task via 15 `cluster_overrides`
  (2026-07-22) that null its themes — those are now orphaned on a dead date and
  deliberately left as a record.

**Metadata repaired.** `host` was wrong or absent across the corpus (All-In
2026-08-14 listed Chamath and Friedberg, who are never mentioned once in the
transcript). Rosters re-derived from transcript openings; every appearance now
carries `host` + `subject_role` (30 guest / 16 panelist / 3 secondary / 1
unknown), sourced via `metadata_by_label()` across **all five** target lists plus
`CNBC_TARGET` plus a new `SUPPLEMENTARY_METADATA` block for the three appearances
acquired outside them.

**Corpus: 48 appearances, 614 theses, 705 named-ticker slots**, timeline coherent
with extractions. `mypy` clean (45 files).

**NOT done — returns are HELD.** The two-of-two audit passes, the `audit_theses`
rewiring to read attribution from the audit, the `subject`-only filtering layer,
and the aggregate before/after comparison. v10 is NOT regenerated.

---

## Current State (as of 2026-08-10)

> Branch **`main`** (committed + pushed: `e57de51` v8, `98442d3` v9).

**2 new appearances added end-to-end → v8, then a targeted regex fix → v9.** Corpus 45 → **47**
transcripts, 562 → **589** theses. New (from the fomo-fund-monitor YouTube triage; operator confirmed
2 of 25 candidates as genuine): **ILTB "Why the markets are pricing AI wrong"** (`NGsi2PC4y68`,
2026-08-04, 20 theses) + **Aria Networks "MFU"** (`MmNWwIYFBeI`, 2026-04-16, 7 theses). Both **solo
Baker** — full attribution, no co-guest split.

Curation gate (operator-reviewed): nulled 4 substring-false-positive clusters; left high-conviction
unclustered theses (T4 $700B credit-gap, T7/T9 NVDA) as noise; no new themes. **v8 = 238 events
(+8, 0 dropped, 0 return changes on 230 pre-existing).**

Then a **targeted regex word-boundary fix** to 4 collision keys in `theme_baskets_v3.json`
(`dram`→`\bdram\b`, `cien`→`\bcien`, `lite`→`\blite`, `tpu`→`\btpu`). A full dry-run showed blanket
`\b`-anchoring was destructive (would drop 27 events / 7 meets-criteria by killing legit stem keys),
so only the 4 true offenders were fixed. **v9 = 236 events (−2 spurious Optical events, 0 return
changes on shared rows);** signal slice improved n 45→44, ret_1y 240.5%→**257.8%**, 100% winrate.
Deliverable **`analysis/step4_signal_events_v9_with_returns_extended.{csv,xlsx}`** (v7, v8 preserved).
Detail: `two_new_appearances_implementation_notes.md`, `two_new_appearances_curation_gate.md`,
`v7_to_v8_changelog.md`, `regex_word_boundary_audit.md`, `v8_to_v9_changelog.md`; decisions
SD-2NEW-1…3 + SD-REGEX-1…3 in `workstreams/transcripts-decisions.md` (2026-08-10).

New known issues: (1) PIPELINE_MAP's "minimal re-run" recipe is unsafe — `fetch_youtube <ids>`
overwrites the per-step manifest and truncated the master 45→16 (recovered by re-running with no
args). (2) 3 cluster_overrides from the v8 task (tpu/dram/cien) are now redundant with the key fix
(harmless). (3) the `coherent` key still semantically over-matches ("coherent cluster") — not a
word-boundary issue, handled per-thesis via overrides.

## Current State (as of 2026-08-01)

> Branch **`main`** (the `baker-corpus-audit-rescore-2026-07` branch was merged to main + deleted).

**6 new appearances added end-to-end → signal events v7 (committed + pushed, `17b1488`).** Corpus
39 → **45** transcripts, 507 → **562** theses. New: All-In E125 (2023-04-21), All-In tariffs/AGI
(2025-07-17), Heller House CFO interview (2026-06-08), CNBC Sharpe SPACs (2021-08-09, Whisper),
CNBC SpaceX drawdown (2026-07-20, Whisper), Sohn AU Coinbase (2021-12-03, secondary coverage).
Deliverable **`analysis/step4_signal_events_v7_with_returns_extended.{csv,xlsx}`** (215 → 230 events).

Key outcomes (operator-reviewed at the curation gate): **Heller House = 0 scored** (Baker interviews
the SpaceX CFO; the 11 theses are the CFO's claims — removed via cluster_override null); new
**`Crypto / Coinbase (COIN)`** theme + `COIN` in UNIVERSE; 3 new ticker-connected keys added,
blackwell/hopper declined; **event overrides globally DATE-ANCHORED** (stripped `mention_number` from all
73 dated matches) after renumbering silently broke 9 SpaceX overrides — this also activated 3 dormant
DRAM overrides (`MU`→`MU,000660.KS`, 0 return impact). v6→v7: +15 events, 0 removed, 0 basket/return
changes on pre-existing rows. All touched modules `mypy --strict` clean. Detail:
`analysis/six_new_appearances_implementation_notes.md`, `analysis/v6_to_v7_changelog.md`,
`analysis/six_new_appearances_curation_gate.md`, `journal.txt`; decisions SD-6NEW-1…3 in
`workstreams/transcripts-decisions.md` (2026-08-01).

## Current State (as of 2026-07-22)

> Working branch this session: **`baker-corpus-audit-rescore-2026-07`**.

**Basket re-resolution APPLIED + 13F AI-signal layer extended (Unity, net-buying ramp).** Two
threads this session, both operator-reviewed:

- **Baker thesis-scoring — basket resolutions finalized.** (1) Second-opinion re-resolution pass
  over all 241 events via `claude-opus-4-6` → `analysis/basket_reresolution_v2.csv` (review artifact).
  (2) Applied the operator's v4 review (`analysis/basket_reresolution_v4.csv`) into
  `manual_overrides.json` — 102 event overrides (STEVE/CHANGE/NO_BASKET/continuation) + the two
  "never-a-trade" macro themes (AI-capex-ROI, Broad-AI-bullish) consolidated to theme-level NO_BASKET.
  (3) Clustering fix: 42 `cluster_override` **removals** (new null/`thesis_id` support) of misclustered
  theses + 8 NO_BASKET flags. (4) Three targeted corrections (Edge-AI→DRAM move, China embargo→NO_BASKET,
  TPU-roundtripping→NVDA-moat). Scored events 194 → **~100**; `step4_signal_events_v6_with_returns_extended.xlsx`
  regenerated each time. Diffs: `analysis/basket_v4_application_diff.md`, `analysis/clustering_fix_diff.md`,
  `analysis/basket_reresolution_v2_implementation_notes.md`.
- **13F AI-signal layer.** Added **Unity (U) → sub-theme "AI/World Models"** in
  `ai_basket_reclassification.json` (flows into ramp basket, sub-theme crossings; new-position trigger
  gated at 2% so U enters as NEW_AI_SUBTHEME not NEW_POSITION — flagged). **Rebuilt the ramp trigger on
  net buying** (deliberate capital deployment from `positions.json` share deltas, ≥5% of portfolio) instead
  of weight drift — May-2026 correctly no longer fires (net seller). Added buying-detail columns
  (net/gross buying %, $, tickers_bought/sold/new/exited) to the Ramp + RampBasket sheets of
  `trigger_analysis.xlsx`. Details in `docs/implementation_notes/13f_signal_triggers_implementation_notes.md`.

All touched modules `mypy --strict` clean. See `workstreams/transcripts-decisions.md` (2026-07-22).

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

**From 2026-09-15 — nothing is blocked.** The default is `subject`, returns are
un-held, v10 is on `main`. Open items, in rough priority order:

1. **The 9m horizon shifted under the refetch** (signal 107.99 → 100.14, control
   13.59 → 23.38). Worth a look before the 9m number goes anywhere external; 1y
   is unaffected.
2. **`000660.KS` has never contributed to a basket.** Decide whether SK Hynix
   belongs in the DRAM baskets enough to warrant a symbol change or a KRX data
   tier, or whether the three overrides should drop it.
3. **The residual caveats below still stand** — they were accepted as the cost of
   the filter, not resolved.
4. `explicit_recommendations` is still unwired (154 items / 42 appearances);
   `analysis/basket_reresolution_v2.csv` triage is still open from 2026-07-22.

**Caveats accepted when the filter was adopted (2026-09-15) — not fixed:**
- 105 theses are still `indeterminate` and excluded. 71 are genuine ambiguity
  (mostly the 19 transcripts with no `>>` markers); 34 are still placement
  failures carrying 25 named tickers. A looser rule (`subject` +
  `indeterminate`) is one line in `filter_by_attribution`.
- 5 `other` verdicts rest on the quote landing in turn 0 with the model reading
  it as a host intro; podcasts also cold-open with a replayed *guest* clip. Both
  passes see the same cue, so two-of-two does not catch it.
- The two Sohn write-ups (`subject_role: secondary`) are a third party's
  rendering of Baker's words — every quote is paraphrase, and the audit reads
  them as his. Unresolved since 2026-09-08.

**Superseded — kept for the reasoning:**

1. **READ `analysis/attribution_filter_comparison.md`.** The `subject`-only
   filter removes ~30% of the corpus and ~30% of scored rows. It is not the
   "barely moves" outcome the hypothesis expected, so the call on whether to
   adopt it is yours. Three things to weigh:
   (a) the ticker-anchored themes are untouched (DRAM/HBM, Reasoning, Trainium,
   Metaverse all unchanged) — the loss is concentrated in panel-narrative themes;
   (b) `TSMC capacity discipline` vanishes entirely, which looks wrong given it
   is a real Baker theme elsewhere — worth a spot-check before accepting;
   (c) **most of the `indeterminate` bucket is a bug, not ambiguity** — see
   SD-ATTR-16. Of 142 indeterminate theses, 54 had `quote_not_located` and a
   further 27 were shown the *wrong transcript turn* by `locate_turn`'s fuzzy
   fallback; only 61 are genuine ambiguity. That is 88 of 157 indeterminate
   named tickers lost to a locator failure. The three theses in the vanished
   TSMC theme are all this. Recommend fixing the locator before flipping the
   default, since the filter's cost is currently dominated by this rather than
   by contamination.
2. **Decide the default.** `--attribution` defaults to `all` in both
   `theme_returns_v2` and `build_repeat_mention_events` so nothing moved without
   sign-off. Flipping the default to `subject` is a one-word change in each.
3. **Then unhold returns and regenerate v10** — `--attribution <chosen>` writes
   `_subject`-suffixed outputs when filtered, so v9 stays intact for comparison.

Open flags carried forward:
- 5 of 71 `other` verdicts rest on the quote landing in turn 0 and the model
  reading turn 0 as a host intro. Podcasts also cold-open with a replayed *guest*
  clip; `bg2_spacex_ipo_2026jun` T1 and `iltb_gpus_tpus_..._2025dec` T8 look like
  that. ~1% of named tickers, conservative direction, not fixed.
- `cnbc_sharpe_angle_spacs_2021aug` — 6/6 quotes unlocatable in the Whisper
  transcript, so all 6 theses force to `indeterminate`. Pre-existing.
- The two Sohn write-ups (`subject_role: secondary`) are a third party's
  rendering of Baker's words, so every quote is paraphrase; the audit reads them
  as Baker. Still unresolved from the previous session.

**From 2026-08-10 (2-new-appearances + regex fix):** v9 is live on `main` (pushed). Optional
follow-ups, none blocking: (a) drop the 3 now-redundant tpu/dram/cien cluster_overrides (SD-REGEX-2);
(b) harden the corpus tooling — make `write_step_manifest` merge-by-id so `fetch_youtube <ids>` can't
truncate the master manifest, or fix the PIPELINE_MAP recipe; (c) the 2026-08-04 ILTB events are too
recent for forward returns — refresh once ~1q accrues; (d) consider whether `coherent` should be
tightened (semantic over-match into Optical, currently patched via overrides).

**From 2026-08-01 (6-new-appearances):** (a) v7 is live on `main` (pushed). (b) Open flags, none blocking:
All-In E125 (2023-04-21) Starship theses likely trace to co-guest Gracias, not Baker — decide keep/drop;
`journal.txt` was created fresh (no prior journal existed in-repo) — confirm location/format or point to the
real one; private tickers (Anthropic/OpenAI/xAI/SpaceX) sit in tickers_direct as NO_DATA (harmless).
(c) The 2026-07-20 events are too recent to have forward returns — refresh once ~1q of data accrues.

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

**Added 2026-09-08:**
- **Attribution belongs in a SEPARATE audit pass, never in the extraction schema.**
  Adding attribution fields to `EXTRACTION_SCHEMA` and rewriting the prompt
  collapsed extraction yield on ~50% of episodes (2024-08-27: 20 theses → 1).
  `audit_attribution.py` achieves the same result for ~$1.32 with zero corpus risk.
- **`extraction_prompt.SYSTEM_PROMPT` is structurally fragile.** One added sentence
  plus three user-template lines dropped an episode from 21 theses to 1, with the
  content re-routed into `meta_views`. Change it by minimal diff only and verify
  thesis counts against baseline on a sample large enough to see a 50% failure rate
  — two episodes cannot.
- **Only `theses` is consumed downstream.** `explicit_recommendations`,
  `catalysts`, `sector_rankings`, `risk_warnings` and `meta_views` are write-only,
  so a claim routed elsewhere is functionally deleted.
- **Never key on `date` or on a `host` string.** Date is not unique (2026-05-12
  holds two records of one Sohn event) and All-In host strings are byte-identical
  across episodes; a `replace(count=1)` on either shuffles data between entries.
  Key on `label` or the entry's dict key.
- **`targets.py` has FIVE target lists plus `CNBC_TARGET` plus
  `SUPPLEMENTARY_METADATA`.** Reading only `YOUTUBE_VIDEOS` + `RSS_TARGETS` gives
  15 appearances an empty participants field.


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
