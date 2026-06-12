# 13F Analysis Pipeline — Implementation Notes

Companion to `docs/specs/13f_analysis_pipeline_spec.md`. Decisions, deviations, tradeoffs, and open questions logged during the Phase-1 multi-prompt build (one timestamped section per prompt). Spec deviations (SD-1…SD-5) are tracked in the build workdir's `spec-deviations.md`.

---

## 2026-06-11 21:39:04 — Prompt 1 (scaffolding + config + EDGAR discovery)

### Plan §13 required log items
- **D0.7 HTML→JSON spec override.** Used `data.sec.gov/submissions/CIK##########.json` (structured JSON), NOT the spec's `cgi-bin/browse-edgar` (HTML) or `efts.sec.gov` full-text. CLAUDE.md "no HTML scraping" + prompt constraints override the spec here. Endpoints live in `constants.EDGAR_SUBMISSIONS_BASE` / `EDGAR_ARCHIVES_BASE`.
- **D0.4 value/count deferral.** `FilingRecord.total_portfolio_value` and `position_count` are `int | None = None`; both come from summing info-table XML rows in Prompt 2. Discovery never fetches/parses XML — keeps it to ≥1 EDGAR request per CIK.
- **D0.8 amendment_type=unknown.** Cannot distinguish restatement vs additive from submissions JSON. Originals → `AMENDMENT_TYPE_NONE` (""), amendments → `AMENDMENT_TYPE_UNKNOWN` ("unknown"). Prompt 2 refines.
- **D8.1 filing_index_url strategy.** Replaced the misleading always-None `info_table_xml_url` with `filing_index_url`, deterministically built now from unpadded int CIK + dash-stripped accession (`constants.filing_index_url`). Prompt 2 fetches `{filing_index_url}index.json` to locate the info-table XML; must NOT assume `primary_doc` == info table (`primary_doc` kept but is the cover-page doc in practice).
- **D10.1 overflow shape + merge + dedup.** `filings.files[]` entries are objects `{name, filingCount, filingFrom, filingTo}`; URL via `submissions_overflow_url(name)` (validates `OVERFLOW_NAME_PATTERN`). Overflow files carry the parallel arrays at the TOP LEVEL (not under `filings`). All rows merged (recent + every overflow), then DEDUPED by `accession_number` (recent wins via `setdefault`), then filtered to TARGET_FORM_TYPES. Fixture deliberately includes a duplicate accession to test dedup.
- **D10.2 skip vs abort.** Structural payload break (unequal parallel-array lengths, missing required array, overflow nested under `filings`, non-list array) → ABORT with `DiscoveryError`. Individual target-form row missing/empty a REQUIRED field (form/accessionNumber/filingDate/reportDate/acceptanceDateTime) → SKIP + WARNING + skip-counter; `primaryDocument` NOT required (stored ""). Non-target forms filtered BEFORE per-row validation (no spurious warnings).
- **D10.3 tz-aware acceptance + no-tz⇒UTC.** `_parse_acceptance` always returns tz-aware UTC: Z/offset → parse + `.astimezone(utc)`; no-tz → `.replace(tzinfo=utc)` (documented assumption — EDGAR acceptance is actually US-Eastern; UTC chosen for deterministic sorting; revisit if intraday timing ever needed). Empty/malformed acceptance → row skipped (not abort). Guarantees the `(filing_date, accepted_date, accession_number)` sort tuple never mixes naive/aware datetimes. Same logic mirrored in `models._parse_dt_with_tz` for round-trip.
- **D0.1 constants in package.** All importable config is `src/celebpm/constants.py`; `config/investors.json` is the only root `config/` artifact (data file, no `__init__.py`, loaded by path from `REPO_ROOT`). No `types.py` (JSON aliases live in constants).
- **D0.11 Protocol seam + required client.** `HttpClient` Protocol (NOT `@runtime_checkable`); `discover_filings(cik, client)` has a REQUIRED `client` param (no default → no accidental live calls). Conformance asserted STATICALLY via `_check: HttpClient = EdgarClient()` in the test module (mypy verifies; no runtime isinstance). `FakeClient` in conftest structurally satisfies the Protocol.
- **D0.3 token-bucket capacity-1 + single-client reuse.** `_TokenBucket` capacity = `EDGAR_BURST_CAPACITY` (1.0), refill 9.0/s → first acquire instant, every subsequent call spaced ~111ms (no startup burst of 9). No threading lock (single-threaded). Limiter state lives on the `EdgarClient` instance → multi-CIK workflows MUST reuse ONE client (documented in client docstring + flagged for Prompt 2/orchestrator). Every HTTP attempt (incl. retries) calls `acquire()`.
- **D-mypy types-requests.** `requests` does NOT ship `py.typed`; added `types-requests` to dev extra. mypy `strict=true` (no `disallow_any_explicit`); no preemptive pandas override.
- **D-types recursive alias outcome: ACCEPTED.** mypy 2.1.0 strict accepts the recursive `JSONValue` `TypeAlias` cleanly (verified standalone before building the rest, and in the full 17-file run). No fallback to `dict[str, object]` needed.
- **D0.6 latest_filing_per_period PROVISIONAL.** Keeps latest `accepted_date` per `period_of_report`; tie-break = larger `accession_number`; result sorted by period DESC. CAVEAT (in docstring + test comment): unsafe for additive amendments; TRUE supersession deferred to Prompt 2. Downstream must not treat as final.

