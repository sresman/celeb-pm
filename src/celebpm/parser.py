"""Pipeline step 2: PARSE FILINGS — info-table XML -> PositionRecords + totals + weights.

Clean fetch/parse split:
  - locate_and_fetch_infotable : the ONLY EDGAR fetch site for the info table
    (exactly ONE get_json for index.json + one get_text for the XML).
  - parse_positions_from_xml   : PURE (no I/O) — rows -> aggregated PositionRecords +
                                  totals + dual weights + updated FilingRecord.
  - refine_amendment_type      : cover-page amendment refinement (one extra get_text,
                                  NEVER a second get_json — reuses the threaded payload).

Namespace-robust: match by namespace-STRIPPED local name (never a hardcoded URI). Never
parse EDGAR HTML — structured XML info tables only.
"""

from __future__ import annotations

import dataclasses
import logging
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from celebpm import constants
from celebpm.constants import JSONObject, JSONValue
from celebpm.edgar_client import HttpClient
from celebpm.errors import DiscoveryError
from celebpm.models import PositionRecord
from celebpm.models import FilingRecord

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------------------
# index.json -> info-table filename selection
# --------------------------------------------------------------------------------------


def _normalized_items(index_payload: JSONObject) -> list[JSONObject]:
    """Read directory.item[] from an EDGAR index.json, defensively.

    Normalizes the EDGAR quirk where `item` may be a single dict instead of a list. Skips
    entries that are not dicts or lack a string `name`. Raises DiscoveryError if `directory`
    is missing/not-a-dict or `item` is missing/not a dict-or-list.
    """
    directory = index_payload.get(constants.INDEX_DIRECTORY_KEY)
    if not isinstance(directory, dict):
        raise DiscoveryError(
            f"index.json {constants.INDEX_DIRECTORY_KEY!r} missing or not an object"
        )
    raw_item = directory.get(constants.INDEX_ITEM_KEY)
    if isinstance(raw_item, dict):
        item_list: list[JSONValue] = [raw_item]
    elif isinstance(raw_item, list):
        item_list = raw_item
    else:
        raise DiscoveryError(
            f"index.json {constants.INDEX_ITEM_KEY!r} missing or not a dict/list"
        )
    items: list[JSONObject] = []
    for entry in item_list:
        if not isinstance(entry, dict):
            continue
        name = entry.get(constants.INDEX_ITEM_NAME_KEY)
        if not isinstance(name, str):
            continue
        items.append(entry)
    return items


def _item_name(item: JSONObject) -> str:
    name = item.get(constants.INDEX_ITEM_NAME_KEY)
    # _normalized_items guarantees a str name; assert for the type checker.
    assert isinstance(name, str)
    return name


def select_infotable_filename(index_payload: JSONObject, primary_doc: str) -> str:
    """Select the info-table .xml filename from an EDGAR index.json directory listing.

    Matching is case-INsensitive, but the ORIGINAL-case name is RETURNED (EDGAR Archives
    URLs are case-sensitive, so a lowercased name would 404).

    Algorithm:
      1. Among .xml candidates, those whose lowercased name contains an INFOTABLE_NAME_HINTS
         substring: exactly one -> return it; more than one -> DiscoveryError (ambiguous).
      2. Else fall back to cover-page exclusion: .xml candidates not equal (case-insensitive)
         to primary_doc and not matching a COVERPAGE_NAME_HINTS substring. Exactly one ->
         return it; >1 -> DiscoveryError; zero -> DiscoveryError (info table absent).
    """
    items = _normalized_items(index_payload)
    # candidates: (original_name, lowered_name) for every .xml item.
    candidates: list[tuple[str, str]] = []
    for item in items:
        name = _item_name(item)
        lowered = name.lower()
        if lowered.endswith(constants.XML_SUFFIX):
            candidates.append((name, lowered))

    if not candidates:
        raise DiscoveryError("no .xml items in index.json directory listing")

    infotable_matches = [
        name
        for (name, lowered) in candidates
        if any(hint in lowered for hint in constants.INFOTABLE_NAME_HINTS)
    ]
    if len(infotable_matches) == 1:
        return infotable_matches[0]
    if len(infotable_matches) > 1:
        raise DiscoveryError(
            f"ambiguous info-table hint match among {infotable_matches}"
        )

    primary_lower = primary_doc.lower()
    noncover = [
        name
        for (name, lowered) in candidates
        if lowered != primary_lower
        and not any(hint in lowered for hint in constants.COVERPAGE_NAME_HINTS)
    ]
    if len(noncover) == 1:
        return noncover[0]
    if len(noncover) > 1:
        raise DiscoveryError(
            f"ambiguous info-table selection (no hint) among {noncover}"
        )
    raise DiscoveryError("no info-table .xml found (cover-page-only directory?)")


