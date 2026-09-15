# Attribution filter — aggregate before/after

`all` = every thesis in the corpus (pre-attribution behaviour). 
`subject` = only theses both audit passes attributed to the subject; 
`other` and `indeterminate` stay in the corpus, tagged, but are excluded.

Returns are NOT computed here. Cluster -> mention rows -> basket resolution only.

## Corpus attribution split

| verdict | theses |
| --- | ---: |
| subject | 467 (76%) |
| other | 42 (7%) |
| indeterminate | 105 (17%) |

## Aggregate

| measure | all | subject | delta | |
| --- | ---: | ---: | ---: | ---: |
| theses | 614 | 467 | -147 | -23.9% |
| named-ticker slots | 705 | 573 | -132 | -18.7% |
| distinct named tickers | 141 | 121 | -20 | -14.2% |
| themes with >=1 mention | 61 | 54 | -7 | -11.5% |
| mention rows | 257 | 205 | -52 | -20.2% |
| repeat mentions | 196 | 151 | -45 | -23.0% |
| meets existing criteria | 86 | 74 | -12 | -14.0% |
| scored rows (basket resolved) | 142 | 118 | -24 | -16.9% |
| basket ticker universe | 71 | 63 | -8 | -11.3% |

## What disappears

**Themes lost entirely (7):** `CDN / token delivery path`, `Datacenter power equipment`, `Defense tech consolidation`, `Legacy software bottom / PE take-privates`, `Merchant silicon alternative (Broadcom/AMD)`, `Sovereign AI`, `Uranium enrichment / national security`

**Named tickers lost from the corpus (20):** `AKAM`, `BTC`, `CHRW`, `CMI`, `CRSO`, `FCX`, `FOX`, `FSLY`, `HMC`, `IRON`, `LEU`, `NET`, `NSANY`, `SCCO`, `SIEGY`, `SPCE-IPO`, `STLA`, `VAST`, `VWAGY`, `Zipline (private)`

**Tickers lost from resolved baskets (8):** `CAT`, `CMI`, `DLR`, `EQIX`, `GEV`, `LEU`, `SIEGY`, `WDAY`

**Mention rows lost (52):**

| theme | date |
| --- | --- |
| `AI bubble not happening` | 2025-10-30 |
| `AI bubble not happening` | 2026-02-24 |
| `AI bubble not happening` | 2026-06-07 |
| `AI capex ROI positive` | 2024-08-27 |
| `AI capex ROI positive` | 2024-12-07 |
| `AI networking (Ethernet/InfiniBand)` | 2026-04-16 |
| `Anthropic valuation / efficiency` | 2026-05-22 |
| `Bottleneck trade ending` | 2026-06-15 |
| `Broad AI bullish / early innings` | 2026-08-14 |
| `CDN / token delivery path` | 2026-06-15 |
| `China AI distillation / export controls` | 2025-01-28 |
| `Coding as killer AI app` | 2026-07-14 |
| `DRAM / HBM memory bottleneck` | 2026-05-22 |
| `Datacenter physical assets` | 2026-06-15 |
| `Datacenter physical assets` | 2026-06-27 |
| `Datacenter power equipment` | 2026-08-14 |
| `Defense tech consolidation` | 2024-12-07 |
| `Edge AI as bear case for cloud` | 2024-01-30 |
| `Humanoid robotics / Tesla Optimus` | 2024-08-07 |
| `Humanoid robotics / Tesla Optimus` | 2025-01-28 |
| `Humanoid robotics / Tesla Optimus` | 2026-02-24 |
| `Inference economics / token factories` | 2026-05-20 |
| `Inference economics / token factories` | 2026-06-15 |
| `Legacy software bottom / PE take-privates` | 2026-08-14 |
| `Merchant silicon alternative (Broadcom/AMD)` | 2026-07-14 |
| `Meta AI transformation` | 2026-06-15 |
| `Microsoft AI position` | 2024-12-07 |
| `Neoclouds as durable model` | 2026-08-31 |
| `Nvidia GPU moat / CUDA ecosystem` | 2026-08-14 |
| `Optical networking / interconnect` | 2024-01-30 |
| `Orbital / space-based compute` | 2026-02-24 |
| `Orbital / space-based compute` | 2026-06-11 |
| `Orbital / space-based compute` | 2026-06-15 |
| `Orbital / space-based compute` | 2026-08-14 |
| `Orbital / space-based compute` | 2026-08-31 |
| `Power / watts as binding constraint` | 2026-08-14 |
| `Private market structural shift` | 2026-06-07 |
| `SPAC structural analysis` | 2026-06-07 |
| `SaaS existential disruption` | 2023-06-19 |
| `Scaling laws intact` | 2024-12-07 |
| `Sovereign AI` | 2026-06-15 |
| `SpaceX ecosystem / Starship economics` | 2024-08-07 |
| `SpaceX ecosystem / Starship economics` | 2025-12-09 |
| `SpaceX ecosystem / Starship economics` | 2026-06-07 |
| `SpaceX ecosystem / Starship economics` | 2026-06-15 |
| `Stranded / behind-the-meter power` | 2026-02-24 |
| `Tesla / EV / FSD` | 2025-01-04 |
| `Uranium enrichment / national security` | 2026-02-24 |
| `xAI competitive position` | 2024-01-30 |
| `xAI competitive position` | 2024-02-23 |
| `xAI competitive position` | 2024-08-07 |
| `xAI competitive position` | 2025-01-28 |

