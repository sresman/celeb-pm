# Main Decisions

> Companion to `workstreams/main.md`. Load on demand, not at startup.
> Append new decisions with date headers. Do not rewrite existing entries.

---

## 2026-06-12 — Phase-1 pipeline build (Prompts 1–6, multi-prompt-build)

Full per-prompt decision log: `docs/implementation_notes/13f_analysis_pipeline_implementation_notes.md`. Spec deviations: build workdir `spec-deviations.md` (SD-1…SD-5). Key cross-cutting decisions:

- **EDGAR via structured JSON only** (`data.sec.gov/submissions/...` + `filings.files[]` overflow), never HTML/cgi-bin (SD-1). `filing_index_url` carried on FilingRecord; Prompt 2 fetches `{index}index.json` to locate the info-table XML — never assume `primary_doc` == info table.
- **CUSIP is the join key everywhere; ticker is display-only** (resolved by OpenFIGI, may be None → CUSIP fallback in views). Diffs/returns/views all join on `(cusip, security_type)`, never ticker.
- **Equity and options are separate tracks, always.** Two weights per position: `weight_pct_reported` (incl. options notional) and `weight_pct_equity_only` (COMMON only; `None` for PUT/CALL). Options are priced on the UNDERLYING as a directional signal (`is_underlying_price=True`), never option P&L.
- **Filing date is the anchor** for all returns/signals (not quarter-end). First quarter is a BASELINE (emits no PositionChanges); a NEW = a CUSIP appearing in a quarter that has a prior.
- **Change classification (spec §1.4) uses `weight_pct_reported` NAV weight, exact strict operators** (>±10% shares, >±50bps weight), inclusive `<=` drift band. Suspected stock split (COMMON, shares≈+100% & flat value) → `split_suspected=True`, forced to HOLD (never ACTIVE_ADD).
- **SD-2 value units = ACCEPT AS-REPORTED (operator decision 2026-06-12).** `value` stored exactly as EDGAR reports it (thousands pre-2023 / dollars post-2023, not normalized). Renamed spec `value_thousands` → `value_reported` (SD-3). Safe because View 1 uses only ratios (weights) + EODHD price-based returns — units cancel; returns are NEVER derived from `value_reported`.
- **Returns use EODHD adjusted close** (split/dividend-immune), per-symbol coverage-threshold fallback to raw close. Cache is a global per-symbol store with a hard history floor (2018-01-01) + per-call rule. Multi-quarter cumulative spans first-held filing → EXIT filing (or today), placed on the last held row. Delisting → carry last available price forward.
- **SPY benchmark on every priced ReturnRecord** (operator-confirmed: 3 raw SPY fields); View 1 adds excess = position − SPY. High/low excess is a relative heuristic, not date-matched alpha (SD-5).
- **View 1 summary written as a sibling `new_ideas_summary.json`** (clean rectangular CSV), not footer rows (SD-4 — ⚠️ operator to confirm acceptable).
- **External-client architecture:** one rate-limited client per source (`EdgarClient`, `OpenFigiClient`, `EodhdClient`), each a `Protocol` seam mocked at the method level; capacity-1 token bucket (`ratelimit.TokenBucket`, uniform spacing, no startup burst); ONE client + shared cache reused across investors/CIKs. Secrets read from `os.environ` (`OPENFIGI_API_KEY` optional, `EODHD_API_KEY` required for prices).
- **Storage = flat JSON per investor** under `data/<slug>/`, atomic + path-safe writes, missing-file → `DiscoveryError`. Frozen `kw_only` dataclasses with `to_dict`/`from_dict`/`__post_init__`; updates via `dataclasses.replace`.
- **Orchestrator (`pipeline.py`) is thin** (compose-only): discover → parse → resolve tickers → diff → returns → View 1. Per-filing failures skip-and-warn with `timeline_degraded` surfaced; SPY-preflight failure is fatal.

### Deferred / out of scope (Phase 2+)
- Views 3–4 (Exit / Survivors) — consume the same `changes`/`returns`. (View 2 Conviction DONE — see 2026-06-24 below.)
- True additive-amendment merge + point-in-time historical ticker resolution.
- SD-4 footer-rows-in-CSV (only if the operator prefers it over the sibling JSON).
- 100%-liquidation / empty-quarter EXIT synthesis (needs the FilingRecord period list passed into `compute_changes`).