def locate_and_fetch_infotable(
    filing: FilingRecord, client: HttpClient
) -> tuple[str, JSONObject]:
    """Fetch index.json ONCE, select the info-table .xml, fetch & return (xml_text, payload).

    The SOLE EDGAR fetch site for the info table. The returned index_payload is threaded back
    to refine_amendment_type so amendment refinement adds AT MOST one extra get_text (the
    cover page) and NEVER a second get_json. EdgarError from the client propagates unchanged.
    """
    index_url = constants.filing_index_json_url(filing.filing_index_url)
    index_payload = client.get_json(index_url)  # the ONE and ONLY get_json
    name = select_infotable_filename(index_payload, filing.primary_doc)  # original-case
    xml_url = f"{filing.filing_index_url}{name}"
    xml_text = client.get_text(xml_url)  # one throttled request
    return xml_text, index_payload


# --------------------------------------------------------------------------------------
# Namespace-robust XML element helpers
# --------------------------------------------------------------------------------------


def _local_name(tag: str) -> str:
    """'{ns}infoTable' -> 'infoTable'; 'infoTable' -> 'infoTable'."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _direct_child_text(elem: ET.Element, local: str) -> str:
    """Stripped .text of the FIRST direct child whose local name == local; '' if none.

    WARN if more than one direct child matches (anomalous; data-quality signal).
    """
    matches = [c for c in elem if _local_name(c.tag) == local]
    if not matches:
        return ""
    if len(matches) > 1:
        logger.warning("multiple <%s> direct children; using first", local)
    return (matches[0].text or "").strip()


def _find_direct_child(elem: ET.Element, local: str) -> ET.Element | None:
    matches = [c for c in elem if _local_name(c.tag) == local]
    if not matches:
        return None
    if len(matches) > 1:
        logger.warning("multiple <%s> direct children; using first", local)
    return matches[0]


# --------------------------------------------------------------------------------------
# Raw row parsing
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class _RawPosition:
    cusip: str
    company_name: str
    title_of_class: str
    security_type: str  # derived COMMON/PUT/CALL
    put_call: str  # "" / "PUT" / "CALL"
    shares: int
    ssh_prnamt_type: str  # "SH" / "PRN" / "" (unrecognized normalized to "")
    value_reported: int
    investment_discretion: str  # SOLE/DEFINED/OTHER or ""


def _parse_int_field(text: str) -> int | None:
    """Float-tolerant integer parse with a non-finite guard. Returns None on failure.

    float64 represents every integer magnitude below 2^53 exactly, far above any 13F value
    or share count, so int(round(float(s))) is lossless here (Decimal rejected as overkill).
    int(round(float("inf"))) raises OverflowError (not ValueError) so we catch BOTH, and
    reject non-finite (inf/-inf/nan) via math.isfinite before rounding.
    """
    try:
        f = float(text.strip())
    except (ValueError, OverflowError):
        return None
    if not math.isfinite(f):
        return None
    try:
        return int(round(f))
    except (ValueError, OverflowError):
        return None


def parse_infotable(xml_text: str) -> tuple[list[_RawPosition], int]:
    """Parse info-table XML -> (raw rows, skipped_count).

    Structural/unparseable XML (ET.ParseError) ABORTS with DiscoveryError. Individual junk
    rows are SKIPPED (WARN, increment counter), mirroring discovery's skip-with-count. A
    valid-but-empty info table (zero rows) is allowed -> ([], 0).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise DiscoveryError(f"info-table XML is not well-formed: {exc}") from exc

    rows: list[_RawPosition] = []
    skipped = 0
    for elem in root.iter():
        if _local_name(elem.tag) != constants.INFOTABLE_ROW_LOCALNAME:
            continue
        parsed = _parse_row(elem)
        if parsed is None:
            skipped += 1
            continue
        rows.append(parsed)
    return rows, skipped


