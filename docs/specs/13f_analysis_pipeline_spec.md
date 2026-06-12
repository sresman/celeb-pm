# 13F Analysis Pipeline — Project Specification

## Purpose

An investor-agnostic pipeline that parses SEC 13F-HR filings, reconstructs position histories, classifies portfolio changes, and computes filing-date-anchored returns. The system is designed for idea generation — identifying whether an investor's new entries and conviction adds are a useful signal — not for replicating portfolios or measuring PM skill.

## Target Investors (Initial)

| Investor | Fund | CIK | Filing History | Notes |
|----------|------|-----|----------------|-------|
| Gavin Baker | Atreides Management, LP | 0001777813 | Q4 2019 – Q1 2026 (~26 quarters) | Concentrated growth/tech, ~$5B AUM, top-10 ~58% |
| Leopold Aschenbrenner | Situational Awareness LP | 0002045724 | Q4 2024 – Q1 2026 (~5 quarters) | AI/compute thesis, heavy options use, ~$13.7B 13F value |

The system must be investor-agnostic: any CIK number in, structured output out.

---

## Layer 1: Filing Parser & Position Reconstruction

### 1.1 Data Ingestion

**Source:** SEC EDGAR, accessed via the EDGAR full-text search API or direct filing index.

**Filing format:** 13F-HR filings contain an XML information table (since ~2013) with one row per position. Each row includes:
- `nameOfIssuer` — company name
- `titleOfClass` — security type (e.g., "COM", "COM CL A")
- `cusip` — 9-character CUSIP identifier
- `value` — market value in thousands (USD)
- `sshPrnamt` — number of shares or principal amount
- `sshPrnamtType` — "SH" (shares) or "PRN" (principal)
- `putCall` — "PUT", "CALL", or absent (common stock)
- `investmentDiscretion` — "SOLE", "DEFINED", "OTHER"
- `otherManager` — if reported by another manager
- `votingAuthority` — sole, shared, none

**CUSIP-to-ticker mapping:** CUSIP is the primary identifier in 13F filings, not ticker. The pipeline needs a CUSIP-to-ticker lookup. Options:
- OpenFIGI API (free, reliable, batch capable)
- SEC EDGAR company search (CIK-to-ticker, but not CUSIP-to-ticker directly)
- Build a local mapping table from historical filings + manual corrections
- EODHD may support CUSIP lookup — check

**Important:** Tickers change (mergers, name changes, re-listings). The mapping must be point-in-time aware or at minimum flag when a CUSIP maps to a different ticker in different quarters.

### 1.2 Filing Metadata

For each 13F filing, extract and store:

```
filing_record:
  cik: str                    # Filer CIK
  fund_name: str              # From cover page
  period_of_report: date      # Quarter-end date (e.g., 2026-03-31)
  filing_date: date           # Date filed with SEC (this is when the public can see it)
  accepted_date: datetime     # EDGAR acceptance timestamp
  total_portfolio_value: int  # Sum of all position values (in $thousands)
  position_count: int         # Number of distinct positions
  amendment: bool             # Is this an amendment to a prior filing?
  amendment_type: str         # "restatement" or "adds new entries" (if amendment)
```

**Amendment handling:** If a filing is an amendment, it replaces the original for that quarter. The pipeline should use the most recent amendment, not the original.

### 1.3 Position Record Schema

For each position in each filing:

```
position_record:
  cik: str
  period: date                # Quarter-end date
  filing_date: date           # When filed
  cusip: str
  ticker: str                 # Resolved from CUSIP
  company_name: str           # From nameOfIssuer
  security_type: str          # "COMMON", "PUT", "CALL" (derived from titleOfClass + putCall field)
  shares: int                 # sshPrnamt
  value_thousands: int        # Market value in $thousands
  weight_pct: float           # This position's value / total portfolio value * 100
  investment_discretion: str  # SOLE, DEFINED, OTHER
```

**Options handling:** When `putCall` is present, the `value` field represents notional value of the underlying shares, NOT premium paid. This is critical for Leopold's portfolio where put notional can dwarf equity positions. The system must:
- Flag options positions distinctly from common stock
- Never add options notional to equity value when computing portfolio weights for comparison purposes
- Track options and equity separately in the position history
- For the "ideas" use case, options positions still matter (a new PUT position is a bearish signal, a new CALL position is a bullish one) but they should not distort weight calculations

