# Q3 2026 classification review — Atreides (Baker) and Situational Awareness (Leopold)

Prepared 2026-11-16 on branch `q3-2026-13f`. **Nothing in any classification file has been edited.** Waiting for sign-off.

## Recommendation (read this first)

1. **Approve the six ticker mappings (Decision 1).** Without them, Nebius ($267M) and Credo ($165M) are silently dropped from Baker's AI basket, because the AI-ramp filter skips any position with no ticker. **That one decision flips the ramp trigger this quarter:**

   | | AI net buying | % of ex-reclass equity ($5,987M) | Ramp (≥5%) |
   |---|---|---|---|
   | As-is (no mappings, no new entries) | +$175M | **+2.93%** | does not fire |
   | With Decisions 1 + 2 applied | +$421M | **+7.04%** | **fires** |

   The swing is almost entirely Nebius: 64K → 1.13M shares = **+$252M** (+4.2 pts). Credo was trimmed (−$55M). TTM (+$26M) and Hut 8 (+$23M) are new.
2. **Approve the new-ticker classifications in Decision 2.** Figma is the one that matters: a new 4.50% position, proposed as non-AI SaaS, consistent with how Adobe and GitLab are treated.
3. **No new IPO reclassifications.** `IPO_RECLASS_TICKERS` stays `{SPCX, CBRS}` (Decision 3).

---

## Filings ingested (step 1–2 results)

| | Atreides (CIK 0001777813) | Situational Awareness (CIK 0002045724) |
|---|---|---|
| Accession | `0001777813-26-000013` | `0000935836-26-000610` (filer-agent prefix, as expected) |
| Period / filed | 2026-09-30 / 2026-11-16 | 2026-09-30 / 2026-11-16 |
| Cover page: entries / value | 46 / $17,994,718,085 | 23 / $1,577,454,028 |
| Pipeline: positions / value | 46 / $17,994,718,085 | 9 / $1,577,454,028 |
| Match | exact | value exact. **Count differs by design:** SA filed 23 rows, but 18 of them are separate option lots on 4 underlyings (6× Bloom calls, 6× Nebius calls, 4× Roundhill DRAM calls, 2× Sandisk calls). The pipeline merges rows by CUSIP + security type, giving 5 equity + 4 call positions. |
| Equity (common) value | $10,741.4M (ex-SPCX/CBRS: **$5,987.3M**) | $532.7M |
| Options notional | $7,253.3M (QQQ put $3,773M, META call $1,378M, SMH put $1,218M, GOOGL call $688M, U call $197M) | $1,044.8M — **all calls; no puts this quarter** |

**Unresolved CUSIPs in the Q3 books (no ticker):**
- Atreides: Credo `G25457105`, On Holding `H5919C104`, Taboola `M8744T106`, INNIO `N52A8C105`, Nebius `N97284108`
- SA: Bitdeer `G11448100`, Nebius `N97284108`, IREN `Q4982L109`

All are foreign-registered (CUSIP starts with a letter). OpenFIGI has never resolved them. This isn't new: `data/cusip_ticker_map.json` holds 31 such entries going back to 2020. Consequence: **no prices, so no forward or lifecycle returns for any of them** (every row reads `NO_DATA` in `filing_to_filing_returns_universal.csv`), and they're excluded from the AI ramp.

---

## Decision 1 — ticker mappings for unresolved CUSIPs

**Proposal:** add `source: "manual"` entries to `data/cusip_ticker_map.json` for the six names below, then re-run the pipeline for both CIKs. The existing resolver already supports this: manual entries are never re-queried or overwritten (`cusip_map.resolve_tickers`). No code change is needed.

Each ticker was verified by matching EODHD's 2026-09-30 close to the 13F's implied price (value ÷ shares):

| CUSIP | Company | Ticker | EODHD 9/30 close | 13F implied | Held by |
|---|---|---|---|---|---|
| `N97284108` | Nebius Group | **NBIS** | $235.88 | $235.85 | both |
| `G25457105` | Credo Technology | **CRDO** | $194.79 | $194.77 | Baker |
| `H5919C104` | On Holding | **ONON** | $29.61 | $29.61 | Baker |
| `M8744T106` | Taboola | **TBLA** | $3.36 | $3.32 | Baker |
| `G11448100` | Bitdeer | **BTDR** | $10.49 | $10.49 | Leopold |
| `Q4982L109` | IREN | **IREN** | $40.88 | $40.88 | Leopold |
| `N52A8C105` | INNIO | ? | — | — | Baker ($6.5M) |

