"""Tests for celebpm.parser. Mock at the client-METHOD level (no HTTP)."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from celebpm import constants, parser
from celebpm.constants import JSONObject
from celebpm.errors import DiscoveryError
from celebpm.models import FilingRecord, PositionRecord
from tests.conftest import FakeClient

_FIXTURES = Path(__file__).parent / "fixtures"

# A reusable filing_index_url for fixtures.
_CIK = "0001777813"
_ACCESSION = "0001777813-26-000012"
_INDEX_URL = constants.filing_index_url(_CIK, _ACCESSION)


def _xml(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _json(name: str) -> JSONObject:
    data: object = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # JSON-decoded dicts are JSONObject by construction (parsed from a JSON file).
    result: JSONObject = data
    return result


def _filing(
    *,
    amendment: bool = False,
    primary_doc: str = "primary_doc.xml",
    amendment_type: str | None = None,
) -> FilingRecord:
    if amendment_type is None:
        amendment_type = (
            constants.AMENDMENT_TYPE_UNKNOWN if amendment else constants.AMENDMENT_TYPE_NONE
        )
    form = constants.FORM_13F_HR_AMENDMENT if amendment else constants.FORM_13F_HR
    return FilingRecord(
        cik=_CIK,
        accession_number=_ACCESSION,
        filing_index_url=_INDEX_URL,
        primary_doc=primary_doc,
        fund_name="Test Fund",
        form_type=form,
        period_of_report=date(2025, 12, 31),
        filing_date=date(2026, 2, 14),
        accepted_date=datetime(2026, 2, 14, 16, 30, tzinfo=timezone.utc),
        amendment=amendment,
        amendment_type=amendment_type,
    )


# ----------------------------------------------------------------------------------
# select_infotable_filename
# ----------------------------------------------------------------------------------


class TestSelectInfotableFilename:
    def test_picks_infotable_by_hint(self) -> None:
        name = parser.select_infotable_filename(_json("filing_index.json"), "primary_doc.xml")
        assert name == "form13fInfoTable.xml"

    def test_single_item_dict_normalized(self) -> None:
        name = parser.select_infotable_filename(
            _json("filing_index_single_item.json"), "primary_doc.xml"
        )
        assert name == "form13fInfoTable.xml"

    def test_mixed_case_matched_returns_original_case(self) -> None:
        name = parser.select_infotable_filename(
            _json("filing_index_mixed_case.json"), "primary_doc.xml"
        )
        # Matched case-insensitively but returned ORIGINAL case (EDGAR URLs are case-sensitive).
        assert name == "Form13FInfoTable.XML"

    def test_two_infotable_hints_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            parser.select_infotable_filename(
                _json("filing_index_two_infotable_hints.json"), "primary_doc.xml"
            )

    def test_ambiguous_no_hint_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            parser.select_infotable_filename(
                _json("filing_index_ambiguous.json"), "primary_doc.xml"
            )

    def test_malformed_items_skipped_still_selects(self) -> None:
        name = parser.select_infotable_filename(
            _json("filing_index_malformed_items.json"), "primary_doc.xml"
        )
        assert name == "form13fInfoTable.xml"

    def test_all_junk_items_no_xml_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            parser.select_infotable_filename(
                _json("filing_index_malformed_items_no_xml.json"), "primary_doc.xml"
            )

    def test_missing_directory_raises(self) -> None:
        payload: JSONObject = {"not_directory": {}}
        with pytest.raises(DiscoveryError):
            parser.select_infotable_filename(payload, "primary_doc.xml")

    def test_item_not_dict_or_list_raises(self) -> None:
        payload: JSONObject = {"directory": {"item": "scalar"}}
        with pytest.raises(DiscoveryError):
            parser.select_infotable_filename(payload, "primary_doc.xml")


# ----------------------------------------------------------------------------------
# locate_and_fetch_infotable
# ----------------------------------------------------------------------------------


class TestLocateAndFetch:
    def test_returns_xml_and_payload_get_json_once(self) -> None:
        index = _json("filing_index.json")
        client = FakeClient(
            routes={constants.filing_index_json_url(_INDEX_URL): index},
            text_routes={_INDEX_URL + "form13fInfoTable.xml": _xml("infotable_common.xml")},
        )
        xml_text, payload = parser.locate_and_fetch_infotable(_filing(), client)
        assert "ALPHA CORP" in xml_text
        assert payload == index
        assert len(client.json_calls) == 1  # EXACTLY ONE get_json

    def test_built_url_uses_original_case_name(self) -> None:
        index = _json("filing_index_mixed_case.json")
        url = _INDEX_URL + "Form13FInfoTable.XML"
        client = FakeClient(
            routes={constants.filing_index_json_url(_INDEX_URL): index},
            text_routes={url: _xml("infotable_common.xml")},
        )
        parser.locate_and_fetch_infotable(_filing(), client)
        assert url in client.text_calls


# ----------------------------------------------------------------------------------
# parse_infotable / field mapping / namespace
# ----------------------------------------------------------------------------------


class TestParseInfotable:
    def test_namespace_robust(self) -> None:
        # Same data, different namespace URI -> identical local-name parse result.
        ns_a = _xml("infotable_common.xml")
        ns_b = ns_a.replace(
            "http://www.sec.gov/edgar/document/thirteenf/informationtable",
            "http://example.com/some/other/namespace/2099",
        )
        rows_a, _ = parser.parse_infotable(ns_a)
        rows_b, _ = parser.parse_infotable(ns_b)
        assert [r.cusip for r in rows_a] == [r.cusip for r in rows_b]
        assert len(rows_a) == 3

    def test_no_namespace_also_parses(self) -> None:
        no_ns = _xml("infotable_common.xml").replace(
            ' xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable"', ""
        )
        rows, _ = parser.parse_infotable(no_ns)
        assert len(rows) == 3

    def test_security_type_derivation(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_options.xml"))
        types = {(r.cusip, r.security_type) for r in rows}
        assert (constants.SECURITY_TYPE_COMMON) in {t for _, t in types}
        assert (constants.SECURITY_TYPE_PUT) in {t for _, t in types}
        assert (constants.SECURITY_TYPE_CALL) in {t for _, t in types}

    def test_empty_putcall_is_common(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_common.xml"))
        assert all(r.security_type == constants.SECURITY_TYPE_COMMON for r in rows)
        assert all(r.put_call == "" for r in rows)

    def test_broken_xml_aborts(self) -> None:
        with pytest.raises(DiscoveryError):
            parser.parse_infotable(_xml("infotable_broken.xml"))

    def test_empty_table_zero_rows(self) -> None:
        rows, skipped = parser.parse_infotable(_xml("infotable_empty.xml"))
        assert rows == []
        assert skipped == 0

    def test_malformed_rows_skip_count(self) -> None:
        rows, skipped = parser.parse_infotable(_xml("infotable_malformed_rows.xml"))
        # 4 good rows kept; 6 junk rows skipped.
        assert len(rows) == 4
        assert skipped == 6

    def test_fractional_value_parses(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_malformed_rows.xml"))
        good = next(r for r in rows if r.cusip == "00846U101")
        assert good.value_reported == 12345
        assert good.shares == 100

    def test_special_char_cusip_kept(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_malformed_rows.xml"))
        assert any(r.cusip == "1234*6@#9" for r in rows)

    def test_empty_name_of_issuer_stored_blank(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_malformed_rows.xml"))
        blank = next(r for r in rows if r.cusip == "02079K305")
        assert blank.company_name == ""

    def test_unrecognized_ssh_type_normalized_to_blank(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            rows, _ = parser.parse_infotable(_xml("infotable_malformed_rows.xml"))
        unrec = next(r for r in rows if r.cusip == "57636Q104")
        assert unrec.ssh_prnamt_type == ""
        assert any("SHARES" in rec.message for rec in caplog.records)

    def test_empty_ssh_type_defaults_to_sh(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_malformed_rows.xml"))
        blank_name = next(r for r in rows if r.cusip == "02079K305")
        assert blank_name.ssh_prnamt_type == constants.SSH_TYPE_SHARES

    def test_dup_field_takes_first_with_warn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            rows, _ = parser.parse_infotable(_xml("infotable_dup_field.xml"))
        assert len(rows) == 1
        assert rows[0].cusip == "00846U101"  # first cusip
        assert rows[0].value_reported == 400000  # first value
        assert any("direct children" in rec.message for rec in caplog.records)


# ----------------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------------


class TestAggregation:
    def test_same_key_summed_one_record(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_common.xml"))
        agg = parser._aggregate(rows)
        alpha = [r for r in agg if r.cusip == "00846U101"]
        assert len(alpha) == 1
        assert alpha[0].value_reported == 750000
        assert alpha[0].shares == 1500

    def test_common_and_option_same_cusip_two_records(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_options.xml"))
        agg = parser._aggregate(rows)
        alpha = [r for r in agg if r.cusip == "00846U101"]
        assert {r.security_type for r in alpha} == {
            constants.SECURITY_TYPE_COMMON,
            constants.SECURITY_TYPE_PUT,
        }

    def test_key_uniqueness(self) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_options.xml"))
        agg = parser._aggregate(rows)
        keys = [(r.cusip, r.security_type) for r in agg]
        assert len(keys) == len(set(keys))

    def test_mixed_shprn_keeps_majority_only(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        rows, _ = parser.parse_infotable(_xml("infotable_mixed_shprn.xml"))
        with caplog.at_level(logging.WARNING):
            agg = parser._aggregate(rows)
        recs = [r for r in agg if r.cusip == "00846U101"]
        assert len(recs) == 1  # NO duplicate key
        rec = recs[0]
        assert rec.ssh_prnamt_type == constants.SSH_TYPE_SHARES  # majority (2 SH vs 1 PRN)
        # value AND shares summed over the MAJORITY (SH) rows only; PRN row dropped entirely.
        assert rec.value_reported == 300000  # excludes the 999000 PRN value
        assert rec.shares == 3000  # excludes the 9999 PRN shares
        assert any("mixed SH/PRN" in r.message for r in caplog.records)

    def test_sh_plus_blank_not_a_mix(self) -> None:
        # A group of SH + ""-type rows (no PRN) sums over ALL rows (no majority-drop).
        rows = [
            parser._RawPosition(
                cusip="00846U101",
                company_name="X",
                title_of_class="COM",
                security_type=constants.SECURITY_TYPE_COMMON,
                put_call="",
                shares=100,
                ssh_prnamt_type=constants.SSH_TYPE_SHARES,
                value_reported=1000,
                investment_discretion="SOLE",
            ),
            parser._RawPosition(
                cusip="00846U101",
                company_name="X",
                title_of_class="COM",
                security_type=constants.SECURITY_TYPE_COMMON,
                put_call="",
                shares=50,
                ssh_prnamt_type="",
                value_reported=500,
                investment_discretion="SOLE",
            ),
        ]
        agg = parser._aggregate(rows)
        assert len(agg) == 1
        assert agg[0].value_reported == 1500
        assert agg[0].shares == 150

    def test_discretion_disagreement_blanks_with_warn(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        rows = [
            parser._RawPosition(
                cusip="00846U101",
                company_name="X",
                title_of_class="COM",
                security_type=constants.SECURITY_TYPE_COMMON,
                put_call="",
                shares=100,
                ssh_prnamt_type=constants.SSH_TYPE_SHARES,
                value_reported=1000,
                investment_discretion="SOLE",
            ),
            parser._RawPosition(
                cusip="00846U101",
                company_name="X",
                title_of_class="COM",
                security_type=constants.SECURITY_TYPE_COMMON,
                put_call="",
                shares=50,
                ssh_prnamt_type=constants.SSH_TYPE_SHARES,
                value_reported=500,
                investment_discretion="DEFINED",
            ),
        ]
        with caplog.at_level(logging.WARNING):
            agg = parser._aggregate(rows)
        assert agg[0].investment_discretion == ""
        assert any("investment_discretion" in r.message for r in caplog.records)


# ----------------------------------------------------------------------------------
# parse_positions_from_xml: totals + dual weights
# ----------------------------------------------------------------------------------


class TestParsePositions:
    def test_common_totals_and_weights(self) -> None:
        updated, positions = parser.parse_positions_from_xml(
            _filing(), _xml("infotable_common.xml")
        )
        assert updated.total_portfolio_value == 1000000
        assert updated.total_equity_value == 1000000
        assert updated.position_count == 2
        by_cusip = {p.cusip: p for p in positions}
        assert by_cusip["00846U101"].weight_pct_reported == pytest.approx(75.0)
        assert by_cusip["09247X101"].weight_pct_reported == pytest.approx(25.0)
        assert sum(p.weight_pct_reported for p in positions) == pytest.approx(100.0)

    def test_options_dual_weights_and_separation(self) -> None:
        updated, positions = parser.parse_positions_from_xml(
            _filing(), _xml("infotable_options.xml")
        )
        # total_portfolio includes options notional; equity excludes it.
        assert updated.total_portfolio_value == 1000000
        assert updated.total_equity_value == 800000
        commons = [p for p in positions if p.security_type == constants.SECURITY_TYPE_COMMON]
        options = [p for p in positions if p.security_type != constants.SECURITY_TYPE_COMMON]
        # Equity-only weights for COMMON sum to ~100 across COMMON only.
        assert sum(
            p.weight_pct_equity_only for p in commons if p.weight_pct_equity_only is not None
        ) == pytest.approx(100.0)
        # Options have weight_pct_equity_only is None (equity/options separation).
        assert options
        assert all(p.weight_pct_equity_only is None for p in options)

    def test_pure_no_client_and_frozen_original(self) -> None:
        filing = _filing()
        updated, _ = parser.parse_positions_from_xml(filing, _xml("infotable_common.xml"))
        # Original unchanged (frozen); replace produced a new object.
        assert filing.total_portfolio_value is None
        assert updated is not filing
        assert updated.total_portfolio_value == 1000000

    def test_zero_row_warn_returns_empty(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            updated, positions = parser.parse_positions_from_xml(
                _filing(), _xml("infotable_empty.xml")
            )
        assert positions == []
        assert updated.total_portfolio_value == 0
        assert updated.total_equity_value == 0
        assert updated.position_count == 0
        assert any("zero rows" in r.message for r in caplog.records)

    def test_adds_amendment_totals_warn_fires(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        filing = _filing(amendment=True, amendment_type=constants.AMENDMENT_TYPE_ADDS)
        with caplog.at_level(logging.WARNING):
            parser.parse_positions_from_xml(filing, _xml("infotable_common.xml"))
        assert any("filing-local" in r.message for r in caplog.records)

    def test_position_count_post_aggregation(self) -> None:
        updated, _ = parser.parse_positions_from_xml(
            _filing(), _xml("infotable_malformed_rows.xml")
        )
        # 4 kept rows, all distinct (cusip, COMMON) -> 4 positions.
        assert updated.position_count == 4

    def test_zero_total_guard(self) -> None:
        # Build an info table whose only row has value 0 -> total 0, weights 0.0, no crash.
        xml = """<?xml version="1.0"?>
        <informationTable>
          <infoTable>
            <nameOfIssuer>ZERO CO</nameOfIssuer>
            <titleOfClass>COM</titleOfClass>
            <cusip>00846U101</cusip>
            <value>0</value>
            <shrsOrPrnAmt><sshPrnamt>0</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
            <investmentDiscretion>SOLE</investmentDiscretion>
          </infoTable>
        </informationTable>"""
        updated, positions = parser.parse_positions_from_xml(_filing(), xml)
        assert updated.total_portfolio_value == 0
        assert positions[0].weight_pct_reported == 0.0
        assert positions[0].weight_pct_equity_only == 0.0


# ----------------------------------------------------------------------------------
# refine_amendment_type
# ----------------------------------------------------------------------------------


class TestRefineAmendmentType:
    def _client(self, cover_fixture: str, name: str = "primary_doc.xml") -> FakeClient:
        return FakeClient(
            routes={},
            text_routes={_INDEX_URL + name: _xml(cover_fixture)},
        )

    def test_non_amendment_unchanged(self) -> None:
        filing = _filing(amendment=False)
        out = parser.refine_amendment_type(filing, FakeClient(routes={}), _json("filing_index.json"))
        assert out is filing

    def test_restatement(self) -> None:
        filing = _filing(amendment=True)
        out = parser.refine_amendment_type(
            filing, self._client("coverpage_amendment_restatement.xml"), _json("filing_index.json")
        )
        assert out.amendment_type == constants.AMENDMENT_TYPE_RESTATEMENT

    def test_adds_with_whitespace_lowercase(self) -> None:
        filing = _filing(amendment=True)
        out = parser.refine_amendment_type(
            filing, self._client("coverpage_amendment_adds.xml"), _json("filing_index.json")
        )
        assert out.amendment_type == constants.AMENDMENT_TYPE_ADDS

    def test_no_get_json_during_refine(self) -> None:
        filing = _filing(amendment=True)
        client = self._client("coverpage_amendment_restatement.xml")
        parser.refine_amendment_type(filing, client, _json("filing_index.json"))
        assert client.json_calls == []

    def test_sgml_txt_cover_unknown_no_raise(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        # primary_doc is a .txt -> not selectable as .xml; index has no cover .xml hint match
        # except primary_doc.xml; use html_primary index but txt primary to force selection of
        # the .xml cover, then feed it the SGML text to exercise the unparseable branch.
        filing = _filing(amendment=True, primary_doc="primary_doc.xml")
        client = FakeClient(
            routes={},
            text_routes={_INDEX_URL + "primary_doc.xml": _xml("coverpage_amendment_sgml.txt")},
        )
        with caplog.at_level(logging.WARNING):
            out = parser.refine_amendment_type(filing, client, _json("filing_index.json"))
        assert out.amendment_type == constants.AMENDMENT_TYPE_UNKNOWN

    def test_html_primary_selects_xml_cover(self) -> None:
        filing = _filing(amendment=True, primary_doc="primary_doc.html")
        client = self._client("coverpage_amendment_restatement.xml", name="primary_doc.xml")
        out = parser.refine_amendment_type(
            filing, client, _json("filing_index_html_primary.json")
        )
        assert out.amendment_type == constants.AMENDMENT_TYPE_RESTATEMENT

    def test_html_primary_no_xml_cover_unknown(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        filing = _filing(amendment=True, primary_doc="primary_doc.html")
        index: JSONObject = {
            "directory": {
                "item": [
                    {"name": "primary_doc.html", "type": "text"},
                    {"name": "form13fInfoTable.xml", "type": "text"},
                ]
            }
        }
        client = FakeClient(routes={})  # no text route needed; should never fetch
        with caplog.at_level(logging.WARNING):
            out = parser.refine_amendment_type(filing, client, index)
        assert out.amendment_type == constants.AMENDMENT_TYPE_UNKNOWN
        assert client.text_calls == []

    def test_html_primary_two_xml_covers_unknown_no_abort(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        filing = _filing(amendment=True, primary_doc="primary_doc.html")
        client = FakeClient(routes={})
        with caplog.at_level(logging.WARNING):
            out = parser.refine_amendment_type(
                filing, client, _json("filing_index_two_coverpage_xml.json")
            )
        assert out.amendment_type == constants.AMENDMENT_TYPE_UNKNOWN
        assert client.text_calls == []

    def test_unrecognized_amendment_type_unknown(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cover = (
            '<?xml version="1.0"?><edgarSubmission>'
            "<amendmentInfo><amendmentType>WAT</amendmentType></amendmentInfo>"
            "</edgarSubmission>"
        )
        filing = _filing(amendment=True)
        client = FakeClient(routes={}, text_routes={_INDEX_URL + "primary_doc.xml": cover})
        with caplog.at_level(logging.WARNING):
            out = parser.refine_amendment_type(filing, client, _json("filing_index.json"))
        assert out.amendment_type == constants.AMENDMENT_TYPE_UNKNOWN


# ----------------------------------------------------------------------------------
# Full-flow get_json-once
# ----------------------------------------------------------------------------------


def test_full_flow_get_json_called_exactly_once() -> None:
    filing = _filing(amendment=True)
    index = _json("filing_index.json")
    client = FakeClient(
        routes={constants.filing_index_json_url(_INDEX_URL): index},
        text_routes={
            _INDEX_URL + "form13fInfoTable.xml": _xml("infotable_common.xml"),
            _INDEX_URL + "primary_doc.xml": _xml("coverpage_amendment_restatement.xml"),
        },
    )
    xml_text, index_payload = parser.locate_and_fetch_infotable(filing, client)
    filing = parser.refine_amendment_type(filing, client, index_payload)
    updated, positions = parser.parse_positions_from_xml(filing, xml_text)
    assert len(client.json_calls) == 1  # the ONE and ONLY get_json across the whole flow
    assert filing.amendment_type == constants.AMENDMENT_TYPE_RESTATEMENT
    assert isinstance(positions[0], PositionRecord)


# ----------------------------------------------------------------------------------
# filing_index_json_url trailing-slash guard
# ----------------------------------------------------------------------------------


class TestFilingIndexJsonUrl:
    def test_builds_index_json(self) -> None:
        assert constants.filing_index_json_url(_INDEX_URL).endswith("/index.json")

    def test_missing_trailing_slash_raises(self) -> None:
        with pytest.raises(ValueError):
            constants.filing_index_json_url("https://example.com/no-slash")
