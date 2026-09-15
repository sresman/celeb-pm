# Situational Awareness (Leopold Aschenbrenner) — Q2 2026 13F: MTM vs. Trading Decomposition

**Filing:** 13F-HR, accession `0000935836-26-000418` (agent-filed; subject CIK 0002045724), period **2026-06-30**, filed 2026-08-14.
**Baseline:** Q1 2026 (`0002045724-26-000008`, period 2026-03-31).
**Method:** For every continuing position, dollar change decomposed as
`ΔValue = MTM (prior_shares × [P_Jun30 − P_Mar31]) + Trading ((Δshares) × P_Jun30)`, using **EODHD adjusted close** at both quarter-ends. Per-position detail: `analysis/sa_q2_2026_mtm_vs_trading.csv`.

> **Correction note (supersedes a prior draft).** An earlier version read the option *notional* as the size of a directional short and inferred a "short-blew-up → margin call → forced unwind" story. That was wrong. Option notional (value of the underlying) is **not** capital at risk; a **long put is defined-risk — max loss is the premium paid**, which the 13F does not report. The book below is **hedged long**, and the Q1→Q2 move is **dropping the hedge and pressing the long**, not a thesis reversal. See "How to read the options" and "Forced or voluntary?".

---

## Headline

| | Q1 2026 | Q2 2026 | Change |
|---|---:|---:|---:|
| Total 13F value | $13.68B | $20.24B | +48% |
| **Equity (long)** | $3.86B | **$20.17B** | **+$16.3B (+422%)** |
| Options notional (defined-risk overlay) | $9.82B | $0.07B | −$9.75B |
| Positions | 42 | 26 | −16 |

**Q1 was a hedged-long book: ~$3.86B of long AI-infrastructure equity, wrapped in a long-options overlay (downside puts on the semis/AI complex + some upside calls). Q2 removes the overlay and expands the outright long to $20.17B.** This is a risk-on escalation — pressing the long and shedding protection — not a bearish-to-bullish reversal.

## The Q1 long book was AI-infrastructure; the puts hedged it
Q1 equity longs: Bloom Energy $879M, CoreWeave $556M, IREN $401M, Core Scientific $389M, Applied Digital $320M, Riot $142M, CleanSpark $104M, plus Bitdeer/WhiteFiber/HIVE and small semis stubs — i.e. **AI datacenter / power / bitcoin-miner-to-AI names**. The put overlay was on **SMH, NVDA, ORCL, AVGO, AMD, MU, TSM, ASML, INTC** — the AI-semiconductor complex. Buying semis/AI puts to protect a long AI-infrastructure book is a **portfolio hedge**, not a directional short.

## Equity: sold or marked down? → **Neither — bought and marked up.**
Of the **+$16.3B** equity increase:
- **Net buying (deliberate): ≈ +$12.4B** (~76%) — $11.10B across priced names + ~$1.3B unpriced (NEBIUS new $1.23B).
- **Mark-to-market: ≈ +$4.0B** (~24%) — appreciation on shares already held.
- Reconciliation gap (fund marks vs. EODHD close), priced names: **−$0.10B** (<1%).

Equity exits were trivial ($26M PSIX, $39M "1B2", and the small semis commons that were delta stubs alongside the puts). **No equity liquidation.**

### Biggest moves (MTM vs Trading, $M)
| Ticker | ΔValue | MTM | Trading | Read |
|---|---:|---:|---:|---|
| MU (Micron) | +5,568 | +14 | **+5,553** | tiny $6M stub → $5.57B outright long (Q1 also carried MU puts+calls; those are gone) |
| SNDK (SanDisk) | +4,949 | +1,868 | +3,081 | doubled shares (+119%) into a +258% move |
| BE (Bloom Energy) | +1,020 | **+1,084** | −64 | **held through a +123% rally** (shares ~flat) — marked up, not traded |
| TSM | +1,258 | +3 | **+1,254** | small stub → $1.27B outright long (Q1 TSM puts+calls gone) |
| NEBIUS | +1,233 | n/a | +1,233 | NEW (price unresolved; all trading) |
| CORZ (Core Scientific) | +276 | **+276** | 0 | pure MTM, shares flat — held |
| CRWV (CoreWeave) | +188 | +158 | +30 | mostly MTM, small add |
| STM (STMicro) | +584 | 0 | +584 | NEW |
| RIOT | +326 | +173 | +153 | add + MTM |
| SHAZ | +439 | +49 | +389 | big add |

