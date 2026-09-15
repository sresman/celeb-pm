# Atreides (Gavin Baker) — Q2 2026 13F Trigger Analysis

**Filing:** 13F-HR, accession `0001777813-26-000009`, period **2026-06-30**, filed **2026-08-14**
**Baseline:** Q1 2026 (`0001777813-26-000006`, period 2026-03-31)
**Ingested via:** `python -m celebpm.pipeline 1777813 --today 2026-08-14` (auto-discovered; 27 filings parsed, 0 skipped)
**Data verified:** parsed values match the raw EDGAR infotable (`ATREIDES13FXMLQ2.xml`) to the dollar. Q1 baseline unchanged by the re-run.

---

## Headline: a wholesale repositioning, not an incremental quarter

| Metric | Q1 2026 | Q2 2026 | Change |
|---|---|---|---|
| Total 13F value | $5.00B | **$14.34B** | **+187%** |
| Equity-only value | $4.10B | **$11.15B** | +172% |
| Options notional | $0.90B | **$3.19B** | +255% |
| Positions | 54 | 49 | −5 |
| NEW / EXIT | — | **15 / 20** | 37% of names turned over |

Two positions now dominate the book: **SpaceX (SPCX) 32.6%** and a **QQQ put hedge 16.4%** = ~49% of reported value.

### ⚠️ Read conviction from SHARE deltas, not weight deltas this quarter
Because the portfolio ~tripled, the classifier reports **0 ACTIVE_ADD and only 1 DRIFT_UP** — every continuing name's *weight* compressed against a 3× larger denominator even when share counts rose. This is exactly the "net buying vs. weight drift" trap. The share-based deployment below is the correct lens.

---

## Net deployment (share-based, deliberate)

| | $ | % of Q2 port |
|---|---|---|
| New-position buying | $6,094M | 42.5% |
| Adds to existing (shares up) | $366M | 2.6% |
| **Gross buying** | **$6,459M** | **45.1%** |
| Trims (shares down) | −$1,293M | −9.0% |
| **NET deliberate buying** | **+$5,166M** | **+36.0%** |
| Full exits (funded the buying; not counted as "selling") | $1,074M / 18 names | — |

**Ramp trigger: FIRES at +36% net deployment** (threshold 5%). This is deliberate capital deployment, not price drift.

