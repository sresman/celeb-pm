# Handoff — 2026-06-11 — Prompt 2 (PARSE FILINGS) complete

## What Prompt 2 delivered
Pipeline step 2: info-table XML → normalized `PositionRecord`s + filled filing totals + dual weights, plus amendment-type refinement and positions storage.

- **`celebpm.parser`** (NEW): `select_infotable_filename`, `locate_and_fetch_infotable` (the SOLE info-table fetch site), `parse_positions_from_xml` (PURE), `refine_amendment_type` (reuses threaded `index_payload`). Namespace-robust local-name matching; one record per `(cusip, security_type)`; float-tolerant numeric parse; skip-with-count for junk rows; DiscoveryError abort for broken XML / unusable index.
- **`celebpm.models.PositionRecord`** (frozen, kw_only): `value_reported` (SD-3), dual weights (`weight_pct_reported`, `weight_pct_equity_only`), equity-only invariant (options ⇒ equity weight None). `FilingRecord` gained `total_equity_value: int | None = None` (None-tolerant). New numeric helpers reject bool.
- **`celebpm.storage`**: `write_positions` (sorts by `(period, cusip, security_type)`, atomic, path-safe) / `read_positions` (missing → DiscoveryError). `_safe_filings_path`→`_safe_path` refactor (behavioral no-op).
- mypy strict clean (21 files); pytest 150 passed (69 prior + 81 new). `tests_live/test_parse_live.py` added (NOT in CI).

## How to run discovery + parse so far
```python
from celebpm import constants, storage
from celebpm.discovery import discover_filings, latest_filing_per_period
from celebpm.edgar_client import EdgarClient
from celebpm.parser import (
    locate_and_fetch_infotable, refine_amendment_type, parse_positions_from_xml,
)

client = EdgarClient()                      # ONE shared client, reused across all CIKs
slug = "atreides_management"
records = latest_filing_per_period(discover_filings("0001777813", client))  # provisional selector

updated_filings = []
all_positions = []
for filing in records:
    xml_text, index_payload = locate_and_fetch_infotable(filing, client)    # the ONE get_json
    if filing.amendment:
        filing = refine_amendment_type(filing, client, index_payload)       # reuse payload; no get_json
    updated, positions = parse_positions_from_xml(filing, xml_text)         # PURE; refined type present
    updated_filings.append(updated)
    all_positions.extend(positions)

# Incremental contract: dedup-by-accession union, then write (write_positions sorts).
try:
    history = storage.read_positions(slug)
except Exception:  # DiscoveryError on first run -> empty history
    history = []
reparsed = {p.accession_number for p in all_positions}
union = [p for p in history if p.accession_number not in reparsed] + all_positions

storage.write_positions(slug, union)        # -> data/<slug>/positions.json (sorted)
storage.write_filings(slug, updated_filings) # re-persist with total_portfolio_value/position_count/total_equity_value
```
Order matters: `refine_amendment_type` runs BEFORE `parse_positions_from_xml` so the ADDS-totals WARN fires and the refined `amendment_type` is on the FilingRecord that parse updates. `index.json` is fetched EXACTLY ONCE per filing.

## Exact next step — Prompt 3 (CUSIP → ticker resolution)
1. Read `positions.json` (`storage.read_positions`), collect distinct `cusip`s.
2. Resolve CUSIP → ticker via **OpenFIGI** (free tier, no key for basic lookups; endpoint/limits → constants). Use `title_of_class` to disambiguate share classes (COM vs COM CL A).
3. Fill `PositionRecord.ticker` via `dataclasses.replace` (records are frozen).
4. Re-write `positions.json` via `storage.write_positions` (same atomic round-trip; re-sorts).
- Do NOT mix in EODHD/prices (Prompt 5). Keep CUSIP as the primary join key; ticker is display/convenience.

## Carried-forward risks / flags
- **SD-2 (value units) — OPERATOR DECISION STILL OPEN.** Value stored as-reported; thousands-vs-dollars boundary (~Jan 2023) not encoded. Weights/returns are ratio-based so unaffected; only absolute dollars differ. See `spec-deviations.md` SD-2 (pick a/b/c).
- **Deferred amendment merge + period supersession.** Prompt 2 only refines `amendment_type` per filing. Until the consuming prompt lands the merge: treat UNKNOWN amendments as RESTATEMENTS (safe — never double-counts); only explicit-ADDS is additive. `latest_filing_per_period` remains provisional.
- **Equity/options separation is absolute.** Never mix options notional into equity weight denominators. PUT/CALL carry `weight_pct_equity_only = None` (not 0.0). Prompt 4 must decide which weight feeds bps thresholds and handle the None equity-weight for options.
- **Implied-price caveat.** Do NOT derive price from `value_reported / shares` until SD-2 is resolved (1000× risk). Also, the rare SH/PRN majority-drop records carry value+shares from the kept majority rows only — implied price reflects that subset.
- **`total_equity_value = None` backfill.** Pre-Prompt-2 filings re-persisted without a re-parse carry None; downstream must tolerate None or a full re-parse backfills it.
- **Pre-2013 / paper filings** have no XML info table → `select_infotable_filename` raises DiscoveryError; the caller should catch+skip with a WARN (target investors are recent, so not special-cased).
- **End-to-end orchestrator/CLI + its integration test** are deferred to a later prompt; Prompt 2 ships the three functions + the documented orchestration only.