Buying concentrates in **memory/semis (MU, SNDK, TSM, STM), neoclouds (CRWV, NEBIUS), and bitcoin-miner→AI-datacenter/power names (CORZ, RIOT, APLD, IREN, CLSK, HIVE, Bitdeer, Bloom Energy)** — i.e. he *added to the same AI-infrastructure theme he already owned*, and let go of the semis hedge over it.

## How to read the options (and what the 13F can't tell you)
⚠️ **The 13F info table has no strike, no expiry, and no premium** (verified against the raw XML). It reports the **notional** (underlying value) and share count of **long** option positions only.
- Capital at risk in these long puts = **premium paid, which is not disclosed** — so the $9.82B notional overstates the economic footprint. The true cost/size of the hedge is **unknown** from this filing.
- Notional was ~2.2× the long-equity book ($8.46B puts vs $3.86B equity), but without strikes/deltas the actual protective ratio (and whether it was a partial or full hedge) **cannot be computed**.
- **Every put went to exactly zero shares** — a full close, not a roll (a roll preserves/adjusts share count). Only INFY ($5M, share count flat) is genuinely roll-vs-MTM ambiguous, and it's immaterial. TSM/BE calls were partial closes (shares −95% / −64%).

| Underlying | Type | Q1 notional | Q2 notional | Status |
|---|---|---:|---:|---|
| SMH / NVDA / ORCL / AVGO / AMD / MU / TSM / ASML / INTC / GLW | Put | $8.45B (sum) | $0 | all CLOSED |
| MU / SNDK / CRWV | Call | $0.95B (sum) | $0 | CLOSED |
| TSM | Call | $355M | $24M | −95% shares |
| BE | Call | $55M | $44M | −64% shares |
| INFY | Put | $7M | $5M | shares flat → roll-vs-MTM ambiguous |

## Forced or voluntary?
**The put-book removal is not evidence of a forced unwind.** Long puts are prepaid, defined-risk instruments — **they cannot be margin-called.** As the AI-semi complex rallied in Q2 (EODHD adj close Mar31→Jun30: SMH +71%, MU +242%, AMD +186%, INTC +216%, TSM +42%), the hedge simply lost value / became less relevant; letting it expire or selling it is a **normal, voluntary** disposition of a hedge, and the most it could have cost was the (undisclosed) premium.

**And there is no forced *equity* liquidation in the data** — the equity book grew +$16.3B, ~76% of it fresh buying, with continuing longs held (flat shares) and marked up. A fund being force-liquidated does not deploy ~$12B into new stock.

So on the "margin calls / forced liquidation" report:
- **A 13F reports only long positions and long options — never short sales or written options.** It therefore cannot *confirm or deny* that SA was short anything or ran leverage. What it *does* show is entirely long and defined-risk, with nothing in it capable of generating a margin call.
- If real margin calls occurred, they would have to originate in **leverage or short/written positions invisible to the 13F**, and a forced response would manifest as **equity selling by quarter-end — which is absent.** By 2026-06-30 the fund is bigger, longer, and unhedged.

**Bottom line:** hedged-long in Q1 → in Q2 he **dropped the hedge and pressed the long**, funding a ~$12.4B net equity build (with ~$4.0B of MTM on holds) in the AI-infrastructure theme. Nothing in the filing indicates forced selling; the put closure is a routine hedge removal, not a blow-up.

### Other limitations
- **No intra-quarter path** — start/end snapshot only; can't timestamp the hedge removal or show round-trips.
- **Unresolved tickers** (~$1.3B of Q2 equity: NEBIUS, IREN, WhiteFiber, Bitdeer, ASML-common) lack EODHD prices; counted as trading without price verification (new/adds, so directionally safe).
- **Simulated/stylized prices** (MU ~$1,154, SanDisk ~$2,274) are internally consistent with filed values but not real-world 2026 prices; conclusions hold within the dataset.