def _parse_row(row: ET.Element) -> _RawPosition | None:
    """Parse one <infoTable> row into a _RawPosition, or None to SKIP (with a WARN)."""
    cusip = _direct_child_text(row, constants.INFOTABLE_FIELD_CUSIP).upper()
    if constants.CUSIP_PATTERN.fullmatch(cusip) is None:
        logger.warning("skipping info-table row: invalid cusip %r", cusip)
        return None

    company_name = _direct_child_text(row, constants.INFOTABLE_FIELD_NAME_OF_ISSUER)
    title_of_class = _direct_child_text(row, constants.INFOTABLE_FIELD_TITLE_OF_CLASS)

    value_text = _direct_child_text(row, constants.INFOTABLE_FIELD_VALUE)
    value_reported = _parse_int_field(value_text)
    if value_reported is None:
        logger.warning("skipping info-table row (cusip %s): bad value %r", cusip, value_text)
        return None
    if value_reported < 0:
        logger.warning("skipping info-table row (cusip %s): negative value", cusip)
        return None

    wrapper = _find_direct_child(row, constants.INFOTABLE_FIELD_SHRS_OR_PRN)
    if wrapper is None:
        ssh_text = ""
        ssh_type_text = ""
    else:
        ssh_text = _direct_child_text(wrapper, constants.INFOTABLE_FIELD_SSH_PRNAMT)
        ssh_type_text = _direct_child_text(
            wrapper, constants.INFOTABLE_FIELD_SSH_PRNAMT_TYPE
        )

    shares = _parse_int_field(ssh_text) if ssh_text != "" else None
    if shares is None:
        logger.warning(
            "skipping info-table row (cusip %s): bad/missing sshPrnamt %r", cusip, ssh_text
        )
        return None
    if shares < 0:
        logger.warning("skipping info-table row (cusip %s): negative sshPrnamt", cusip)
        return None

    ssh_prnamt_type = ssh_type_text.strip().upper()
    if ssh_prnamt_type == "":
        ssh_prnamt_type = constants.SSH_TYPE_SHARES  # empty/missing -> default SH
    elif ssh_prnamt_type not in {constants.SSH_TYPE_SHARES, constants.SSH_TYPE_PRINCIPAL}:
        logger.warning(
            "info-table row (cusip %s): unrecognized sshPrnamtType %r -> normalized to ''",
            cusip,
            ssh_prnamt_type,
        )
        ssh_prnamt_type = ""

    put_call_raw = _direct_child_text(row, constants.INFOTABLE_FIELD_PUT_CALL).upper()
    if put_call_raw == "":
        security_type = constants.SECURITY_TYPE_COMMON
        put_call = ""
    elif put_call_raw == constants.PUT_CALL_PUT:
        security_type = constants.SECURITY_TYPE_PUT
        put_call = constants.PUT_CALL_PUT
    elif put_call_raw == constants.PUT_CALL_CALL:
        security_type = constants.SECURITY_TYPE_CALL
        put_call = constants.PUT_CALL_CALL
    else:
        logger.warning(
            "skipping info-table row (cusip %s): unknown putCall %r", cusip, put_call_raw
        )
        return None

    discretion = _direct_child_text(
        row, constants.INFOTABLE_FIELD_INVESTMENT_DISCRETION
    ).upper()
    if discretion not in constants.DISCRETION_VALUES:
        discretion = ""

    return _RawPosition(
        cusip=cusip,
        company_name=company_name,
        title_of_class=title_of_class,
        security_type=security_type,
        put_call=put_call,
        shares=shares,
        ssh_prnamt_type=ssh_prnamt_type,
        value_reported=value_reported,
        investment_discretion=discretion,
    )


# --------------------------------------------------------------------------------------
# Aggregation by (cusip, security_type) — STRICT uniqueness
# --------------------------------------------------------------------------------------


