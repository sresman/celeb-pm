# Handoff — main — 2026-06-12 — Prompt 6 (View 1 + end-to-end orchestrator)

## What Prompt 6 delivered
- `src/celebpm/views.py` — View-1 (New Ideas Feed) builder. Disk-free/deterministic (may WARN),
  pandas-free. `build_new_ideas_view(*, config, positions, changes, returns) -> NewIdeasView`
  (frozen `NewIdeaRow`/`NewIdeasSummary`/`NewIdeasView`).
- `src/celebpm/view_io.py` — the SINGLE pandas import in the codebase. Writes
  `views/new_ideas.csv` + a sibling `views/new_ideas_summary.json` atomically + path-safe.
- `src/celebpm/pipeline.py` — thin compose-only orchestrator `run_pipeline(...) -> PipelineResult`
  plus a `python -m celebpm.pipeline` CLI runner.
- `storage.safe_data_path(...)` (public path-safety helper); View-1 constants in `constants.py`;
  pandas mypy override in `pyproject.toml`.
- Tests: `tests/test_views.py` (19), `tests/test_view_io.py` (5), `tests/test_pipeline.py` (3),
  `tests_live/test_pipeline_live.py` (manual). New fixture `tests/fixtures/infotable_alpha_only.xml`.
- Status: `mypy .` clean (47 files); `pytest` 526 passed (499 prior + 27 new).

## The whole Phase-1 pipeline is COMPLETE
parser → positions → diffs → returns → View 1. End-to-end wiring exists and is integration-tested.

## How to RUN it end-to-end
With the env sourced (EODHD_API_KEY for prices; EDGAR User-Agent is in constants):
```
.venv/bin/python -m celebpm.pipeline 0002045724 --data-root data
# optional: --today YYYY-MM-DD (defaults to date.today())
```
Or programmatically: `from celebpm.pipeline import run_pipeline; run_pipeline(cik, today=...)`.

## Where outputs land
`data/<slug>/`:
- `filings.json`, `positions.json`, `changes.json`, `returns.json`
- `views/new_ideas.csv` (one row per NEW idea, sorted by initial weight DESC)
- `views/new_ideas_summary.json` (win rate, avg winner/loser, median holding, %→ACTIVE_ADD, notes)

Shared (investor-agnostic): `data/cusip_ticker_map.json`, `data/price_cache/`.

## Next steps
- **Views 2–4 (Conviction / Exit / Survivors)** — OUT of scope for Prompt 6. They consume the
  SAME `changes`/`returns`/`positions` already produced. If/when built, `views.py` can grow into a
  `views/` package (`new_ideas.py`, `conviction.py`, ...). Do NOT pre-build the package.

## Resolved / carried flags
- **SD-2 (value units)** — RESOLVED: accept-as-reported. View 1 uses only price-derived returns
  and `weight_pct_reported`, never `value_reported` for numerics. No units normalization in code.
- **SD-4** — View 1 summary is a sibling JSON, NOT CSV footer rows (clean rectangular CSV).
- **SD-5** — `excess_next_period_high/low_pct` are a relative heuristic (position high/low vs SPY
  high/low), NOT date-matched alpha; carried into the summary JSON `notes`. `excess_filing_to_filing_pct`
  IS a clean same-window comparison.
- **timeline_degraded** — if a filing is skipped (EdgarError/DiscoveryError) the run still produces
  all artifacts but `PipelineResult.timeline_degraded=True` and `quarters_held` may understate tenure.
- **Ticker is display-only** — joins are on CUSIP; ticker_display falls back to CUSIP, never blank/"None".
- **tests_live/** run the REAL pipeline (EDGAR + OpenFIGI + EODHD) and can be run manually; they are
  excluded from default pytest discovery and skip without EODHD_API_KEY.
