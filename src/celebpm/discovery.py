"""Filing discovery (pipeline step 1: FETCH FILINGS).

Depends on the HttpClient Protocol (D0.11), not the concrete EdgarClient. `client` is a
REQUIRED parameter (v3 — no default; prevents accidental live network calls). See plan §10.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from celebpm import constants
from celebpm.constants import JSONObject, JSONValue
from celebpm.edgar_client import HttpClient
from celebpm.errors import DiscoveryError
from celebpm.models import FilingRecord

logger = logging.getLogger(__name__)

# The parallel arrays read in lockstep from a filings table.
_PARALLEL_ARRAYS = (
    "form",
    "accessionNumber",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
    "primaryDocument",
)

# Fields that, if missing/empty on a target-form row, cause a SKIP (WARN), not an ABORT.
# primaryDocument is NOT required (we locate the info table via filing_index_url).
_REQUIRED_ROW_FIELDS = (
    "form",
    "accessionNumber",
    "filingDate",
    "reportDate",
    "acceptanceDateTime",
)


def discover_filings(cik: str | int, client: HttpClient) -> list[FilingRecord]:
    """Discover all 13F-HR / 13F-HR/A filings for a CIK. PURE of disk I/O.

    `client` is REQUIRED (v3). The composing caller builds ONE EdgarClient() and reuses it
    across CIKs (D0.3).

    >=1 EDGAR request: GET submissions_url(cik). Merges any filings.files overflow files.
    Returns ALL matching filings (originals + amendments), SORTED by
    (filing_date, accepted_date, accession_number) DESCENDING.
    """
    padded = constants.cik_to_padded(cik)
    url = constants.submissions_url(padded)
    payload = client.get_json(url)

    fund_name = _str_or_empty(payload.get("name"))

    filings = payload.get("filings")
    if filings is None:
        return []
    if not isinstance(filings, dict):
        raise DiscoveryError(f"`filings` must be an object, got {type(filings).__name__}")

    recent = filings.get("recent")
    if recent is None:
        rows: list[_RawRow] = []
    else:
        if not isinstance(recent, dict):
            raise DiscoveryError(
                f"`filings.recent` must be an object, got {type(recent).__name__}"
            )
        rows = _extract_rows(recent, source="filings.recent")

    # Merge overflow files (older filings paged out of `recent`).
    overflow_entries = filings.get("files")
    if overflow_entries:
        if not isinstance(overflow_entries, list):
            raise DiscoveryError(
                f"`filings.files` must be a list, got {type(overflow_entries).__name__}"
            )
        for entry in overflow_entries:
            if not isinstance(entry, dict):
                raise DiscoveryError("each `filings.files` entry must be an object")
            name = entry.get("name")
            if not isinstance(name, str):
                raise DiscoveryError(f"overflow entry `name` must be a string, got {name!r}")
            overflow_url = constants.submissions_overflow_url(name)  # validates name pattern
            overflow_payload = client.get_json(overflow_url)
            # Overflow files have the parallel-array shape at the TOP LEVEL (not under `filings`).
            if "filings" in overflow_payload and "recent" not in overflow_payload:
                raise DiscoveryError(
                    f"overflow file {name!r} has unexpected `filings` key; expected top-level arrays"
                )
            rows.extend(_extract_rows(overflow_payload, source=f"overflow:{name}"))

    # Dedup by accession_number (defensive against recent/overflow overlap).
    deduped: dict[str, _RawRow] = {}
    for row in rows:
        deduped.setdefault(row.accession_number, row)

    records: list[FilingRecord] = []
    skipped = 0
    for row in deduped.values():
        if row.form not in constants.TARGET_FORM_TYPES:
            continue
        built = _build_record(row, cik=padded, fund_name=fund_name)
        if built is None:
            skipped += 1
            continue
        records.append(built)

    if skipped:
        logger.warning("skipped %d malformed target-form row(s) for CIK %s", skipped, padded)

    records.sort(
        key=lambda r: (r.filing_date, r.accepted_date, r.accession_number),
        reverse=True,
    )
    return records


def latest_filing_per_period(records: list[FilingRecord]) -> list[FilingRecord]:
    """PROVISIONAL. Reduce to one record per period_of_report (latest accepted wins).

    TIE-BREAK (v3): if accepted_date ties, keep the larger accession_number. Returns one
    record per period, SORTED by period_of_report DESCENDING.

    CAVEAT: unsafe for ADDITIVE amendments ('adds new entries') which don't restate the full
    portfolio. True supersession is DEFERRED to Prompt 2. Downstream code must NOT treat this
    as final supersession (D0.6).
    """
    best: dict[date, FilingRecord] = {}
    for rec in records:
        current = best.get(rec.period_of_report)
        if current is None:
            best[rec.period_of_report] = rec
            continue
        if (rec.accepted_date, rec.accession_number) > (
            current.accepted_date,
            current.accession_number,
        ):
            best[rec.period_of_report] = rec
    return sorted(best.values(), key=lambda r: r.period_of_report, reverse=True)


class _RawRow:
    """A single filing row pulled from the parallel arrays (still raw strings)."""

    __slots__ = (
        "form",
        "accession_number",
        "filing_date",
        "report_date",
        "acceptance",
        "primary_doc",
    )

    def __init__(
        self,
        form: str,
        accession_number: str,
        filing_date: str,
        report_date: str,
        acceptance: str,
        primary_doc: str,
    ) -> None:
        self.form = form
        self.accession_number = accession_number
        self.filing_date = filing_date
        self.report_date = report_date
        self.acceptance = acceptance
        self.primary_doc = primary_doc


def _extract_rows(table: JSONObject, source: str) -> list[_RawRow]:
    """Read the parallel arrays from a table object into _RawRow objects.

    ABORTS (DiscoveryError) on a missing required array or unequal array lengths.
    Cells are coerced to "" if null/missing; per-row required-field validation happens later.
    """
    arrays: dict[str, list[JSONValue]] = {}
    for name in _PARALLEL_ARRAYS:
        if name == "primaryDocument" and name not in table:
            # primaryDocument is optional at the array level; fill with empties later.
            arrays[name] = []
            continue
        value = table.get(name)
        if value is None:
            raise DiscoveryError(f"{source}: missing required parallel array {name!r}")
        if not isinstance(value, list):
            raise DiscoveryError(
                f"{source}: parallel array {name!r} must be a list, got {type(value).__name__}"
            )
        arrays[name] = value

    # Determine the canonical length from the required (non-optional) arrays.
    required_lengths = {
        name: len(arrays[name]) for name in _PARALLEL_ARRAYS if name != "primaryDocument"
    }
    lengths = set(required_lengths.values())
    if len(lengths) > 1:
        raise DiscoveryError(
            f"{source}: parallel arrays have unequal lengths: {required_lengths}"
        )
    n = lengths.pop() if lengths else 0

    primary = arrays["primaryDocument"]
    if primary and len(primary) != n:
        raise DiscoveryError(
            f"{source}: primaryDocument length {len(primary)} != row count {n}"
        )

    rows: list[_RawRow] = []
    for i in range(n):
        rows.append(
            _RawRow(
                form=_cell(arrays["form"], i),
                accession_number=_cell(arrays["accessionNumber"], i),
                filing_date=_cell(arrays["filingDate"], i),
                report_date=_cell(arrays["reportDate"], i),
                acceptance=_cell(arrays["acceptanceDateTime"], i),
                primary_doc=_cell(primary, i) if primary else "",
            )
        )
    return rows


def _cell(array: list[JSONValue], index: int) -> str:
    """Coerce a parallel-array cell to a string ('' if null)."""
    if index >= len(array):
        return ""
    value = array[index]
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _build_record(row: _RawRow, cik: str, fund_name: str) -> FilingRecord | None:
    """Build a FilingRecord from a target-form row. Returns None to SKIP a malformed row."""
    # Required-field presence check (SKIP on violation).
    required_values = {
        "form": row.form,
        "accessionNumber": row.accession_number,
        "filingDate": row.filing_date,
        "reportDate": row.report_date,
        "acceptanceDateTime": row.acceptance,
    }
    for field_name in _REQUIRED_ROW_FIELDS:
        if not required_values[field_name]:
            logger.warning(
                "skipping row (accession=%r): missing required field %r",
                row.accession_number,
                field_name,
            )
            return None

    try:
        period = date.fromisoformat(row.report_date)
        filing = date.fromisoformat(row.filing_date)
        accepted = _parse_acceptance(row.acceptance)
    except ValueError as exc:
        logger.warning(
            "skipping row (accession=%r): unparseable date/datetime: %s",
            row.accession_number,
            exc,
        )
        return None

    amendment = row.form == constants.FORM_13F_HR_AMENDMENT
    amendment_type = (
        constants.AMENDMENT_TYPE_UNKNOWN if amendment else constants.AMENDMENT_TYPE_NONE
    )

    return FilingRecord(
        cik=cik,
        accession_number=row.accession_number,
        filing_index_url=constants.filing_index_url(cik, row.accession_number),
        primary_doc=row.primary_doc,
        fund_name=fund_name,
        form_type=row.form,
        period_of_report=period,
        filing_date=filing,
        accepted_date=accepted,
        amendment=amendment,
        amendment_type=amendment_type,
        total_portfolio_value=None,
        position_count=None,
    )


def _parse_acceptance(value: str) -> datetime:
    """Parse acceptanceDateTime -> tz-aware UTC datetime.

    A Z-suffixed/offset timestamp is parsed and converted to UTC. A no-tz timestamp is
    ASSUMED UTC (documented assumption — D10.3). Raises ValueError on unparseable input
    (caught upstream -> row is skipped).
    """
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _str_or_empty(value: JSONValue) -> str:
    """Coerce a JSON value to a string ('' if not a string / None)."""
    return value if isinstance(value, str) else ""
