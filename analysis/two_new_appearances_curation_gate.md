# Curation Gate — 2 New Appearances (2026-08-10)

Pipeline ran extract → aggregate → audit → reaudit. Timeline: **562 → 589 theses**
(+27). Reaudit set: **0 of the 27 new theses qualified** (max 4 tickers each < A's
≥5; no ETFs → not C; T3/T4's four mega-caps are named in-text → not orphan B).
Below is what needs an operator decision before returns (steps 7–8).

## The 2 appearances (thesis counts, attribution)
| Date | Appearance | Theses | Attribution | Clustered / Unclustered | Signal quality |
|------|-----------|--------|-------------|-------------------------|----------------|
| 2026-04-16 | Aria Networks launch — "MFU is the most important metric" (`MmNWwIYFBeI`) | 7 | Baker, featured speaker ✓ **clean** | 5 / 2 | Conceptual AI-infra (networking/tokenomics); **0 tickers** on any thesis |
| 2026-08-04 | Invest Like the Best — "Why the markets are pricing AI wrong" (`NGsi2PC4y68`) | 20 | Baker, interviewee (host O'Shaughnessy) ✓ **clean** | 7 / 13 | High-signal AI-infra; the July-2026 selloff / $700B credit-gap thesis |

Both are **solo Baker** appearances — no co-guest or interviewer contamination
(contrast the 6-new-appearances Heller House CFO problem). Full attribution to Baker.

---

## DECISION 1 — 4 substring false-positive clusters (regex keys lack word boundaries) ⚠️
These clustered ONLY because a theme's `keys` regex matched a substring inside an
unrelated word. Each would emit a **spurious signal event scored against that
theme's basket** (the basket is the theme's own tickers, not the thesis's), so
they are bad data if left in:

| Thesis | False theme | Key | Triggering word |
|--------|-------------|-----|-----------------|
| ARIA T1 | Google TPU competitive position | `tpu` | "ou**tpu**t" |
| ARIA T5 | DRAM / HBM memory bottleneck | `dram` | "**dram**atically" |
| ILTB T14 | Optical networking / interconnect | `cien` | "sample-effi**cien**t" |
| ILTB T3 | Scaling laws intact | `compute.*scale` | "compute … hyper**scale**r" (real words, wrong theme — T3 is hyperscaler compute *repricing*, not scaling laws) |

**Recommendation:** null all 4 via `cluster_overrides` (durable, doesn't delete the
extraction) before returns. I can add these overrides on your OK.

**Systemic flag (out of this task's scope):** these keys have no word boundaries,
so the same false positives (`tpu`←output, `dram`←dramatically, `cien`←efficient,
etc.) almost certainly contaminate older theses across the corpus too. Fixing that
means anchoring the regex keys (e.g. `\btpu\b`, `\bdram\b`) and re-running returns
for the whole corpus — a separate, larger change. Flagging, not doing it here.

---

## DECISION 2 — High-conviction Baker theses that did NOT cluster
Genuine strong Baker views the regex keys missed. Several map cleanly onto
**existing** themes whose keys just didn't fire:

| Thesis (conf) | Tickers | Best existing-theme home | Note |
|---------------|---------|--------------------------|------|
| ILTB T4 (high) | MSFT META AMZN GOOGL | *AI capex ROI positive* / hyperscaler-capex | **The core thesis** — hyperscaler OCF accelerating, market models Blackwell/Rubin at Ampere economics (the ~$700B credit gap) |
| ILTB T7 (high) | NVDA | *Nvidia GPU moat / CUDA ecosystem* | NVDA at 10-yr-low forward P/E; Baker says not over-earning |
| ILTB T9 (high) | NVDA | *Nvidia GPU moat / CUDA ecosystem* | Nvidia "credit wrapper + revenue share" model underappreciated |
| ILTB T1 (high) | NVDA | *AI bubble not happening* / *Broad AI bullish* | July selloff a sentiment overreaction, no fundamental basis |
| ILTB T5 (high) | NVDA | *Open source AI bullish for hardware* | OSS token-share growth is neutral-to-positive for infra |
| ILTB T8 (high) | MU HYNIX SAMSUNG | *DRAM / HBM memory bottleneck* | Memory LTAs structurally sticky (game-theoretic) |
| ILTB T2 / T15 (high/mod) | — | *Neoclouds as durable model* | T15 explicitly names Fireworks/Base10/Modal |
| ILTB T19 (high) | — | **none exists** | "Regulatory risk is the single biggest tail risk to AI" |

**Recommendation (conservative default):** leave unclustered — consistent with how
existing macro/meta theses are handled; extending keys retrofits scoring onto old
theses too and risks scope creep (same call as the 6-new gate's Decision 3).
**If you want signal from these,** the highest-value, lowest-risk additions are
`cluster_overrides` for **T4, T7, T9** into the existing themes above (targeted,
doesn't touch the corpus-wide regex). Your call.

---

## DECISION 3 — New theme(s)?
Two strong theses have no existing home:
- **ILTB T19** — AI regulatory / data-center-moratorium tail risk (no basket; hard to make tradeable — it's a macro risk, arguably no clean basket).
- **ILTB T17** — token-for-labor substitution (20–50% of comp) — thematic, no obvious ticker basket.

**Recommendation:** do **not** add themes for these (single-mention, no clean
tradeable basket). Leave as noise unless you want them tracked qualitatively.

---

## Applied-by-default (unless you object) — ticker hygiene
- **SPACEX, HYNIX (SK Hynix), SAMSUNG** in tickers_direct → **NO_DATA** (private /
  Korean listings), resolve gracefully to no return. Harmless; leave. SPACEX is
  already covered qualitatively by the Orbital / SpaceX-ecosystem baskets (T11/T12).
- **All other new tickers already in the 78-name UNIVERSE**: NVDA, MSFT, META,
  AMZN, GOOGL, MU, ASML, KLAC, LRCX, AMAT. **No UNIVERSE additions needed.**
- ILTB T11 correctly multi-assigned to Orbital + SpaceX-ecosystem; T13 to
  DRAM/HBM + AI-capex-ROI + Disaggregation (all legitimate).

## Also note before returns
- **Price cache is stale** (Known Issue #2: EODHD cache ends ~2026-06-29). Both new
  events (2026-04-16, 2026-08-04) need `theme_returns_v2 --force-refetch` and
  `build_repeat_mention_events --force-refetch` to extend the cache, or the recent
  horizons return INSUFFICIENT_DATA. The 2026-08-04 event will only have ~short
  horizons available (1m/1q) given today is 2026-08-10.

---

## ⏸ PAUSED — awaiting operator decisions on 1–3 above before running:
```
theme_returns_v2 --force-refetch
build_repeat_mention_events --force-refetch
```
Nothing downstream of reaudit has been run or written. No overrides applied yet.
