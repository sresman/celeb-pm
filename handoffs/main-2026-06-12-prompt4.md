# Handoff — Prompt 4 (QoQ Diff & Change Classification) — 2026-06-12

## What Prompt 4 delivered

QoQ position-change diff + classification (spec §1.4), disk-free + deterministic, plus storage.

- **`models.py`**: `ChangeType(str, Enum)` (NEW/EXIT/ACTIVE_ADD/ACTIVE_TRIM/DRIFT_UP/DRIFT_DOWN/HOLD)
  and `PositionChange` (frozen, kw_only) with non-nullable `prior_period`/`prior_filing_date`,
  current/prior quantity fields, derived deltas, `change_type`, `split_suspected`,
  `corporate_action_note`. `__post_init__` enforces NEW/EXIT/matched invariants, the strict
  `split_suspected ⇒ HOLD`, `prior_period < period`, finite/sign/bool guards. `to_dict`/`from_dict`
  round-trip through bare JSON. Added `_require_date` helper.
- **`diff.py`**: `classify_change` (split short-circuit then ACTIVE/DRIFT/HOLD cascade, COMMON-only
  split), `_compute_deltas`, `diff_quarters` (one adjacent pair; matched→classify, only-current→NEW,
  only-prior→EXIT; both sides must be non-empty), `compute_changes` (multi-quarter orchestration;
  first period is BASELINE and emits nothing; per-period validation for ALL periods).
- **`constants.py`**: Prompt-4 thresholds (`CHANGE_SHARES_DELTA_PCT_THRESHOLD=10.0`,
  `CHANGE_WEIGHT_DELTA_BPS_THRESHOLD=50.0`, `PCT_TO_BPS`, split bands) + `changes_path(slug)`.
- **`storage.py`**: `write_changes` / `read_changes` (atomic, path-safe, sorted, single-cik +
  duplicate-key guards; missing/malformed → DiscoveryError).
- **Tests**: 345 total green (239 baseline + 106 new). mypy strict clean (30 source files).

## Venv usage snippet (read_positions → compute_changes → write_changes)

```python
from celebpm import storage
from celebpm.diff import compute_changes

slug = "atreides_management"
positions = storage.read_positions(slug)          # [PositionRecord], all quarters
changes = compute_changes(positions)              # [PositionChange]; first quarter emits nothing
storage.write_changes(slug, changes)              # data/<slug>/changes.json (bare JSON list)

# read back
loaded = storage.read_changes(slug)
```

Run checks: `.venv/bin/mypy .` and `.venv/bin/pytest`.

## BLOCKER for Prompt 5 — EODHD key

`.env` exists but contains **NO EODHD API key**. Prompt 5 (prices + returns) needs it.
**Operator action required:** add the EODHD key to `.env` before Prompt 5 can fetch prices.
(Confirmed: `grep -i eodhd .env` finds nothing.)

## Exact next step — Prompt 5 (prices + filing-date-anchored returns + SPY benchmark)

- Consumes `PositionChange` anchored on **`filing_date`** (and `period`). NEW/ACTIVE_ADD rows are the
  signal anchors; EXIT rows anchor "exit-then-what" returns.
- Add the `ReturnRecord` model (the remaining placeholder in `models.py`, fields per spec §1.5);
  it references `change_type`.
- Returns are anchored on **`filing_date`, NOT period-end** (filing date is the anchor — CLAUDE.md).
- Must **normalize ticker → EODHD symbol** (e.g. exchange suffixes); tickers are display-only and may
  be None — join logic should not depend on ticker stability.
- **Do NOT derive implied price from `*_value_reported`** or read `value_delta`/`value_delta_pct` as a
  real change. Use external EODHD prices keyed by ticker/cusip. The SD-2 thousands→dollars boundary
  quarter makes those value fields a ~1000× artifact.
- Benchmark against SPY over the same filing-date-anchored windows.

## Carried flags (for Prompt 5/6 to decide)

- **SD-2 units open.** `value_reported` (and thus `value_delta`/`value_delta_pct`) is stored
  as-reported; the SEC thousands→dollars boundary (~Jan 2023) is unresolved. Boundary-quarter value
  deltas are a ~1000× artifact. Classification + split detection are unaffected (they use shares +
  weight). Consumers must not misread value deltas as a real change.
- **ticker is display-only.** May be None; never used for joining (join on `(cusip, security_type)`).
- **First-quarter baseline holdings come from `positions.json`, not `changes.json`.** The earliest
  quarter emits no change records by design.
- **0-share trim is exit-like for Prompt 6.** A position trimmed to 0 shares while still reported in
  the filing classifies as matched (~ACTIVE_TRIM via -100% shares), NOT EXIT. The Exit view may want
  to treat it as exit-like.
- **Prompt 6 should compare `change_type` against `ChangeType` members, not string literals**
  (str-Enum mixes in str, so string comparisons silently succeed and hide typos).