---

## 2026-06-24 — View 2 (Conviction Tracker) build (Prompts 1–3, multi-prompt-build)

Full per-decision detail (SD-V2-1…SD-V2-8) lives in `docs/implementation_notes/view2_conviction_tracker_implementation_notes.md`. Key points:

- **View 2 = one row per ACTIVE_ADD event.** Pure builder `build_conviction_adds_view` in `views.py` (reuses View-1 helpers, disk/network/pandas-free) + writer `write_conviction_adds_view` in `view_io.py`. Outputs `data/<slug>/views/conviction_adds.csv` + `conviction_adds_summary.json`.
- **No new data fetching.** `prior_quarter_return_pct` = the prior chain entry's existing `ReturnRecord.filing_to_filing_return_pct`; `cumulative_return_since_entry_pct` = ratio of the add's vs the cycle-entry's `price_on_filing_date`. Reuses existing returns only (operator decision).
- **Two entrypoints (operator chose "Both"):** wired into `run_pipeline` (build+write from the same in-memory inputs, no extra network) AND a standalone offline runner `python -m celebpm.build_views <CIK> --data-root data` that rebuilds View 1 + View 2 from persisted JSON.
- **⚠️ SD-V2-1 OPEN (operator to confirm):** `still_held` is per security-CHAIN (chain's last entry at the dataset's `latest_period` and non-EXIT), NOT per add-cycle. Literal-spec reading; 2/3 QA reviewers preferred per-cycle. Locked by a test; flipping is a one-function change.
- Mechanical deviations: `is_underlying_price` column omitted (SD-V2-2), sort tiebreak cusip/security_type (SD-V2-3), `quarters_held_before_add` counts observed not calendar quarters (SD-V2-4), "next quarter" = next chain entry (SD-V2-5), held-before-dataset = first entry of current cycle (SD-V2-6), `add_type` boundary 0.0 → AVERAGING_DOWN (SD-V2-7), `return_rec` test factory gained `price_on_filing` (SD-V2-8).
- **Verification:** `mypy --strict` clean; `pytest` 567 passing (526 → +41 View-2 tests); offline rebuild vs Situational Awareness → 16 conviction adds.

---

## 2026-07-09 — View 3 (Position Lifecycle) + ticker classifications + SMH benchmark

Full per-decision detail in `docs/implementation_notes/view_position_lifecycle_implementation_notes.md`
(SD-V3-1…11, SD-SMH-1). Key points:

- **View 3 = one row per `(cusip, security_type)` per quarter held**, grouped into entry→exit CYCLES.
  `build_position_lifecycle_view` in `views.py` + `write_position_lifecycle_view` (CSV-only) in
  `view_io.py`; wired into `run_pipeline` AND `build_views`. `cycle_id = {entry_ticker}_{security_type}_{n}`
  (ticker with CUSIP fallback; n increments per re-entry). EXIT closes a cycle; NEW / first-appearance
  opens one. changes↔returns joined by `(cusip, security_type, period)`, not list index.
- **Sector/industry/theme: manual `data/ticker_classifications.json` is PRIMARY** (shared, keyed by
  ticker → {sector, industry, theme}; `storage.read_ticker_classifications`), EODHD fundamentals cache
  is the FALLBACK (sector/industry only; theme has no EODHD equivalent). Precedence is BINARY — if a
  ticker is in the file its values win outright (fundamentals not consulted, even for null fields).
- **FLAG-V3-A:** the EODHD fundamentals endpoint returns HTTP 403 on the current key (fundamentals is a
  separate EODHD plan tier). Handled gracefully (per-symbol skip → blank) and now MITIGATED for classified
  tickers via the manual file. The `build_views` runner may now perform ONE network step (the fundamentals
  fetch) — a deliberate relaxation of its prior no-network contract; it still degrades gracefully without a key.
- **SMH (VanEck Semiconductor ETF) added as a SECOND benchmark** alongside SPY on every `ReturnRecord`
  (`smh_filing_to_filing_return_pct` + high/low). `returns.py` generalized `_spy_window` → `_benchmark_window`
  called for both. Views: lifecycle gained `smh_period_return_pct` + `excess_vs_smh_pct`; View 1 + View 2
  gained `smh_excess_*` columns mirroring the SPY-excess block.
