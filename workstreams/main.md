# Main Workstream

> Living doc. Clean up when major blocks complete. `/resume main` reads this.

---

> **Related workstream:** Gavin Baker transcript corpus + thesis extraction lives in
> `workstreams/transcripts.md` (branch `gavin-baker-transcript-corpus`) — standalone of this pipeline;
> its `analysis/thesis_timeline.json` is intended to be cross-referenced against these 13F outputs.

## Current State (as of June 24 2026)

**Phase 1 COMPLETE.** Full investor-agnostic pipeline built and verified end-to-end (Prompts 1–6 via multi-prompt-build): EDGAR discovery → parse info-table XML → CUSIP→ticker (OpenFIGI) → QoQ diff & classification → filing-date-anchored returns + SPY → View 1 (New Ideas Feed) CSV. `mypy --strict` clean (47 files), `pytest` 526 passing; live-validated against Situational Awareness (CIK 0002045724) → 69 new ideas, full CSV + summary written. Run: `.venv/bin/python -m celebpm.pipeline <CIK> --data-root data` (with `.env` sourced).

**View 2 (Conviction Tracker) COMPLETE** — built in `views.py`/`view_io.py`, wired into `run_pipeline` (writes `views/conviction_adds.csv` + `conviction_adds_summary.json` from the same in-memory `config`/`positions`/`changes`/`returns`, no extra network), and also rebuildable offline via `.venv/bin/python -m celebpm.build_views <CIK> --data-root data`. `mypy --strict` clean; `pytest` 567 passing; offline rebuild against Situational Awareness → 16 conviction adds.

**View 3 (Position Lifecycle) COMPLETE** — `build_position_lifecycle_view` in `views.py` + `write_position_lifecycle_view` (CSV-only) in `view_io.py`. Reshapes `changes.json`+`returns.json` into one row per `(cusip, security_type)` per quarter held, grouped into entry→exit cycles (`cycle_id` = `{ticker}_{security_type}_{n}`). Adds sector/industry via a NEW cached EODHD fundamentals fetch — `fundamentals.py` resolver + `FundamentalsEntry` model + `data/eodhd_fundamentals_cache.json` (shared, keyed by `eodhd_symbol`) + `EodhdClient.fetch_fundamentals`. Wired into `run_pipeline` AND `build_views`. **Sector/industry/theme now come PRIMARILY from a hand-maintained `data/ticker_classifications.json`** (shared, keyed by ticker; `storage.read_ticker_classifications`), with the EODHD fundamentals cache as a secondary fallback (sector/industry only). Added a `theme` column. `mypy --strict` clean; `pytest` **613 passing**. Real-data offline check (atreides, 211-ticker classifications) → 1321 rows, 1179 carry sector+theme, 142 uncovered blank. Decisions + deviations: `docs/implementation_notes/view_position_lifecycle_implementation_notes.md` (SD-V3-1…11). **FLAG-V3-A (EODHD fundamentals 403 on the current key) is now MITIGATED** for classified tickers via the manual file; the 403 graceful-skip fallback is unchanged. Extend the classifications file manually as new investors are added.

**SMH benchmark added (2026-06-24)** — `ReturnRecord` now carries an SMH (VanEck Semiconductor ETF) trio alongside SPY (`smh_filing_to_filing_return_pct` + high/low), computed via the generalized `_benchmark_window` in `returns.py` (SMH has NO fatal preflight — secondary benchmark, missing → null; SD-SMH-1). Views: lifecycle gained `smh_period_return_pct` + `excess_vs_smh_pct` (after `excess_period_return_pct`); View 1 + View 2 gained `smh_excess_*` columns mirroring the SPY-excess block. `mypy --strict` clean; `pytest` **615 passing**. Real-data recompute verified (847/847 priced records get SMH; no committed-data writes). **To persist into stored returns.json + view CSVs, re-run the full pipeline:** `.venv/bin/python -m celebpm.pipeline 0001777813 --data-root data` (SMH.US already cached).

---

## Active specs in use

<!--
Specs currently being implemented in this workstream. The /resume
command reads this section and loads referenced specs into context.
Remove entries when work completes (prompted by /wrap-up). Keep
this list lean.

Format: `path/to/spec.md` -- brief context on what's being worked on.
-->

_No active specs._ — Phase 1 of `docs/specs/13f_analysis_pipeline_spec.md` (Layer 1 + View 1) is COMPLETE. Implementation log: `docs/implementation_notes/13f_analysis_pipeline_implementation_notes.md`; deviations SD-1…SD-5 in the build workdir `spec-deviations.md`.

