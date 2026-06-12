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
- Views 2–4 (Conviction / Exit / Survivors) — consume the same `changes`/`returns`.
- True additive-amendment merge + point-in-time historical ticker resolution.
- SD-4 footer-rows-in-CSV (only if the operator prefers it over the sibling JSON).
- 100%-liquidation / empty-quarter EXIT synthesis (needs the FilingRecord period list passed into `compute_changes`).
