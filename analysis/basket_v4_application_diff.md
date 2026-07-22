# Basket v4 application — diff summary

**Date:** 2026-07-16
**Input:** `analysis/basket_reresolution_v4.csv` (136 reviewed events, `final_action` column)
**Applied to:** `analysis/manual_overrides.json` → re-ran `theme_returns_v2` → `build_repeat_mention_events`
**Output:** `analysis/step4_signal_events_v6_with_returns_extended.xlsx` (signal_events + slice_summary)

> Includes the follow-up consolidation of the two "never-a-trade" macro themes
> (`AI capex ROI positive`, `Broad AI bullish / early innings`) to theme-level NO_BASKET.

---

## 1. Overrides: before → after

| | before | after | net |
|---|---|---|---|
| event_overrides | 15 | **105** | +90 |
| cluster_overrides | 1 | 1 | 0 (untouched) |
| total entries | 16 | **106** | +90 |

Built in two passes:
1. **+102** new event overrides from the 102 actionable v4 rows (all except KEEP CURRENT=32 / KEEP NO_BASKET=2):

   | action | count | override effect |
   |---|---|---|
   | NO_BASKET | 47 | `resolved_basket=[]`, `basket_source=NO_BASKET`, `basket_direction=""` |
   | KEEP (continuation) | 22 | locks current `old_basket/old_source/old_direction`; tagged `"reason":"trade_continuation"` |
   | CHANGE | 18 | sets `final_basket/final_source/final_direction` |
   | STEVE | 15 | Steve's final call (incl. 8 → NO_BASKET, 1 → PAIR_TRADE) |

2. **−14 / +2** consolidation: the 14 per-mention entries for the two macro themes were replaced by **2 theme-level NO_BASKET catch-alls** (mirroring the existing `Microsoft AI position` catch-all), so every mention — reviewed or not, now or future — resolves to NO_BASKET.

All per-event entries match on **theme + date (ISO) + mention_number** and were **prepended** (first-match-wins → a v4 decision beats any theme-level catch-all for its specific event). No pre-existing entry (the original 15 event + 1 cluster) was deleted or modified. (The "41" in prior notes = the 41 event *rows* the old overrides touched, not entry count.)

UNIVERSE extended by 6 (`WMT, HD, LOW, COST, KR` retail + `000660.KS` SK Hynix) so the CHANGE baskets price. `000660.KS` 404s on EODHD → graceful NO_DATA (DRAM baskets still score via MU). `LEU` was already present.

---

## 2. Scored trade events: before → after

**Scored = `basket_source ∉ {NO_BASKET, PAIR_TRADE}` and `basket_direction ≠ PAIR_TRADE`.**

| | before | after (v4) | after (+ 2-theme consolidation) |
|---|---|---|---|
| scored trade events | 194 | 138 | **135** |

Net **−59** from the 194 baseline (target was "roughly 57 fewer"). The extra −3 vs. the first pass is the two macro themes going fully NO_BASKET: `AI capex ROI` m3 (2025-01-28, was AMZN/MSFT/GOOGL/META) + m4 (2025-03-29, **reverted the v4 NVDA CHANGE** — see §4) and `Broad AI bullish` m6 (2025-10-22, was SMH).

`basket_source` distribution:

| source | before | after |
|---|---|---|
| NO_BASKET | 45 | 103 |
| BAKER_NAMED | 84 | 89 |
| OBVIOUS_UNIVERSE | 86 | 41 |
| RETAIL_PROXY | 16 | 4 |
| CONSTRUCTED | 8 | 3 |
| PAIR_TRADE | 2 | 3 |

---

## 3. Three-way repeat-mention slice table: before → after

Row counts (n) are unchanged — the slices partition by repeat-mention/criteria, not by basket; turning a trade into NO_BASKET drops it from the return averages (its `ret` becomes the string `NO_BASKET`) but not from n. Averages moved **up** because the removed events were the lower-return macro/index longs, leaving a higher-quality scored set.

| group | n | ret_1y before → after | excess_1y before → after | winrate_1y before → after |
|---|---|---|---|---|
| 1_all_repeat_mentions | 184 | 84.97 → **110.85** | 49.51 → **72.45** | 79.3 → **81.8** |
| 2_signal_meets_criteria | 44 | 152.90 → **199.31** | 102.04 → **144.87** | 83.3 → **92.9** |
| 3_control_no_criteria | 140 | 54.41 → **69.56** | 25.87 → **38.65** | 77.5 → **76.7** |