def _aggregate(raw: list[_RawPosition]) -> list[_RawPosition]:
    """One record per (cusip, security_type). NEVER produces a duplicate key.

    No genuine SH/PRN mix: value & shares summed over ALL rows. Genuine SH-vs-PRN mix: keep
    MAJORITY-type rows only (ties -> SH), sum BOTH their value and shares, DROP minority rows
    (information loss), loud WARN. ("" counts as SH-side; never a PRN presence.)
    """
    groups: dict[tuple[str, str], list[_RawPosition]] = {}
    order: list[tuple[str, str]] = []
    for r in raw:
        key = (r.cusip, r.security_type)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(r)

    result: list[_RawPosition] = []
    for key in order:
        rows = groups[key]
        cusip, security_type = key

        sh_side = [r for r in rows if r.ssh_prnamt_type != constants.SSH_TYPE_PRINCIPAL]
        prn = [r for r in rows if r.ssh_prnamt_type == constants.SSH_TYPE_PRINCIPAL]
        genuine_mix = bool(sh_side) and bool(prn)

        if genuine_mix:
            # Majority by row count; ties -> SH side.
            if len(sh_side) >= len(prn):
                kept = sh_side
                kept_type = constants.SSH_TYPE_SHARES
                dropped_type = constants.SSH_TYPE_PRINCIPAL
            else:
                kept = prn
                kept_type = constants.SSH_TYPE_PRINCIPAL
                dropped_type = constants.SSH_TYPE_SHARES
            logger.warning(
                "cusip %s: mixed SH/PRN (%d SH-side, %d PRN); keeping %d majority %s row(s), "
                "DROPPING %d minority %s row(s) (value AND shares) — information loss",
                cusip,
                len(sh_side),
                len(prn),
                len(kept),
                kept_type,
                len(rows) - len(kept),
                dropped_type,
            )
            summed_rows = kept
            ssh_prnamt_type = kept_type
        else:
            summed_rows = rows
            # The single present type ("" rows resolve to SH per the parse default).
            if prn:
                ssh_prnamt_type = constants.SSH_TYPE_PRINCIPAL
            else:
                ssh_prnamt_type = constants.SSH_TYPE_SHARES

        value_reported = sum(r.value_reported for r in summed_rows)
        shares = sum(r.shares for r in summed_rows)

        first = rows[0]
        company_name = first.company_name
        title_of_class = first.title_of_class
        if any(r.company_name != company_name for r in rows):
            logger.warning("cusip %s: differing company_name across rows; using first", cusip)
        if any(r.title_of_class != title_of_class for r in rows):
            logger.warning("cusip %s: differing title_of_class across rows; using first", cusip)

        discretions = {r.investment_discretion for r in rows}
        if len(discretions) > 1:
            logger.warning(
                "cusip %s: differing investment_discretion across rows; setting ''", cusip
            )
            investment_discretion = ""
        else:
            investment_discretion = first.investment_discretion

        result.append(
            _RawPosition(
                cusip=cusip,
                company_name=company_name,
                title_of_class=title_of_class,
                security_type=security_type,
                put_call=first.put_call,
                shares=shares,
                ssh_prnamt_type=ssh_prnamt_type,
                value_reported=value_reported,
                investment_discretion=investment_discretion,
            )
        )
    return result


# --------------------------------------------------------------------------------------
# Pure parse: totals + dual weights + updated FilingRecord
# --------------------------------------------------------------------------------------


def parse_positions_from_xml(
    filing: FilingRecord, xml_text: str
) -> tuple[FilingRecord, list[PositionRecord]]:
    """PURE (no I/O). Parse the already-fetched info-table XML, aggregate, compute totals +
    dual weights, and return the dataclasses.replace-updated FilingRecord + PositionRecords.

    Totals are COMPUTED from parsed+aggregated rows (post-skip); they MAY diverge from the
    SEC cover-page summary. Equity/options separation is absolute: total_equity_value sums
    COMMON only; options get weight_pct_equity_only=None (never 0.0).
    """
    raw, skipped = parse_infotable(xml_text)
    if skipped:
        logger.warning(
            "skipped %d malformed info-table row(s) for accession %s",
            skipped,
            filing.accession_number,
        )

    if not raw:
        logger.warning(
            "info-table for accession %s parsed to zero rows", filing.accession_number
        )
        updated = dataclasses.replace(
            filing,
            total_portfolio_value=0,
            position_count=0,
            total_equity_value=0,
        )
        return updated, []

    agg = _aggregate(raw)

    total_portfolio_value = sum(p.value_reported for p in agg)
    total_equity_value = sum(
        p.value_reported for p in agg if p.security_type == constants.SECURITY_TYPE_COMMON
    )
    position_count = len(agg)

    if total_portfolio_value == 0:
        logger.warning(
            "accession %s: total_portfolio_value is 0; weights set to 0.0",
            filing.accession_number,
        )

    if filing.amendment_type == constants.AMENDMENT_TYPE_ADDS:
        logger.warning(
            "accession %s is an ADDS amendment; computed totals are filing-local, NOT "
            "period-complete (merge is deferred)",
            filing.accession_number,
        )

    positions: list[PositionRecord] = []
    for p in agg:
        if total_portfolio_value == 0:
            weight_pct_reported = 0.0
        else:
            weight_pct_reported = p.value_reported / total_portfolio_value * 100

        weight_pct_equity_only: float | None
        if p.security_type == constants.SECURITY_TYPE_COMMON:
            if total_equity_value == 0:
                weight_pct_equity_only = 0.0
            else:
                weight_pct_equity_only = p.value_reported / total_equity_value * 100
        else:
            weight_pct_equity_only = None  # options NOT in equity denominator

        positions.append(
            PositionRecord(
                cik=filing.cik,
                accession_number=filing.accession_number,
                period=filing.period_of_report,
                filing_date=filing.filing_date,
                cusip=p.cusip,
                company_name=p.company_name,
                title_of_class=p.title_of_class,
                security_type=p.security_type,
                put_call=p.put_call,
                ticker=None,
                shares=p.shares,
                ssh_prnamt_type=p.ssh_prnamt_type,
                value_reported=p.value_reported,
                investment_discretion=p.investment_discretion,
                weight_pct_reported=weight_pct_reported,
                weight_pct_equity_only=weight_pct_equity_only,
            )
        )

    updated = dataclasses.replace(
        filing,
        total_portfolio_value=total_portfolio_value,
        position_count=position_count,
        total_equity_value=total_equity_value,
    )
    return updated, positions


