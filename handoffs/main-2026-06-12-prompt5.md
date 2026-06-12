# Handoff — Prompt 5 (EODHD prices + filing-date-anchored returns + SPY)

## What Prompt 5 delivered
- **`price_types.py`** — `PriceBar`, `SymbolSeries`, `WindowExtrema` (no persistence), `PriceClient`
  + `PriceProvider` Protocols. Stdlib-only (acyclic).
- **`eodhd_client.py`** — `EodhdClient.from_env()`; `_get` owns throttle/retry (one token/attempt,
  Retry-After else per-minute backoff); 404 → empty SymbolSeries, other 4xx → EodhdError; top-level
  must be a list; dedupe-last + WARN; bool/numeric-string-rejecting narrowers; token never logged;
  `api_token=None` omits the param.
- **`symbol_map.py`** — `to_eodhd_symbol` (.US suffix, class-share single-pass, 2-letter exchange
  passthrough with non-.US WARN) + `load_symbol_overrides` (full-EODHD-symbol values, never crashes).
- **`price_cache.py`** — global per-symbol cache I/O (versioned wrapper, best-effort reads) +
  `CachingPriceProvider` (owns normalization/overrides/today/cache/field-selection/alignment).
- **`returns.py`** — `compute_returns(changes, provider) -> list[ReturnRecord]` (disk-free).
- **`models.py`** — `ReturnRecord` (+ `_optional_date`); **`storage.py`** — `write_returns`/
  `read_returns`; **`errors.py`** — `EodhdError`; **`constants.py`** — all EODHD consts + path helpers.
- Tests: +154 (499 total). `tests_live/test_returns_live.py` validates the live API (run manually).
- **mypy strict: clean (40 files). pytest: 499 passed.**

## Compose snippet (one client → provider → engine → storage)
```python
from datetime import date
from celebpm.eodhd_client import EodhdClient
from celebpm.price_cache import CachingPriceProvider
from celebpm.storage import read_changes, write_returns
from celebpm.returns import compute_returns

run_today = date.today()                                   # the SINGLE today for the run
client = EodhdClient.from_env()                            # ONE shared client per run
provider = CachingPriceProvider(client, today=run_today)   # owns today + normalization +
#                                                            overrides + the global cache; SPY reused
changes = read_changes(slug)
records = compute_returns(changes, provider)               # reads provider.today; passes RAW tickers;
#                                                            passes SPY_BENCHMARK_SYMBOL as the SPY ticker
write_returns(slug, records)
# NOTE: if you change a symbol override (or correct a symbol that previously cached as an EMPTY
# series), DELETE that symbol's data/price_cache/<symbol>.json — the old/empty cache is
# authoritative over its [requested_from, requested_to] range and will not refetch on its own.
```

## Exact next step — Prompt 6 (View 1: New Ideas Feed CSV)
- Read `returns.json` → emit View 1 CSV. **Compute excess-return columns HERE** (NOT in Prompt 5):
  `excess_filing_to_filing_pct = filing_to_filing_return_pct − spy_filing_to_filing_return_pct` and
  the high/low analogues. **When the SPY trio is None (per-window gap), render "benchmark N/A" — NEVER
  compute `position − None`.**
- Surface `is_underlying_price` to LABEL option rows; keep **equity and options in separate views**
  (never aggregate options notionals with equity). Surface `cumulative_return_pct` for long-duration
  ideas.
- A `security_name` column (NOT on ReturnRecord) would be sourced in Prompt 6.
- Build the thin orchestrator wiring discover → parse → resolve → diff → returns → views (the compose
  snippet above is the returns leg). Orchestrator was NOT built in Prompt 5.

## Carried flags
- **SD-2 accept-as-reported** — returns come from EODHD prices ONLY; `value_reported` is never used
  to derive price.
- **ticker is display-only** — CUSIP is the join/chain key; cumulative prices both endpoints under
  the LAST-held row's ticker (mid-chain rename caveat, L14).
- **EODHD F6 (rate limits) UNVERIFIED beyond the probe** — `EODHD_REQUESTS_PER_MINUTE=60.0` is a
  conservative guess (tunable in constants.py). `tests_live/test_returns_live.py` exercises the real
  API and can be run manually now that the key is present (F1–F5 + adjusted-close + F7 shape).
- **Full-span refetch cost on daily runs (L12)** — a rule-4 refetch (a `today` lookup whose cache
  requested_to is now in the past) re-fetches the FULL [history_start, today] span per affected
  symbol per new run-day. Bounded; incremental append is a future optimization (L7).
- **Empty-series caches are authoritative-for-their-range (L9)** — delete the file to retry a 404/[]
  symbol after fixing an override.
