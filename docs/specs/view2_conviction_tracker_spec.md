# View 2: Conviction Tracker — Spec

## Purpose

Surface every ACTIVE_ADD event as a signal row. The core question: when an investor adds to an existing position, what happens next? Secondary question: is adding to winners vs. averaging down on losers a different signal?

## Data Sources

All inputs already exist from the Phase 1 pipeline:
- `changes.json` — every quarter-over-quarter position change with classification, weights, share deltas
- `returns.json` — forward returns (filing-to-filing, next-period high/low, SPY benchmark) for every change event including ACTIVE_ADDs
- `positions.json` — for company name lookup

No new data fetching or pipeline changes required. This is a view module only.

## Output

`data/<slug>/views/conviction_adds.csv` + `data/<slug>/views/conviction_adds_summary.json` (same pattern as View 1).

## Row Definition

One row per ACTIVE_ADD event. If an investor adds to the same position in Q3 and Q5, those are two separate rows.

## Columns

| Column | Source | Description |
|--------|--------|-------------|
| quarter | change.period | Quarter when the add occurred |
| ticker | change.ticker | |
| company | positions lookup | |
| security_type | change.security_type | COMMON / CALL / PUT |
| is_option | derived | |
| weight_before_pct | change.prior_weight_pct | Position weight before the add |
| weight_after_pct | change.current_weight_pct | Position weight after the add |
| weight_delta_pct | change.weight_delta_bps / 100 | How much NAV weight they committed (in pct, not bps) |
| shares_delta_pct | change.shares_delta_pct | % increase in share count |
| prior_quarter_return_pct | Compute: price change on the position between prior filing date and this filing date | How the position performed in the quarter BEFORE the add. Positive = adding to a winner. Negative = averaging down. |
| add_type | derived from prior_quarter_return_pct | "ADDING_TO_WINNER" (prior return > 0), "AVERAGING_DOWN" (prior return <= 0), or null if unpriced |
| quarters_held_before_add | Count of consecutive quarters position existed before this add | How long they held before deciding to add |
| nth_add | Sequential count | Is this the 1st, 2nd, 3rd add to this position? |
| original_entry_quarter | The NEW event quarter for this CUSIP+security_type | When they first entered |
| cumulative_return_since_entry_pct | Return from original entry filing date to this add's filing date | How the position has done since they first bought it |
| filing_to_filing_return_pct | returns | Forward return from this add's filing date to next filing date |
| filing_to_next_period_high_pct | returns | Best the idea did in the next quarter after the add |
| filing_to_next_period_low_pct | returns | Worst drawdown in the next quarter after the add |
| excess_filing_to_filing_pct | returns | vs SPY |
| excess_next_period_high_pct | returns | vs SPY |
| excess_next_period_low_pct | returns | vs SPY |
| followed_by_exit | derived | Did the position EXIT in the next quarter? (add was a swing/catalyst trade) |
| followed_by_another_add | derived | Did another ACTIVE_ADD follow? (sustained conviction building) |
| still_held | derived | Is the position in the most recent filing? |
| priced | returns | Whether forward returns could be computed |
| cusip | change.cusip | |
| filing_date | change.filing_date | |

## Sort Order

Descending by weight_delta_pct (biggest conviction increases first), then by quarter descending.

## Summary JSON

```
{
  "total_adds": int,
  "priced_adds": int,
  "win_rate_pct": float,          // filing-to-filing > 0
  "avg_winner_return_pct": float,
  "avg_loser_return_pct": float,
  "avg_weight_delta_pct": float,  // average size of add
  
  // The key split
  "adding_to_winners": {
    "count": int,
    "win_rate_pct": float,
    "avg_return_pct": float,
    "avg_next_period_high_pct": float
  },
  "averaging_down": {
    "count": int,
    "win_rate_pct": float, 
    "avg_return_pct": float,
    "avg_next_period_high_pct": float
  },
  
  "pct_followed_by_exit": float,  // add was a short-term catalyst trade
  "pct_followed_by_another_add": float,  // sustained conviction
  "median_quarters_held_before_add": float,
  "pct_first_add": float,         // % that were the 1st add vs 2nd/3rd
  
  "notes": "..."
}
```

## Edge Cases

- **Position with no prior NEW in the dataset.** If the investor held a position before the first filing in our data, adds to it will have no `original_entry_quarter`. Set to null; `quarters_held_before_add` counts from the first filing where it appeared, `cumulative_return_since_entry_pct` computed from that first appearance.
- **Re-entries.** If a position was exited and re-entered, the add links to the most recent NEW, not the original one. Same hold-chain logic as View 1.
- **Multiple adds same quarter.** Not possible — there's one change record per (cusip, security_type) per quarter.
- **Prior quarter return for first-quarter positions.** If a NEW and ACTIVE_ADD happen in consecutive quarters, prior_quarter_return_pct is the return during the NEW quarter. If the NEW is the immediately prior quarter, this is straightforward. If there's a gap (NEW in Q1, HOLD in Q2, ADD in Q3), prior_quarter_return_pct is the Q2→Q3 return.
