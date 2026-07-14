# Override + New-Theme Re-run — Diff Summary

**Date:** 2026-07-09
**What ran:** clustering → **cluster overrides** → event generation → basket resolution →
**event overrides** → returns → repeat-mention build. Audit was **not** re-run (no thesis content
changed; `thesis_timeline_v2_flat.json` is current at 507). Prices: 25 new tickers fetched + cached.
**Deliverable:** `analysis/step4_signal_events_v6_with_returns_extended.xlsx` (`signal_events` +
`slice_summary`), schema + `is_derisk_signal` / `is_thesis_close` / `exclude_from_long_stats`.

---

## 1. Durable override layer (survives rebuilds)

`analysis/manual_overrides.json` — applied after clustering + basket resolution, immediately before
returns, by BOTH `theme_returns_v2.py` and `build_repeat_mention_events.py` (shared code). Two kinds:
**cluster_overrides** (re-theme a thesis) and **event_overrides** (set basket/source/direction +
flags). Match keys: theme / date / mention_number / summary_contains. Overrides win over clustering.

**Rows changed by overrides: 41** (+ 1 thesis re-themed):

| n | Theme | Override |
|--:|---|---|
| 9 | China AI distillation / export controls | → ASML,LRCX,AMAT,KLAC LONG (was NVDA/MIXED) |
| 6 | SaaS existential disruption | → CRM,NOW,TEAM,SNOW,**HUBS** SHORT |
| 5 | Metaverse / gaming as platform | → ATVI,EA,TTWO LONG (**RBLX removed**) |
| 4 | Neoclouds as durable model | → CRWV,NBIS BAKER_NAMED |
| 3 | Reasoning / inference-time compute | flywheel→GOOGL; 2025-05-28→MU (compute-demand keeps NVDA,AMD) |
| 2 | DISH / 5G bearish | → T,VZ,TMUS SHORT |
| 2 | Microsoft AI position | → NO_BASKET |
| 2 | Custom ASIC failure thesis | → PAIR_TRADE (long NVDA+GOOGL / short AVGO), no returns |
| 2 | Inference economics / token factories | source→BAKER_NAMED (CRWV stays) |
| 2 | Bottleneck trade ending | → NO_BASKET + **is_derisk_signal=TRUE** |
| 1 | Intel recovery / foundry failure | mention 1 (2019-11-26)→NO_BASKET (m2/m3 keep INTC LONG) |
| 1 | Power / watts as binding constraint | 2020-05-07 edge thesis→NO_BASKET |
| 1 | SpaceX ecosystem / Starship economics | 2021-11-01→VSAT,SATS,LUMN SHORT |
| 1 | Google TPU competitive position | m4 (2026-05-20)→reversal+close, excluded from long stats |
| — | (cluster) Google TPU → China | GLM 5.2 thesis (2026-06-27) re-themed |

---

## 2. New themes added (7) — capture test (507-thesis corpus)

