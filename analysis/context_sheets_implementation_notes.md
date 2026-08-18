# Implementation notes — context sheets in `trigger_analysis.xlsx`

Added 10 context sheets + a two-manager Summary to `analysis/trigger_analysis.xlsx`
alongside the 6 existing (unchanged) Baker trigger sheets. Generator:
`tools/transcripts/build_trigger_workbook.py`. Run: `python tools/transcripts/build_trigger_workbook.py`.

Tab order: `Summary` → Baker context (Holdings, AI Basket, Baskets, Flows, Options, Exits+New)
→ Leo context (Holdings, Baskets, Flows) → Baker triggers (Ramp … RampBasket).

## Decisions / conventions

- **Decomposition = 13F-implied marks** (operator-approved). Price = `value_reported / shares`
  per position; `MTM = prior_shares·(P_q2−P_q1)`, `Trade = Δshares·P_q2`. Reconciles to the
  penny (`recon_gap == 0` on all 66 Baker rows; verified). NEW → all Trade; EXIT → all Trade =
  `−prior_value`; options → not decomposed (notional only).
- **`value_delta` recomputed locally** as `current_value − prior_value`. `changes.json` stores
  `None` for NEW, which would break the column's reconciliation with MTM+Trade.
- **Baker weights**: both `weight_pct_equity_only` (house-rule denominator; sums to 100% across
  COMMON) and `weight_pct_reported` (share of total book incl. options notional) shown.
- **AI basket (Sheet 2)**: membership via `trig.resolve_ai` (same taxonomy as the triggers);
  weight uses equity-only denominator → 43.4% for Q2 2026. SPCX is `ai:false` (Space/Orbital) so
  it is NOT in the AI basket even though it is 41.9% of equity. The AI-specific ramp did not fire
  in Q2 (self-funded rotation: sold Astera to fund Cerebras/CoreWeave), so there is no
  `ai_weight_current` row at 2026-08-14 in `13f_signal_triggers_clean.csv` — expected.
- **Flow-of-Funds basket attribution is single-basket** (first membership in `theme_baskets_v3`
  file order) so flows sum to the book. A ticker's full (overlapping) basket list is on the
  Baskets sheet, which intentionally lists a ticker under every basket it belongs to.
- **Thesis-to-action x-ref (Baker Flows)** = all three treatments: (a) latest ticker-tagged
  thesis text (date/confidence/summary from `thesis_timeline_v2_flat.json`), (b) heuristic
  ALIGNS/CHECK/NEUTRAL flag, (c) blank manual column. Matching is ticker-based
  (`tickers_direct`/`tickers_subject`); where no ticker-tagged thesis exists (e.g. Orbital/SPCX —
  SpaceX theses predate its ticker) the flag reads `manual`. Leo Flows has no in-repo thesis
  corpus → manual column only.
- **SpaceX callout (Summary, required)**: SPCX is a NEW $4.67B / 32.6% position that entered the
  13F via the Q2 2026 IPO (pre-IPO private holding → reportable security), not fresh market
  buying. Callout shows net trading AS-FILED ($4.0B) vs EX-SpaceX (−$0.67B → **net SELLER** once
  stripped). Ex-SpaceX, genuinely new capital went to SPCX + the QQQ hedge, not the AI book.
- **Leopold sheets** sourced entirely from `analysis/sa_q2_2026_mtm_vs_trading.csv` (already uses
  EODHD quarter-end prices; left as-is, `recon_gap` retained from that file). Basket map:
  `analysis/sa_theme_baskets.json` (NEW; operator's 3 named baskets verbatim + emergent ones;
  matches by ticker then company-name alias for unresolved-ticker positions).

## New artifacts
- `analysis/sa_theme_baskets.json` — Leopold ticker→basket map (hand-editable).
- `analysis/atreides_q2_2026_mtm_vs_trading.csv` — Baker decomposition, parity with the SA CSV.

## Iteration 2 (operator review fixes)

- **One basket per ticker.** The Baskets/Holdings/Flows sheets were classifying off
  `theme_baskets_v3.json` (many-to-many thesis/corpus map — NVDA is in 7 baskets), causing
  duplicated rows. Reverted to a single-valued assignment matching the prior trigger_analysis:
  `primary_basket()` = `baker_basket_overlay.json` (curated) → `ai_basket_reclassification.json`
  single bucket → position `theme` → "Unassigned". Each ticker now appears once; its other theme
  memberships show in an `also_in` note column. `analysis/baker_basket_overlay.json` (NEW) holds
  the curated primaries (NVDA→Nvidia GPU moat, MU→DRAM/HBM, SPCX→Orbital, etc.).
- **SPCX = IPO reclassification, not a buy.** `IPO_RECLASS_TICKERS = {"SPCX"}`; change_type
  `IPO_RECLASSIFICATION`, `mtm`/`trade` set to `None` so it is excluded from every net-buying/MTM
  total (Holdings decomp blank, Flows Orbital net-trade = 0, Exits+New breaks it out of NEW into
  its own section). Summary net-trading is ex-reclass (−$0.67B, net seller); the callout shows
  as-filed ($4.00B) vs ex-SpaceX and is sourced from `spcx_reclass_value`.
