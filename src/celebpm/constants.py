"""All non-secret tunables + JSON type aliases + pure path/URL helpers.

No secrets here (.env holds API keys; EDGAR needs none). Every URL/limit/timeout/
threshold/path lives here so there is one place to change (CLAUDE.md: no hardcoded values).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Final, TypeAlias

from celebpm.errors import DiscoveryError

# --- JSON typing (v3: lives here, no types.py) ---
# Recursive alias. Verified to type-check under mypy strict (see implementation-notes.md).
# If a future mypy rejects the recursion, fall back to `JSONObject = dict[str, object]`
# and narrow explicitly at the discovery boundary; log the choice in implementation-notes.md.
JSONValue: TypeAlias = (
    "str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]"
)
JSONObject: TypeAlias = "dict[str, JSONValue]"

# --- Repo root resolution (package lives at src/celebpm/constants.py) ---
# src/celebpm/constants.py -> parents[0]=celebpm, [1]=src, [2]=<repo root>.
# Documented assumption: we run from an editable checkout (pip install -e .), so the package
# stays inside the repo tree and parents[2] is the repo root.
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

# --- EDGAR identity (SEC requires "Name email" User-Agent) ---
OPERATOR_NAME: Final[str] = "celeb-pm research"
OPERATOR_EMAIL: Final[str] = "steve@collectifadv.com"
USER_AGENT: Final[str] = f"{OPERATOR_NAME} {OPERATOR_EMAIL}"  # do NOT change (accepted decision)

# --- EDGAR endpoints (structured JSON API only; NO HTML/cgi-bin) ---
EDGAR_SUBMISSIONS_BASE: Final[str] = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES_BASE: Final[str] = "https://www.sec.gov/Archives/edgar/data"

# --- Rate limiting / HTTP policy ---
EDGAR_RATE_LIMIT_PER_SEC: Final[float] = 9.0  # refill rate; safety margin below SEC's hard 10/sec
EDGAR_BURST_CAPACITY: Final[float] = 1.0  # v3: bucket capacity == 1 -> uniform ~111ms spacing
HTTP_TIMEOUT_SECONDS: Final[float] = 15.0
HTTP_MAX_RETRIES: Final[int] = 3  # number of RETRIES; total attempts = 1 + HTTP_MAX_RETRIES (v3)
HTTP_RETRY_BACKOFF_SECONDS: Final[float] = 0.5  # base for exponential backoff
HTTP_RETRY_STATUS: Final[frozenset[int]] = frozenset(
    {429, 500, 502, 503, 504}
)  # 403 NOT here (v3)

# --- Target form types ---
FORM_13F_HR: Final[str] = "13F-HR"
FORM_13F_HR_AMENDMENT: Final[str] = "13F-HR/A"
TARGET_FORM_TYPES: Final[frozenset[str]] = frozenset({FORM_13F_HR, FORM_13F_HR_AMENDMENT})

# --- Amendment type sentinels (see D0.8) ---
AMENDMENT_TYPE_RESTATEMENT: Final[str] = "restatement"
AMENDMENT_TYPE_ADDS: Final[str] = "adds new entries"
AMENDMENT_TYPE_UNKNOWN: Final[str] = "unknown"  # set by Prompt 1; refined in Prompt 2
AMENDMENT_TYPE_NONE: Final[str] = ""  # for non-amendments

# --- On-disk layout (see spec §Storage) ---
DATA_ROOT: Final[str] = "data"  # relative to REPO_ROOT; resolved via path helpers
FILINGS_FILE: Final[str] = "filings.json"
POSITIONS_FILE: Final[str] = "positions.json"  # Prompt 2
CHANGES_FILE: Final[str] = "changes.json"  # Prompt 4
RETURNS_FILE: Final[str] = "returns.json"  # Prompt 5
VIEWS_DIR: Final[str] = "views"  # Prompt 7

# --- View 1 (New Ideas Feed) output files ---
NEW_IDEAS_FILE: Final[str] = "new_ideas.csv"
NEW_IDEAS_SUMMARY_FILE: Final[str] = "new_ideas_summary.json"

# --- View 1 CSV rendering ---
CSV_NA_REP: Final[str] = ""  # None -> empty cell
EXIT_CURRENT_LABEL: Final[str] = "CURRENT"  # exit_quarter None -> still held
VIEW_TMP_PREFIX: Final[str] = ".newideas-"

# --- View 1 column order (single source of truth for the CSV header) ---
NEW_IDEAS_COLUMNS: Final[tuple[str, ...]] = (
    "quarter",
    "ticker",
    "company",
    "security_type",
    "is_option",
    "is_underlying_price",
    "initial_weight_pct",
    "best_case_entry_return_pct",
    "worst_case_entry_return_pct",
    "filing_to_filing_return_pct",
    "filing_to_next_period_high_pct",
    "filing_to_next_period_low_pct",
    "excess_filing_to_filing_pct",
    "excess_next_period_high_pct",
    "excess_next_period_low_pct",
    "cumulative_return_pct",
    "quarters_held",
    "max_weight_pct",
    "exit_quarter",
    "became_active_add",
    "priced",
    "cusip",
    "filing_date",
)

# --- View 1 summary JSON keys ---
SUMMARY_KEY_TOTAL_NEW: Final[str] = "total_new"
SUMMARY_KEY_PRICED_NEW: Final[str] = "priced_new"
SUMMARY_KEY_WIN_RATE_PCT: Final[str] = "win_rate_pct"
SUMMARY_KEY_AVG_WINNER: Final[str] = "avg_winner_return_pct"
SUMMARY_KEY_AVG_LOSER: Final[str] = "avg_loser_return_pct"
SUMMARY_KEY_MEDIAN_HOLDING_QUARTERS: Final[str] = "median_holding_quarters"
SUMMARY_KEY_PCT_BECAME_ACTIVE_ADD: Final[str] = "pct_became_active_add"
SUMMARY_KEY_NOTES: Final[str] = "notes"

# --- View 1 summary notes (SD-5 caveat + option-direction one-liner) ---
SUMMARY_NOTES: Final[str] = (
    "High/low excess is a relative heuristic (position high/low vs SPY high/low), "
    "not date-matched alpha; option returns are the underlying's directional move "
    "(long-only, not inverted for written options)."
)

# --- Validation patterns (v3 path-safety) ---
SLUG_PATTERN: Final[str] = r"^[a-z0-9_]+$"
OVERFLOW_NAME_PATTERN: Final[str] = r"^CIK\d+-submissions-\d+\.json$"

INVESTORS_CONFIG_PATH: Final[Path] = REPO_ROOT / "config" / "investors.json"

# --- Prompt 2: filing-directory index (Archives {filing_index_url}index.json) ---
FILING_INDEX_NAME: Final[str] = "index.json"

# --- Info-table / cover-page LOCAL element & field names (namespace-stripped).
#     We match purely by namespace-stripped local name; the namespace URI varies
#     slightly across years, so we do NOT store or compare URIs at all
#     (INFOTABLE_NS_URIS / COVERPAGE_NS_URIS deliberately NOT added — dead under
#     local-name matching). ---
INFOTABLE_ROW_LOCALNAME: Final[str] = "infoTable"
INFOTABLE_FIELD_NAME_OF_ISSUER: Final[str] = "nameOfIssuer"
INFOTABLE_FIELD_TITLE_OF_CLASS: Final[str] = "titleOfClass"
INFOTABLE_FIELD_CUSIP: Final[str] = "cusip"
INFOTABLE_FIELD_VALUE: Final[str] = "value"
INFOTABLE_FIELD_SSH_PRNAMT: Final[str] = "sshPrnamt"  # nested under shrsOrPrnAmt
INFOTABLE_FIELD_SSH_PRNAMT_TYPE: Final[str] = "sshPrnamtType"  # nested under shrsOrPrnAmt
INFOTABLE_FIELD_SHRS_OR_PRN: Final[str] = "shrsOrPrnAmt"  # wrapper element
INFOTABLE_FIELD_PUT_CALL: Final[str] = "putCall"
INFOTABLE_FIELD_INVESTMENT_DISCRETION: Final[str] = "investmentDiscretion"
COVERPAGE_AMENDMENT_INFO_LOCALNAME: Final[str] = "amendmentInfo"
COVERPAGE_AMENDMENT_TYPE_LOCALNAME: Final[str] = "amendmentType"

# --- index.json directory keys (EDGAR shape) ---
INDEX_DIRECTORY_KEY: Final[str] = "directory"
INDEX_ITEM_KEY: Final[str] = "item"
INDEX_ITEM_NAME_KEY: Final[str] = "name"

# --- index.json item-selection heuristics ---
# A directory item is a candidate info table when its name ends with .xml and is NOT the
# cover page. Cover pages are typically primary_doc.xml / *.txt.
# (The overly-broad "table" hint is DELIBERATELY OMITTED — it false-matched cover/other docs.)
XML_SUFFIX: Final[str] = ".xml"
INFOTABLE_NAME_HINTS: Final[tuple[str, ...]] = ("infotable", "form13finfotable")
COVERPAGE_NAME_HINTS: Final[tuple[str, ...]] = ("primary_doc", "primarydoc", "coverpage")

# --- Security type values (PositionRecord.security_type) ---
SECURITY_TYPE_COMMON: Final[str] = "COMMON"
SECURITY_TYPE_PUT: Final[str] = "PUT"
SECURITY_TYPE_CALL: Final[str] = "CALL"
SECURITY_TYPES: Final[frozenset[str]] = frozenset(
    {SECURITY_TYPE_COMMON, SECURITY_TYPE_PUT, SECURITY_TYPE_CALL}
)
# Raw putCall values (uppercased) -> security_type:
PUT_CALL_PUT: Final[str] = "PUT"
PUT_CALL_CALL: Final[str] = "CALL"

# --- sshPrnamtType values ---
SSH_TYPE_SHARES: Final[str] = "SH"
SSH_TYPE_PRINCIPAL: Final[str] = "PRN"

# --- investmentDiscretion allowed values (validation; "" sentinel for empty/unknown) ---
DISCRETION_SOLE: Final[str] = "SOLE"
DISCRETION_DEFINED: Final[str] = "DEFINED"
DISCRETION_OTHER: Final[str] = "OTHER"
DISCRETION_VALUES: Final[frozenset[str]] = frozenset(
    {DISCRETION_SOLE, DISCRETION_DEFINED, DISCRETION_OTHER}
)

# --- CUSIP shape (real CUSIP alphabet, NOT isalnum).
# Valid CUSIP characters are A-Z, 0-9, plus the three special chars *, @, #.
# isalnum() would wrongly drop CUSIPs containing those three. We validate exactly
# 9 chars, each (after .upper()) in this set. ---
CUSIP_LENGTH: Final[int] = 9
CUSIP_ALLOWED_CHARS: Final[str] = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789*@#"
CUSIP_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9*@#]{9}$")

# --- Cover-page amendmentType mapping (§6); compared after strip()+upper() ---
COVERPAGE_AMENDMENT_RESTATEMENT_VALUES: Final[frozenset[str]] = frozenset({"RESTATEMENT"})
COVERPAGE_AMENDMENT_ADDS_VALUES: Final[frozenset[str]] = frozenset(
    {"NEW HOLDINGS", "NEW", "ADDS NEW ENTRIES"}
)

# --- OpenFIGI / CUSIP->ticker resolution (Prompt 3) ---

# --- OpenFIGI endpoint / request shape ---
OPENFIGI_MAPPING_URL: Final[str] = "https://api.openfigi.com/v3/mapping"
OPENFIGI_ID_TYPE_CUSIP: Final[str] = "ID_CUSIP"
OPENFIGI_API_KEY_ENV: Final[str] = "OPENFIGI_API_KEY"  # optional; absent on no-key tier
OPENFIGI_API_KEY_HEADER: Final[str] = "X-OPENFIGI-APIKEY"
OPENFIGI_CONTENT_TYPE: Final[str] = "application/json"
# NOTE: jobs are queried UNFILTERED (no exchCode). US preference is applied in select_match,
# NOT on the request — filtering on the job hides ADR/cross-listed candidates and can mark
# them permanently unresolved.

# --- Rate / batch limits.
#     BOTH the no-key AND the with-key values are documented-but-NOT-guaranteed; tunable here.
OPENFIGI_MAX_JOBS_PER_REQUEST_NO_KEY: Final[int] = 10  # documented no-key max jobs/request; documented, not guaranteed; tunable here
OPENFIGI_REQUESTS_PER_MINUTE_NO_KEY: Final[float] = 25.0  # documented ~25/min no-key; documented, not guaranteed; tunable here
OPENFIGI_MAX_JOBS_PER_REQUEST_WITH_KEY: Final[int] = 100  # documented with-key max; documented, not guaranteed; tunable here
OPENFIGI_REQUESTS_PER_MINUTE_WITH_KEY: Final[float] = 250.0  # documented with-key ~/min; documented, not guaranteed; tunable here
OPENFIGI_RATE_BUCKET_CAPACITY: Final[float] = 1.0  # same capacity-1 discipline as EDGAR

# --- 429 backoff: OpenFIGI's limit is PER MINUTE. The EDGAR-style 0.5*2**attempt backoff
#     can exhaust retries before a 60s window clears. So 429 (only) uses a fixed wait sized
#     to clear a per-minute window. Honor Retry-After first.
OPENFIGI_RATE_LIMIT_BACKOFF_SECONDS: Final[float] = 60.0  # per-minute window reset; tunable here

# --- Response keys (narrow JSONObject at the boundary; no Any) ---
OPENFIGI_RESP_DATA_KEY: Final[str] = "data"
OPENFIGI_RESP_WARNING_KEY: Final[str] = "warning"
OPENFIGI_RESP_ERROR_KEY: Final[str] = "error"
OPENFIGI_MATCH_TICKER_KEY: Final[str] = "ticker"
OPENFIGI_MATCH_NAME_KEY: Final[str] = "name"
OPENFIGI_MATCH_EXCH_CODE_KEY: Final[str] = "exchCode"
OPENFIGI_MATCH_SECURITY_TYPE_KEY: Final[str] = "securityType"
OPENFIGI_MATCH_SECURITY_TYPE2_KEY: Final[str] = "securityType2"
OPENFIGI_MATCH_MARKET_SECTOR_KEY: Final[str] = "marketSector"
OPENFIGI_MATCH_COMPOSITE_FIGI_KEY: Final[str] = "compositeFIGI"
OPENFIGI_MATCH_FIGI_KEY: Final[str] = "figi"

# --- In-payload MISS whitelist (the ONLY warning strings that mean "permanent, cache
#     unresolved"). Compared trimmed + case-insensitively. An in-payload `error`, or a
#     `warning` NOT in this set, is treated as TRANSIENT -> OpenFigiError -> retry next run
#     (NOT cached unresolved). See plan §3.
OPENFIGI_MISS_WARNINGS: Final[frozenset[str]] = frozenset(
    {"no identifier found."}
)  # store/compare normalized (lower+strip)

# --- Selection heuristic preferences (deterministic; see plan §4) ---
OPENFIGI_PREFERRED_EXCH_CODE: Final[str] = "US"
OPENFIGI_PREFERRED_MARKET_SECTOR: Final[str] = "Equity"
# securityType2 == "Common Stock" is the strongest common-equity signal across years.
OPENFIGI_PREFERRED_SECURITY_TYPE2: Final[tuple[str, ...]] = ("Common Stock",)

# --- Resolution source markers (CusipMapEntry.source) ---
CUSIP_SOURCE_OPENFIGI: Final[str] = "openfigi"
CUSIP_SOURCE_MANUAL: Final[str] = "manual"
CUSIP_SOURCE_UNRESOLVED: Final[str] = "unresolved"
CUSIP_SOURCES: Final[frozenset[str]] = frozenset(
    {CUSIP_SOURCE_OPENFIGI, CUSIP_SOURCE_MANUAL, CUSIP_SOURCE_UNRESOLVED}
)

# --- Shared (global, NOT per-investor) cusip map file (see plan §5 rationale) ---
CUSIP_MAP_FILE: Final[str] = "cusip_ticker_map.json"  # under DATA_ROOT; bare list on disk

# --- Prompt 4: QoQ change-classification thresholds (spec §1.4; tunable, start here) ---
# Share-count threshold separating ACTIVE (deliberate buy/sell) from PASSIVE (price drift).
# Spec uses STRICT > / < at +/-10%. Stored as a percent magnitude (10.0 == 10%).
CHANGE_SHARES_DELTA_PCT_THRESHOLD: Final[float] = 10.0
# NAV-weight threshold for a "meaningful" change, in BASIS POINTS. Spec uses STRICT > / <
# at +/-50bps. (1% == 100bps; weight_delta_bps = (cur_wt_pct - prior_wt_pct) * 100.)
CHANGE_WEIGHT_DELTA_BPS_THRESHOLD: Final[float] = 50.0
PCT_TO_BPS: Final[float] = 100.0  # 1 percentage point == 100 basis points

# --- Split detection (spec §1.4 edge case): shares ~+100%, value ~flat ---
# A suspected forward 2:1 split shows shares_delta_pct near +100 and |value_delta_pct| near 0.
# Bands are tunable; chosen wide enough to catch real splits, tight enough to avoid ACTIVE_ADDs.
SPLIT_SHARES_DELTA_PCT_CENTER: Final[float] = 100.0  # 2:1 forward split center
SPLIT_SHARES_DELTA_PCT_TOLERANCE: Final[float] = 5.0  # accept [95, 105]% share growth
SPLIT_VALUE_DELTA_PCT_MAX_ABS: Final[float] = 10.0  # value moved <=10% in abs terms

# --- EODHD price API (Prompt 5). VERIFIED against the live API via orchestrator probe; values
#     are facts, not assumptions. F6 (rate limits) / F7 (404/delisting shape) confirmed only by
#     tests_live/test_returns_live.py. ---
EODHD_EOD_URL_TEMPLATE: Final[str] = "https://eodhd.com/api/eod/{symbol}"  # VERIFIED host+path
EODHD_API_KEY_ENV: Final[str] = "EODHD_API_KEY"  # read from os.environ
EODHD_PARAM_API_TOKEN: Final[str] = "api_token"  # VERIFIED query-param name
EODHD_PARAM_FMT: Final[str] = "fmt"
EODHD_PARAM_FMT_JSON: Final[str] = "json"
EODHD_PARAM_FROM: Final[str] = "from"  # VERIFIED YYYY-MM-DD inclusive
EODHD_PARAM_TO: Final[str] = "to"  # VERIFIED YYYY-MM-DD inclusive
EODHD_PARAM_PERIOD: Final[str] = "period"
EODHD_PARAM_PERIOD_DAILY: Final[str] = "d"
# Response row keys (narrow at boundary; no Any). VERIFIED exact spellings.
EODHD_ROW_DATE_KEY: Final[str] = "date"
EODHD_ROW_OPEN_KEY: Final[str] = "open"
EODHD_ROW_HIGH_KEY: Final[str] = "high"
EODHD_ROW_LOW_KEY: Final[str] = "low"
EODHD_ROW_CLOSE_KEY: Final[str] = "close"
EODHD_ROW_ADJ_CLOSE_KEY: Final[str] = "adjusted_close"  # VERIFIED snake_case, adjustment applied
EODHD_ROW_VOLUME_KEY: Final[str] = "volume"

# --- EODHD rate / HTTP policy (reuse HTTP_* where shared) ---
# FLAG (F6): EODHD limits are PLAN-DEPENDENT and undocumented-at-this-tier. Start conservative;
# the live smoke test (one shared client) exercises the real limit. Tunable here.
EODHD_REQUESTS_PER_MINUTE: Final[float] = 60.0  # FLAG: conservative guess; plan-dependent
EODHD_RATE_BUCKET_CAPACITY: Final[float] = 1.0  # capacity-1 discipline (EDGAR/OpenFIGI)
EODHD_RATE_LIMIT_BACKOFF_SECONDS: Final[float] = 60.0  # 429 fixed wait (per-minute reset)

# --- EODHD symbol normalization ---
EODHD_US_EXCHANGE_SUFFIX: Final[str] = ".US"  # default exchange for US equities
EODHD_CLASS_SHARE_SEPARATOR: Final[str] = "-"  # EODHD class-share form: BRK-B.US
# Chars in an OpenFIGI ticker that denote a share class and map to the EODHD separator:
EODHD_CLASS_SEPARATORS_IN: Final[tuple[str, ...]] = ("/", ".", " ")  # BRK/B, BRK.B, "BRK B"
SPY_BENCHMARK_SYMBOL: Final[str] = "SPY.US"  # benchmark symbol constant (operator-confirmed)
SYMBOL_OVERRIDES_FILE: Final[str] = "symbol_overrides.json"  # under price_cache dir; optional
# Already-suffixed passthrough: a ticker ALREADY ending in '.XX' where XX is EXACTLY two
# uppercase letters is treated as a pre-formed EODHD exchange suffix and passed through.
EODHD_EXCHANGE_SUFFIX_PATTERN: Final[re.Pattern[str]] = re.compile(r"\.[A-Z]{2}$")

# --- EODHD storage / cache layout ---
PRICE_CACHE_DIR: Final[str] = "price_cache"  # under DATA_ROOT; global (prices are investor-agnostic)
PRICE_CACHE_SUFFIX: Final[str] = ".json"
PRICE_CACHE_SCHEMA_VERSION: Final[int] = 1  # cache-FILE wrapper version
PRICE_CACHE_TMP_PREFIX: Final[str] = ".pricecache-"
RETURNS_TMP_PREFIX: Final[str] = ".returns-"
PRICE_CACHE_WRAPPER_SCHEMA_KEY: Final[str] = "schema_version"
PRICE_CACHE_WRAPPER_SERIES_KEY: Final[str] = "series"
# require at least ONE alphanumeric BEFORE any separator — rejects degenerate '.', '..', '.US'.
# A symbol becomes a filename, so this is ALSO the path-safety guard. Total length 1..32.
EODHD_SYMBOL_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,31}$")

# --- EODHD price source / alignment policy ---
EODHD_USE_ADJUSTED_CLOSE: Final[bool] = True  # DECISION: returns use adjusted_close (D5.5)
# Coverage-threshold fallback. If the fraction of a symbol's bars with a USABLE adjusted_close
# (>= 0, non-None) is < this threshold, the WHOLE symbol falls back to raw `close` (consistently,
# never mixed). Otherwise adjusted_close is used per-bar (the rare unusable bar is skipped).
ADJ_CLOSE_MIN_COVERAGE: Final[float] = 0.5
PRICE_ASOF_DIRECTION_PRIOR: Final[str] = "prior"  # documented rule sentinel (no other modes built)
# HARD FLOOR: the provider REFUSES to query EODHD before this date. A `date` constant (NOT parsed).
EODHD_HISTORY_START: Final[date] = date(2018, 1, 1)  # before earliest target quarter; HARD FLOOR
# Staleness — SOFT WARN ONLY (the hard cap is REMOVED; do NOT re-add PRICE_STALENESS_MAX_DAYS).
PRICE_STALENESS_WARN_DAYS: Final[int] = 10

# Compiled patterns (module-level; avoid recompiling per call).
_SLUG_RE: Final[re.Pattern[str]] = re.compile(SLUG_PATTERN)
_OVERFLOW_NAME_RE: Final[re.Pattern[str]] = re.compile(OVERFLOW_NAME_PATTERN)

# Maximum CIK length (EDGAR zero-pads to 10 digits).
_CIK_MAX_DIGITS: Final[int] = 10


# --- Pure path / URL helpers ---


def cik_to_padded(cik: str | int) -> str:
    """Zero-pad a CIK to the 10-digit form the submissions API requires.

    Strips whitespace; requires all-digits; rejects empty / non-numeric / >10 digits
    -> raises ValueError. Accepts int or str.
    """
    raw = str(cik).strip()
    if not raw:
        raise ValueError("CIK is empty")
    if not raw.isdigit():
        raise ValueError(f"CIK is not numeric: {cik!r}")
    if len(raw) > _CIK_MAX_DIGITS:
        raise ValueError(f"CIK has more than {_CIK_MAX_DIGITS} digits: {cik!r}")
    return raw.zfill(_CIK_MAX_DIGITS)


def submissions_url(cik: str | int) -> str:
    """https://data.sec.gov/submissions/CIK##########.json — uses ZERO-PADDED 10-digit CIK."""
    padded = cik_to_padded(cik)
    return f"{EDGAR_SUBMISSIONS_BASE}/CIK{padded}.json"