Each captures **exactly** its intended theses, **zero collisions** (Unity∩gaming = 0; gaming captures
no pre-2023 metaverse; cooling doesn't touch the power-constraint theme):

| Theme | Basket | Captured (date) |
|---|---|---|
| Unity / world models | U | 2026-05-28 |
| AI world models for gaming | SONY, NTDOY | 2026-07-08 |
| Datacenter physical assets | EQIX, DLR | 2026-06-12, 06-15, 06-27 |
| Power / cooling equipment suppliers | VRT, ETN, PWR | 2026-05-20 |
| CDN / token delivery path | NET, FSLY, AKAM | 2026-06-15 |
| Uranium enrichment / national security | LEU | 2026-02-24 |
| Stranded / behind-the-meter power | CRSO* | 2026-02-24 |

*CRSO (Crusoe, private) 404s on EODHD → NO_DATA (handled gracefully; `fetch_prices` no longer crashes
on invalid tickers). UNIVERSE expanded by 25 names for the override + new-theme baskets.

---

## 3. THESIS_REVERSAL guard — before / after

Old detector (bearish keywords: losing/lost/risk/mistake/bubble/worst/flinched/break-down) fired **17**
false-heavy reversals. New guard requires an explicit change from Baker's own prior stance
(no-longer / used-to / was-wrong / changed-mind / walked-back / lost-its-leadership, matched on the
**summary** only). Now fires **2**:

- ✅ **Google TPU 2026-05-20** — "Google has **lost its** per-cost-token **leadership**…" (the genuine
  reversal; the operator's validation case — still fires).
- ⚠️ **Intel 2020-07-27** — "…having **lost its** 50-year manufacturing **lead**." A legitimate
  structural-loss observation (not in the operator's exclusion set). It does **not** change Intel's
  basket (INTC LONG) or exclude it — cosmetic flag only. Flagged for awareness.

Eliminated false positives incl. the operator's named ones: **DRAM 2025-12-09, TSMC 2025-12-09, and
all SpaceX rows** no longer fire. (TPU m4 is also force-tagged via override, so it's covered either way.)

---

## 4. Updated 3-way repeat-mention slice (did the headline move?)

Repeat mentions (mention ≥ 2), excluding thesis-close/reversal rows. **n: all 184 / signal 44 /
control 140.** Return% / excess-vs-SMH% / win% — **all / signal / control**:

| Horizon | ret (all/sig/ctrl) | exSMH (all/sig/ctrl) | win (all/sig/ctrl) |
|---|---|---|---|
| 1m | 2.1 / 4.0 / 1.5 | −0.7 / −0.2 / −0.8 | 54 / 53 / 54 |
| 1q | 12.9 / 12.2 / 13.1 | 7.2 / 2.9 / 8.8 | 59 / 63 / 58 |
| 6m | 34.3 / 37.3 / 33.4 | 11.6 / 17.9 / 9.6 | 72 / 85 / 68 |
| 9m | 37.4 / **72.2** / 21.7 | 22.1 / **42.8** / 12.7 | 69 / 83 / 63 |
| 1y | 85.0 / **152.9** / 54.4 | 49.5 / **102.0** / 25.9 | 79 / 83 / 78 |
| 18m | 106.4 / 53.8 / **122.3** | 49.4 / 5.6 / **62.7** | 84 / 70 / 88 |
| 2y | 57.1 / **103.2** / 30.2 | 8.7 / **42.9** / −11.3 | 58 / 43 / 67 |

**Movement vs the pre-override rescore** (signal / control 1y ret was 107.8 / 50.6): the corrected
baskets **sharpened the signal group markedly** — 1y signal ret 108 → **153**, 1y signal excess-SMH
57 → **102**; control barely moved (51 → 54). So at **9m / 1y / 2y** the criteria now separate much
more strongly from control; **1m/1q/6m** still ~tied and **18m** still inverts (control wins). The
"criteria add signal at medium-to-long horizons" read is now stronger, not weaker. Same caveats:
small n (44 signal), single manager, momentum era, theme-proxy baskets, calendar-edge dropout on the
longest horizons.

---

## 5. Verification gates — all pass

| Gate | Result |
|---|---|
| China export-control rows → ASML/LRCX/AMAT/KLAC LONG, all 9 mentions | ✅ |
| SpaceX 2021-11-01 → VSAT/SATS/LUMN SHORT; 1y positive (short worked) | ✅ +29.8% |
| Sohn Montreal 2025-05-28 DRAM + reasoning rows → MU, ~+912% 1y | ✅ both 911.98% |
| Metaverse → ATVI/EA/TTWO; no RBLX anywhere | ✅ |
| Unity theme exists with the 2026-05-28 thesis (ticker U) | ✅ |
| TPU m4 (2026-05-20) reversal + close + excluded; m5 (GLM) under China | ✅ |
| No Heller House anywhere | ✅ |
| is_derisk_signal TRUE on Bottleneck 2026-06-11 & 2026-06-15 | ✅ |
| mypy --strict clean on touched scripts | ✅ |

---

## 6. Files

- **New:** `analysis/manual_overrides.json` (durable override layer)
- **Changed:** `analysis/theme_baskets_v3.json` (+7 themes → 59), `tools/transcripts/theme_returns_v2.py`
  (override engine, reversal guard, UNIVERSE +25, graceful fetch), `tools/transcripts/build_repeat_mention_events.py`
  (overrides, reversal, PAIR_TRADE, new flag columns)
- **Regenerated:** `analysis/step4_signal_events_v5.csv`,
  **`analysis/step4_signal_events_v6_with_returns_extended.csv` + `.xlsx`**
- `analysis/step4_signal_events_v6_manual_legacy.csv` retained (pre-rebuild hand-curated set).

The override layer is durable: any future `aggregate → (audit) → theme_returns_v2 →
build_repeat_mention_events` rebuild re-applies `manual_overrides.json` automatically.
