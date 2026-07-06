# View 3 — Position Lifecycle — Implementation Notes

Append-only log of decisions, deviations, tradeoffs, and open questions. Newest section at the
bottom (CLAUDE.md spec-workflow requirement).

---

## 2026-06-24 — initial build (builder + writer + fundamentals fetch + pipeline/build_views wiring)

**What was built.** View 3 reshapes the existing `changes.json` + `returns.json` (1:1) into a
single `data/<slug>/views/position_lifecycles.csv` — one row per `(cusip, security_type)` per
quarter held, grouped into entry→exit cycles. Sector/industry come from a new, cached EODHD
fundamentals fetch (`fundamentals.py` resolver + `data/eodhd_fundamentals_cache.json` + a single
shared cache, mirroring the CUSIP map). Wired into both `run_pipeline` and the `build_views`
runner. CSV-only (no summary JSON). `mypy --strict` clean; `pytest` 601 passing (567 baseline +
34 new).

**Operator decisions captured before coding (AskUserQuestion):**
- `build_views` MAY fetch fundamentals (lazily builds an EodhdClient; relaxes its prior strict
  no-network contract — only for the fundamentals step; degrades gracefully without a key).
- `cycle_id` = composite `{ticker}_{security_type}_{n}` (ticker, not cusip).
- `sector` = EODHD `General.Sector` only (single taxonomy; not `GicSector`).
- CSV only — no sibling summary JSON.

**Spec-ambiguity decisions / deviations (SD-V3-*):**
- **SD-V3-1 (cycle_id format).** `f"{entry_ticker}_{security_type}_{n}"`, n=1,2,… per re-entry.
  `entry_ticker` = the cycle's ENTRY-record ticker via `_ticker_display` (ticker → position
  ticker → CUSIP fallback), computed once so the id is stable within a cycle even if the ticker
  churns mid-cycle. n is NOT zero-padded (matches the operator's `CIEN_COMMON_2` example); a
  security with >9 cycles would sort lexically oddly, but max ~26 quarters makes that impossible.
- **SD-V3-2 (sector source).** `General.Sector` (e.g. "Technology"), NOT `General.GicSector`
  (e.g. "Information Technology"). Single consistent taxonomy per the operator. `industry` =
  `General.Industry`. ETFs (`General.Type == "ETF"`) → sector = `"ETF"` (industry as reported,
  usually None).
- **SD-V3-3 (fundamentals cache key).** Keyed by `eodhd_symbol` (the actual fetch unit, e.g.
  `GOOGL.US`), NOT raw ticker. Robust to ticker churn / null tickers (CLAUDE.md: CUSIP/symbol is
  the identifier, ticker is display). The view looks up sector via each row's
  `ReturnRecord.eodhd_symbol`. Cache file name stays `eodhd_fundamentals_cache.json` per spec.
- **SD-V3-4 (changes↔returns join).** Joined by `(cusip, security_type, period)` — a unique key
  per change — not by list index, matching the existing view ethos (`_return_by_period_key`).
- **SD-V3-5 (no summary).** CSV only; the writer returns just the csv Path. The spec's Output
  section defines only the CSV.
- **SD-V3-6 (cum_return_from_entry_pct at entry).** Set to `0.0` at the entry quarter
  UNCONDITIONALLY (literal spec), even when the entry quarter is unpriced. For later quarters it
  is `(price_on_filing_date / entry_price - 1) * 100`, or None when either price is missing.
- **SD-V3-7 (entry_price).** = the cycle's FIRST record's `price_on_filing_date` (may be None if
  that quarter is unpriced); constant across the cycle.
- **SD-V3-8 (EXIT closes the cycle, forces a new one next).** The EXIT row belongs to the current
  cycle; the record after an EXIT always opens a new cycle (tracked via a `prev_was_exit` flag),
  in addition to the NEW-opens-a-cycle and first-appearance-opens-a-cycle rules. First appearance
  of a (cusip, security_type) that is NOT a NEW (held before our data begins) opens cycle 1.
- **SD-V3-9 (`_get` parametrized).** `EodhdClient._get` gained a keyword `url` param so
  `fetch_eod` and the new `fetch_fundamentals` share the throttle/retry choke point. The client
  stays transport-only; `General.*` parsing lives in the resolver.
- **SD-V3-10 (unresolved fundamentals cached; transport errors NOT).** A 404 / object-with-no-
  sector is cached `resolved=False` so it is not re-fetched. A per-symbol `EodhdError` (transport
  / 4xx incl. 403) is logged + SKIPPED (not cached) so it retries next run.

**Verification.** `mypy --strict` clean; `pytest` 601 passing. Real-data offline check (slug
`atreides_management`, empty fundamentals → no network, output to a temp dir so neither the real
views nor the cache were touched): 1321 lifecycle rows == 1321 changes; header == LIFECYCLE_COLUMNS;
rows sorted (cycle_id, quarters_since_entry); 365 cycles (338 NEW + 27 held-before-data);
77 securities re-enter and receive distinct cycle_ids (e.g. `0QZB_CALL_1` / `0QZB_CALL_2`);
every entry row reads `quarters_since_entry=0` and `cum_return_from_entry_pct=0.0`.

**OPEN — FLAG-V3-A (operator): EODHD fundamentals endpoint returns HTTP 403 on the current key.**
A single live probe (`/api/fundamentals/AAPL.US` and `SPY.US`) returned **403 Forbidden** (not
401), i.e. the key authenticates but the plan does NOT include fundamentals data (EODHD sells
fundamentals as a separate subscription from EOD prices). Consequence: View 3 `sector`/`industry`
render BLANK until the operator's EODHD plan covers fundamentals (or a fundamentals-capable key is
supplied). The graceful path is verified working live (403 → per-symbol skip → blank sector → no
crash; pipeline/build_views still complete). NOTE: because transport/4xx errors are deliberately
NOT cached, a cold run currently re-attempts all ~193 unique symbols every run (each a single
non-retried 403). If 403 persists, consider (operator call) either (a) short-circuiting the batch
after a 403 authorization error, or (b) caching a 403 as unresolved. Left as-is pending the
plan/key decision — flag, don't silently change behavior.

