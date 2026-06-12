"""Tests for discovery. All client interaction is method-level mocked (no HTTP)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pytest

from celebpm import constants
from celebpm.constants import JSONObject
from celebpm.discovery import discover_filings, latest_filing_per_period
from celebpm.errors import DiscoveryError
from celebpm.models import FilingRecord

from tests.conftest import FakeClient

CIK = "0001777813"


def _routes(sample: JSONObject, overflow: JSONObject | None = None) -> dict[str, JSONObject]:
    routes = {constants.submissions_url(CIK): sample}
    if overflow is not None:
        routes[
            constants.submissions_overflow_url("CIK0001777813-submissions-001.json")
        ] = overflow
    return routes


class TestDiscoverFilings:
    def test_filters_to_target_forms(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        assert all(r.form_type in constants.TARGET_FORM_TYPES for r in records)
        # No "NT 10-K" row.
        assert all(r.form_type != "NT 10-K" for r in records)

    def test_dates_parsed(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        rec = records[0]
        assert isinstance(rec.period_of_report, date)
        assert isinstance(rec.filing_date, date)
        assert isinstance(rec.accepted_date, datetime)

    def test_accepted_date_tz_aware_utc(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        for rec in records:
            assert rec.accepted_date.tzinfo is not None
            assert rec.accepted_date.utcoffset() == timezone.utc.utcoffset(None)

    def test_amendment_flags(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        amendments = [r for r in records if r.amendment]
        assert len(amendments) == 1
        assert amendments[0].form_type == constants.FORM_13F_HR_AMENDMENT
        assert amendments[0].amendment_type == constants.AMENDMENT_TYPE_UNKNOWN
        for r in records:
            if not r.amendment:
                assert r.amendment_type == constants.AMENDMENT_TYPE_NONE

    def test_deferred_fields_none(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        for rec in records:
            assert rec.total_portfolio_value is None
            assert rec.position_count is None

    def test_fund_name_from_json(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        assert all(r.fund_name == "Atreides Management, LP" for r in records)

    def test_filing_index_url(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        for rec in records:
            assert rec.filing_index_url == constants.filing_index_url(
                CIK, rec.accession_number
            )

    def test_sorted_descending(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        keys = [(r.filing_date, r.accepted_date, r.accession_number) for r in records]
        assert keys == sorted(keys, reverse=True)

    def test_overflow_merged_and_deduped(self, fake_client: FakeClient) -> None:
        records = discover_filings(CIK, fake_client)
        accessions = [r.accession_number for r in records]
        # Early quarter from overflow is present.
        assert "0001777813-23-000015" in accessions
        assert "0001777813-24-000050" in accessions
        # The overlapping accession (in both recent and overflow) appears exactly once.
        assert accessions.count("0001777813-26-000011") == 1
        # All accessions unique.
        assert len(accessions) == len(set(accessions))


class TestDiscoverFailureModes:
    def test_absent_filings_returns_empty(self) -> None:
        client = FakeClient(_routes({"cik": CIK, "name": "x"}))
        assert discover_filings(CIK, client) == []

    def test_empty_recent_arrays_returns_empty(self) -> None:
        sample: JSONObject = {
            "cik": CIK,
            "name": "x",
            "filings": {
                "recent": {
                    "form": [],
                    "accessionNumber": [],
                    "filingDate": [],
                    "reportDate": [],
                    "acceptanceDateTime": [],
                    "primaryDocument": [],
                }
            },
        }
        client = FakeClient(_routes(sample))
        assert discover_filings(CIK, client) == []

    def test_unequal_array_lengths_aborts(self) -> None:
        sample: JSONObject = {
            "cik": CIK,
            "name": "x",
            "filings": {
                "recent": {
                    "form": ["13F-HR", "13F-HR"],
                    "accessionNumber": ["0001777813-26-000011"],
                    "filingDate": ["2026-02-10", "2025-11-14"],
                    "reportDate": ["2025-12-31", "2025-09-30"],
                    "acceptanceDateTime": ["2026-02-10T21:30:00Z", "2025-11-14T17:00:00Z"],
                    "primaryDocument": ["p.xml", "p.xml"],
                }
            },
        }
        client = FakeClient(_routes(sample))
        with pytest.raises(DiscoveryError):
            discover_filings(CIK, client)

    def test_row_missing_report_date_skipped(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        sample: JSONObject = {
            "cik": CIK,
            "name": "x",
            "filings": {
                "recent": {
                    "form": ["13F-HR", "13F-HR"],
                    "accessionNumber": ["0001777813-26-000011", "0001777813-25-000040"],
                    "filingDate": ["2026-02-10", "2025-11-14"],
                    "reportDate": ["", "2025-09-30"],  # first row missing reportDate
                    "acceptanceDateTime": ["2026-02-10T21:30:00Z", "2025-11-14T17:00:00Z"],
                    "primaryDocument": ["p.xml", "p.xml"],
                }
            },
        }
        client = FakeClient(_routes(sample))
        with caplog.at_level(logging.WARNING):
            records = discover_filings(CIK, client)
        assert len(records) == 1
        assert records[0].accession_number == "0001777813-25-000040"
        assert any("skipping row" in rec.message for rec in caplog.records)

    def test_malformed_acceptance_skipped(self) -> None:
        sample: JSONObject = {
            "cik": CIK,
            "name": "x",
            "filings": {
                "recent": {
                    "form": ["13F-HR", "13F-HR"],
                    "accessionNumber": ["0001777813-26-000011", "0001777813-25-000040"],
                    "filingDate": ["2026-02-10", "2025-11-14"],
                    "reportDate": ["2025-12-31", "2025-09-30"],
                    "acceptanceDateTime": ["not-a-datetime", "2025-11-14T17:00:00Z"],
                    "primaryDocument": ["p.xml", "p.xml"],
                }
            },
        }
        client = FakeClient(_routes(sample))
        records = discover_filings(CIK, client)
        assert len(records) == 1
        assert records[0].accession_number == "0001777813-25-000040"

    def test_acceptance_no_tz_assumed_utc(self) -> None:
        sample: JSONObject = {
            "cik": CIK,
            "name": "x",
            "filings": {
                "recent": {
                    "form": ["13F-HR"],
                    "accessionNumber": ["0001777813-25-000040"],
                    "filingDate": ["2025-11-14"],
                    "reportDate": ["2025-09-30"],
                    "acceptanceDateTime": ["2025-11-14T17:05:12"],  # no tz
                    "primaryDocument": ["p.xml"],
                }
            },
        }
        client = FakeClient(_routes(sample))
        records = discover_filings(CIK, client)
        assert records[0].accepted_date == datetime(
            2025, 11, 14, 17, 5, 12, tzinfo=timezone.utc
        )


class TestOverflowMalformed:
    def _sample_with_overflow(self) -> JSONObject:
        return {
            "cik": CIK,
            "name": "x",
            "filings": {
                "recent": {
                    "form": ["13F-HR"],
                    "accessionNumber": ["0001777813-26-000011"],
                    "filingDate": ["2026-02-10"],
                    "reportDate": ["2025-12-31"],
                    "acceptanceDateTime": ["2026-02-10T21:30:00Z"],
                    "primaryDocument": ["p.xml"],
                },
                "files": [{"name": "CIK0001777813-submissions-001.json", "filingCount": 1}],
            },
        }

    def test_overflow_nested_under_filings_aborts(self) -> None:
        overflow: JSONObject = {"filings": {"form": ["13F-HR"]}}
        client = FakeClient(_routes(self._sample_with_overflow(), overflow))
        with pytest.raises(DiscoveryError):
            discover_filings(CIK, client)

    def test_overflow_missing_array_aborts(self) -> None:
        overflow: JSONObject = {
            "form": ["13F-HR"],
            "accessionNumber": ["0001777813-23-000015"],
            "filingDate": ["2023-05-15"],
            # reportDate missing
            "acceptanceDateTime": ["2023-05-15T16:30:00Z"],
            "primaryDocument": ["p.xml"],
        }
        client = FakeClient(_routes(self._sample_with_overflow(), overflow))
        with pytest.raises(DiscoveryError):
            discover_filings(CIK, client)

    def test_overflow_name_not_string_aborts(self) -> None:
        sample = self._sample_with_overflow()
        filings = sample["filings"]
        assert isinstance(filings, dict)
        filings["files"] = [{"name": 123, "filingCount": 1}]
        client = FakeClient(_routes(sample))
        with pytest.raises(DiscoveryError):
            discover_filings(CIK, client)

    def test_overflow_non_object_payload_aborts(self) -> None:
        # FakeClient.get_json only returns JSONObject; emulate a non-object overflow by
        # routing the overflow URL to a payload that, when parsed, is a list nested wrongly.
        # Since get_json must return a dict, we test the boundary via a dict that fails the
        # top-level-arrays contract instead: a scalar-valued "form".
        overflow: JSONObject = {"form": "13F-HR"}  # not a list
        client = FakeClient(_routes(self._sample_with_overflow(), overflow))
        with pytest.raises(DiscoveryError):
            discover_filings(CIK, client)


class TestLatestFilingPerPeriod:
    def _rec(
        self, accession: str, period: str, accepted: str, amendment: bool = False
    ) -> FilingRecord:
        form = (
            constants.FORM_13F_HR_AMENDMENT if amendment else constants.FORM_13F_HR
        )
        atype = (
            constants.AMENDMENT_TYPE_UNKNOWN if amendment else constants.AMENDMENT_TYPE_NONE
        )
        return FilingRecord(
            cik=CIK,
            accession_number=accession,
            filing_index_url=constants.filing_index_url(CIK, accession),
            primary_doc="p.xml",
            fund_name="x",
            form_type=form,
            period_of_report=date.fromisoformat(period),
            filing_date=date.fromisoformat(period),
            accepted_date=datetime.fromisoformat(accepted),
            amendment=amendment,
            amendment_type=atype,
        )

    def test_amendment_replaces_original(self) -> None:
        # PROVISIONAL: latest accepted wins per period (see D0.6 caveat).
        original = self._rec("a-1", "2025-12-31", "2026-02-10T21:00:00+00:00")
        amendment = self._rec(
            "a-2", "2025-12-31", "2026-02-14T16:00:00+00:00", amendment=True
        )
        result = latest_filing_per_period([original, amendment])
        assert len(result) == 1
        assert result[0].accession_number == "a-2"

    def test_periods_without_amendments_pass_through(self) -> None:
        r1 = self._rec("a-1", "2025-12-31", "2026-02-10T21:00:00+00:00")
        r2 = self._rec("b-1", "2025-09-30", "2025-11-14T17:00:00+00:00")
        result = latest_filing_per_period([r1, r2])
        assert {r.accession_number for r in result} == {"a-1", "b-1"}

    def test_accepted_tie_larger_accession_wins(self) -> None:
        r1 = self._rec("acc-100", "2025-12-31", "2026-02-10T21:00:00+00:00")
        r2 = self._rec("acc-200", "2025-12-31", "2026-02-10T21:00:00+00:00")
        result = latest_filing_per_period([r1, r2])
        assert len(result) == 1
        assert result[0].accession_number == "acc-200"

    def test_sorted_by_period_descending(self) -> None:
        r1 = self._rec("a-1", "2025-03-31", "2025-05-15T16:00:00+00:00")
        r2 = self._rec("b-1", "2025-12-31", "2026-02-10T21:00:00+00:00")
        r3 = self._rec("c-1", "2025-09-30", "2025-11-14T17:00:00+00:00")
        result = latest_filing_per_period([r1, r2, r3])
        periods = [r.period_of_report for r in result]
        assert periods == sorted(periods, reverse=True)
