# Handoff — 2026-06-12 — Prompt 3 (CUSIP→Ticker Resolution) DONE

## What Prompt 3 delivered
RESOLVE IDENTIFIERS pipeline step: map CUSIP→ticker via OpenFIGI (no-key tier) with a
persistent shared local cache + manual overrides. Pure functions + storage; NO orchestrator/CLI
(later prompt). 239 tests green, mypy strict clean.

- `src/celebpm/ratelimit.py` — `TokenBucket` + `parse_retry_after` (lifted from edgar_client,
  shared). edgar_client re-exports them as `_TokenBucket` / `_parse_retry_after`.
- `src/celebpm/openfigi_client.py` — `MappingClient` Protocol (+ `max_jobs_per_request`),
  `MapJob`/`MapMatch`/`MapResult`, `OpenFigiClient` (`from_env`, per-minute throttle, 429
  per-minute backoff, single-throttle `_post`, one-chunk `map_jobs`, strict boundary narrowing).
- `src/celebpm/cusip_map.py` — `collect_cusips`, `select_match` (US/Common/Equity/composite +
  deterministic tie-break + ambiguity), `resolve_tickers` (resolver owns chunking + partial
  success + in-place cache mutation + don't-clobber enrichment), `ResolveResult`.
- `src/celebpm/models.py` — `CusipMapEntry` (figi_* provenance, ambiguous, resolved_at ISO str).
- `src/celebpm/storage.py` — `read_cusip_map` / `write_cusip_map` + `_assert_under_root`.
- `src/celebpm/errors.py` — `OpenFigiError`. `src/celebpm/constants.py` — OpenFIGI block + helper.

## Run discovery → parse → resolve (compose snippet; ONE EdgarClient + ONE OpenFigiClient)
```python
from celebpm import storage
from celebpm.edgar_client import EdgarClient
from celebpm.openfigi_client import OpenFigiClient
from celebpm.cusip_map import resolve_tickers

edgar  = EdgarClient()                       # ONE client for the whole run
figi   = OpenFigiClient.from_env()           # key from env if non-blank; else no-key
cache  = storage.read_cusip_map(data_root)   # shared across investors; missing -> {}

for slug in investor_slugs:
    # ... discovery + parse already produced positions.json for this slug ...
    positions = storage.read_positions(slug, data_root)
    result    = resolve_tickers(positions, figi, cache)   # MUTATES cache in place
    storage.write_positions(slug, result.positions, data_root)
    storage.write_cusip_map(cache, data_root)             # PERSIST after each investor
    if result.partial:
        ...  # remaining misses retry next run
```
Run live smoke: `.venv/bin/pytest tests_live/test_resolve_live.py` (manual, hits real OpenFIGI).

## EXACT NEXT STEP — Prompt 4 (QoQ DIFF & CHANGE CLASSIFICATION)
- Join positions across consecutive quarters on **cusip + security_type** — NOT ticker
  (ticker is display-only, may be None, may change on rename/merger).
- `weight_pct_reported` thresholds drive change classification.
- New `ChangeType` enum + `PositionChange` model (placeholder comment already in models.py).
- Anchor on filing_date (per CLAUDE.md), not period-end.

## Carried-forward flags
- **SD-2 (units) still OPEN**: `value_reported` stored as-reported; thousands-vs-dollars boundary
  (~Jan 2023) unresolved — no implied-price derivation until resolved (Prompt 5).
- **Ticker is display-only** and may be the CURRENT ticker even for old quarters (no point-in-time
  security master). Out of scope for now.
- **Prompt 5 must normalize ticker → EODHD symbol** (OpenFIGI `BRK/B` ≠ EODHD symbol).
- **EODHD API key is ABSENT from .env** — required for Prompt 5; add it before that prompt.
- **Concurrent runs unsupported** (shared cusip_ticker_map.json, no locking; resolve once per run).
- View 1 (Prompt 6/7) must render a fallback for `ticker=None` (unresolved CUSIPs), not blank/"None".
