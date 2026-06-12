# Main Workstream

> Living doc. Clean up when major blocks complete. `/resume main` reads this.

---

## Current State (as of June 12 2026)

**Phase 1 COMPLETE.** Full investor-agnostic pipeline built and verified end-to-end (Prompts 1–6 via multi-prompt-build): EDGAR discovery → parse info-table XML → CUSIP→ticker (OpenFIGI) → QoQ diff & classification → filing-date-anchored returns + SPY → View 1 (New Ideas Feed) CSV. `mypy --strict` clean (47 files), `pytest` 526 passing; live-validated against Situational Awareness (CIK 0002045724) → 69 new ideas, full CSV + summary written. Run: `.venv/bin/python -m celebpm.pipeline <CIK> --data-root data` (with `.env` sourced).

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

Next spec sections (Phase 2, not started): §View 2 Conviction Tracker, §View 3 Exit Signals, §View 4 Survivors — add their paths here when work begins.

---

## Immediate Next Steps

1. **Operator confirm SD-4** — View 1 summary stats are written to a sibling `new_ideas_summary.json` rather than as footer rows in `new_ideas.csv`. Confirm acceptable, or request footer rows (small follow-up).
2. **(Optional) run the second investor** — `python -m celebpm.pipeline 0001777813 --data-root data` (Atreides, 26 quarters; first end-to-end run that exercises EODHD at volume + the OpenFIGI no-key rate limit).
3. **Phase 2** — build View 2 (Conviction), View 3 (Exit), View 4 (Survivors): sibling builders in `views.py` + writers in `view_io.py`, consuming the existing `changes.json`/`returns.json`/`positions.json`. No pipeline changes needed.

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

**Pipeline (`src/celebpm/`):** `pipeline.py` (thin end-to-end orchestrator + `python -m celebpm.pipeline` CLI) · `config_loader.py` (investors.json) · `discovery.py` (EDGAR filing discovery) · `parser.py` (info-table XML → PositionRecords) · `openfigi_client.py` + `cusip_map.py` (CUSIP→ticker) · `diff.py` (QoQ change classification) · `eodhd_client.py` + `price_cache.py` + `symbol_map.py` (prices) · `returns.py` (filing-anchored returns + SPY) · `views.py` + `view_io.py` (View 1 builder + CSV/summary writer) · `models.py` (all frozen records: FilingRecord/PositionRecord/CusipMapEntry/PositionChange/ReturnRecord + ChangeType) · `storage.py` (flat-JSON per-investor I/O) · `constants.py` · `errors.py` · `ratelimit.py` · `price_types.py`.

**Config/data:** `config/investors.json` (CIK→name/fund/slug) · outputs at `data/<slug>/{filings,positions,changes,returns}.json` + `views/new_ideas.csv` + `views/new_ideas_summary.json` · global `data/cusip_ticker_map.json`, `data/price_cache/<symbol>.json`.

**Docs:** `docs/specs/13f_analysis_pipeline_spec.md` · `docs/implementation_notes/13f_analysis_pipeline_implementation_notes.md` · per-prompt handoffs in `handoffs/`.