**INNIO:** EODHD has no data under `INNO` or `INNI`. If you know the ticker I'll add it. Otherwise it stays unresolved; its basket is already covered by the overlay's CUSIP entry, and at 0.11% it doesn't move anything.

**Things to know before approving:**
- **This rewrites history for these names.** Nebius and Credo were also held in Q1–Q2 2026 (and Nebius was Leopold's ~$1.23B Q2 position). Prior-quarter trigger rows and forward returns will change wherever these names appear. I'll report every historical trigger event that changes.
- **`data/` is gitignored.** The manual mappings will live only in your local `data/cusip_ticker_map.json`, not in the commit. The committed analysis outputs will reflect them.
- **Scope choice:** I've limited this to names in the Q3 books. 25 other historical unresolved names (ASML, Elastic, Wix, GlobalFoundries, JFrog, Nu, Grab, Joby, WhiteFiber, Tower Semi, Seagate, etc.) would also gain returns if mapped, and that would change the backtest more widely. I'd treat that as a separate task.

## Decision 2 — classification entries

**Weights:** common stock as % of ex-reclass equity (Baker $5,987.3M; Leopold $532.7M). Options as % of total reported value (notional, context only; never in weights or signals).

### Baker — names that need an entry (currently Unassigned, mis-keyed or missing)

| Ticker | Company | Missing from | Size | Q3 change | Proposed classification | Reason |
|---|---|---|---|---|---|---|
| FIG | Figma | AI basket, ticker classifications | $269.2M, **4.50%** | NEW | AI basket: `ai:false`, `Enterprise SaaS`. Ticker classifications: Software / Application Software / Enterprise SaaS | Design SaaS with AI features. Same call as ADBE/GTLB. **New position >2%.** |
| NBIS | Nebius | ticker (Decision 1), AI basket, ticker classifications | $266.7M, **4.45%** | ADD (64K → 1.13M sh) | AI basket: `ai:true`, `AI/Datacenter Compute`. Ticker classifications: Technology / Cloud Infrastructure / AI/Cloud | GPU neocloud, same bucket as CRWV. Overlay already maps it to "Neoclouds as durable model". |
| ONON | On Holding | ticker (Decision 1), ticker classifications | $192.2M, 3.21% | NEW (re-entry; last held Q1 2024) | Ticker classifications: Consumer Discretionary / Footwear & Apparel / Consumer Discretionary. No AI-basket entry needed (falls through as non-AI). | Athletic footwear. Today it shows as "Unassigned" on the context sheets. |
| CRDO | Credo | ticker (Decision 1), ticker classifications. **AI basket is keyed `CREDO`, which can never match a ticker.** | $164.9M, 2.75% | TRIM (1.13M → 847K) | Rename AI-basket key `CREDO` → `CRDO` (bucket unchanged: `AI/Datacenter Networking`). Ticker classifications: Semiconductors / Interconnect / AI/Datacenter Networking | Fixes a key that has never bound. |
| ADSK | Autodesk | AI basket, ticker classifications | $46.1M, 0.77% | NEW | `ai:false`, `Enterprise SaaS`. Software / Application Software / Enterprise SaaS | Design/engineering SaaS; same call as FIG. |
| TTMI | TTM Technologies | AI basket, ticker classifications | $26.5M, 0.44% | NEW | `ai:true`, `Semiconductor Supply Chain`. Technology / Electronic Components / Semiconductor Supply Chain | PCBs and substrates for AI servers and networking. Matches how ROG is treated. |
| HUT | Hut 8 | AI basket, ticker classifications | $23.3M, 0.39% | NEW | `ai:true`, `AI/Datacenter Power`. Technology / Digital Infrastructure / AI/Datacenter Power | Bitcoin miner converting powered sites to AI/HPC. Same call as CIFR in Q2. |
| TBLA | Taboola | ticker (Decision 1), ticker classifications | $2.8M, 0.05% | ~HOLD | Internet / Advertising / Digital Advertising. No AI-basket entry. | Overlay CUSIP entry already covers its basket. |
| INNIO | INNIO | ticker unknown | $6.5M, 0.11% | ~HOLD | No change (AI-basket key `INNIO` + overlay CUSIP entry already exist) | See Decision 1. |

### Baker — missing only from ticker classifications

These are already in the AI basket, so triggers and baskets are correct. Only the sector/industry/theme columns in the position-lifecycle view are blank.

| Ticker | Company | Size | Proposed (sector / industry / theme) |
|---|---|---|---|
| CBRS | Cerebras | $619.6M (reclass memo) | Semiconductors / AI Accelerators / AI/Datacenter Chips |
| SPCX | SpaceX | $4,134.5M (reclass memo) | Aerospace / Launch & Satellite / Space |
| PDFS | PDF Solutions | $33.9M, 0.57% | Software / Semiconductor Analytics / Semiconductor Supply Chain |
| QNT | Quantinuum | $1.9M, 0.03% | Technology / Quantum Computing / Quantum Computing |
| FRVO | Fervo Energy | $0.1M, 0.00% | Utilities / Geothermal Power / Clean Energy/Grid |

### Baker — absent from some files, but no entry needed

`baker_basket_overlay.json` is an **override list** (10 tickers + 7 CUSIPs), not a full map. Every other ticker falls through to AI-basket bucket → ticker-classification theme → "Unassigned". These names fall through correctly:

- PANW (Cybersecurity, 3.84%)
- TWLO (Enterprise SaaS, 3.55%)
- CVNA (E-commerce, **NEW 2.60%**)
- W (E-commerce)
- AFRM (Fintech)
- COMP (Real Estate)
- NOK (Telecom)
- EQPT (Construction)
- BTGO (Crypto)

They're also absent from the AI basket, which correctly makes them non-AI. QQQ and SMH appear only as puts: hedges, excluded from signals, already covered in ticker classifications.

### Leopold — `sa_theme_baskets.json` and ticker classifications

The AI-basket file and the Baker overlay aren't used for Leopold. His sheets use `sa_theme_baskets.json`.

| Ticker | Company | Type | Size | Q3 change | SA basket today | Proposed |
|---|---|---|---|---|---|---|
| DRAM | Roundhill Memory ETF | **CALL** | $140.3M (8.9% of book) | NEW | **none** | Add to `Memory / semis` (memory-chip ETF; pairs with the SNDK calls) |
| FRMI | Fermi Inc | COMMON | $11.2M, 2.11% | NEW | **none** | Add to `AI datacenter / power` (AI power/datacenter campus developer) |
| SHAZ | SharonAI | COMMON | $440.7M, **82.7%** | ADD (5.40M → 8.07M sh) | Neoclouds | no basket change |
| NBIS | Nebius | **CALL** | $332.6M (21.1% of book) | NEW (common fully exited) | Neoclouds (name alias) | no basket change; add `NBIS` ticker once mapped |
| BE | Bloom Energy | **CALL** | $389.2M (24.7% of book) | ADD (145.8K → 1.405M sh underlying; common exited) | AI datacenter / power | none |
| SNDK | Sandisk | **CALL** | $182.7M (11.6% of book) | NEW (common exited) | Memory / semis | none |
| CLSK, IREN, BTDR | CleanSpark, IREN, Bitdeer | COMMON | $38.9M / $21.6M / $20.3M | cut 75% / 94% / 44% | Crypto miners → AI/HPC | none; add `BTDR` ticker once mapped |

**Ticker classifications** has no entry for any of Leopold's nine Q3 names. It only feeds the position-lifecycle view's sector column, not his workbook sheets. I propose adding all nine:

| Ticker | Sector / industry / theme |
|---|---|
| SHAZ | Technology / GPU Cloud / AI/Cloud |
| NBIS | Technology / Cloud Infrastructure / AI/Cloud |
| BE | Utilities / Fuel Cells / AI/Datacenter Power |
| SNDK | Semiconductors / NAND Memory / AI/Datacenter Memory |
| DRAM | ETF / Memory ETF / ETF |
| CLSK | Technology / Bitcoin Mining → HPC / Crypto |
| IREN | Technology / Bitcoin Mining → HPC / Crypto |
| BTDR | Technology / Bitcoin Mining → HPC / Crypto |
| FRMI | Real Estate / Datacenter Development / AI/Datacenter Power |

## Decision 3 — IPO reclassification

**None this quarter.** Every new common position was already publicly traded before the quarter, with no earlier 13F history that suggests a pre-IPO stake:

| Manager | New positions |
|---|---|
| Baker | FIG (public since Jul 2025), CVNA, MSFT, ADSK, TTMI, HUT, ONON (re-entries or long-listed names) |
| Leopold | FRMI (public since Oct 2025) |

SharonAI was already held in Q1 and Q2 2026, so its Q3 add is a share-count increase, not an entry. `IPO_RECLASS_TICKERS` stays `{SPCX, CBRS}`.

---

## Leopold exits — classification check

The book went from **$20.24B (Q2) to $1.58B (Q3)**. All 19 full exits are classified `EXIT`. The biggest:

| Name | Prior value |
|---|---|
| SNDK | $5.67B |
| MU | $5.57B |
| BE common | $1.90B |
| TSM | $1.27B |
| Nebius common | $1.23B |
| CRWV | $745M |
| CORZ | $666M |
| STM | $584M |
| APLD | $469M |
| RIOT | $468M |

Smaller exits: KEEL, SEI, WhiteFiber, TE, HIVE, BW, PUMP, VSH, CBRS, TSM calls and the INFY put.

**One misclassification in the pipeline's per-position labels.** CleanSpark (−75% of shares) and Bitdeer (−44%) are labelled `HOLD`, not `ACTIVE_TRIM`. The classifier works on *weight*, and their weights rose because the book shrank 92%. This is the Q2 "weight-drift trap" in reverse. The workbook's money-flow breakdown uses share changes, so it will show them correctly as selling. I'm noting it here, not changing the classifier (that's spec logic).