- **Allocation change on Holdings.** Added `wt_Q1%`, `wt_Q2%`, `Δwt_pp` (equity-only, from both
  quarters' positions), green/red shaded.
- **Baker Baskets readability.** Rewrote `sheet_baker_baskets`: one section per primary basket,
  section band with #held · $ · wt · net-trade, constituents sorted by size, blank separator,
  `also_in` note, largest basket first / Unassigned last. 46 unique rows, no duplication.
- **Leo baskets** (`sa_theme_baskets.json`): split crypto miners ("Crypto miners → AI/HPC") out of
  "AI datacenter / power" per operator; 7 baskets total.
- **theme_baskets_v3.json**: git forensics showed its uncommitted diff is the two-podcast pipeline
  run (added corpus `keys` + 4 new `MANUAL_2026AUG_SWEEP` baskets + em-dash re-encode); no existing
  ticker membership changed. Not touched by this work. Left as-is for the operator to commit.

## Iteration 3 (basket corrections + theme-allocation summary)

- **Overlay corrections** (`baker_basket_overlay.json`): META/AMZN/GOOGL collapsed into
  "Hyperscalers (quasi-index)" (cloud buyers, not picks-and-shovels); NVDA stays "Nvidia GPU moat"
  (it's a chipmaker). Added `primary_basket_by_cusip` for null-ticker positions: CREDO→AI/Datacenter
  Networking, INNIO→AI/Datacenter Power, NEBIUS→Neoclouds, WIX→Web/SMB SaaS, TABOOLA→AdTech,
  GlobalFoundries→Semiconductor Manufacturing, JFrog→Enterprise SaaS. `primary_basket()` now takes
  cusip and checks the by-cusip map after the by-ticker map.
- **Theme-allocation summary is now the PRIMARY view atop Baker Baskets**: one row per basket with
  wt_Q2%, wt_Q1%, Δpp (green/red), #held, net_trade — sorted by Q2 weight desc. Position detail
  moved below as secondary. Q1 basket weight includes since-exited names (so a fully-exited theme
  shows its drop); exits are themed via `data/ticker_classifications.json` + the cusip overlay, so
  there is no "Unassigned" bucket.
- **Equity/options separation fix** (house rule): exit rows only take an equity-only Q1 weight when
  security_type==COMMON, and the Baskets/Flows equity aggregations skip option exits. An option exit
  can carry the underlying's cusip, which was double-counting that common's weight (Σ Q1 was 108.5%);
  now Σ Q2 = Σ Q1 = 100.0%. Option exits remain on the Exits+New / Options sheets.

## Iteration 4 (denominator switch: total-book → thesis-investable equity, ex-IPO-reclass)

- **Problem**: the trigger sheets weighted against TOTAL BOOK (reported weight, incl. options
  notional + SPCX). With SPCX permanently ~33% of book, every AI subtheme's weight was compressed
  below the fixed 4%/2% thresholds — worsening each quarter as SPCX's mark rises. `Cross4pct`,
  `Cross2pct`, `NewPosition 2%`, and `Ramp` (net_buying_pct) were all on this compressed basis.
- **Fix (operator "option 2")**: denominator = **thesis-investable equity = Σ COMMON value ex
  `IPO_RECLASS_TICKERS` ({SPCX})**, applied across ALL periods (also removes options-notional
  compression throughout; makes the "equity weight" docstring true). Weights sum to exactly 100%
  ex-SPCX per period.
  - `build_13f_analysis.py`: `ex_reclass_denoms()` + rescale in `annotate_common` (drop reclass
    rows, weight × total_book/ex_equity); `compute_net_buying` denominator → ex-reclass equity;
    `trigger_new_position` sources weight from the rescaled `common` row. Regenerates
    `13f_signal_triggers_clean.csv`.
  - `build_trigger_workbook.py`: `ex_reclass_scale_by_fd()` rescales `build_lookups` forward-alloc
    tracking; context-sheet weights (Holdings Q1/Q2/Δ, AI basket + trailing history, Baskets
    summary, Summary) on the same basis; **SPCX shown as a labeled `[memo]` row** (% of TOTAL
    equity) excluded from the thesis denominator so thesis baskets sum to 100%.
- **Why the Δ is not a denominator artifact**: the thesis book GREW Q1→Q2 ($4.10B → $6.48B ex-SPCX),
  so flat-dollar names show negative Δ — the increase/decrease signal is preserved. MU 6.3%→12.7%
  (Δ+6.4) is a real doubling of conviction within the investable book (vs the SPCX-diluted +1.1pp).
- **Trigger event deltas** (total-book → ex-reclass): NEW_POSITION 32→**39** (decompression — small
  new buys now clear 2%), CROSS_2PCT 28→**31**, CROSS_4PCT 22→**18** (uniformly higher weights cross
  the 4% line earlier and stay above, so fewer distinct re-crossings), SUBTHEME 15→15, RAMP 11→11.
- Legacy `generate_13f_triggers.py` (imported only for helpers; not the workbook's source) docstring
  annotated to point at `build_13f_analysis.py` as the authoritative ex-reclass generator.