**Proposed approach:** Compute two weight measures:
1. `weight_pct_reported` — position value / total 13F value (as SEC reports it, includes options notional)
2. `weight_pct_equity_only` — position value / total equity-only value (excludes all options positions from denominator)

For investors who don't use options (or use them minimally), these will be nearly identical. For Leopold, they'll diverge significantly.

### 1.4 Quarter-over-Quarter Diff & Change Classification

For each position, compare current quarter to prior quarter using the same CUSIP + security_type combination:

```
position_change:
  cusip: str
  ticker: str
  security_type: str
  
  # Current quarter
  current_shares: int
  current_value_thousands: int
  current_weight_pct: float
  
  # Prior quarter
  prior_shares: int | null      # null if NEW
  prior_value_thousands: int | null
  prior_weight_pct: float | null
  
  # Derived
  shares_delta: int             # current - prior
  shares_delta_pct: float       # % change in share count
  weight_delta_bps: float       # Change in portfolio weight in basis points
  
  # Classification
  change_type: enum             # See classification logic below
```

**Classification logic (applied in this order):**

| Classification | Rule | What It Means |
|---------------|------|---------------|
| `NEW` | CUSIP not in prior quarter | Fresh idea — highest signal for idea generation |
| `EXIT` | CUSIP was in prior quarter, not in current | They're done with it |
| `ACTIVE_ADD` | shares_delta_pct > +10% AND weight_delta > +50bps | Active conviction increase — they're buying more |
| `ACTIVE_TRIM` | shares_delta_pct < -10% AND weight_delta < -50bps | Active reduction — they're selling |
| `DRIFT_UP` | weight_delta > +50bps AND abs(shares_delta_pct) <= 10% | Price went up, they didn't act — passive signal |
| `DRIFT_DOWN` | weight_delta < -50bps AND abs(shares_delta_pct) <= 10% | Price went down, they didn't act — may indicate conviction (holding through weakness) |
| `HOLD` | Everything else | Noise, minor rebalancing |

**Edge cases to handle:**
- Stock splits: share count doubles but value stays ~same. Detect via shares_delta_pct ≈ +100% with value_delta ≈ 0%. Flag and don't classify as ACTIVE_ADD.
- Corporate actions (mergers, spinoffs): CUSIP changes. These will appear as EXIT + NEW for different CUSIPs. The pipeline should log these but flagging them automatically is hard — manual review may be needed for edge cases.
- Position appearing for first time as PUT or CALL (not common): classify as NEW with security_type noted.

### 1.5 Return Calculation

**Anchor: filing date, not quarter-end date.**

Rationale: Filing date is when the position becomes public knowledge. This is the date YOU could have acted on the information. Quarter-end date is when the investor held the position, but you didn't know that until the filing date.

For each position, compute:

```
return_record:
  cusip: str
  ticker: str
  change_type: str              # From classification above
  
  # Filing date prices
  filing_date: date             # This quarter's filing date
  price_on_filing_date: float   # Closing price on filing date
  next_filing_date: date        # Next quarter's filing date (or today if most recent)
  price_on_next_filing_date: float
  
  # Next quarter price range (between this filing date and next filing date)
  next_period_high: float       # Highest price in the window from this filing date to next filing date
  next_period_low: float        # Lowest price in same window
  next_period_high_date: date   # Date the high was hit
  next_period_low_date: date    # Date the low was hit
  
  # Forward returns (all measured from this filing date price)
  filing_to_filing_return_pct: float       # To next filing date close — the "snapshot" return
  filing_to_next_period_high_pct: float    # To best price in next period — "was there alpha in this idea?"
  filing_to_next_period_low_pct: float     # To worst price in next period — "what was the max drawdown?"
  
  # Entry estimate range (for NEW positions only)
  # Since we don't know when they bought during the entry quarter, bracket it
  entry_quarter_high: float           # Highest price during the quarter the position was opened
  entry_quarter_low: float            # Lowest price during the quarter
  best_case_entry_price: float        # Assumes bought at quarter low
  worst_case_entry_price: float       # Assumes bought at quarter high
  best_case_entry_return_pct: float   # Return from quarter low to next filing date price
  worst_case_entry_return_pct: float  # Return from quarter high to next filing date price
```

