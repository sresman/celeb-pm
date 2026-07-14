# Re-score Diff Summary — corrected/expanded corpus

**Date:** 2026-07-09
**Rebuilt end-to-end** from the corrected 39-file / 507-thesis corpus:
`aggregate_theses` → `audit_theses` → `theme_returns_v2` → `build_repeat_mention_events`.
Audit cost ~$2.29 (258 re-audited, 249 reused). Standalone of `src/celebpm`.

---

## 1. Verification (all pass)

| Check | Result |
|---|---|
| Heller House theses in any output | **Absent** (timeline_v2_flat, v5.csv, v6_extended.csv all clean) |
| Aleph theses re-dated | **2025-10-22** everywhere (was 2024-02-14) |
| The two "All-In 2024-06-15" files | **0 rows dated 2024-06-15**; now 2026-06-27 (E278) + 2026-06-07 (Liquidity) |
| Unity (ticker U) in thesis timeline | **Present** — 2026-05-28, `tickers_direct` (Limitless) ✓ |
| Micron / HBM mention count > 11 | **"DRAM / HBM memory bottleneck": 11 → 16** ✓ |

⚠️ **Unity nuance (checkpoint met, but flag):** U appears in the *thesis timeline* (✓ the gap
is filled), but **not in the signal-events sheet**. The Unity "world-model builder" thesis is
**unclustered** — its summary matches none of the 52 fixed theme patterns in
`theme_baskets_v3.json`, and no basket contains ticker U. To bring Unity into signal scoring, add
a **"Unity / world models"** theme (keys e.g. `world model|game engine|3d simulation|unity`,
basket `["U"]`) to `theme_baskets_v3.json` and re-run. Recommended follow-up.

---

## 2. Corpus diff — old (27 files / 319 theses) → new (39 files / 507 theses)

**+12 files, +188 theses.** Clustering (same `theme_baskets_v3.json`, 52 themes) applied to both
the old and new timelines; counts are per-theme **unique-date mentions**.

### Themes that gained mentions (top by gain)

| Δ | Theme | old → new |
|--:|---|---|
| +6 | Power / watts as binding constraint | 6 → 12 |
| +5 | DRAM / HBM memory bottleneck | 11 → 16 |
| +5 | Edge AI as bear case for cloud | 2 → 7 |
| +5 | xAI competitive position | 7 → 12 |
| +4 | SpaceX ecosystem / Starship economics | 9 → 13 |
| +4 | Optical networking / interconnect | 8 → 12 |
| +4 | Humanoid robotics / Tesla Optimus | 4 → 8 |
| +4 | AI capex ROI positive | 4 → 8 |
| +3 | Nvidia GPU moat / CUDA ecosystem | 5 → 8 |
| +3 | Scaling laws intact | 5 → 8 |
| +3 | China AI distillation / export controls | 6 → 9 |
| +3 | Neoclouds as durable model | 1 → 4 |
| +3 | Metaverse / gaming as platform | 2 → 5 |
| +2 | SPAC structural analysis · AI bubble not happening | — |

The new All-In (E221/E274/E278/Liquidity), ILTB (EP.149/167/260/385), TWiST, iConnections, and
Limitless files drive the gains — concentrated in AI-infra physical constraints (power, memory,
optical), xAI, SpaceX, and robotics.

### New themes: **0**
No genuinely-new theme appears, because clustering uses the **fixed hand-maintained 52-theme set**
in `theme_baskets_v3.json`; new theses can only map to existing themes. Genuinely-new angles in the
expanded corpus (most notably **Unity / world-models**, and arguably a distinct **orbital-compute
economics** cut) require adding theme definitions to that file. Flagged for review.

---

## 3. Manual v6 edits NOT reapplied (for your review)

The prior `step4_signal_events_v6.csv` was hand-curated on top of the old v5 (preserved now as
`analysis/step4_signal_events_v6_manual_legacy.csv`). The from-scratch rebuild regenerates events
purely from the state machine, so these manual decisions are **not carried forward**. The exact
delta (old_v5 → old_v6):

**Manually REMOVED (11 THESIS_REVERSAL events)** — the rebuild REGENERATES these (16 reversals now
in v5), so they are back unless you re-remove them:
- Intel recovery/foundry @2020-07-27 · SpaceX ecosystem @2024-02-14 · AI-bubble-not-happening
  @2024-06-15 · SpaceX ecosystem @2024-06-15 · xAI @2024-12-07 · DRAM/HBM @2025-12-09 · TSMC
  capacity @2025-12-09 · Orbital compute @2026-05-12 · Google TPU @2026-05-20 · Orbital compute
  @2026-05-20 · SpaceX ecosystem @2026-06-11