def submissions_overflow_url(name: str) -> str:
    """https://data.sec.gov/submissions/{name} — name from filings.files[].name.

    e.g. 'CIK0001777813-submissions-001.json'. See D9.1.
    v3: VALIDATES name against OVERFLOW_NAME_PATTERN before building the URL; raises
    DiscoveryError otherwise (path-safety / no injection).
    """
    if not isinstance(name, str) or not _OVERFLOW_NAME_RE.match(name):
        raise DiscoveryError(
            f"overflow file name does not match {OVERFLOW_NAME_PATTERN!r}: {name!r}"
        )
    return f"{EDGAR_SUBMISSIONS_BASE}/{name}"


def filing_index_url(cik: str | int, accession: str) -> str:
    """Archives index DIRECTORY url for a filing.

    https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodashes}/
    Uses UNPADDED integer CIK and DASH-STRIPPED accession. Prompt 2 fetches
    {this}index.json to find the info-table XML. NOT a cgi-bin URL (forbidden).
    """
    cik_int = int(cik_to_padded(cik))  # validates + drops leading zeros
    accession_nodashes = accession.replace("-", "")
    return f"{EDGAR_ARCHIVES_BASE}/{cik_int}/{accession_nodashes}/"


def _default_data_root() -> Path:
    return REPO_ROOT / DATA_ROOT