**Interpretation of the three forward return measures:**
- High return positive + filing-to-filing positive → idea worked and held its gains
- High return positive + filing-to-filing flat/negative → idea had a move but round-tripped (timing dependent)
- High return weak + filing-to-filing weak → idea didn't work
- Low return deeply negative even if filing-to-filing positive → volatile, hard to hold through the drawdown

**Multi-quarter holding returns:** For positions held across N quarters, also compute cumulative return from first filing date to last filing date (or current date). This captures the full value of a long-duration idea.

**Price data source:** EODHD (already integrated in the STW pipeline). Need:
- Daily close prices on specific dates (filing dates)
- Quarter high/low prices (for entry range estimation)
- Handle ticker changes, delistings, acquisitions (use last available price)

---

## Layer 2: Analytical Views

These are the views built on top of the raw data. Not all need to be built at once — start with View 1 and expand.

### View 1: New Ideas Feed

**Purpose:** Answer "are this investor's new entries worth paying attention to?"

For each `NEW` position across all quarters:

| Field | Description |
|-------|-------------|
| Quarter | When the position first appeared |
| Ticker | |
| Company | |
| Security Type | Common / Call / Put |
| Initial Weight | % of portfolio at entry |
| Best Case Entry Return | Assumes bought at quarter low, measured to next filing date |
| Worst Case Entry Return | Assumes bought at quarter high, measured to next filing date |
| Filing Date Return (1Q) | Return from filing date to next filing date |
| Return to Next Period High | Best the idea did in the next quarter — "was there alpha?" |
| Return to Next Period Low | Worst drawdown in the next quarter — "what was the risk?" |
| Filing Date Return (cumulative) | If held multiple quarters, total return from first filing to last |
| Quarters Held | How long they kept it |
| Max Weight Reached | Peak portfolio weight during holding period |
| Exit Quarter | When it disappeared (or "CURRENT" if still held) |

Sort by: initial weight descending (their biggest new ideas first).

Summary statistics at the bottom:
- Win rate: % of NEW entries with positive filing-to-filing return
- Average winner return vs. average loser return
- Median holding period for NEW entries
- % of NEW entries that became ACTIVE_ADD in subsequent quarters (i.e., they liked it enough to buy more)

### View 2: Conviction Tracker

All `ACTIVE_ADD` events, sorted by weight_delta descending.

Interesting cross-reference: for each ACTIVE_ADD, what was the position's return in the quarter BEFORE the add? Positive = adding to a winner (momentum). Negative = averaging down (contrarian conviction). Track the distribution — does this investor tend to add to winners or double down on losers? And which pattern produces better subsequent returns?

### View 3: Exit Signals

All `EXIT` events. For each:
- How many quarters was it held?
- What was the cumulative return during the hold?
- Was it a winner or loser when exited?
- Was the exit preceded by ACTIVE_TRIM in the prior quarter? (Gradual exit vs. abrupt exit)

### View 4: Survivors

Positions held for 4+ consecutive quarters without an ACTIVE_TRIM. These are the core conviction names. What do they have in common? (Sector, market cap, valuation profile at entry.)

---

## Technical Architecture

### Pipeline Steps

```
1. FETCH FILINGS
   Input: CIK number
   Process: Query EDGAR for all 13F-HR filings for this CIK
   Output: List of filing metadata + XML information table URLs

2. PARSE FILINGS
   Input: XML information tables
   Process: Extract all position records per filing
   Output: Normalized position records with filing metadata

3. RESOLVE IDENTIFIERS
   Input: CUSIPs from position records
   Process: Map CUSIP → ticker via OpenFIGI or local table
   Output: Position records enriched with tickers

4. COMPUTE DIFFS
   Input: Position records for consecutive quarters
   Process: Match on CUSIP + security_type, compute deltas, classify changes
   Output: Position change records with classifications

5. FETCH PRICES
   Input: Tickers + dates (filing dates, quarter date ranges)
   Process: Pull from EODHD
   Output: Price records

6. COMPUTE RETURNS
   Input: Position changes + prices
   Process: Filing-to-filing returns, entry range estimates
   Output: Return records

7. GENERATE VIEWS
   Input: All of the above
   Process: Aggregate into analytical views
   Output: CSV/JSON tables for each view
```