# --------------------------------------------------------------------------------------
# Amendment-type refinement
# --------------------------------------------------------------------------------------


def _select_coverpage_filename(
    filing: FilingRecord, index_payload: JSONObject
) -> str | None:
    """Pick the cover-page .xml to parse, or None if unselectable (NEVER aborts).

    If primary_doc ends with .xml (case-insensitive) use it. Else hunt index_payload for a
    .xml whose lowercased base matches a COVERPAGE_NAME_HINTS substring; exactly one ->
    return its original-case name; >1 or zero -> None (caller leaves UNKNOWN + WARN).
    """
    if filing.primary_doc and filing.primary_doc.lower().endswith(constants.XML_SUFFIX):
        return filing.primary_doc

    items = _normalized_items(index_payload)
    matches: list[str] = []
    for item in items:
        name = _item_name(item)
        lowered = name.lower()
        if lowered.endswith(constants.XML_SUFFIX) and any(
            hint in lowered for hint in constants.COVERPAGE_NAME_HINTS
        ):
            matches.append(name)
    if len(matches) == 1:
        return matches[0]
    return None


def refine_amendment_type(
    filing: FilingRecord, client: HttpClient, index_payload: JSONObject
) -> FilingRecord:
    """Refine an amendment's amendment_type from its cover page (one extra get_text).

    Reuses the threaded index_payload — NEVER a second get_json. Non-amendments returned
    unchanged. Cover-page selection NEVER aborts: ambiguity/absence/unparseable/non-XML ->
    leave AMENDMENT_TYPE_UNKNOWN + WARN. (NEVER XML-parses a .htm/.html/.txt document.)
    """
    if filing.amendment is not True:
        return filing

    name = _select_coverpage_filename(filing, index_payload)
    if name is None:
        logger.warning(
            "accession %s: no unambiguous cover-page .xml; leaving amendment_type UNKNOWN",
            filing.accession_number,
        )
        return filing

    xml_url = f"{filing.filing_index_url}{name}"
    cover_text = client.get_text(xml_url)
    try:
        root = ET.fromstring(cover_text)
    except ET.ParseError:
        logger.warning(
            "accession %s: cover page %s not well-formed XML; leaving UNKNOWN",
            filing.accession_number,
            name,
        )
        return filing

    amendment_info = None
    for elem in root.iter():
        if _local_name(elem.tag) == constants.COVERPAGE_AMENDMENT_INFO_LOCALNAME:
            amendment_info = elem
            break
    if amendment_info is None:
        logger.warning(
            "accession %s: no amendmentInfo in cover page; leaving UNKNOWN",
            filing.accession_number,
        )
        return filing

    amendment_type_text = ""
    for elem in amendment_info.iter():
        if _local_name(elem.tag) == constants.COVERPAGE_AMENDMENT_TYPE_LOCALNAME:
            amendment_type_text = (elem.text or "").strip().upper()
            break

    if amendment_type_text in constants.COVERPAGE_AMENDMENT_RESTATEMENT_VALUES:
        refined = constants.AMENDMENT_TYPE_RESTATEMENT
    elif amendment_type_text in constants.COVERPAGE_AMENDMENT_ADDS_VALUES:
        refined = constants.AMENDMENT_TYPE_ADDS
    else:
        logger.warning(
            "accession %s: unrecognized/absent amendmentType %r; leaving UNKNOWN",
            filing.accession_number,
            amendment_type_text,
        )
        return filing

    return dataclasses.replace(filing, amendment_type=refined)
