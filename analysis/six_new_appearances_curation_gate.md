# Curation Gate — 6 New Appearances (2026-07-22)

Pipeline ran through extract → aggregate → audit → reaudit. Timeline: **507 → 562 theses**
(+55 across the 6 new appearances). Below is what needs an operator decision before returns (steps 7–8).

## The 6 appearances (thesis counts, attribution)
| Date | Appearance | Theses | Attribution | Signal quality |
|------|-----------|--------|-------------|----------------|
| 2021-08-09 | CNBC Sharpe Angle (SPACs) | 6 | Baker (interviewee) ✓ | SPAC-era macro; 3 cluster to "SPAC structural analysis" |
| 2021-12-03 | Sohn AU 2021 Coinbase | 3 | Baker ✓ (secondary-coverage transcript) | COIN pick — **no basket exists** |
| 2023-04-21 | All-In E125 (Starship w/ Gracias) | 10 | Baker + **Antonio Gracias** (Starship T1–T3 likely Gracias) | mixed; 3 cluster to SpaceX |
| 2025-07-17 | All-In tariffs / AGI prize | 15 | Baker (featured) ✓ | high-signal AI, but most UNCLUSTERED |
| 2026-06-08 | Heller House (Baker interviews SpaceX CFO) | 11 | **~90% CFO Bret Johnsen, not Baker** ⚠️ | 9 cluster to tradeable baskets |
| 2026-07-20 | CNBC SpaceX drawdown | 10 | Baker (interviewee) ✓ | high-signal AI-infra |

## DECISION 1 — Heller House (SD-6NEW-1): CFO attribution
Video is literally "Gavin Baker interviews SpaceX CFO Bret Johnsen." 9 of 11 extracted theses are the
**CFO describing SpaceX operations/financials** (Starlink customer math, orbital-compute GW targets,
$3.75B AI-hosting run-rate, Terafab JV), which the extractor attributed to Baker. This mirrors the
2026-07-08 removal of an earlier Heller House file as a red herring. They cluster into **tradeable**
baskets and would emit signal events:
- T1/T2/T3/T7/T10/T11 → SpaceX ecosystem + Orbital (RKLB/LUNR/ASTS/RDW/SPCE)
- T3 → DRAM/HBM (MU) + Optical (CIEN/COHR/LITE); T5 → Power (VST/CEG); T8 → Intel (INTC); T9 → Google TPU (GOOGL)
Only **T9 (TSMC concentration bottleneck)** and maybe **T10 (terrestrial vs orbital cost curve)** reflect
documented Baker views.
**Recommendation:** remove all 11 from scoring via `cluster_override` null removals (durable, doesn't
delete the extraction).

## DECISION 2 — Sohn Coinbase (COIN): no basket exists
The 3 Coinbase theses are unclustered; there is no crypto/Coinbase theme (only Stablecoin→V/MA SHORT).
This is a clear high-conviction single-stock Baker pick.
**Recommendation:** add a new theme `Crypto / Coinbase (COIN)` LONG `[COIN]` to theme_baskets_v3.json
(keys: coinbase, web3, programmable crypto, crypto exchange) + add `COIN` to UNIVERSE.

## DECISION 3 — Strong AI theses that did NOT cluster
Genuine high-conviction Baker AI views that the regex keys missed (stay as "noise" unless keys extended):
- 2025-07-17 T5 (Grok/Hopper leapfrog), T6 (Blackwell step-up), T7 (lowest-cost token producer wins),
  T9 (software productivity), T14 (electricity is the binding constraint)
- 2026-07-20 T3 (structurally short compute)
T7/T14/T3 arguably belong to "Inference economics / token factories" and "Power / watts" themes.
**Recommendation (conservative):** leave unclustered — consistent with how existing macro/meta theses
are handled; extending keys retrofits scoring onto old theses too and risks scope creep.

## Applied-by-default (unless you object) — ticker hygiene
- Private names in tickers_direct (Anthropic, OpenAI, xAI, SpaceX) resolve NO_DATA automatically — harmless; leave.
- Audit already removed the wrong SPCE tag on drawdown T1 ("SpaceX" ≠ Virgin Galactic). ✓
- FOX / FDX / UPS (All-In E125: Fox defamation, Starship-vs-air-cargo) — tangential, not Baker trades → NO_BASKET.
- TSM / SMCI not in UNIVERSE — only matters if a basket uses them (TSM only relevant if Heller T9 kept).
- FLAG: All-In E125 Starship theses (T1–T3) likely trace to co-guest Gracias, not Baker (same class as Heller House).
- FLAG: All-In E125 T2 (Starlink satellites) mis-clustered into "Optical networking / interconnect".
