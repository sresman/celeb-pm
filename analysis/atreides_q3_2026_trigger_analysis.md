# Atreides (Gavin Baker) — Q3 2026 13F Trigger Analysis

> **Updated 2026-11-17:** the ramp now counts full exits as selling, as the spec intended (`COUNT_EXITS = True`). Under the corrected rule the Q3 ramp is **+2.20% and does not fire**. It read +7.04% before the fix.

**Filing:** 13F-HR, accession `0001777813-26-000013`, period **2026-09-30**, filed **2026-11-16**
**Baseline:** Q2 2026 (`0001777813-26-000009`, period 2026-06-30)
**Ingested via:** `python -m celebpm.pipeline 0001777813 --data-root data` (28 filings parsed, 0 skipped)
**Data verified:** cover page 46 entries / $17,994,718,085 = pipeline 46 / $17,994,718,085. Five positions spot-checked against the raw infotable (`ATREIDES13F09302026v2.xml`) match to the share and dollar: SPCX, ALAB, NBIS, FIG, and the QQQ put.
**Weights:** % of thesis-investable equity = common stock **excluding** the IPO-reclass names SPCX and CBRS ($5,987.3M). Options are **informational only**: they are in no total, weight, trigger or signal, and notional is never a position size.

---

## Headline: an AI rotation under a flat book, not a ramp

| Metric | Q2 2026 | Q3 2026 | Change |
|---|---|---|---|
| Equity (common) value | $11.15B | **$10.74B** | −4% |
| Thesis-investable equity (ex SPCX/CBRS) | $5.79B | **$5.99B** | +3% |
| Common positions | 46 | 41 | −5 |
| NEW / EXIT (common, genuine) | — | **7 / 12** | |
| SPCX + CBRS (IPO-reclass memo) | $5.36B | $4.75B | marks down |

**Signals this quarter:**
- **AI_BASKET_RAMP does not fire: +2.20%** of thesis-investable equity (threshold 5%). Full exits now count as selling.
- **AI/Datacenter Compute crosses 4%**: 3.96% → 7.40%, driven by Nebius.
- **NEW_AI_POSITION_2PCT: Microsoft** at 2.36% (hyperscaler re-entry; last held Q4 2025).

---

## Net deployment (share-based, deliberate; ex SPCX/CBRS)

| | $ | % of thesis equity |
|---|---|---|
| New-position buying (7 names) | +$854M | +14.3% |
| Adds to existing (shares up) | +$1,327M | +22.2% |
| **Gross buying** | **+$2,181M** | **+36.4%** |
| Trims (shares down) | −$926M | −15.5% |
| Full exits (12 names) | −$858M | −14.3% |
| **NET deliberate buying** | **+$397M** | **+6.6%** → **net BUYER** |
| Mark-to-market (price moves) | −$200M | |
| **Δ value (reconciles: MTM + trading, gap $0)** | **+$196M** | |

The IPO-reclass names are excluded from every figure above. Their own share changes this quarter were **SPCX +73,111 sh (≈ +$11M)** and **CBRS +377,742 sh (≈ +$67M)**. On an as-filed basis, net trading is +$0.48B.

### Ramp, by name (points of $5,987M thesis equity)

| Bucket | $ | pts |
|---|---|---|
| Gross buying (adds + new) | +$1,027M | +17.15 |
| Trims | −$605M | −10.11 |
| Full exits (APH, SMTC, CIFR) | −$290M | −4.84 |
| **Net** | **+$131M** | **+2.20** → no fire |

| Name | $ | pts |
|---|---|---|
| ALAB (add) | +$442M | +7.38 |
| NBIS (add, 64K → 1.13M sh) | +$252M | +4.21 |
| CIEN (add) | +$123M | +2.05 |
| AKAM (add) | +$106M | +1.77 |
| NVDA (add) | +$52M | +0.87 |
| TTMI (new) | +$26M | +0.43 |
| HUT (new) | +$23M | +0.38 |
| INTC, AMBQ, PDFS, ROG, VECO, FRVO | ~+$2M | +0.04 |
| COHR | −$4M | −0.07 |
| CRWV | −$9M | −0.15 |
| CRDO | −$55M | −0.92 |
| U | −$103M | −1.72 |
| MU (711K → 304K sh) | −$434M | −7.25 |
| APH (exit) | −$113M | −1.88 |
| SMTC (exit) | −$89M | −1.49 |
| CIFR (exit) | −$88M | −1.47 |
| **Net** | **+$131M** | **+2.20** |