## Other observations

- About a dozen small Baker holdings (QNT, BTGO, FRVO, EQPT, INNIO, AMBQ, COMP, PDFS, ROG, VECO, W, INTC, TBLA) all rose by the **same ~1.0% in shares**, and SPCX rose 0.27%. That looks like a fund-level accounting effect, not deliberate buys. The amounts are immaterial (well under $1M each except SPCX).

## What step 4 will touch (for your awareness, no decision needed)

- `build_trigger_workbook.py` hardcodes the Q2 period: `BAKER_PERIOD`, `BAKER_PRIOR_PERIOD`, `BAKER_FILING_DATE`, `BAKER_HISTORY_PERIODS`, the `SA_CSV` path, and four "Q2 2026" sheet titles. I'll update these values to Q3. This is a config/label change, not logic.
- Neither `sa_q2_2026_mtm_vs_trading.csv` nor `atreides_q2_2026_trigger_analysis.md` has a generator script. The Atreides decomposition CSV is written by the workbook builder. I'll produce the SA CSV with the same decomposition function and columns, and write the Atreides markdown in the Q2 file's format.

## To approve

Reply with any edits, or "approve as proposed". Please also say:
- (a) INNIO's ticker, if you know it
- (b) whether to map the 25 historical unresolved names now or leave that for later (I recommend later)

