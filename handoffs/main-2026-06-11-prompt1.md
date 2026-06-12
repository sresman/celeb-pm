# Handoff — Prompt 1 (2026-06-11)

## What Prompt 1 delivered

Pipeline step 1 (**FETCH FILINGS**) + the package skeleton everything later builds on.

- **Package** `src/celebpm/` (src-layout, editable-installed): `constants.py` (all tunables + JSON aliases + path/URL helpers), `errors.py` (CelebPMError → ConfigError/EdgarError/DiscoveryError), `config_loader.py` (`InvestorConfig`, `load_investor`/`load_all_investors`), `models.py` (`FilingRecord` frozen dataclass), `edgar_client.py` (`HttpClient` Protocol + `_TokenBucket` + `EdgarClient`), `discovery.py` (`discover_filings`, `latest_filing_per_period`), `storage.py` (`write_filings`/`read_filings`).
- **Config data file** `config/investors.json` (Atreides / Situational Awareness, keyed by padded CIK).
- **Tests**: 69 unit tests (`tests/`), all green; mypy strict clean across 17 files. Live smoke `tests_live/test_discovery_live.py` (manual, excluded from default pytest).

Status: `.venv/bin/mypy .` → no issues; `.venv/bin/pytest` → 69 passed.

## How to run the pipeline so far

```bash
# from /Users/stevenresman/Projects/celeb-pm
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
.venv/bin/mypy .        # strict, clean
.venv/bin/pytest        # 69 passed
# Live smoke (hits real EDGAR, manual only):
.venv/bin/pytest tests_live/
```

Compose discovery + storage (note: ONE EdgarClient, reused across CIKs):

```python
from celebpm.edgar_client import EdgarClient
from celebpm.discovery import discover_filings
from celebpm.storage import write_filings
from celebpm.config_loader import load_investor

client = EdgarClient()                      # build ONCE; reuse for every CIK
for cik in ("0001777813", "0002045724"):
    cfg = load_investor(cik)                # InvestorConfig (slug, name, ...)
    records = discover_filings(cik, client) # list[FilingRecord], DESC sorted, pure (no disk)
    path = write_filings(cfg.slug, records) # data/<slug>/filings.json (atomic, bare JSON list)
    print(cfg.slug, "->", len(records), "filings @", path)
```

## Exact next step — Prompt 2 (PARSE: info-table XML → PositionRecord)

1. For each `FilingRecord`, fetch `{record.filing_index_url}index.json` (via the SAME `EdgarClient`, `get_json`) to enumerate the filing's documents and locate the **information-table XML** (do NOT assume `primary_doc` is the info table — it is typically the cover-page XML).
2. Fetch that XML with `client.get_text(...)` and parse the information-table rows → `PositionRecord` (add the dataclass in `models.py` at the documented placeholder; per spec §1.3; give it `to_dict`/`from_dict`).
3. Fill the deferred `FilingRecord` fields: `total_portfolio_value`, `position_count`, and refine `amendment_type` (restatement vs additive) — produce updated records via `dataclasses.replace(record, ...)` (FilingRecord is `frozen=True`; never mutate).
4. Persist positions to `data/<slug>/positions.json` (add a `write_positions`/`read_positions` pair in `storage.py` following the `filings.json` atomic-write + path-safety pattern).

## Key carried-forward decisions / risks (plan §15)

1. **Single-client reuse is REQUIRED.** The rate-limiter (token bucket, capacity 1, 9/s) lives on the `EdgarClient` instance. A fresh client per CIK resets the bucket and can trip SEC's rolling-window block. Build ONE client and pass it to every `discover_filings` call (and reuse it in Prompt 2's index/XML fetches). This is why `discover_filings`'s `client` param has no default.
2. **`filing_index_url` is the seam to the XML.** The info-table XML filename is NOT in submissions JSON. Prompt 2 MUST fetch `{filing_index_url}index.json` to find it. `primary_doc` is carried but is not guaranteed to be the info table.
3. **`FilingRecord` is frozen** — updated records via `dataclasses.replace(record, ...)`, never mutation.
4. **Options vs equity totals.** `total_portfolio_value` will eventually need TWO denominators (reported vs equity-only); `FilingRecord` currently has a single field. Prompt 2 may need to add `total_equity_value_thousands` via schema extension (again, produced via `replace`). Equity and options must stay separate tracks (CLAUDE.md).
5. **`amendment_type` + `latest_filing_per_period` are PROVISIONAL.** Supersession-by-acceptance is the spec default but unsafe for additive amendments. Implement TRUE supersession in Prompt 2 once `amendment_type` and info-table contents are known; don't build view logic distinguishing restatement vs additive until then.
6. **`acceptanceDateTime` is treated as UTC** (naive timestamps assumed UTC) for deterministic sorting; revisit (`_parse_acceptance` → US-Eastern) only if a later prompt needs wall-clock-accurate intraday timing.
7. **`REPO_ROOT = parents[2]`** assumes an editable checkout; a site-packages install would break path resolution (out of scope).
8. **Recursive `JSONValue` alias accepted** by mypy 2.1.0; fallback to `dict[str, object]` + boundary narrowing is the documented escape hatch if a future mypy rejects it.