---

## 2026-06-24 — manual ticker classifications as PRIMARY sector/industry/theme source

**Why.** FLAG-V3-A (above): the EODHD fundamentals endpoint 403s on the current key. Rather than
upgrade the plan, a hand-maintained `data/ticker_classifications.json` (shared across investors,
keyed by ticker → `{sector, industry, theme}`) is now the PRIMARY source; the EODHD fundamentals
cache stays as a secondary fallback (unchanged, still fetched/cached — it just gracefully 403-skips).

**What was built.**
- New `theme` column in `LIFECYCLE_COLUMNS` (immediately after `industry`) + `PositionLifecycleRow.theme`.
- `constants.TICKER_CLASSIFICATIONS_FILE` + `ticker_classifications_path()` (→ `data/ticker_classifications.json`); `CLASSIFICATION_{SECTOR,INDUSTRY,THEME}_KEY`.
- `storage.read_ticker_classifications()` — reads the JSON OBJECT; missing file → `{}`; non-object root/value or non-string field → DiscoveryError; missing fields → None. READ-ONLY (never written by the pipeline).
- `build_position_lifecycle_view` gained `classifications: dict[str, dict[str, str | None]] | None = None`. New `_lookup_classification` resolves (sector, industry, theme) per row.
- `pipeline.py` + `build_views.py` both `read_ticker_classifications` and pass it to the builder. The EODHD fundamentals fetch is unchanged (`fundamentals.py` untouched).
- `view_io` writer emits the `theme` column.

**Lookup precedence (SD-V3-11).** Look up the row's `ticker_display` (bare ticker; CUSIP fallback)
in `classifications`. If the ticker is PRESENT, its sector/industry/theme win OUTRIGHT — the EODHD
cache is NOT consulted, even for fields the manual entry left null (binary precedence, not
per-field merge). If ABSENT, fall back to the EODHD fundamentals cache (sector/industry only;
`theme` has no EODHD equivalent → stays None). Blank on all three if neither source covers it.
Classifications are NEVER auto-generated/guessed; the file is extended manually per investor.

**Verification.** `mypy --strict` clean; `pytest` **613 passing** (+12). Real-data offline check
(atreides, real `ticker_classifications.json` = 211 tickers, empty fundamentals → no network, temp
output): `theme` present right after `industry`; 1179 / 1321 rows carry sector+theme from the file;
142 rows (uncovered tickers, no EODHD cache) blank on all three — matches the spec's expectation.
FLAG-V3-A is now effectively MITIGATED for covered tickers; the 403 fallback path is unchanged.

---

## 2026-06-24 — SMH (VanEck Semiconductor ETF) added as a SECOND benchmark

**Why.** Add SMH alongside SPY as a sector benchmark for every return record + the views.

**What was built (cross-cutting: returns engine + all three views).**
- `constants.SMH_BENCHMARK_SYMBOL = "SMH.US"`.
- `ReturnRecord` gained `smh_filing_to_filing_return_pct` / `smh_next_period_high_pct` /
  `smh_next_period_low_pct` (mirrors the SPY trio) + an SMH set-together-or-all-None invariant +
  to_dict/from_dict.
- `returns.py`: `_spy_window` generalized to `_benchmark_window(provider, symbol, ...)`, called
  for both SPY and SMH; `_compute_one` populates both trios; `_unpriced_record` nulls SMH too.
- View 3 (lifecycle): two new columns AFTER `excess_period_return_pct` —
  `smh_period_return_pct` (SMH f2f) and `excess_vs_smh_pct` (position f2f − SMH f2f).
- View 1 (new_ideas) + View 2 (conviction_adds): three SMH-excess columns mirroring the SPY-excess
  block — `smh_excess_filing_to_filing_pct` / `_next_period_high_pct` / `_next_period_low_pct`
  (added right after the SPY-excess columns).

**SD-SMH-1 (DEVIATION from the SPY pattern): no fatal SMH preflight.** SPY has a fatal
`has_series_data` preflight because it is THE required benchmark. SMH is a SECONDARY benchmark and
the task specifies missing SMH data → null fields. So SMH is computed per-window identically to
SPY but WITHOUT a global preflight: a fully-absent SMH (or any per-window gap) yields an all-None
SMH trio and never aborts the run. The two benchmark trios are independent (the model invariant
allows SMH all-None while SPY is set).

**Verification.** `mypy --strict` clean; `pytest` **615 passing** (+ SMH cases in test_returns,
test_views, test_view_io, test_pipeline; trio/round-trip in test_models/test_storage). Real-data
recompute (atreides, live EODHD prices, reusing the price cache + fetching SMH.US once, NO EDGAR,
NO committed-data writes): 847/847 priced records carry SMH (same coverage as SPY); e.g. GOOGL
2020-03-31 SPY +18.18% / SMH +30.09% (excess-vs-SMH −20.51%); to_dict/from_dict round-trips SMH.

**OPEN — to PERSIST the new fields, the operator must re-run the FULL pipeline** (stored
returns.json + view CSVs are NOT auto-refreshed by this change; build_views alone cannot add the
new price data):
`.venv/bin/python -m celebpm.pipeline 0001777813 --data-root data` (with `.env` sourced). SMH
prices fetch fine (the 403 only affects fundamentals); SMH.US is already cached from verification.