### Spot decisions (plan silent)
- **`EdgarClient(sleep_func=...)` param added.** The plan injected time/sleep only on `_TokenBucket`. To keep the Retry-After / backoff client tests free of real sleeps (no HTTP-level mocking, per CLAUDE.md), I added `sleep_func: Callable[[float], None] = time.sleep` to `EdgarClient.__init__`, threaded into the bucket and `_backoff`. Production default unchanged (`time.sleep`).
- **`_TokenBucket.acquire` fake-clock grant.** When an injected `sleep_func` does not advance the injected clock (test fakes), after computing the wait the bucket explicitly grants the awaited token (tokens→1.0) so timing assertions are deterministic. Equivalent to the real `time.sleep`/`time.monotonic` path where the clock advances during sleep.
- **`session.get` monkeypatch ignore code.** The sanctioned session-level retry test triggers mypy `[assignment]` (not `[method-assign]`) due to the precise `requests` stub `get` signature. Used `# type: ignore[assignment]` with a justification comment. This is the single sanctioned session-level seam; no other HTTP-level mocking exists.
- **Non-object overflow payload test.** Since `FakeClient.get_json` is typed to return `JSONObject` (dict), the literal non-dict-overflow case can't route through it; exercised the equivalent boundary failure with a scalar-valued `form` array → `DiscoveryError`. The non-dict top-level JSON case is guarded + unit-tested in `EdgarClient.get_json` (`test_non_object_json_raises`).
- **`models._optional_int` rejects bool.** `bool` is an `int` subclass; explicitly rejected so `True`/`False` don't silently coerce into `total_portfolio_value`/`position_count`.

---

## 2026-06-11 22:33:04 — Prompt 2 (PARSE FILINGS) execution

