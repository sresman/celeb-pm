# Clustering-fix diff — misclustered-thesis removals + NO_BASKET flags

**Date:** 2026-07-16
**Change:** 42 `cluster_override` removals (`to_theme: null`) + 1 existing override updated + 8 `NO_BASKET` event overrides → re-ran `theme_returns_v2` → `build_repeat_mention_events`.
**Output:** `analysis/step4_signal_events_v6_with_returns_extended.xlsx` (signal_events + slice_summary).

---

## 0. Two data issues found up front (and how they were handled)

**(a) The task's `Tn` labels didn't match the timeline's `thesis_id`.** ~13 of 29 listed
removals pointed at the wrong thesis (e.g. `2026-05-22 T5` "selling GPUs to China" is actually
**T15**; `T5` is Cursor. `2026-05-22 T7` "Strait of Hormuz" is actually **T16**; `T7` is the real
power/cooling/optical thesis). **Every removal was re-resolved by its description against the theses
actually clustered in each `from_theme`** — not by the literal `Tn`. All 9 DRAM ids happened to be
correct; Optical/Power/China/NVDA-moat had shifts.

**(b) The 29 listed removals under-covered the shared dates.** Several removal dates carried
*additional* misclustered theses the task didn't list (e.g. DRAM `2021-11-30` also had SpaceX/Starlink;
`2023-06-19` also had GPU-utilization; `2026-06-11` also had SpaceX-terrestrial + Cursor). Applying only
the 29 left those dates alive, missing the target counts. **Per operator authorization, the removal set
was extended by 13** to eliminate the clearly-misclustered stragglers on DRAM/Optical/Power (full list
in §3).

---

## 1. Pipeline support added (Step 1)

`cluster_override` now supports **removal**: a `to_theme` (or `new_theme`) of `null` /
`"unclustered"` drops the matched thesis from `from_theme` without re-adding it anywhere — it
generates no event and does not count toward any theme's mention numbering (the thesis stays in the
timeline). `_match` gained **`thesis_id`** support (per-date ordinal) alongside theme/date. Removal is
**scoped to `from_theme`**, so a thesis correctly clustered elsewhere survives there (essential for
multi-clustered theses like `2026-05-22 T15`, removed from NVDA-moat but kept in China as NO_BASKET).
`mypy --strict` clean.

---

## 2. Overrides: before → after

| | before | after |
|---|---|---|
| cluster_overrides | 1 | **43** (+42 removals; the existing GLM TPU→China entry updated to TPU→**null**) |
| event_overrides | 105 | **113** (+8 NO_BASKET) |

---

## 3. Mention counts: before → after

| theme | before | after | target | first mention (after) |
|---|---|---|---|---|
| DRAM / HBM memory bottleneck | 16 | **9** | 7 | 2024-08-07 ✅ |
| Optical networking / interconnect | 12 | **3** | 3 ✅ | 2024-01-30 ✅ |
| Power / watts as binding constraint | 12 | **5** | 5 ✅ | 2020-05-07 (m1 NO_BASKET); real trade 2024-02-23 ✅ |
| China AI distillation / export controls | 9 | **6** | 6 ✅ | 2024-12-07 |
| Nvidia GPU moat / CUDA ecosystem | 8 | **7** | 7 ✅ | 2020-07-27 |