---

# Addendum (2026-11-16, after operator approval)

Approved and applied: the six Q3 mappings (NBIS, CRDO, ONON, TBLA, BTDR, IREN), the CREDO→CRDO key rename, every Decision 2 entry, and no IPO reclassifications. INNIO stays unresolved.

## Older unresolved CUSIPs — mapping verification

The real count was **24**, not 25: 31 unresolved, minus the 6 Q3 mappings, minus INNIO.

**Check:** every period the position was held, EODHD's close on the period end (or the last trading day before it) vs. the 13F value ÷ shares. Value units are auto-detected (pre-2023 filings report in $ thousands). A match is within 2%.

**22 mapped** (`source: "manual"` in `data/cusip_ticker_map.json`; every held period matches):

| CUSIP | Company | Ticker | Periods matched |
|---|---|---|---|
| 69120X107 | Owlet | OWLT | 4/4 |
| 83542D102 | Sonder Holdings | SOND | 6/6 |
| 902104108 | II-VI (now Coherent; old CUSIP) | IIVI | 3/3 |
| G0370L124 | Altimeter Growth Corp (units) | AGCUU | 4/4 |
| G19550113 | Catalyst Partners Acquisition (units) | CPARU | 7/7 |
| G29018101 | dLocal | DLO | 4/4 |
| G39387108 | GlobalFoundries | GFS | 2/2 |
| G4124C109 | Grab Holdings | GRAB | 3/3 |
| G4124C117 | Grab Holdings (warrants) | GRABW | 1/1 |
| G65163100 | Joby Aviation | JOBY | 17/17 |
| G66721104 | Norwegian Cruise Line | NCLH | 2/2 |
| G6683N103 | Nu Holdings | NU | 5/5 |
| G68707101 | PagSeguro Digital | PAGS | 2/2 |
| G6964L107 | Paysafe | PSFE | 1/1 |
| G7997R103 | Seagate Technology (Leopold) | STX | 1/1 |
| G96115103 | WhiteFiber (Leopold) | WYFI | 3/3 |
| M6191J100 | JFrog | FROG | 3/3 |
| M87915274 | Tower Semiconductor (Leopold) | TSEM | 2/2 |
| M98068105 | Wix.com | WIX | 5/5 |
| N07059210 | ASML Holding (both managers) | ASML | 3/3 |
| N14506104 | Elastic | ESTC | 12/12 |
| V7780T103 | Royal Caribbean | RCL | 1/1 |