- **Fetch/parse split (fix #1).** Three single-responsibility functions in `celebpm.parser`: `locate_and_fetch_infotable` (the SOLE info-table fetch site — one `get_json` for index.json + one `get_text` for the XML; returns `(xml_text, index_payload)` ONLY, no `used_fallback` flag); `parse_positions_from_xml` (PURE, no client, no I/O); `refine_amendment_type` (one `get_text`, reuses the threaded `index_payload`, NEVER a second `get_json`). Intended orchestration: locate → (if amendment) refine → parse, so the ADDS-totals WARN fires correctly because refine runs before parse. `get_json`-called-exactly-once asserted both per-call and across the full flow.
- **One record per (cusip, security_type) — STRICT uniqueness (fix #2).** `_aggregate` groups by `(cusip, security_type)`, preserving first-seen order. COMMON+CALL on the same name → two records (equity/options separation is absolute). No genuine SH/PRN mix (all SH-side / all PRN / all "") → sum value AND shares over ALL rows. Genuine SH-vs-PRN mix (≥1 SH-side where "" counts as SH AND ≥1 PRN) → keep MAJORITY-type rows only (ties→SH), sum BOTH value and shares over the kept rows, DROP minority rows entirely (value AND shares — information loss), loud WARN. Never sub-keys, never duplicates a key. Verified: mixed fixture (2 SH @100k/200k vs 1 PRN @999k) → ONE record value=300000 shares=3000 type=SH.
- **value_reported / total_equity_value rename (SD-3) + as-reported units (SD-2).** Spec's `value_thousands` renamed to `value_reported`; FilingRecord equity total is `total_equity_value` (no `_thousands`). Value stored EXACTLY as EDGAR reports it; no thousands-vs-dollars conversion or cutoff guess (SD-2 still operator-open). Both already documented in `spec-deviations.md`.
- **Dual weights + options→None invariant.** `total_portfolio_value` = sum all aggregated (incl. options notional); `total_equity_value` = sum COMMON only; `position_count` = distinct (cusip, security_type) post-agg/post-skip. `weight_pct_reported = value/total_portfolio_value*100` (zero-total guard → 0.0 + WARN). `weight_pct_equity_only`: COMMON → value/total_equity_value*100 (zero-equity guard → 0.0); PUT/CALL → None (never 0.0). `PositionRecord.__post_init__` enforces COMMON⇒not-None / option⇒None. FilingRecord updated via `dataclasses.replace`.
- **Zero-row info table (fix #1).** Plain WARN ("parsed to zero rows"); returns replace-updated FilingRecord (totals 0, count 0) + empty list. No `used_fallback` plumbing anywhere.
- **UNKNOWN-amendment = future-restatement guidance + deferred merge (§6.1/§6.2).** `refine_amendment_type` records the honest sentinel (RESTATEMENT/ADDS, else leave UNKNOWN). The "treat UNKNOWN as restatement; only explicit-ADDS is additive" semantics + the additive merge + period supersession are DEFERRED to the consuming prompt — NOT built here. `latest_filing_per_period` stays provisional. Cover-page selection NEVER aborts (ambiguous/absent/unparseable/non-XML → UNKNOWN + WARN). amendmentType normalized via strip+upper (fix #8); first amendmentInfo → first amendmentType.
- **CUSIP alphabet relaxation (fix #5).** Validate `len==9` + uppercase + every char in `[A-Z0-9*@#]` via `CUSIP_PATTERN` (NOT isalnum, which would wrongly drop `*`/`@`/`#`). Same set used in the row-skip filter (parser) and the construction guard (PositionRecord). Special-char CUSIP `1234*6@#9` verified KEPT; `SHORT`/lowercase skipped/rejected with detail logged.
- **Original-case filename return (fix #3).** `select_infotable_filename` matches case-insensitively (compares `name.lower()`) but RETURNS the original-case name (EDGAR Archives URLs are case-sensitive). `Form13FInfoTable.XML` verified returned verbatim and used in the built XML URL.
- **index.json single-dict normalization (fix #4).** `directory.item` may be a single dict instead of a list → wrapped to `[item]`. Non-dict / no-string-name items skipped. Missing/non-dict `directory`, or `item` neither dict nor list → DiscoveryError. After filtering, no `.xml` candidates → DiscoveryError.
- **Selection priority.** Info-table hint match wins: exactly one hinted `.xml` → return it; >1 → DiscoveryError (ambiguous, never index-pick). No hint → cover-page exclusion (drop primary_doc + COVERPAGE_NAME_HINTS); exactly one → return; >1 or zero → DiscoveryError. Info-table directories abort on ambiguity; cover-page selection (refine) never aborts.
- **Float-tolerant numeric parse (fix #14).** `int(round(float(s.strip())))` for value/sshPrnamt; catch BOTH ValueError and OverflowError; `math.isfinite` guard rejects inf/-inf/nan BEFORE rounding. `"12345.00"`→12345, `"100.0"`→100; `"inf"`/`"nan"`/`""` → row skip. No Decimal (float64 exact for sub-2^53 integers).
- **sshPrnamtType handling (fix #10).** empty/missing → default "SH"; exactly SH/PRN → keep; any other present value (e.g. "SHARES") → normalize to "" + WARN (not an abort; "" is valid in __post_init__). "" counts as SH-side in the mix detection, never a PRN presence.
- **putCall.** empty/absent → COMMON, put_call=""; PUT/CALL → option; any other → row skip + WARN.
- **Two-level field extraction.** Top-level fields from DIRECT children of `infoTable`; sshPrnamt/sshPrnamtType from the `shrsOrPrnAmt` child's children. Multiple same-local-name direct children → take first + WARN (`_direct_child_text`/`_find_direct_child`). Namespace-robust via `_local_name` (strips `{uri}`); verified identical parse across two different NS URIs and with no namespace.
- **Removed dead constants (fix #11).** Did NOT add `NON_XML_COVERPAGE_SUFFIXES`, `COVERPAGE_IS_AMENDMENT_LOCALNAME`, or NS-URI sets. `"table"` omitted from `INFOTABLE_NAME_HINTS`.
- **Deterministic write ordering (fix #12).** `write_positions` sorts by `(period, cusip, security_type)` before serializing → byte-identical files across input orders (asserted).
- **Trailing-slash guard (fix #13).** `filing_index_json_url` raises ValueError if `filing_index_url` lacks a trailing `/`.
- **Storage refactor.** `_safe_filings_path`→generic `_safe_path` + thin wrapper (strict behavioral no-op; existing storage tests unchanged). Shared `_atomic_write_json` extracted; `write_filings` now delegates to it (filings round-trip behaviorally identical). `read_positions` missing-file → DiscoveryError (contract unchanged); incremental caller catches it as empty first-run history (documented + tested).
- **total_equity_value schema-test verification (fix #6).** Re-ran Prompt 1's FilingRecord/storage tests after adding the key — none asserted an exact key set, so no Prompt 1 test edits were required. Added explicit tests: new-key round-trip + old-dict-without-key parses as None (None-tolerant from_dict).
- **Public/internal API surface (fix #15).** No `_select_infotable -> tuple[str, bool]`, no `used_fallback`, no `resolve_period_filings`/`_PeriodResolution`, no `parse_filing_positions`.

### Spot decisions (plan silent)
- Added `_optional_str` to models (plan assumed it existed for `ticker`; Prompt 1 had none). Mirrors `_optional_int`.
- Added `constants.positions_path` alongside `filings_path` (plan named only `POSITIONS_FILE`).
- Extracted `_atomic_write_json` shared by both writers (DRY; no behavior change for filings).
- `FakeClient` extended with `json_calls`/`text_calls` (plus the existing `calls`) for unambiguous get_json-once assertions.
- Test typing shims (`_json` → JSONObject; `_as_obj` widens to_dict output to `dict[str, object]` for from_dict, since dict is invariant). Test-only.

---
## [2026-06-12 01:09:07] Prompt 3 completed (second execution pass)

Prompt 3 (CUSIP→ticker resolution via OpenFIGI) was completed across TWO execution passes.
Pass 1 wrote ratelimit.py / openfigi_client.py / cusip_map.py + models/errors/constants
additions. This pass (pass 2) finished the remaining work and made it green.

### Fixes / corrections this pass
- **_TokenBucket explicit re-export**: mypy strict rejects `from celebpm.ratelimit import
  TokenBucket as _TokenBucket` as an implicit reexport. Changed edgar_client.py to a plain
  `from celebpm.ratelimit import TokenBucket, parse_retry_after` + explicit module-level
  assignments `_TokenBucket = TokenBucket` / `_parse_retry_after = parse_retry_after`.
  tests/test_edgar_client.py unchanged and passing.
- **parse_retry_after root-cause bug**: the lifted parser called
  email.utils.parsedate_to_datetime() unguarded; on Python >=3.10 that RAISES ValueError on
  an unparseable value (it does not return None). Plan requires None for unparseable. Wrapped
  in try/except (ValueError, TypeError) -> None. Integer-seconds + HTTP-date + None/blank all
  covered by new tests/test_ratelimit.py. EDGAR Retry-After behavior preserved through this path.
- **storage cusip-map**: added read_cusip_map (missing->{}, bare-list-on-disk->dict-keyed,
  duplicate->DiscoveryError, forward-compat optional fields) and write_cusip_map (dict|list both
  validated, sorted bare list, atomic, path-safe). Extracted _assert_under_root(root, target)
  that resolves BOTH paths; refactored _safe_path to call it (behavior-identical; existing
  traversal tests unchanged). cusip_map_path uses unresolved REPO_ROOT/DATA_ROOT when data_root
  is None, but _assert_under_root resolves both sides so containment holds.
- **FakeMappingClient** added to conftest (settable max_jobs_per_request; records call_count +
  chunks; raise-on-Nth-call for partial-success). Static MappingClient conformance asserted.

### Key Prompt-3 decisions (carried from the v4 plan, re-affirmed)
- Dropped cross-quarter conflict machinery; replaced with present-time ambiguity (>1 distinct
  ticker in the strongest surviving tier of one query) -> ambiguous=True + WARN, surfaced on
  cache hits too. Point-in-time historical ticker drift is NOT observable without a historical
  security master (open question for operator).
- Transient-vs-permanent split: in-payload whitelisted miss (OPENFIGI_MISS_WARNINGS, normalized
  lower+strip) or empty data:[] -> permanent unresolved (cached); in-payload error string or an
  unrecognized warning or any structural failure -> OpenFigiError (TRANSIENT, retry next run,
  NOT cached) so the cache is never poisoned.
- UNFILTERED query (no exchCode on the job); all US preference in select_match.
- from_env: blank/whitespace OPENFIGI_API_KEY treated as absent -> no-key mode.
- In-place cache mutation (result.cache is cache; no per-investor deep copy) + partial-success
  (whole-chunk-then-merge; only OpenFigiError caught, all else propagates). Compose snippet
  persists cache after each investor (documentation only — no orchestrator built this prompt).
- Don't-clobber: a real ticker in cache wins via dataclasses.replace; unresolved / not-yet-reached
  leaves the position's existing ticker unchanged (never overwrite a ticker with None).
- resolved_at = now().isoformat() (tz-aware UTC w/ offset), called ONCE per run, shared by all
  entries written that run.
- The client owns alignment via the positional length-guard; the resolver has NO alignment
  re-check and merges by the client-assigned MapResult.cusip.

---

## Prompt 4 — QoQ Diff & Change Classification (2026-06-12 01:55:34)

- **First-quarter baseline emits NO records.** `compute_changes` treats the earliest period as a
  BASELINE: it is never passed as a current side, so it produces no PositionChange rows. Baseline
  holdings live in `positions.json` and are read from there by downstream consumers (Prompt 6).
  Emitting the first quarter as all-NEW would pollute View 1 / Conviction / return windows with
  spurious entries.
- **NEW carries a real prior_period.** Because every emitted row comes from a Q[i-1]→Q[i]
  transition, a NEW row carries the prior quarter it is new RELATIVE to (`prior_period` /
  `prior_filing_date` non-None) with `prior_shares/value/weight` = None and all deltas None.
- **Non-nullable prior_period/prior_filing_date schema.** Both are `date` (NOT `date | None`) on
  PositionChange, including NEW rows. Drove the decision to add only `_require_date` (NO
  `_optional_date` — it would be dead code).
- **split ⇒ HOLD short-circuit.** `classify_change` computes `split_suspected` (COMMON-only)
  first, then returns `(HOLD, True)` IMMEDIATELY before the threshold cascade. The strict
  `split_suspected ⇒ change_type == HOLD` invariant in `__post_init__` is now mechanically
  guaranteed, robust to any future band/threshold tuning. Verified with a +9999bps weight test.
- **shares_delta_pct is None ⇒ HOLD.** A matched row with `prior.shares == 0` has
  `shares_delta_pct = None` (no ZeroDivisionError). Such a row is NOT drift-eligible (share intent
  unprovable) and falls through to HOLD, regardless of weight.
- **weight_pct_reported feeds thresholds; exact strict operators.** Thresholds use
  `weight_pct_reported` (NAV weight; `current_weight_pct`/`prior_weight_pct`). STRICT `>` /
  `<` at +10/-10% shares and +50/-50bps weight (boundary values are NOT active/drift); the
  shares-drift band is INCLUSIVE `<=`. No float epsilon.
- **SD-3 value_reported naming.** PositionChange fields are `current_value_reported` /
  `prior_value_reported` (matching PositionRecord's SD-3 `value_reported`), diverging from spec
  §1.4's stale `*_value_thousands`. Classification LOGIC is exactly the spec table; only the field
  NAMES diverge.
- **SD-2 value_delta artifact + split-collision limitation.** `value_delta`/`value_delta_pct` at
  the SEC thousands→dollars boundary quarter are a ~1000× artifact (≈ +100,000%), NOT a real change.
  Classification is unaffected (it reads only `shares_delta_pct` + `weight_delta_bps`, both
  unit-independent). The split value-gate SEES the huge artifact and returns False, so no false
  split at the boundary. LIMITATION: a genuine 2:1 split landing in the SAME quarter as the units
  boundary → value_delta_pct huge → split NOT detected → classifies as ACTIVE_ADD. Rare; documented.
  The large-but-finite value passes `__post_init__` (finite guard only; tested).
- **Multi-accession in a period → RAISE.** `compute_changes` (and `diff_quarters` per side) raise
  DiscoveryError when a period spans >1 `accession_number` (or has a duplicate (cusip,
  security_type), or mixed filing_date). No select-latest, no merge. This validation runs for EVERY
  period INCLUDING a single baseline-only period, BEFORE the <2-periods short-circuit, so a corrupt
  baseline-only investor fails loud rather than silently returning [].
- **0-share CURRENT position is a HOLDING, not an EXIT.** A (cusip, security_type) present in BOTH
  quarters with `current.shares == 0` is reported in the filing → classified NORMALLY (matched,
  typically ACTIVE_TRIM via -100% shares when weight also drops). EXIT means ABSENT from the current
  filing, not present-with-zero. Flagged for Prompt 6: the Exit view may want to treat a 0-share
  ACTIVE_TRIM as exit-like.
- **Full-liquidation / empty-quarter invisibility.** A quarter with ZERO reportable holdings yields
  no PositionRecords → invisible to the period-derived timeline. Consequences: a 100%-liquidation
  quarter generates NO EXIT rows; a final all-out quarter vanishes; an empty EARLIEST quarter makes
  Q2 silently become the baseline. Representing any of these would need the FilingRecord period list
  passed into `compute_changes`. OUT of scope here; N/A for the two concentrated target funds.
- **filing_date ordering NOT enforced.** `__post_init__` enforces only `prior_period < period`;
  `prior_filing_date` vs `filing_date` is unconstrained (SEC amendments/late filings can reorder
  filing dates). Tested: a row with prior_filing_date > filing_date but prior_period < period
  constructs successfully.
- **ticker fallback uses `is not None`, not `or`.** Matched row:
  `ticker = current.ticker if current.ticker is not None else prior.ticker`. NEW carries current's
  ticker; EXIT carries prior's; both-None → None.

### Spot decisions (plan silent)
- `compute_changes` groups periods via `collections.defaultdict(list)`; periods sorted ascending
  before iteration (deterministic).
- Factored a private `_side_anchor` helper (single-cik/period/filing_date/accession + unique-key
  validation, returns the key map + anchors) shared by both sides of `diff_quarters` — avoids
  duplicating the per-side validation. Behavior is exactly the per-side contract in the plan.
- EXIT branch carries `assert prior is not None` purely as a mypy narrowing aid (the union key
  with current absent guarantees prior present); not a runtime guard.
- In test_models.py reused the existing `_as_obj` widening helper for `from_dict` calls over
  `to_dict()` output (dict invariance under mypy strict), matching that file's convention.

---

## 2026-06-12 11:21:09 — Prompt 5 implementation (EODHD prices + returns + SPY)

Implemented v5 plan exactly. Key decisions / mechanisms recorded:

- **Cache hard-floor + per-call rule (price_cache.CachingPriceProvider):** EODHD_HISTORY_START =
  date(2018,1,1) is a HARD FLOOR. price_asof order: (1) on>today → None no-fetch (checked FIRST);
  (2) on<floor → None, cache HIT (no fetch) — kills the refetch loop below the floor; (3)
  floor≤on≤cached requested_to → serve from cache; (4) on>requested_to (≤today) → refetch
  [floor,today], overwrite file, UPDATE the in-memory memo. window_extrema clamps start to the
  floor, refetches when end>requested_to, ValueErrors on start>end. Post-IPO symbol (first bar after
  the floor) asked for a sub-first-bar date returns None because it is before the first bar (not the
  floor) and stays a hit — no loop.
- **schema_version in the cache-FILE WRAPPER** ({"schema_version":N,"series":{...}}), NOT on
  SymbolSeries. read_price_cache compares series["symbol"] on the RAW dict BEFORE from_dict; ANY
  corrupt/version-mismatch/symbol-mismatch/bad-fetched_at/dup/non-ascending cache → MISS (None),
  never raises. Bad symbol on WRITE → EodhdError; on READ → None.
- **Cumulative spans to EXIT (returns._compute_cumulatives/_emit_cumulative):** chains = runs of
  consecutive non-EXIT changes per (cusip, security_type) ordered by filing_date; EXIT terminates a
  chain and supplies END=its filing_date; still-held → END=provider.today; placed on the LAST-HELD
  row using THAT row's ticker for both endpoints (mid-chain rename caveat L14). first denominator
  ≤0/None or end None → cumulative None. Re-entry after EXIT = a new chain. Length-1 still-held and
  single-quarter-then-exit both get a cumulative (REPLACES v4's "single-quarter → None").
- **Delisting carry-forward (returns._compute_one):** extrema is NOT an unpriced trigger. If
  window_extrema is None but both endpoints resolved (carry-forward) and price_on_filing_date>0 →
  PRICED, next_period_high/low = max/min(endpoints) with endpoint dates + WARN. UNPRICED = symbol
  None OR filing denom None/≤0 OR next endpoint None. Same endpoint-derivation applied to SPY.
- **0.0 / denominator handling:** provider "usable" = chosen-field non-None AND ≥0 (0.0 is a valid
  bankruptcy close; included in the view, has_series_data, window_extrema). Engine rejects 0.0 ONLY
  as a denominator (filing price ≤0 → unpriced; entry-low ≤0 → entry fields None). 0.0 numerator →
  −100%. ReturnRecord price invariant is finite + ≥0 (NOT >0); returns sign-unconstrained.
- **Per-symbol transport-error isolation:** _compute_one may raise EodhdError; the compute_returns
  loop catches it for a NON-SPY symbol → priced=False + logger.error + continue (not cached →
  retries next run). SPY preflight (has_series_data False OR a transport EodhdError) is the ONLY
  fatal path → raises EodhdError.
- **Coverage-threshold adjusted fallback (CachingPriceProvider._usable_view):** coverage = usable-
  adjusted bars / total; <0.5 → raw close for ALL bars (WARN once), else adjusted per-bar (skip the
  rare unusable bar). Never mixed within a symbol. Boundary 0.5 → adjusted. Memoized per symbol;
  invalidated on a rule-4 refetch.
- **Provider-owns-normalization seam:** returns.py is disk-free + override-free; passes RAW
  change.ticker to the provider, which owns to_eodhd_symbol + overrides (loaded once),
  the cache, field selection, alignment, and `today` (frozen at construction; validated
  history_start ≤ today). eodhd_symbol audit field set via provider.resolve_symbol.
- **SPY convention:** engine passes the literal SPY_BENCHMARK_SYMBOL ("SPY.US") as the ticker arg;
  the provider normalizes it (.US passthrough). No sentinel/special branch. Same coverage +
  denominator->0 formula as positions; per-window gap → SPY trio None + WARN (position fields set).
- **price_types.py:** stdlib-only (datetime/dataclasses/typing) — NO constants import (acyclic).
  WindowExtrema has NO to_dict/from_dict (transient compute result). SymbolSeries.from_dict raises
  on shape violations (best-effort cache path); the LIVE client uses _parse_series which raises
  EodhdError (different error contracts; _parse_series NEVER calls from_dict).
- **EODHD F1–F5 VERIFIED via the live orchestrator probe** (host/path, ?api_token= query param,
  top-level JSON list, row keys incl. adjusted_close snake_case with adjustment applied, inclusive
  from/to). F6 (rate limits) best-effort/UNVERIFIED beyond the probe; F7 (404/empty shape) handled
  structurally (404→empty SymbolSeries) + observed by the live test. api_token=None OMITS the param
  → 401 → EodhdError. Token value never logged.

### D5.x decisions confirmed
- D5.1 entry window = calendar quarter [quarter_start(period), period] (arithmetic quarter_start).
- D5.2 EXIT emits a priced=False row but supplies the terminating END to the preceding held row's
  cumulative.
- D5.3 cumulative span+placement = first-held filing → (EXIT filing_date | today) on the last-held
  row (REPLACES v4's single-quarter→None).
- D5.5 adjusted close via coverage-threshold (ADJ_CLOSE_MIN_COVERAGE=0.5) at the symbol level.

### Spot decisions where the plan was silent
- _unpriced_record sets eodhd_symbol=None for a transport-error record (resolution untrusted on a
  transport failure); EXIT rows restore the resolved symbol via dataclasses.replace.
- window_extrema high/low tie-break: equal prices → high picks the later date, low the earlier date
  (deterministic; plan only required high/low + dates).
- SymbolSeries.from_dict validates fetched_at parses (raises → cache MISS) per the plan; the parsed
  datetime is otherwise unused (provenance-only).
- Reused the existing test_models `_as_obj` widening helper for ReturnRecord round-trip from_dict
  calls (dict invariance under mypy strict).

---

## Prompt 6 — View 1 + end-to-end orchestrator (2026-06-12 11:51:03)

- **View-1 join keys.** NEW→ReturnRecord: `(cusip, security_type, filing_date, ChangeType.NEW)`
  (matches returns.json's own 4-tuple dedup key → unique). NEW→PositionRecord (company):
  `(cusip, security_type, period == change.period)`. Hold-chain group key: `(cusip, security_type)`.
- **Hold-chain semantics (strict per-cycle slice).** For each NEW, walk only changes with
  `period > NEW.period`, STOP at the first EXIT. `quarters_held` = 1 (the NEW) + subsequent
  HELD changes (non-None `current_weight_pct`) before that EXIT — counts OBSERVED reporting
  periods, assumes no skipped filings (skips surface via `timeline_degraded`). `max_weight_pct`
  = max `current_weight_pct` over NEW + held (NEW is the floor). `exit_quarter` = first EXIT
  period after NEW else None ("CURRENT" in CSV). `became_active_add` = any ACTIVE_ADD with
  period > NEW.period in this cycle. A re-entry after EXIT is a separate NEW row with its own
  cycle (verified in test_re_entry_strict_slicing: Q1-NEW max over Q1+Q2 only, Q4-NEW over Q4+Q5).
- **Median-over-closed.** `median_holding_quarters` = median(quarters_held) over CLOSED NEWs
  only (`exit_quarter is not None`); still-held excluded as censored; None if no closed NEWs.
  Pure median (sort + mean-of-two for even counts); no numpy.
- **Win-rate denominator.** Population = NEW with non-None `filing_to_filing_return_pct`
  (clearer than the `priced` flag — an unpriced row has a None return and drops out). >0 win;
  ==0 in denominator only; <0 loser. avg winner/loser guard their empty sub-pop → None.
- **Excess only when both present.** `position − SPY` computed in the builder iff BOTH operands
  non-None (SPY trio is all-set-or-all-None per the model invariant). SD-5 caveat: the high/low
  excess columns are a relative heuristic (position high/low vs SPY high/low, NOT date-matched
  alpha) — carried into the summary JSON `notes` via the SUMMARY_NOTES constant.
- **is_option / is_underlying_price derived from the NEW's security_type, NOT the ReturnRecord** —
  so an unpriced option NEW (no ReturnRecord) is still correctly flagged (test_unpriced_option).
- **Summary as sibling JSON (SD-4).** `new_ideas_summary.json` next to `new_ideas.csv`, NOT
  footer rows (keeps the CSV a clean rectangular table; pandas round-trip safe).
- **Per-filing skip → timeline_degraded.** run_pipeline wraps locate/refine/parse per filing in
  `try/except (EdgarError, DiscoveryError)` → loud WARN + record `filing.period_of_report` into
  skipped_periods + continue. `timeline_degraded = n_filings_skipped > 0`. SPY preflight
  (non-empty changes) is FATAL and propagates; resolve partial is non-fatal (INFO log).
- **Empty short-circuit.** `returns = compute_returns(changes, provider) if changes else []` —
  belt-and-suspenders (compute_returns already early-returns [] before the SPY preflight on
  empty changes; verified). Empty investor → header-only CSV + all-None summary.
- **pandas confined to view_io.py** as the single justified `Any` boundary; `import pandas as pd`
  annotated `# pandas boundary: untyped`. Override added for BOTH `pandas` and `pandas.*`; no
  `# type: ignore` needed at the edge. Builder (views.py) is pandas-free.
- **Public safe_data_path.** Added `storage.safe_data_path(slug, filename, data_root)` — view_io
  uses it for BOTH the CSV and summary paths (no private `_safe_path` cross-module use). It
  asserts the resolved path is under `<data_root>/<slug>/` (filename may contain `views/`); a
  `../evil` slug raises DiscoveryError (test_path_safety_traversal_slug).
- **Spot decisions (plan silent):** `_build_dataframe` uses `from_records(..., columns=...)`
  (non-empty) / `DataFrame(data=[], columns=...)` (empty). `_write_csv_atomic` os.close's the
  mkstemp fd (pandas owns the path handle) then to_csv → os.replace, temp cleaned on failure.
  Integration test routes the amendment cover page to a benign `<edgarSubmission/>` so
  refine_amendment_type leaves UNKNOWN + WARN without aborting. Sort key
  `(-initial_weight_pct, cusip, security_type)` for DESC-weight, asc tiebreaks.