- **SD-SMH-1 (deviation from the SPY pattern):** SMH has NO fatal preflight. SPY's `has_series_data`
  preflight is fatal because it is THE required benchmark; SMH is secondary, so a fully-absent SMH (or any
  per-window gap) yields an all-None SMH trio and never aborts (task spec: missing SMH → null fields). The
  two benchmark trios are independent (model invariant allows SMH all-None while SPY is set).
- **Verification:** `mypy --strict` clean; `pytest` **615 passing** (567 → +48). Real-data offline checks
  (atreides): View 3 reshape → 1321 rows / 365 cycles / 77 re-entries, 1179 rows sector+theme from the
  211-ticker file; SMH recompute over live prices → 847/847 priced records carry SMH. No committed-data writes.
- **⚠️ TO PERSIST SMH into stored `returns.json` + view CSVs, re-run the full pipeline:**
  `.venv/bin/python -m celebpm.pipeline 0001777813 --data-root data` (SMH.US already price-cached). This
  change adds only the computation; stored per-investor artifacts are not auto-refreshed.

## 2026-09-03 — Trigger-analysis workbook: ex-reclass denominator + forward returns (branch `trigger-denominator-ex-spcx`)

Analysis layer only (`tools/transcripts/`, `analysis/`); the `src/celebpm` pipeline is untouched.

- **DECISION — weight all AI-signal triggers + context sheets on thesis-investable equity (COMMON ex
  IPO-reclassification), not total book.** WHY: SpaceX (SPCX) entered the 13F via its Q2-2026 IPO at ~33% of
  total book, and Cerebras (CBRS) likewise — both pre-existing private crossover holdings becoming
  reportable, NOT market purchases. On a total-book denominator they compressed every AI subtheme's weight
  below the fixed 4%/2% cross thresholds, and it worsens each quarter as their marks rise. Ex-reclass
  weights sum to 100% per period and thresholds behave as originally calibrated. `IPO_RECLASS_TICKERS =
  {SPCX, CBRS}`.
- **Reclass treatment:** change_type `IPO_RECLASSIFICATION`; MTM/Trading = None (excluded from every
  net-buying/MTM total and from `net_buying_pct`'s denominator + `narrow()` numerator); dropped from the
  trigger universe and the ramp/AI baskets; shown as `[memo]` rows (% of total equity) on the context sheets.
- **Basis is consistent across the whole workbook** — triggers, context sheets (Holdings Q1/Q2/Δ, AI-basket
  roll-up + trailing history, Baskets theme-allocation summary, Flows, Summary) all use the same ex-reclass
  denominator; verified CBRS = 10.61%→memo, Σ thesis = 100%.
- **DECISION — forward-returns performance is filing-anchored buy-and-hold, EW baskets, at 1m/1q/6m/1y/2y vs
  SMH and SPY** (`trigger_forward_returns.py`, `compute_stats()` reused by the workbook's Performance sheet).
  An event counts for a horizon only once its window is fully observed (prices through the Q2 filing).
  Tradeable basket per trigger: NewPosition=named ticker; NewSubtheme=entering tickers; Cross=all subtheme
  tickers; Ramp=narrow AI picks-and-shovels basket.
- **Finding (honest read):** signal beats SPY at every horizon but is ~in line with SMH (largely AI-beta);
  AI_BASKET_RAMP (deliberate deployment) is the only trigger that beats SMH consistently. Single regime
  (2020–26 AI bull), right-skewed (avg ≫ median). Ex-reclass net deployment = −$1.35B (net seller) vs $4.00B
  as-filed.
- **Denominator is analysis-layer config** (module-level `IPO_RECLASS_TICKERS`), duplicated across three
  tool modules — acceptable; centralize if a 4th consumer appears.
- **Committed shared inputs** the corrected workbook depends on (Q2-current): `ai_basket_reclassification.json`,
  `theme_baskets_v3.json`, `filing_to_filing_returns_universal.csv`, `thesis_timeline_v2_flat.json`,
  `sa_q2_2026_mtm_vs_trading.csv`. These also carry the two-podcast-run changes; folded in so the artifact is
  reproducible. Broader two-podcast corpus (audits/extractions/transcripts/manifests) left uncommitted.
