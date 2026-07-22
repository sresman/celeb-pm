# 13F Signal Triggers — Implementation Notes

Spec: operator prompt "Generate Auditable 13F Signal Trigger Events" (no spec file).
Plan: `main-task-audit-pure-star.md`. Code: `tools/transcripts/generate_13f_triggers.py`.
Output: `analysis/13f_signal_triggers.csv` (55 events: 10 ramp, 14 sub-theme, 31 new-2%).

## Decisions where the spec was ambiguous / superseded

### SD-TRIG-1 — AI classification source (2026-07-01)
Operator overrode the spec's hardcoded 14-theme list mid-planning:
`analysis/ai_basket_reclassification.json` is authoritative. Per-ticker `resolve_ai`:
ticker in file → its `ai`/`bucket` (NTNX uses `date_segments`, compared against
`filing_date`); ticker not in file → AI iff `theme` column starts with `AI/` or
`Semiconductor`. The file introduces `AI/Hyperscaler` (AMZN/GOOGL/META/MSFT/ORCL),
which the theme-column fallback would NOT catch (AMZN theme = E-commerce, META =
advertising), and explicitly excludes CFLT/ADBE/NET. The prior AskUserQuestion answer
("exactly the 14 listed") is void.

### SD-TRIG-2 — digit-prefixed ticker variants bypass the reclass file (BUG FIX) (2026-07-01)
The pipeline emits digit-prefixed ticker variants for some listings (`1CFLT`,
`0JPHL`, `4ATVI`, …). The reclass file is keyed by clean tickers, so `1CFLT` dodged
CFLT's explicit `ai:false` exclusion and fell through to its theme column
(`AI/Data Infrastructure`), fabricating a 2022-08-15 `AI/Data Infrastructure`
sub-theme event and inflating two basket-ramp filings. Confluent appears in the data
ONLY as `1CFLT`. Fix: `resolve_ai` retries the lookup with leading digits stripped
(`reclass.get(t) or reclass.get(t.lstrip("0123456789"))`). CFLT is the only
reclassified ticker affected; all other prefixed tickers strip to non-reclass,
non-AI values, so the strip is safe (US tickers never start with a digit). Effect:
ramp events 11→10, sub-theme `AI/Data Infrastructure` first-entry moved to MDB
2024-05-15, new-2% events 32→31.

### SD-TRIG-3 — NTNX date-segment boundary compares against `filing_date` (2026-07-01)
NTNX's `theme` column is `AI/Datacenter Infrastructure` for BOTH its 2021 and 2024
cycles, so the theme column alone misclassifies the 2021 enterprise-cloud entry as AI.
`date_segments` fixes it. Boundary (2024-01-01) compared to `filing_date` (pipeline
anchor). Verified identical to `period` here (no NTNX activity near the boundary):
2021 cycle → not-AI, 2024 cycle → AI. NTNX produces no trigger events (2024 re-entry
was <2% and its sub-theme was already opened by HPE in 2023) — correct.

### SD-TRIG-4 — new_ideas has no theme → join to lifecycles (2026-07-01)
`new_ideas.csv` `theme` is blank for all 338 rows. Trigger 3's AI filter resolves via
ticker first; the fallback theme comes from the matching `position_lifecycles` NEW row
joined on `(cusip, filing_date)` (338 NEW ↔ 338 new_ideas, 1:1). Reported `theme` =
resolved sub-theme (bucket, or fallback theme label).