Headline is unchanged and **strengthened**: the signal slice (meets existing criteria) still cleanly beats control on every metric, and the 1y excess gap widened materially: signal−control **76.2pp → 106.2pp**.

---

## 4. Conflicts with prior overrides & the m4 revert

- **Exact theme+date conflicts with the original 15 overrides: none.** No v4 row shares the exact `theme + date` of any existing override. (Intel gained a *new* 2020-07-27 SHORT alongside the untouched 2019-11-26 NO_BASKET; the date-specific SpaceX/Power/Reasoning/TPU overrides sit on dates no v4 row touches.)
- **One catch-all functional overlap, no actual collision:** the existing `Reasoning / inference-time compute` "flywheel" catch-all (→GOOGL, summary-matched). Neither v4 Reasoning row contains "flywheel", and the new entries are date+mention-specific, so neither shadows the other.
- **Intra-v4 supersession (m4 → NVDA reverted):** the v4 CHANGE that set `AI capex ROI positive` m4 (2025-03-29) → NVDA was **superseded by the operator's later theme-level ruling** that the whole theme is never-a-trade macro commentary "regardless of which mention number." The theme-level NO_BASKET catch-all now zeros m4 too. This is the latest review winning, consistent with the task's own "latest review wins" rule — flagged here because it reverts an explicit earlier v4 decision.

---

## 5. Verification checklist

| check | result |
|---|---|
| Scored events ≈ 57 fewer | ✅ 194 → 135 (−59; −56 from v4 + −3 from the 2-theme consolidation) |
| AAPL long, edge AI 2024-08-27 | ✅ `AAPL / BAKER_NAMED / LONG` |
| INTC short, Intel 2020-07-27 | ✅ `INTC / BAKER_NAMED / SHORT` |
| LEU long, uranium 2026-02-24 | ✅ `LEU / OBVIOUS_UNIVERSE / LONG` |
| EV SPACs PAIR_TRADE 2021-11-30 | ✅ `TSLA, LCID(short), RIVN(short) / PAIR_TRADE` (returns skipped) |
| Continuation baskets retained | ✅ DRAM=MU, power=VST/CEG, optical=CIEN/COHR/LITE |
| Existing overrides hold | ✅ China=ASML/LRCX/AMAT/KLAC, SpaceX short=VSAT/SATS/LUMN, Custom ASIC=PAIR_TRADE |
| Unity still scored | ✅ `Unity / world models` 2026-05-28, basket=`U` |
| NO_BASKET themes → zero scored | ✅ AI bubble, scaling laws, **AI capex ROI (all 8), Broad AI bullish (all 8)** all 0 scored; SpaceX/Orbital/xAI retain only their explicit CHANGE proxies + KEEP CURRENT rows + the existing SpaceX short |

### Residual scored events in the space/xAI macro themes (all by explicit instruction — not gaps)

| theme | scored | provenance |
|---|---|---|
| xAI competitive position | 1 | `GOOGL` ← v4 CHANGE (m8 2025-10-22) |
| SpaceX ecosystem / Starship econ | 4 | `ASML,LRCX,KLAC,AMAT` ← CHANGE (m6); `VSAT,SATS,LUMN` ← existing override (m1); `RKLB,LUNR,ASTS,RDW` ×2 ← KEEP CURRENT |
| Orbital / space-based compute | 2 | `RKLB,LUNR,ASTS,RDW` ×2 ← KEEP CURRENT |

---

## 6. Pipeline fix (pre-existing bug surfaced)

`theme_returns_v2.OUTPUT_FIELDS` was missing `override_note` (and the 4 override flag columns
`is_derisk_signal/is_thesis_reversal/is_thesis_close/exclude_from_long_stats`), which
`apply_event_override` sets on any overridden row. Its `csv.DictWriter` therefore raised
`ValueError: dict contains fields not in fieldnames: 'override_note'` whenever an event override
applied — a latent crash masked in prior runs by piping the script through `tail` (which swallowed
its non-zero exit; the deliverable xlsx comes from `build_repeat_mention_events`, which was
unaffected). Added the five fields to `OUTPUT_FIELDS`; both scripts now exit 0 and `mypy --strict`
is clean. (The deliverable was never affected — this only fixes the legacy `step4_signal_events_v3.csv` writer.)