The three AI exits (APH −$113M, SMTC −$89M, CIFR −$88M, together −4.84 pts) take net AI buying from +7.04% to +2.20%. Before the exits fix, the Nebius/Credo ticker mappings decided whether Q3 fired (+2.93% without them, +7.04% with). Under the corrected rule it doesn't fire either way.

**Read:** the AI book rotated toward networking (Astera) and neoclouds (Nebius), funded by Micron and three AI exits; net new AI capital was small (+$131M). Memory fell from 14.2% to 5.4% of the thesis book, while Neoclouds rose from 4.0% to 7.4%. Outside AI, Baker opened Figma (4.5%), On Holding (3.2%) and Carvana (2.6%), and exited Alphabet common while buying GOOGL calls.

---

## Top 10 adds (by trading $)

| Name | Type | $ | Shares | Basket |
|---|---|---|---|---|
| ALAB | ADD | +$442M | 1.22M → 2.46M | AI/Datacenter Networking |
| META | ADD | +$341M | 403K → 872K | Hyperscalers |
| FIG | NEW | +$269M | 12.81M | Enterprise SaaS |
| NBIS | ADD | +$252M | 64K → 1.13M | Neoclouds |
| ONON | NEW | +$192M | 6.49M | Consumer Discretionary |
| CVNA | NEW | +$155M | 2.48M | E-commerce |
| MSFT | NEW | +$142M | 276K | AI/Hyperscaler |
| CIEN | ADD | +$123M | 689K → 1.04M | AI/Datacenter Optical |
| AKAM | ADD | +$106M | 911K → 1.91M | AI/Edge Computing |
| NVDA | ADD | +$52M | 1.25M → 1.48M | Nvidia GPU moat |

## Top 10 trims / exits (by trading $)

| Name | Type | $ | Shares | Basket |
|---|---|---|---|---|
| MU | TRIM | −$434M | 711K → 304K | DRAM / HBM memory |
| GOOGL | EXIT | −$175M | all | Hyperscalers |
| PANW | TRIM | −$118M | 877K → 579K | Cybersecurity |
| APH | EXIT | −$113M | all | AI/Datacenter Networking |
| U | TRIM | −$103M | 10.25M → 7.73M | AI/World Models |
| AMZN | TRIM | −$101M | 970K → 566K | Hyperscalers |
| SMTC | EXIT | −$89M | all | AI/Edge Computing |
| CIFR | EXIT | −$88M | all | AI/Datacenter Power |
| DKS | EXIT | −$85M | all | Consumer Discretionary |
| ACVA | EXIT | −$71M | all | E-commerce |

Other exits: Wix −$66M (CUSIP unresolved), MA −$48M, TTAN −$38M, FERG −$35M, NTRA −$28M, WRBY −$21M.

---

## Options — informational aside (never in any total, weight or signal)

| Underlying | Put/Call | Underlying shares | Notional (informational) | vs Q2 |
|---|---|---|---|---|
| QQQ | PUT | 5,100,000 | $3,773M | up from 3.2M sh |
| META | CALL | 1,900,000 | $1,378M | up from 1.2M sh |
| SMH | PUT | 2,000,000 | $1,218M | new |
| GOOGL | CALL | 2,000,000 | $688M | new (common exited) |
| U | CALL | 4,800,000 | $196M | new |
| CBRS | CALL | — | (prior $155M) | closed |

Directionally: the index/semis hedges (QQQ and SMH puts) got larger, alongside upside calls on META, GOOGL and U. 13F carries no strike or expiry, so these say nothing about premium or capital at risk.

---

## Data notes

- **Q3 ticker mappings** (manual, verified against EODHD 9/30 closes): NBIS, CRDO, ONON, TBLA (Baker), BTDR, IREN (Leopold). INNIO (`N52A8C105`, $6.5M) remains unresolved. The 24 older foreign CUSIPs stay unresolved by design; the one visible this quarter is Wix's exit.
- **One past trigger changed** because Credo now has a ticker: `NEW_AI_POSITION_2PCT` for CRDO on 2026-05-18 (Q1 2026). Nebius changed no past events.
- **Fix applied this cycle:** option exits had been counted in equity money-flow totals. Q2's published ex-reclass net trading moves from **−$1.35B to −$1.26B** (the RBLX and U call exits, −$90M notional, are removed). Q3 is computed on the corrected basis.
- **Ramp rule corrected (2026-11-17):** full exits now count as selling. Across history the ramp goes from 12 to 9 events: 2023-11-14, 2024-11-14 and 2026-11-16 no longer fire.