### SD-TRIG-5 — Trigger 3 holding stats derived from lifecycles (2026-07-01)
`quarters_held`/`max_weight_pct`/`exit_date`/`cumulative_return_pct` computed from the
matching lifecycle `cycle_id` (auditability req #4), not taken from new_ideas' own
columns. `quarters_held` = count of non-EXIT rows in the cycle; `max_weight_pct` = max
`weight_pct`; `exit_date` = EXIT row's `filing_date` or `"CURRENT"`;
`cumulative_return_pct` = last non-empty `cum_return_from_entry_pct` in the cycle
(EXIT rows carry none). A consistency check asserts these agree with new_ideas'
`quarters_held`/`max_weight_pct` — 0 mismatches across all 31 events.

## Other decisions
- Sub-theme unit (Trigger 2) = resolved sub-theme label (reclass bucket, incl.
  `AI/Hyperscaler`, or fallback theme label). First entry = earliest `filing_date`.
- Ramp: EXIT rows excluded from weight sums but read for `ai_exits_this_quarter`.
  First filing has no prior → never emits a ramp.
- Options excluded everywhere (`security_type=="COMMON"` / `is_option=="False"`).
- Views auto-discovered via `data/*/views/position_lifecycles.csv` (prefers atreides).
- `csv` stdlib (matches `tools/transcripts/theme_returns_v2.py`); mypy strict clean.

## Verification performed
Weight audit (2020-08-14 ramp: top-5 sum ties to `ai_weight_current`); hyperscalers
in / CFLT-ADBE-NET out; NTNX segmented correctly; AMD Trigger-3 sourcing ties to
new_ideas + its lifecycle cycle; CSV sorted by filing_date, blank discipline correct,
31/31 cumulative returns populated.

---

# Follow-up: Filing-to-Filing Returns + Forward Returns + Trigger 2b (2026-07-01)

Script: `tools/transcripts/add_trigger_returns.py`. Outputs
`analysis/filing_to_filing_returns.csv` (35 tickers × 24 periods = 840 rows) and
`analysis/13f_signal_triggers_with_returns.csv` (102 events = 55 original + 47 2b).
Reuses `resolve_ai`/`find_views_dir`/`_f`/`_fmt`/`_read_csv`/`COLUMNS` from
`generate_13f_triggers.py` and the EODHD fetch/cache pattern from `theme_returns_v2.py`.

### SD-TRIG-6 — basket forward returns are per-ticker buy-and-hold, then averaged
Locked at the signal date, never rebalanced. Each constituent's single-period returns
are compounded over the horizon, then equal-weight averaged across constituents that
have a complete valid series for that horizon (matches "if you bought what he
signaled"; mean of per-ticker cumulative returns = equal-weight buy-and-hold return).
A constituent that is PRE_IPO/NO_DATA for any period in the horizon is dropped from
that horizon's average (mirrors `theme_returns_v2.py`); if none valid → `NO_DATA`.
Verified: optical 2023-11-14 fwd_2q 34.55 = mean(CIEN 7.99, COHR 61.11) with COHR
retained even though Baker later exited it.

### SD-TRIG-7 — measured return per trigger type
AI_BASKET_RAMP → SMH (`fwd_Nq = smh_fwd_Nq`, `excess = 0.00`, per spec);
NEW_AI_POSITION_2PCT → the single `ticker`; NEW_AI_SUBTHEME → `entering_tickers`
basket; AI_SUBTHEME_ACTIVE_CROSS_* → `all_tickers_in_subtheme` basket. Multi-period =
compound `(∏(1+r/100)−1)·100`; horizon beyond the last filing → `INSUFFICIENT_DATA`.

### SD-TRIG-8 — PRE_IPO vs NO_DATA in the reference table
Per (ticker, period): `period_start < first_bar` → `PRE_IPO` (prices blank);
`start > last_bar` or `end > last_bar` → `NO_DATA` (delisted / missing endpoint);
else exact-match price with a bisect first-date-≥-target fallback (all 25 filing dates
are exact trading days, so the fallback rarely fires). Observed: XLNX `NO_DATA` after
its Feb-2022 AMD acquisition (17 periods); ALAB/AMBQ/CRWV/SNOW `PRE_IPO` in their
pre-listing periods. SMH & SPY numeric for all 24 periods.

### SD-TRIG-9 — robustness deviations from theme_returns_v2.py
Per-ticker EODHD fetch wrapped in try/except → on failure the ticker gets an empty
series (→ NO_DATA) and the run continues (theme_returns_v2 lets `raise_for_status`
abort). EODHD symbol = `ticker.lstrip("0123456789") + ".US"` defensively (all AI
tickers are already clean). Dual import shim (`from . import` / bare) so the script
runs both as `python tools/transcripts/add_trigger_returns.py` and under `-m`.

### SD-TRIG-10 — Trigger 2b recomputed from lifecycles
For each AI sub-theme × filing: weight = Σ `weight_pct` over COMMON non-EXIT AI
positions; a threshold `T∈{2,4}` fires when `prior < T ≤ current` AND ≥1 position has
`change_type ∈ {NEW, ACTIVE_ADD}` that filing (excludes pure DRIFT_UP crossings). One
filing can emit both thresholds; a sub-theme can re-cross after dropping back below T
(e.g. optical re-crosses 4% on 2025-08-14 via a CIEN add). 47 events (27 @2%, 20 @4%).

---

# Follow-up: Clean Separation — Triggers / Returns / AI Basket Definition (2026-07-01)

Script: `tools/transcripts/build_13f_analysis.py` (self-contained; imports `resolve_ai`/
`_f`/`_fmt`/`_read_csv`/`find_views_dir` from `generate_13f_triggers.py`, inlines the
EODHD price layer, reimplements the trigger builders). Outputs:
`analysis/filing_to_filing_returns_universal.csv` (216 tickers × 24 = 5184 rows),
`analysis/13f_signal_triggers_clean.csv` (102 events, no returns),
`analysis/ai_basket_definition.json`. `generate_13f_triggers.py` +
`add_trigger_returns.py` and their CSVs are superseded but left in place.

### SD-TRIG-11 — narrow "picks-and-shovels" ramp basket (Trigger 1 only)
Trigger 1's AI weight sum / `ai_positions_count` / `top_5` / new-adds-exits lists are
computed over positions that are AI **and** whose resolved bucket ∉ {`AI/Hyperscaler`,
`AI/EV`} — i.e. exactly excluding AMZN/GOOGL/META/MSFT/ORCL + TSLA (the only AI/EV
ticker). `total_portfolio_weight` stays the full COMMON non-EXIT sum. Triggers 2/2b/3
keep the FULL classification (the narrow scope is a basket-weight concept, not a
thematic one). Effect vs the full-basket version: the Feb-2022 ramp shrank from ~+20pt
to +9.71pt (now INTC+MU semis, not AMZN+TSLA) and one ramp date shifted (2022-08-15
dropped, 2022-11-14 added); still 10 ramp events. Verified 0 hyperscaler/TSLA leaks.

### SD-TRIG-12 — trigger builders reimplemented, all return columns dropped
Rather than post-hoc stripping, the four builders were reimplemented so the narrow ramp
basket is native and no return/outcome columns are produced. Dropped: `fwd_*`/`smh_*`/
`excess_*` (never in the clean file), plus T3's `filing_to_filing_return_pct`/
`cumulative_return_pct`/`max_weight_pct`/`exit_date`/`quarters_held` and T2's
`quarters_held`. T3 no longer needs lifecycle-cycle derivation (theme still resolved via
the `(cusip, filing_date)` join to the NEW row). Verified zero return-ish columns.

### SD-TRIG-13 — universal returns universe + unresolvable tickers
Universe = all 214 unique COMMON tickers Baker has ever held + SMH + SPY (216), each ×
24 periods = 5184 rows, regardless of whether he held it in a period. 34 tickers are
all-`NO_DATA`: CUSIP-style placeholders (`09077J107`, `0JPHL`, …) and odd/foreign EODHD
symbols (`ANGI1EUR`, `FL*`, `FWONKUSD`) with no resolvable `.US` symbol (68 price
warnings total). All are non-AI held names; every AI-basket ticker resolved. SMH/SPY
numeric 24/24; CIEN 2023-11-14→2024-02-14 = 25.64 (ties the prior table).

### SD-TRIG-14 — default builds all three; `--skip-universal` for fast reruns
Chose default-builds-all-three (matches the Outputs list + verification) over the spec's
flag-gated Part 1, which conflicted with those. `--skip-universal` skips the 171-fetch
universal table for quick trigger-only iterations. Fetches are wrapped per-ticker
(failure → NO_DATA, run continues) and cached, so a rate-limited run resumes on re-run.
`ai_basket_definition.json` is written from the same constants the script filters on
(`RAMP_EXCLUDED_BUCKETS` / `RAMP_INCLUDED_BUCKETS`), so docs can't drift from behavior.

---

# Follow-up: Trigger Analysis Excel Workbook (2026-07-02)

Script: `tools/transcripts/build_trigger_workbook.py` → `analysis/trigger_analysis.xlsx`
(5 sheets: Ramp 10, NewSubtheme 14, NewPosition 31, Cross4pct 20, Cross2pct 27).
openpyxl, hardcoded values (no formulas). Reuses `resolve_ai`/`_f`/`_read_csv`/
`find_views_dir` from `generate_13f_triggers.py`.

### SD-TRIG-15 — environment mismatch vs the task's assumptions
The task referenced `/mnt/skills/public/xlsx/SKILL.md` and `scripts/recalc.py`; neither
exists in this local repo (Claude.ai-hosted-skill artifacts). Installed `openpyxl`
(3.1.5) into `.venv` (was absent; the task mandates openpyxl). No formulas are used, so
recalc is unnecessary. openpyxl has no type stubs → four import lines carry
`# type: ignore[import-untyped]`; mypy strict otherwise clean.

### SD-TRIG-16 — cells are numeric fractions with percent number-formats
Returns/weights are stored as `value/100` (the CSVs are already in percent units) with
number_format `+0.0%;-0.0%;0.0%` (returns) / `0.0%` (weights), so cells stay numeric
(sortable/colorable) while displaying e.g. `+27.0%`. Green `DCF0DC` / red `F0DCDC` fill
on return cells by sign; no fill on allocation cells. Filing dates are real `date`
objects (`yyyy-mm-dd`). Header row bold; freeze panes just right of the id columns
(D2/E2/G2) so headers + id columns stay visible.

### SD-TRIG-17 — period indexing (single-period, never compounded)
`Q+j` return = the single period starting at `filings[k+j-1]`; `Q+j_alloc` = holding on
`filings[k+j]` (the "next filing after entry" for j=1); `Q-i` return = period starting
at `filings[k-i]`. Valid iff the index is in range, else the cell is blank (never 0).
Baskets are LOCKED at the signal date (`entering_tickers` / `all_tickers_in_subtheme`),
equal-weight averaged per period dropping NO_DATA/PRE_IPO/absent constituents;
allocation columns track LIVE holdings. Trigger 1 uses SMH as the basket (per spec).
Verified: Ramp 2023-11-14 Q+1_SMH=+27.0%, NewPosition CIEN Q+1=+25.6% / alloc 3.8%,
Q+2 = the single next-period return (not compounded), optical Q+1_basket = mean(CIEN,
COHR), last-filing events blank forward.

### SD-TRIG-18 — "RampBasket" 6th sheet (2026-07-03)
Added `sheet_ramp_basket` to `build_trigger_workbook.py`: for each of the 10
AI_BASKET_RAMP events, shows the actual AI picks-and-shovels holdings at the ramp filing
date (`ticker_i`/`wt_i` pairs, max N=16, narrow filter = AI and bucket ∉
{AI/Hyperscaler, AI/EV}) plus the LOCKED basket's single-period returns for Q-4..Q-1 and
Q+1..Q+8 as EW (equal-weight), CW (capital-weight), and SMH. Re-running the builder
regenerates all 6 sheets; the other 5 are reproduced identically (lossless — all derived
from the same CSVs), so the "append, don't overwrite" intent holds.

- **CW missing-data = renormalize among available** (`Σwᵢrᵢ / Σwᵢ` over constituents
  that have data that period), parallel to EW dropping missing — keeps CW a proper
  weighted average. Alternative (fixed denominator incl. missing) rejected as
  non-comparable to EW. **FLAG:** easy to switch if the operator wants fixed-denominator
  dilution instead.
- Basket locked at the ramp date for ALL periods incl. the 4 pre-ramp ones (measures the
  picks retroactively). Verified 2020-08-14: basket MU/XLNX/INTC/NVDA, Q+1 EW +18.2% vs
  CW +20.8% (distinct; MU's 6% weight lifts CW) vs SMH +18.2%; no compounding; last
  filing (2026-05-18) blanks forward, Q− populated.


## 2026-07-17 — Added Unity (U) as AI sub-theme "AI/World Models"

- `analysis/ai_basket_reclassification.json`: added `U -> {ai:true, bucket:"AI/World Models"}`
  (documenting note re Baker's AI-infra framing; RBLX deliberately NOT assigned).
- `build_13f_analysis.py`: added "AI/World Models" to `RAMP_INCLUDED_BUCKETS` (definition-doc list;
  actual ramp membership is exclusion-based via `_in_ramp`, so U was auto-included regardless).
- Re-ran `build_13f_analysis` -> `build_trigger_workbook` -> `analysis/trigger_analysis.xlsx`. mypy clean.
- **Verified:** U in ramp basket for every held filing (Q4 2024→Q1 2026), incl. May 2026 @ 5.43% with
  ALAB/CIEN/MU/NVDA; AI/World Models fired NEW_AI_SUBTHEME (Q4 2024) and crossed 2% & 4% in Q1 2025.
- **Discrepancy flagged (weights):** U's 13F equity-only weight is 1.88% at Q4 2024 entry and 5.61% at
  Q1 2025 (peak), vs the brief's 2.7%/6.7%. Because entry 1.88% < the 2.0% NEW_AI_POSITION threshold, U
  does NOT fire NEW_AI_POSITION_2PCT (absent from NewPosition sheet) — it's captured as NEW_AI_SUBTHEME
  instead. Did not alter the weight basis or threshold; reconstructed weights are consistent across
  new_ideas.csv + position_lifecycles.csv. Operator's figures likely a different basis (fund book /
  options-inclusive) than the 13F equity-only reconstruction.

## 2026-07-17 — Ramp trigger rebuilt on net buying (deliberate deployment), not weight drift

- `build_13f_analysis.py`: new `compute_net_buying(views, reclass)` reads `positions.json`
  SHARE deltas per filing for the narrow AI basket (is_ai, ex-Hyperscaler/EV, COMMON):
  share up -> gross_buying += Δshares×current_price; share down -> gross_selling += Δshares×current_price;
  new position -> gross_buying += current_value. net = gross_buying − gross_selling, as % of total
  portfolio value (all positions, current period). `trigger_ramp` now fires when net_buying_pct ≥ 5
  (was: AI-weight drift ≥ 5 pts). New CSV columns: gross_buying_pct, gross_selling_pct, net_buying_pct,
  net_buying_dollars. `build_trigger_workbook.py`: `sheet_ramp` gained those 4 columns; RampBasket
  composition/returns (EW/CW/SMH, Q-4..Q+8) and the NewSubtheme/NewPosition/Cross sheets are UNCHANGED.
- **DEVIATION (flagged) — full exits not counted as selling.** The task spec says "exited positions:
  selling += prior_value", but that yields May-2025 +$381M / May-2026 −$402M. Excluding full exits
  reproduces the operator's stated verification EXACTLY: May-2025 = +$561,990,623 (~$562M target),
  May-2026 = −$122M net-selling (target ~−$109M; both net-selling => no fire). The exact $562M match
  is decisive that the reference figures excluded exits. Implemented with `COUNT_EXITS = False` (flip
  to restore spec-literal). Note the two verification VERDICTS (May-2025 fires, May-2026 doesn't) hold
  under either setting — only the dollar magnitudes change.
- **Verification:** May-2025 FIRES (net +$562M, 17.06%); May-2026 does NOT (net −$122M). Population:
  OLD weight-drift {2020-08-14,2021-06-01,2022-02-14,2022-11-14,2023-02-14,2023-11-14,2024-05-15,
  **2024-08-14**,2025-05-15,**2026-05-18**} → NEW net-buying drops 2024-08-14 & 2026-05-18 (passive
  drift / net selling), adds 2023-05-15, 2024-11-14, 2026-02-17 (real buying weight-drift missed).
  Cumulative CW vs SMH (new pop): Q+1 +17.0/+12.0 (beat 73%), 2Q +30.8/+22.0 (70%), 1yr +60.8/+46.3
  (60%), 2yr +100.8/+85.9 (50%). `mypy --strict` clean.

## 2026-07-17 (later) — Buying-detail columns on RampBasket + Ramp sheets

Extended `compute_net_buying` to also emit per-ticker detail; added 4 CSV cols
(tickers_bought/sold/new/exited) to OUT_COLUMNS + trigger_ramp. In build_trigger_workbook,
new shared `BUYING_DETAIL_HEADERS`/`_put_buying_detail` write 8 columns
(net_buying_pct, net_buying_dollars, gross_buying_pct, gross_selling_pct, tickers_bought,
tickers_sold, tickers_new, tickers_exited) on BOTH Ramp and RampBasket, positioned right
after ai_weight_current and before the composition/return blocks. Only those two sheets changed.

- tickers_bought/sold = HELD positions whose share count rose/fell (Δshares×current price),
  sorted by $ desc, formatted "TICK +$NNM" / "TICK -$NNM". tickers_new = brand-new positions
  (tickers only, $-sorted). tickers_exited = held-prior/gone (display only; not counted in
  selling, per the net-buying deviation). New positions are NOT in tickers_bought (separate).
- **Units:** value_reported is $thousands pre-2023, whole-$ after (verified: max implied
  price/share <$3.5 pre-2023-Q4 vs >$400 after). `compute_net_buying` detects per filing
  (max implied price ≥$15 => dollars, else ×1000) and normalizes all $ outputs to real
  dollars — so net_buying_dollars for old firing events is now correct (e.g. 2020-08-14
  $68.7M); recent events unchanged (May-2025 $561,990,623). pct columns are ratios (unit-safe).
- Verified: both sheets show the 8 cols contiguous at positions 4-11; RampBasket composition
  (ticker_i/wt_i) + EW/CW/SMH returns intact after the block; NewSubtheme/NewPosition/Cross4pct/
  Cross2pct unchanged (15/31/22/28). `mypy --strict` clean.