**Manually ADDED (9 events)** — reclassifications of the above (reversal→HC), now dropped:
- HC_HIGH_PROFILE_VENUE: SpaceX @2024-02-14, Orbital @2026-05-12
- FIRST_MENTION_AND_HC: AI-bubble @2024-06-15, SpaceX @2024-06-15, xAI @2024-12-07, DRAM/HBM
  @2025-12-09, Google TPU @2026-05-20, Orbital @2026-05-20, SpaceX @2026-06-11

**Pattern:** your prior curation treated several keyword-triggered "reversals" as false positives
and reclassified them as high-conviction mentions. Those dates are pre-correction (old dates), so
if you want to re-apply the *logic*, the cleaner fix is to tighten the `THESIS_REVERSAL`
keyword/guard in `theme_returns_v2.generate_events` rather than per-row edits. Legacy file retained
for line-by-line comparison.

---

## 4. is_repeat_mention test — 3-way slice (the noise-vs-criteria question)

Output sheet: **`analysis/step4_signal_events_v6_with_returns_extended.xlsx`** (233 mention rows;
`signal_events` sheet + `slice_summary` sheet). Restricting to repeat mentions
(`is_repeat_mention = TRUE`, mention_number ≥ 2): **n = 184**; signal (meets ≥1 of the 4 existing
criteria) **= 42**; control (repeat but no criterion) **= 142**.

Average basket return / excess-vs-SMH / win-rate, by horizon — **all / signal / control**:

| Horizon | ret% (all/sig/ctrl) | excess-SMH% (all/sig/ctrl) | win% (all/sig/ctrl) |
|---|---|---|---|
| 1m | 0.9 / 3.4 / 0.0 | −2.2 / −1.2 / −2.5 | 48 / 55 / 45 |
| 1q | 11.3 / 10.8 / 11.5 | 5.7 / 1.6 / 7.2 | 58 / 63 / 56 |
| 6m | 32.2 / 31.4 / 32.4 | 8.9 / 12.1 / 8.0 | 72 / 85 / 68 |
| 9m | 31.8 / **56.0** / 21.0 | 16.5 / **26.6** / 11.9 | 69 / 83 / 63 |
| 1y | 68.4 / **107.8** / 50.6 | 32.9 / **57.0** / 22.1 | 81 / 83 / 80 |
| 18m | 107.1 / 55.2 / **122.8** | 50.1 / 7.0 / **63.2** | 79 / 70 / 82 |
| 2y | 60.0 / **102.6** / 35.2 | 11.6 / **42.3** / −6.4 | 53 / 43 / 58 |

**Read (yours to interpret):** the existing criteria **do** appear to add signal at the
**9m / 1y / 2y** horizons — the signal subset roughly doubles the control's return and excess (e.g.
1y excess +57.0 vs +22.1; 2y excess +42.3 vs −6.4). But at **1m / 1q / 6m** signal ≈ control, and
at **18m** control actually outperforms. So the criteria are **not** obviously noise, but the effect
is horizon-dependent and inverts at 18m. **Heavy caveats:** n is small (42 signal), it's a single
manager over a strong-momentum 2020-2026 window, baskets are theme-proxies (not his actual
positions), and long-horizon rows drop out near the calendar edge. Treat as directional, not
conclusive.

---

## 5. Outputs written

| File | What |
|---|---|
| `analysis/thesis_timeline.json`, `all_summaries.json` | rebuilt (507 theses / 39 files) |
| `analysis/thesis_timeline_v2.json`, `_flat.json` | re-audited (507 entries, corrected dates) |
| `analysis/thesis_audits/*.json` | 507 (orphans purged; 258 re-audited, 249 reused) |
| `analysis/step4_signal_events_v5.csv` | standard criteria-event grain (146 events), corrected dates |
| **`analysis/step4_signal_events_v6_with_returns_extended.csv` / `.xlsx`** | **repeat-mention sheet + 3-way slice** (deliverable) |
| `analysis/step4_signal_events_v6_manual_legacy.csv` | old hand-curated v6 (preserved for review) |

**Not run** (unchanged from prior): the 13F-side pipeline (`build_13f_analysis.py`,
`build_trigger_workbook.py`) — independent of the thesis-returns layer and not part of this re-score.
`trigger_analysis.xlsx` is therefore still on the old basis; regenerate separately if needed.