### Storage

Flat files (CSV or JSON) are fine for this scale. Each investor gets a directory:

```
/data/
  /atreides_management/
    filings.json          # Filing metadata
    positions.json        # All position records, all quarters
    changes.json          # Quarter-over-quarter diffs with classifications
    returns.json          # Return computations
    /views/
      new_ideas.csv
      conviction_adds.csv
      exits.csv
      survivors.csv
  /situational_awareness/
    (same structure)
```

### Dependencies

- Python 3.10+
- `requests` — EDGAR API calls
- `xml.etree.ElementTree` — 13F XML parsing
- `pandas` — data manipulation and output
- EODHD API (already have key from STW pipeline)
- OpenFIGI API (free, no key required for basic lookups) — for CUSIP-to-ticker resolution

### EDGAR API Notes

- EDGAR requires a User-Agent header identifying the requester (SEC policy): `User-Agent: CompanyName admin@email.com`
- Rate limit: 10 requests per second
- Filing index URL pattern: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=13F-HR&dateb=&owner=include&count=40&search_text=&action=getcompany`
- Alternatively, use the EDGAR full-text search API: `https://efts.sec.gov/LATEST/search-index?q=&forms=13F-HR&dateRange=custom&startdt={start}&enddt={end}`
- The actual information table XML is linked from the filing index page

---

## Design Decisions & Open Questions

### Confirmed Decisions

1. **Filing date anchored returns** — not quarter-end. We're measuring the value of the public information signal.
2. **Change classification by NAV weight, not position %** — a position doubling from 1% to 2% NAV doesn't matter. A position going from 3% to 6% does.
3. **50bps NAV threshold for meaningful changes** — tunable, but starting here. Below this is noise/drift.
4. **10% share count threshold for active vs. passive** — separates deliberate buying/selling from price-driven weight changes.
5. **Separate equity and options tracking** — never mix options notional with equity value for weight calculations.
6. **Best/worst case entry returns for NEW positions** — using quarter high/low since we don't know actual entry price.
7. **Three forward return measures** — filing-to-filing (snapshot), return to next period high (was there alpha), return to next period low (max drawdown). All three needed to fully characterize idea quality.
8. **Investor-agnostic design** — CIK in, structured output out. No hardcoded investor-specific logic.

### Open Questions (Decide During Build)

1. **CUSIP-to-ticker resolution strategy** — OpenFIGI is the cleanest option but need to test reliability for historical CUSIPs. May need a fallback lookup table.
2. **Stock split detection** — can we reliably detect splits from the data alone (share count doubles, value unchanged) or do we need an external corporate actions feed?
3. **Merger/spinoff handling** — when company A acquires company B and the CUSIP changes, this shows as EXIT(B) + NEW(A). Flagging these automatically requires a corporate actions database. Start with manual review, automate later if the volume justifies it.
4. **Options position aggregation** — if an investor holds both common stock AND calls on the same name, should the NEW/EXIT/ADD/TRIM classification consider them jointly or separately? Probably separately (different instruments, different signals), but worth discussing.
5. **Benchmark returns** — compute SPY return over the same filing-to-filing window, plus SPY next-period high/low. Adds minimal complexity and lets you see whether a NEW entry outperformed or just rode beta.

---

## Phase 1 Deliverable

The initial build should produce:
1. A working parser that ingests all 13F-HR filings for a given CIK
2. Position records for all quarters
3. Quarter-over-quarter diffs with change classifications
4. Filing-date-anchored returns with entry range estimates for NEW positions
5. View 1 (New Ideas Feed) as a CSV export

Test on both Atreides (26 quarters, no options complexity) and Situational Awareness (5 quarters, heavy options) to validate the schema handles both.
