# Signal Events Changelog — v6 → v7 (2026-07-22)

Deliverable: `analysis/step4_signal_events_v7_with_returns_extended.{csv,xlsx}` (v6 preserved for diff).
Driver: 6 new Baker appearances added to the corpus (timeline 507 → **562 theses**; 45 transcripts).

## Headline
- **Rows: 215 → 230 (+15 new events, 0 removed).**
- **0 basket changes and 0 return changes on pre-existing events** (after the override fix below).
- 21 pre-existing events **renumbered** (mention_number only — no basket/return impact).
- Heller House (2026-06-08): **0 events** — all 11 theses removed from scoring per operator (CFO attribution).
- Slice summary essentially unchanged: signal (meets criteria) n=45, ret_1y **240.5%**, winrate 100%;
  control n=126, ret_1y 44.3%. (New events are mostly recent/unclustered, so they land in the control or
  INSUFFICIENT_DATA buckets and don't move the signal slice.)

## 1. New events (15)
13 sit on the 6 new-appearance dates; 2 are OLD theses newly caught by the new theme/keys.

| Date | Theme | Basket | Source | meets_criteria | 1q | 1y |
|------|-------|--------|--------|:--:|--:|--:|
| 2021-08-09 | SPAC structural analysis | — | NO_BASKET | ✓ | — | — |
| 2021-12-03 | Crypto / Coinbase (COIN) | COIN | SOHN_AU_2021 | ✓ | −39.3 | **−82.7** |
| 2022-03-25 | Crypto / Coinbase (COIN) | COIN | SOHN_AU_2021 | – | −70.0 | −66.2 |
| 2023-04-21 | Optical networking / interconnect | CIEN,COHR,LITE | BAKER_NAMED | ✓ | 12.5 | 13.5 |
| 2023-04-21 | SpaceX ecosystem / Starship | RKLB,SPCE,RDW | RETAIL_PROXY | – | 34.5 | −18.0 |
| 2025-07-17 | China AI distillation / export | ASML,LRCX,AMAT,KLAC | OBVIOUS_UNIV | – | 28.7 | **159.8** |
| 2025-07-17 | Inference economics / token factories | CRWV | BAKER_NAMED | – | 5.3 | −44.7 |
| 2025-07-17 | Power / watts as binding constraint | VST,CEG | BAKER_NAMED | – | 23.6 | −15.0 |
| 2025-07-17 | Stablecoin / Visa-MC disruption | V,MA | OBVIOUS_UNIV | – | −0.2 | −1.5 |
| 2025-12-09 | Inference economics / token factories | CRWV | BAKER_NAMED | ✓ | −11.9 | n/a |
| 2026-07-20 | Inference economics / token factories | CRWV | BAKER_NAMED | – | n/a | n/a |
| 2026-07-20 | Optical networking / interconnect | CIEN,COHR,LITE | BAKER_NAMED | – | n/a | n/a |
| 2026-07-20 | Orbital / space-based compute | SPCX | OBVIOUS_UNIV | – | n/a | n/a |
| 2026-07-20 | Reasoning / inference-time compute | NVDA,AMD | OBVIOUS_UNIV | – | n/a | n/a |
| 2026-07-20 | SpaceX ecosystem / Starship | SPCX | OBVIOUS_UNIV | – | n/a | n/a |

`n/a` = INSUFFICIENT_DATA (2026-07-20 events are 2 days old — no forward window yet).

The 2 non-new-date events came from the approved curation:
- **2022-03-25 Coinbase** — an old On-The-Tape web3-infra thesis caught by the new `Crypto/Coinbase` keys (flagged minor dual-use at the gate).
- **2025-12-09 Inference economics** — old "Google lowest-cost token producer" thesis (T3) caught by the new `lowest.?cost token` key (dual-clustered; also still in Google TPU).

New theme + keys added this session (operator-approved): `Crypto / Coinbase (COIN)` LONG; keys
`lowest.?cost token` (Inference economics), `electricity generation` (Power/watts),
`structurally short (of )?compute` (Reasoning/inference-time compute). Blackwell/Hopper keys were
reviewed and **declined** (15-thesis blast radius) — so All-In-tariffs T5/T6 stay NO_BASKET by choice.

## 2. Renumbering (21 mention_number shifts)
New earlier-dated appearances inserted earlier mentions, shifting all later mentions in 5 themes:
- **SpaceX ecosystem** (+2 dates: 2023-04-21, 2026-07-20) → 2024-08-07 onward each +1 (11 rows).
- **Optical networking** (+2023-04-21, +2026-07-20) → 3 rows shifted.
- **China AI distillation** (+2025-07-17) → 3 rows +1.
- **Inference economics** (+2025-07-17, +2025-12-09) → 2 rows (e.g. 2026-05-20: 1→3).
- **SPAC structural analysis** (+2021-08-09) → 2 rows +1.
Mention-number shifts carry **no basket or return change** — returns are date-anchored.

## 3. Override regression found & fixed (root cause)
The renumbering **broke 9 SpaceX event-overrides** keyed by `(date, mention_number)`: the stale
`mention_number` no longer matched, so overrides silently stopped applying and 9 SpaceX events reverted
their baskets (e.g. 2026-05-20 lost its ASML/LRCX/KLAC/AMAT semicap override; several NO_BASKET flags
reverted to space proxies).
**Fix:** date-anchored the 10 SpaceX event-overrides — removed the fragile `mention_number`, kept `date`
(`(theme,date)` is unique in the mention grain, so it's sufficient and renumbering-proof). This restores
the operator's validated v6 SpaceX baskets (confirmed: 0 basket changes on existing rows post-fix).

## 4. Global date-anchoring APPLIED (operator-approved 2026-07-22)
All event-override matches were date-anchored: `mention_number` removed from **73** matches (0 of 113
used `mention_number` without a `date`, so the transform is lossless — `(theme,date)` is unique in the
mention grain). This immunizes the whole override file against future renumbering and activates
overrides that were dormant due to stale mention numbers.

**Net effect of the global pass (vs the interim SpaceX-only fix): 3 basket-label changes, 0 return changes.**
Previously-dormant DRAM overrides now apply their intended basket:
- 2025-01-04, 2025-05-28, 2026-05-28 | DRAM / HBM: `MU` → `MU, 000660.KS`; source `OBVIOUS_UNIVERSE` → `BAKER_NAMED`.

Returns are **unchanged**: `000660.KS` (SK Hynix Korean listing) resolves NO_DATA on EODHD, so it does
not enter the equal-weight basket return — only the basket label/source reflect the operator's intent.
The other dormant DRAM overrides had an intended basket identical to the natural one (`MU`), so no visible
change. Slice summary unchanged (signal n=45, ret_1y 240.5%).

## 5. Data-quality notes
- Audit removed a wrong `SPCE` ticker tag (drawdown T1 "SpaceX" — private, ≠ Virgin Galactic).
- Private-company tokens (Anthropic/OpenAI/xAI/SpaceX) remain in tickers_direct → resolve NO_DATA (harmless).
- All-In E125 (2023-04-21) Starship theses likely trace to co-guest Antonio Gracias, not Baker
  (standard All-In multi-speaker caveat); they drive the new SpaceX/Optical 2023-04-21 events.
- Coinbase (COIN) 2021 pick scored −82.7% at 1y (pick preceded the 2022 crypto drawdown).
