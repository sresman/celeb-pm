# Signal Events Changelog — v7 → v8 (2026-08-10)

Deliverable: `analysis/step4_signal_events_v8_with_returns_extended.{csv,xlsx}` (v7 preserved for diff).
Driver: 2 new Baker appearances added to the corpus (timeline 562 → **589 theses**; 47 transcripts).
Source: fomo-fund-monitor YouTube triage; operator-confirmed as the only 2 genuine new appearances of 25 candidates.

## Headline
- **Rows: 230 → 238 (+8 new events, 0 removed).**
- **0 basket changes and 0 return changes on pre-existing events** (230 shared (date,theme) keys, 0 differing).
- 4 pre-existing events **renumbered** (mention_number only — no basket/return impact; caused by inserting the 2026-04-16 Aria mentions between existing ones).
- Both appearances are **solo Baker** — full attribution, no co-guest/interviewer contamination.
- Price cache extended via `--force-refetch` to 2026-08-07 (last trading day).
- Slice summary essentially unchanged: signal (meets criteria) n=45, ret_1y **240.5%**, winrate 100%;
  control n=134 (was 126), ret_1y 44.3%. New events are recent/unclustered → land in control or
  INSUFFICIENT_DATA and don't move the signal slice.

## 1. New events (8)
2 on the Aria date (2026-04-16), 6 on the ILTB date (2026-08-04).

| Date | Theme | Basket | Source | meets_criteria | 1q |
|------|-------|--------|--------|:--:|--:|
| 2026-04-16 | AI networking (Ethernet/InfiniBand) | ANET | BAKER_NAMED | – | +4.7 |
| 2026-04-16 | Inference economics / token factories | CRWV | BAKER_NAMED | ✓ | −38.8 |
| 2026-08-04 | DRAM / HBM memory bottleneck | MU | OBVIOUS_UNIVERSE | – | n/a¹ |
| 2026-08-04 | Disaggregation prefill/decode | NVDA | OBVIOUS_UNIVERSE | – | n/a¹ |
| 2026-08-04 | Orbital / space-based compute | SPCX² | OBVIOUS_UNIVERSE | – | n/a¹ |
| 2026-08-04 | SpaceX ecosystem / Starship economics | SPCX² | OBVIOUS_UNIVERSE | – | n/a¹ |
| 2026-08-04 | AI capex ROI positive | — | NO_BASKET | – | n/a¹ |
| 2026-08-04 | Broad AI bullish / early innings | — | NO_BASKET | – | n/a¹ |

¹ INSUFFICIENT_DATA — event is 2026-08-04, only ~6 calendar days before the run; no 1m+ horizon yet.
  The 2026-04-16 Aria events have 1m/1q but not 1y (2027-04-16 is future), so they don't affect the 1y slice.
² SPCX = SpaceX proxy ticker; resolves NO_DATA (private) → no return, harmless.

Note on ILTB event count: the 20 ILTB theses collapse to 6 mention-grain rows (one row per
theme×date). Legit clusters that survived: DRAM/HBM (T10,T13), Disaggregation (T13),
Orbital (T11,T12), SpaceX (T11), plus AI-capex-ROI (T13) and Broad-AI-bullish (T16) which are
NO_BASKET "never-a-trade" themes by standing override.

## 2. Removed from scoring — 4 substring false-positive clusters
Added as `cluster_overrides` (null destination) in `manual_overrides.json`. Each clustered ONLY
because a theme's regex key matched a substring inside an unrelated word:

| Thesis | False theme | Key | Triggering word |
|--------|-------------|-----|-----------------|
| ARIA 2026-04-16 T1 | Google TPU competitive position | `tpu` | "ou**tpu**t" |
| ARIA 2026-04-16 T5 | DRAM / HBM memory bottleneck | `dram` | "**dram**atically" |
| ILTB 2026-08-04 T14 | Optical networking / interconnect | `cien` | "sample-effi**cien**t" |
| ILTB 2026-08-04 T3 | Scaling laws intact | `compute.*scale` | "compute … hyper**scale**r" (wrong theme) |

## 3. Renumbered mentions (4, mention_number only)
Inserting the 2026-04-16 Aria mentions shifted later mentions of two themes:
- Inference economics / token factories: 2026-05-20 (3→4), 2026-06-15 (4→5), 2026-07-20 (5→6)
- AI networking (Ethernet/InfiniBand): 2026-06-07 (3→4)

## 4. Operator decisions carried in (see two_new_appearances_curation_gate.md)
- Decision 1: null the 4 false positives ✓ applied.
- Decision 2: leave high-conviction unclustered theses (T4 $700B credit gap; T7/T9 NVDA) as noise — no overrides.
- Decision 3: no new themes (regulatory tail-risk T19, token-for-labor T17 left as noise).
- Ticker hygiene: SPACEX/HYNIX(000660.KS)/SAMSUNG → NO_DATA; all other new tickers already in UNIVERSE.