def investor_data_dir(slug: str, data_root: Path | str | None = None) -> Path:
    """<data_root>/<slug>/ — created on demand by writers.

    data_root defaults to REPO_ROOT/DATA_ROOT; parametrizable so tests use a tmp dir.
    """
    root = Path(data_root) if data_root is not None else _default_data_root()
    return root / slug


def filings_path(slug: str, data_root: Path | str | None = None) -> Path:
    """<data_root>/<slug>/filings.json"""
    return investor_data_dir(slug, data_root) / FILINGS_FILE


def positions_path(slug: str, data_root: Path | str | None = None) -> Path:
    """<data_root>/<slug>/positions.json (Prompt 2)."""
    return investor_data_dir(slug, data_root) / POSITIONS_FILE


def changes_path(slug: str, data_root: Path | str | None = None) -> Path:
    """<data_root>/<slug>/changes.json (Prompt 4).

    RAW convenience helper mirroring positions_path (NO slug-safety); returns the on-disk path
    for changes.json. NOT used by storage internals (those call _safe_path, which adds the
    slug-safety / under-root checks) — provided for external callers.
    """
    return investor_data_dir(slug, data_root) / CHANGES_FILE


def cusip_map_path(data_root: Path | str | None = None) -> Path:
    """<data_root>/cusip_ticker_map.json — SHARED across investors (CUSIP->ticker is global)."""
    root = Path(data_root) if data_root is not None else _default_data_root()
    return root / CUSIP_MAP_FILE