> **Why the automated AI-basket ramp does *not* fire (and shouldn't).** With Q2's new tickers now added to `ai_basket_reclassification.json`, the narrow "picks-and-shovels" AI basket's share-based **net deployment for Q2 is −$48M (−0.3% of book)** — gross AI buying of $1,108M (Cerebras $687M, CoreWeave +$131M, Amphenol $113M, Cipher $88M, PDF $47M, Akamai +$27M) almost exactly offset by $1,156M of AI trims, dominated by **Astera Labs −$1,038M**. In other words the **AI-infra rotation was self-funded — he sold Astera to fund Cerebras/CoreWeave/Amphenol.** The genuinely new $5.17B of net capital went to **SpaceX (space/orbital, excluded from the AI basket) + the QQQ hedge**, not to the AI book. So the portfolio-wide ramp fires (+36%) while the AI-specific ramp is flat — both are correct and the contrast is the point.

---

## NEW positions (15)

| Ticker | Type | $ value | Weight | Company |
|---|---|---:|---:|---|
| **SPCX** | Common | **$4,670M** | **32.58%** | Space Exploration Technologies (SpaceX) |
| CBRS | Common | $687M | 4.79% | Cerebras Systems |
| META | **Call** | $676M | 4.72% | Meta Platforms |
| META | Common | $227M | 1.58% | Meta Platforms |
| CBRS | **Call** | $155M | 1.08% | Cerebras Systems |
| APH | Common | $113M | 0.79% | Amphenol (datacenter connectivity) |
| GTLB | Common | $103M | 0.72% | GitLab |
| CIFR | Common | $88M | 0.61% | Cipher (bitcoin/datacenter power) |
| IOT | Common | $75M | 0.52% | Samsara |
| PDFS | Common | $47M | 0.33% | PDF Solutions (semi yield) |
| TTAN | Common | $38M | 0.27% | ServiceTitan |
| NTRA | Common | $28M | 0.20% | Natera |
| INNIO | Common | $14M | 0.10% | Innio NV (energy) |
| QNT | Common | $3M | 0.02% | Quantinuum (quantum) |
| FRVO | Common | ~$0M | 0.00% | Fervo Energy (geothermal/DC power) |

SpaceX appears in a 13F because it **IPO'd in Q2 2026** (corpus: "SpaceX IPO" / "SpaceX IPO drawdown," Jun–Jul 2026) — previously a private crossover holding, now a 13(f) security.

## EXITS (20, $1.07B)

LITE $188M · SATS $117M · ZM $106M · RKT $87M · VST $79M · RBLX $78M (+RBLX calls $57M) · HUBS $57M · SNPS $54M · RL $44M · AXON $43M · WING $42M · U calls $33M · CHYM $30M · AVAV $30M · RBRK $28M · JFROG $26M · SNOW $22M · V $22M · GFS $21M.

## Deliberate ADDS / TRIMS (continuing names)

- **Adds:** CRWV **+$131M (+162% sh)** · PANW +$107M (+56%) · WIX +$37M (+124%) · AKAM +$27M (+33%) · MA +$23M (+89%)
- **Trims:** **ALAB −$1,038M (−64% sh)** — the one big sale · U −$61M (−17%) · MU −$57M (−6%) · W −$54M (−41%) · TWLO −$42M (−22%) · GOOGL −$24M (−12%)

## Options overlay

| Ticker | Type | Change | Notional | Prior |
|---|---|---|---:|---:|
| **QQQ** | Put | HOLD (shares +129%) | **$2,356M (16.4%)** | $808M |
| META | Call | NEW | $676M | — |
| CBRS | Call | NEW | $155M | — |
| RBLX / U | Calls | EXIT | — | $57M / $33M |

The Nasdaq put hedge **~tripled** to 16.4% of the book — portfolio insurance against a tech/IPO drawdown on top of the concentrated long book.

---

## Thesis-to-action confirmation (vs. signal-events corpus, through 2026-08-04)

**Confirmed (talked → bought/held):**
- **Space/orbital compute** (41 recent thesis mentions; high-conviction on BG2/All-In/CNBC/ILTB, corpus resolved the basket to ticker **SPCX**) → **NEW SpaceX, 32.6% — the biggest position.** Textbook.
- **Neoclouds / CoreWeave** (high-conviction repeatedly May–Jul 2026, CRWV+NBIS) → **CRWV add +162% shares.**
- **Cerebras / disaggregated inference** (high-conviction 2026-06-27, "NVDA, CBRS") → **NEW CBRS $842M (common+calls).**
- **DRAM/HBM memory / Micron** (high-conviction all through 2026) → **MU core hold $821M** (minor −6% trim).
- **Meta AI transformation** (moderate, May–Jun) → **NEW META $903M**, expressed with **calls** (bullish leverage).
- **Anti-SaaS / "AI destroying the application layer"** (high-conviction bearish) → **EXITED HUBS, SNOW, ZM, RBRK, JFROG** (the short/avoid side confirmed).

**Divergences (talked ≠ acted) — worth a look:**
- **Optical / ALAB** — high-conviction "copper vs fiber" and optical-networking talk (May 2026), yet Q2 **trimmed ALAB −64% and exited Lumentum**. Either profit-taking or a genuine cool-off on fiber names; CIEN/COHR were only held, not built.
- **AI networking / Arista (ANET)** — repeated high-conviction, **no position.**
- **Datacenter REITs (EQIX/DLR) & power (VST/GEV/VRT)** — discussed, but power was expressed via small new names (**Fervo, Cipher**) and **Vistra was exited**; the discussed REITs weren't bought.
- **NVDA** — named far more than any other ticker (73×), but held as a **tiny, flat** position. Consistent pattern: he narrates NVDA as the ecosystem anchor and expresses the trade through picks-and-shovels, neoclouds, and memory instead.

---

## Open items (for operator)
1. **Update `analysis/ai_basket_reclassification.json`** with Q2's new tickers (SPCX→Space/orbital, CBRS→AI datacenter compute, CIFR/FRVO→power, etc.) so the automated AI-basket triggers (Trigger 1/2/2b/3) classify Q2 correctly. Bucket assignment is curated — needs your call.
2. **4 unresolved CUSIPs** (ticker=None) in Q2 — OpenFIGI misses (WIX/Credo/etc. resolved via company_name here). Re-run resolves on next pass.
3. **EODHD_API_KEY blank** in `.env` — forward returns/fundamentals for new Q2 tickers are `NO_DATA` until a key is set (does not affect any classification or net-buying figure above).