**Removals (42), by theme:** DRAM 13 (9 listed + 4 extra), Optical 17 (9 + 8 extra), Power 8 (7 + 1
extra), China 3, NVDA-moat 1. The **13 extra** (operator-authorized) were the un-listed misclusters on
shared dates: DRAM `2021-11-30 T6`, `2023-06-19 T9`, `2026-06-11 T2`+`T4`; Optical `2023-06-19
T4/T8/T9`, `2024-08-27 T3`, `2026-02-24 T2/T8`, `2026-05-22 T7/T19`; Power `2026-06-15 T8`. (Full list
with summaries is in each override's `note` in `manual_overrides.json`.)

### ⚠️ DRAM landed at 9, not 7

After removing every clear mis-cluster, **9 genuinely on-theme HBM/DRAM mentions remain** — I did not
cut real signal to force 7:

`2024-08-07` (HBM primary axis) · `2025-01-04` (HBM best asset) · `2025-05-28` (SK Hynix/Micron HBM) ·
`2025-12-09` (true DRAM capacity cycle) · `2026-05-12` (memory cycle call) · `2026-05-20` (DRAM
undervalued) · `2026-05-22` (memory makers 3-5x PE) · `2026-05-28` (Micron/SK Hynix HBM) · `2026-06-27`
(DRAM #1 bottleneck).

The "first = Aug 2024" anchor is correct. The count target of 7 almost certainly predates the recent
gap-fill (the corpus grew 26→39 files; four of these DRAM mentions are May-2026 appearances). **If you
want exactly 7, tell me which 2 to drop** — I won't delete genuine DRAM theses on my own.

---

## 4. NO_BASKET event overrides (Steps 2–3, all applied ✅)

Correctly-themed, not-a-trade mentions set to NO_BASKET (mention retained, removed from scored returns):

| theme | date | note |
|---|---|---|
| China AI distillation | 2025-03-29 | enforcement-difficulty commentary |
| China AI distillation | 2026-05-22 | selling depreciated GPUs (also removed from NVDA-moat) |
| Nvidia GPU moat | 2024-08-07 | "three architectures" structural observation |
| xAI competitive position | 2025-10-22 | flag decision (**reverts the earlier v4 →GOOGL**) |
| Reasoning / inference-time compute | 2024-12-07 | flag decision (was continuation NVDA/AMD) |
| Reasoning / inference-time compute | 2025-12-09 | flag decision (**supersedes the "flywheel" catch-all →GOOGL**) |
| Inference economics / token factories | 2026-05-20 | flag decision (supersedes catch-all →CRWV) |
| Neoclouds as durable model | 2025-03-29 | flag decision (supersedes catch-all →CRWV/NBIS) |

Matched by `(theme, date)` and **prepended** (first-match wins), so each supersedes any theme-level
catch-all or prior per-mention override for that event and is robust to the mention renumbering.

---

## 5. Total scored events & 3-way slice table

**Scored trade events: 135 → 100** (target ~97; the +3 over 97 is the DRAM 9-vs-7).

| group | n (before→after) | ret_1y | excess_1y | winrate_1y |
|---|---|---|---|---|
| 1_all_repeat_mentions | 184 → **157** | 110.85 → **115.04** | 72.45 → **77.67** | 81.8 → **78.8** |
| 2_signal_meets_criteria | 44 → **40** | 199.31 → **234.92** | 144.87 → **174.03** | 92.9 → **100.0** |
| 3_control_no_criteria | 140 → **117** | 69.56 → **62.92** | 38.65 → **35.77** | 76.7 → **69.6** |

The signal vs. control separation **widened again**: the signal slice now shows a **100% 1-year win
rate** and +174% mean 1y excess, vs. control +35.8% (69.6% win rate). Removing the keyword-collision
noise (which had diluted both slices, disproportionately the signal slice) sharpened the headline.

---

## 6. Conflicts resolved

- **GLM 5.2 (`2026-06-27`):** the existing TPU→China cluster_override had its destination changed to
  **null** (removes from TPU), plus a new China→null removal — so GLM is out of *both* themes, per the task.
- **`2026-05-22` selling-GPUs (T15):** removed from NVDA-moat (cluster) but **kept in China as
  NO_BASKET** — the `from_theme`-scoped removal makes this multi-cluster case work correctly.
- **xAI `2025-10-22`:** NO_BASKET now supersedes the earlier v4 CHANGE→GOOGL (prepended).
- **Reasoning `2025-12-09`:** NO_BASKET supersedes the "flywheel" summary catch-all (→GOOGL).
- **No pre-existing override deleted.** Stale mention-number-keyed overrides on the renumbered themes
  (DRAM/Optical/Power) simply no-op; those themes resolve to their correct theme-default baskets (MU /
  CIEN·COHR·LITE / VST·CEG), so scored baskets are unaffected.