def price_cache_dir(data_root: Path | str | None = None) -> Path:
    """<data_root>/price_cache/ — SHARED across investors (prices are global)."""
    root = Path(data_root) if data_root is not None else _default_data_root()
    return root / PRICE_CACHE_DIR


def price_cache_path(symbol: str, data_root: Path | str | None = None) -> Path:
    """<data_root>/price_cache/<symbol>.json — SHARED across investors (prices are global).

    RAW convenience helper (NO symbol-safety validation here); price_cache.py validates the
    symbol against EODHD_SYMBOL_PATTERN and asserts the path stays under data_root.
    """
    return price_cache_dir(data_root) / f"{symbol}{PRICE_CACHE_SUFFIX}"


def symbol_overrides_path(data_root: Path | str | None = None) -> Path:
    """<data_root>/price_cache/symbol_overrides.json — optional manual override map."""
    return price_cache_dir(data_root) / SYMBOL_OVERRIDES_FILE


def returns_path(slug: str, data_root: Path | str | None = None) -> Path:
    """<data_root>/<slug>/returns.json (Prompt 5).

    RAW convenience helper mirroring changes_path (NO slug-safety); storage internals call
    _safe_path (which adds slug-safety / under-root checks).
    """
    return investor_data_dir(slug, data_root) / RETURNS_FILE


def filing_index_json_url(filing_index_url: str) -> str:
    """{filing_index_url}index.json — the directory listing for one filing.

    filing_index_url must already end with '/' (built by filing_index_url()). We assert
    this rather than silently building a malformed URL, then append the constant so there
    is one place to change. A clear ValueError beats a silent 404.
    """
    if not filing_index_url.endswith("/"):
        raise ValueError(f"filing_index_url must end with '/': {filing_index_url!r}")
    return f"{filing_index_url}{FILING_INDEX_NAME}"