## Per theme (mention rows)

| theme | all | subject | delta |
| --- | ---: | ---: | ---: |
| `Orbital / space-based compute` | 13 | 8 | -5  <- |
| `SpaceX ecosystem / Starship economics` | 17 | 13 | -4  <- |
| `xAI competitive position` | 13 | 9 | -4  <- |
| `AI bubble not happening` | 7 | 4 | -3  <- |
| `Humanoid robotics / Tesla Optimus` | 9 | 6 | -3  <- |
| `AI capex ROI positive` | 10 | 8 | -2  <- |
| `Datacenter physical assets` | 3 | 1 | -2  <- |
| `Inference economics / token factories` | 6 | 4 | -2  <- |
| `AI networking (Ethernet/InfiniBand)` | 4 | 3 | -1  <- |
| `Anthropic valuation / efficiency` | 6 | 5 | -1  <- |
| `Bottleneck trade ending` | 2 | 1 | -1  <- |
| `Broad AI bullish / early innings` | 10 | 9 | -1  <- |
| `CDN / token delivery path` | 1 | 0 | -1  <- |
| `China AI distillation / export controls` | 7 | 6 | -1  <- |
| `Coding as killer AI app` | 4 | 3 | -1  <- |
| `DRAM / HBM memory bottleneck` | 10 | 9 | -1  <- |
| `Datacenter power equipment` | 1 | 0 | -1  <- |
| `Defense tech consolidation` | 1 | 0 | -1  <- |
| `Edge AI as bear case for cloud` | 5 | 4 | -1  <- |
| `Legacy software bottom / PE take-privates` | 1 | 0 | -1  <- |
| `Merchant silicon alternative (Broadcom/AMD)` | 1 | 0 | -1  <- |
| `Meta AI transformation` | 3 | 2 | -1  <- |
| `Microsoft AI position` | 2 | 1 | -1  <- |
| `Neoclouds as durable model` | 5 | 4 | -1  <- |
| `Nvidia GPU moat / CUDA ecosystem` | 10 | 9 | -1  <- |
| `Optical networking / interconnect` | 3 | 2 | -1  <- |
| `Power / watts as binding constraint` | 7 | 6 | -1  <- |
| `Private market structural shift` | 2 | 1 | -1  <- |
| `SPAC structural analysis` | 4 | 3 | -1  <- |
| `SaaS existential disruption` | 7 | 6 | -1  <- |
| `Scaling laws intact` | 9 | 8 | -1  <- |
| `Sovereign AI` | 1 | 0 | -1  <- |
| `Stranded / behind-the-meter power` | 2 | 1 | -1  <- |
| `Tesla / EV / FSD` | 2 | 1 | -1  <- |
| `Uranium enrichment / national security` | 1 | 0 | -1  <- |
| `AI destroying application layer value` | 1 | 1 | +0 |
| `AI world models for gaming` | 1 | 1 | +0 |
| `ALAB / copper vs fiber` | 1 | 1 | +0 |
| `ASML / semcap equipment criticality` | 2 | 2 | +0 |
| `Crossover investing philosophy` | 3 | 3 | +0 |
| `Crypto / Coinbase (COIN)` | 2 | 2 | +0 |
| `Custom ASIC failure thesis` | 2 | 2 | +0 |
| `DISH / 5G bearish` | 2 | 2 | +0 |
| `Disaggregation prefill/decode` | 6 | 6 | +0 |
| `Frontier model concentration` | 4 | 4 | +0 |
| `Google AI distribution moat` | 1 | 1 | +0 |
| `Google TPU competitive position` | 5 | 5 | +0 |
| `Inflation macro framework` | 2 | 2 | +0 |
| `Intel recovery / foundry failure` | 3 | 3 | +0 |
| `MSTR / Bitcoin strategy risk` | 1 | 1 | +0 |
| `Metaverse / gaming as platform` | 5 | 5 | +0 |
| `Nuclear / clean energy for AI` | 1 | 1 | +0 |
| `Nuclear/quantum bubble warning` | 1 | 1 | +0 |
| `Open source AI bullish for hardware` | 3 | 3 | +0 |
| `Power / cooling equipment suppliers` | 1 | 1 | +0 |
| `Reasoning / inference-time compute` | 7 | 7 | +0 |
| `Stablecoin / Visa-MC disruption` | 1 | 1 | +0 |
| `TSMC capacity discipline` | 3 | 3 | +0 |
| `Target / omnichannel retail` | 3 | 3 | +0 |
| `Trainium / Amazon custom silicon` | 5 | 5 | +0 |
| `Usage-based AI pricing shift` | 2 | 2 | +0 |