**2 left unmapped:**

| CUSIP | Company | Tried | Result |
|---|---|---|---|
| 09077J107 | Bird Global | BRDS | Off by exactly 25× in all 3 periods. EODHD's series looks adjusted for Bird's 2023 1-for-25 reverse split. |
| 85572U102 | Starry Group | STRY | No EODHD data (delisted 2023). |

Both were sub-$1M positions in 2021–22.

Like the Q3 mappings, these entries live in gitignored `data/cusip_ticker_map.json`. This table is the tracked record.

## Older mappings — AI-basket proposals (awaiting approval; NOT applied)

### Something to decide first: Elastic is already counted as AI

`data/ticker_classifications.json` already had `ESTC → theme "AI/Data Infrastructure"`. Once ESTC resolved, the subtheme and new-position triggers (which fall back to that theme) started counting it as AI from **2020** on. That adds 6 events, all ESTC: 2020-05 new subtheme and cross 2%/4%; 2021-08 cross 2% and new 2% position; 2023-08 cross 2% and new 2% position. It also reshapes the 2024-05 "AI/Data Infrastructure" crosses. The ramp's net-buying numbers are unchanged, because the ramp filter reads only `ai_basket_reclassification.json`.

### Proposed entries for `analysis/ai_basket_reclassification.json`

Existing buckets only.

| Ticker | Held by (size) | Proposed | Reason |
|---|---|---|---|
| ESTC | Baker 2019–2025 (peak ~$130M) | `date_segments`: before 2023-01-01 → `ai:false`, `Enterprise SaaS`; from 2023-01-01 → `ai:true`, `AI/Data Infrastructure` | Same date-split approach as NTNX. 2019–22 Elastic was search/observability SaaS. The vector-search/AI pitch dates from 2023, consistent with MDB (AI at its May 2024 entry) and SNOW (Feb 2025). **Effect:** drops the four 2020 and 2021 ESTC events; keeps 2023-08 and 2024-05. |
| ASML | Baker Q4 2024–Q1 2025 ($204M → $13M); Leopold Q1 2026 ($494M) | `ai:true`, `Semiconductor Supply Chain` | Lithography toolmaker, same bucket as LRCX. It enters the ramp basket, so the Q4 2024 and Q1 2025 ramp math changes. |
| GFS | Baker Q4 2024 ($16M), Q1 2026 ($21M) | `ai:true`, `Semiconductor Manufacturing` | Foundry, same as INTC. Baker's overlay already puts it in this bucket by CUSIP. |
| IIVI | Baker 2021 (~$100M at peak) | `ai:false`, `Semiconductor Supply Chain` | Optical/compound-semi materials before the AI narrative. Same reasoning as NET's 2020 entry (`ai:false`, "pre-AI narrative"). Today's COHR (new CUSIP) stays AI as-is. |
| STX, TSEM, WYFI | Leopold only | Consistency only: STX `ai:true` `AI/Datacenter Storage`; TSEM `ai:true` `Semiconductor Manufacturing`; WYFI `ai:true` `AI/Datacenter Compute` | **No effect on any output.** The AI basket file is only read for Baker. For Leopold, they'd go in `sa_theme_baskets.json` as tickers: STX and TSEM → `Memory / semis`, WYFI → `Neoclouds` (WhiteFiber is already matched there by company-name alias). |

**No AI entry proposed** for OWLT, SOND, AGCUU, CPARU, DLO, GRAB/GRABW, JOBY, NCLH, NU, PAGS, PSFE, FROG, WIX, RCL. These are consumer, fintech, travel, SPAC and dev-tool names, and absence correctly makes them non-AI. WIX already has `ai:false`. JFrog would mirror GTLB (`ai:false`), so no entry is needed.