Next spec sections (Phase 2): ~~§View 2 Conviction Tracker~~ DONE (`docs/specs/view2_conviction_tracker_spec.md`), §View 3 Exit Signals, §View 4 Survivors — add their paths here when work begins. View-2 deviations SD-V2-1…SD-V2-8 are recorded in `docs/implementation_notes/view2_conviction_tracker_implementation_notes.md`.

---

## Immediate Next Steps

1. **Operator confirm SD-4** — View 1 summary stats are written to a sibling `new_ideas_summary.json` rather than as footer rows in `new_ideas.csv`. Confirm acceptable, or request footer rows (small follow-up).
2. **(Optional) run the second investor** — `python -m celebpm.pipeline 0001777813 --data-root data` (Atreides, 26 quarters; first end-to-end run that exercises EODHD at volume + the OpenFIGI no-key rate limit).
3. **Phase 2** — View 2 (Conviction) DONE; View 3 (Position Lifecycle) DONE. Next: **View 4** (Exit Signals / Survivors per spec): sibling builders in `views.py` + writers in `view_io.py`, consuming the existing `changes.json`/`returns.json`/`positions.json` over the same build+write wiring pattern.
   - **FLAG-V3-A mitigated:** sector/industry/theme now come from `data/ticker_classifications.json` (manual, keyed by ticker). EODHD fundamentals (HTTP 403 on the current key) remains a secondary fallback. To classify a new investor's tickers, append them to that file. (Upgrading the EODHD plan would re-enable the automatic fallback but is no longer required.)
4. **Confirm SD-V2-1** — `still_held` is computed per security-chain (not per add-cycle); see `docs/implementation_notes/view2_conviction_tracker_implementation_notes.md`. Confirm per-chain, or request per-cycle (one-function change).

---

## Settled Decisions

Full details in `workstreams/main-decisions.md` (loaded on demand, not at startup).

**Key rules (always apply):**
1. **CUSIP is the join key; ticker is display-only** (may be None → CUSIP fallback). Never join on ticker.
2. **Equity and options are separate tracks** — never mix options notional into equity weight denominators. `weight_pct_equity_only` is `None` for PUT/CALL; options price on the underlying as a directional signal only.
3. **Filing date is the anchor** for returns/signals (not quarter-end). First data quarter is a baseline (no changes emitted).
4. **`value` stored as-reported (SD-2)** — never derive price/returns from `value_reported`; use EODHD prices. View math is ratios + prices, so units cancel.
5. **No hardcoded values** — all URLs/limits/thresholds/paths/column names in `constants.py`. Secrets via `os.environ` only (`EODHD_API_KEY`, optional `OPENFIGI_API_KEY`).
6. **One rate-limited client per source, reused across CIKs**; mock at the client-method level; live tests in `tests_live/` (excluded from CI).
7. **Spec is source of truth**; deviations are logged (SD-1…SD-5) — flag, don't silently deviate.

Full rationale: `workstreams/main-decisions.md` (2026-06-12 section).

---

## Key Files

**Pipeline (`src/celebpm/`):** `pipeline.py` (thin end-to-end orchestrator + `python -m celebpm.pipeline` CLI) · `config_loader.py` (investors.json) · `discovery.py` (EDGAR filing discovery) · `parser.py` (info-table XML → PositionRecords) · `openfigi_client.py` + `cusip_map.py` (CUSIP→ticker) · `diff.py` (QoQ change classification) · `eodhd_client.py` + `price_cache.py` + `symbol_map.py` (prices) · `returns.py` (filing-anchored returns + SPY) · `views.py` + `view_io.py` (View 1 + View 2 builders + CSV/summary writers) · `build_views.py` (standalone offline View 1+2 rebuild runner) · `models.py` (all frozen records: FilingRecord/PositionRecord/CusipMapEntry/PositionChange/ReturnRecord + ChangeType) · `storage.py` (flat-JSON per-investor I/O) · `constants.py` · `errors.py` · `ratelimit.py` · `price_types.py`.

**Config/data:** `config/investors.json` (CIK→name/fund/slug) · outputs at `data/<slug>/{filings,positions,changes,returns}.json` + `views/new_ideas.csv` + `views/new_ideas_summary.json` + `views/conviction_adds.csv` + `views/conviction_adds_summary.json` · global `data/cusip_ticker_map.json`, `data/price_cache/<symbol>.json`.

**Docs:** `docs/specs/13f_analysis_pipeline_spec.md` · `docs/implementation_notes/13f_analysis_pipeline_implementation_notes.md` · per-prompt handoffs in `handoffs/`.
