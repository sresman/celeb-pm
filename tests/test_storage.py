"""Tests for storage. Uses tmp_path — never touches the real data/."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from celebpm import constants, storage
from celebpm.errors import DiscoveryError
from celebpm.models import (
    ChangeType,
    CusipMapEntry,
    FilingRecord,
    FundamentalsEntry,
    PositionChange,
    PositionRecord,
    ReturnRecord,
)

SLUG = "atreides_management"


def _position(
    *,
    cusip: str,
    period: date = date(2025, 12, 31),
    security_type: str = constants.SECURITY_TYPE_COMMON,
    put_call: str = "",
    accession_number: str = "0001777813-26-000012",
    weight_equity: float | None = 50.0,
) -> PositionRecord:
    return PositionRecord(
        cik="0001777813",
        accession_number=accession_number,
        period=period,
        filing_date=date(2026, 2, 14),
        cusip=cusip,
        company_name="X CORP",
        title_of_class="COM",
        security_type=security_type,
        put_call=put_call,
        shares=1000,
        ssh_prnamt_type=constants.SSH_TYPE_SHARES,
        value_reported=500000,
        investment_discretion="SOLE",
        weight_pct_reported=50.0,
        weight_pct_equity_only=weight_equity,
    )


def _sample_records() -> list[FilingRecord]:
    return [
        FilingRecord(
            cik="0001777813",
            accession_number="0001777813-26-000012",
            filing_index_url=constants.filing_index_url(
                "0001777813", "0001777813-26-000012"
            ),
            primary_doc="primary_doc.xml",
            fund_name="Atreides Management, LP",
            form_type=constants.FORM_13F_HR_AMENDMENT,
            period_of_report=date(2025, 12, 31),
            filing_date=date(2026, 2, 14),
            accepted_date=datetime(2026, 2, 14, 16, 30, tzinfo=timezone.utc),
            amendment=True,
            amendment_type=constants.AMENDMENT_TYPE_UNKNOWN,
            total_portfolio_value=None,
            position_count=None,
        ),
        FilingRecord(
            cik="0001777813",
            accession_number="0001777813-25-000040",
            filing_index_url=constants.filing_index_url(
                "0001777813", "0001777813-25-000040"
            ),
            primary_doc="primary_doc.xml",
            fund_name="Atreides Management, LP",
            form_type=constants.FORM_13F_HR,
            period_of_report=date(2025, 9, 30),
            filing_date=date(2025, 11, 14),
            accepted_date=datetime(2025, 11, 14, 17, 5, 12, tzinfo=timezone.utc),
            amendment=False,
            amendment_type=constants.AMENDMENT_TYPE_NONE,
        ),
    ]


class TestRoundTrip:
    def test_write_then_read_reproduces_records(self, tmp_path: Path) -> None:
        records = _sample_records()
        storage.write_filings(SLUG, records, data_root=tmp_path)
        loaded = storage.read_filings(SLUG, data_root=tmp_path)
        assert loaded == records

    def test_tz_aware_and_none_fields_preserved(self, tmp_path: Path) -> None:
        records = _sample_records()
        storage.write_filings(SLUG, records, data_root=tmp_path)
        loaded = storage.read_filings(SLUG, data_root=tmp_path)
        assert loaded[0].accepted_date.tzinfo is not None
        assert loaded[1].total_portfolio_value is None
        assert loaded[1].position_count is None

    def test_on_disk_is_bare_list(self, tmp_path: Path) -> None:
        storage.write_filings(SLUG, _sample_records(), data_root=tmp_path)
        path = constants.filings_path(SLUG, data_root=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)

    def test_no_leftover_temp_file(self, tmp_path: Path) -> None:
        storage.write_filings(SLUG, _sample_records(), data_root=tmp_path)
        target_dir = tmp_path / SLUG
        leftovers = [p for p in target_dir.iterdir() if p.name != constants.FILINGS_FILE]
        assert leftovers == []


class TestFailureModes:
    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.read_filings("never_written", data_root=tmp_path)

    def test_traversal_slug_rejected_on_write(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.write_filings("../escape", _sample_records(), data_root=tmp_path)

    def test_traversal_slug_rejected_on_read(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.read_filings("../escape", data_root=tmp_path)


class TestPositions:
    def test_round_trip(self, tmp_path: Path) -> None:
        records = [
            _position(cusip="00846U101"),
            _position(
                cusip="09247X101",
                security_type=constants.SECURITY_TYPE_PUT,
                put_call=constants.PUT_CALL_PUT,
                weight_equity=None,
            ),
        ]
        storage.write_positions(SLUG, records, data_root=tmp_path)
        loaded = storage.read_positions(SLUG, data_root=tmp_path)
        assert sorted(loaded, key=lambda r: r.cusip) == sorted(records, key=lambda r: r.cusip)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.read_positions("never_written", data_root=tmp_path)

    def test_bare_list_on_disk(self, tmp_path: Path) -> None:
        storage.write_positions(SLUG, [_position(cusip="00846U101")], data_root=tmp_path)
        path = constants.positions_path(SLUG, data_root=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)

    def test_no_leftover_temp(self, tmp_path: Path) -> None:
        storage.write_positions(SLUG, [_position(cusip="00846U101")], data_root=tmp_path)
        target_dir = tmp_path / SLUG
        leftovers = [p for p in target_dir.iterdir() if p.name != constants.POSITIONS_FILE]
        assert leftovers == []

    def test_traversal_slug_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.write_positions("../escape", [], data_root=tmp_path)

    def test_deterministic_sorted_and_idempotent(self, tmp_path: Path) -> None:
        a = _position(cusip="ZZZZZ9999", period=date(2025, 12, 31))
        b = _position(cusip="00846U101", period=date(2025, 12, 31))
        c = _position(cusip="00846U101", period=date(2024, 12, 31))
        path = constants.positions_path(SLUG, data_root=tmp_path)

        storage.write_positions(SLUG, [a, b, c], data_root=tmp_path)
        first = path.read_text(encoding="utf-8")
        loaded = storage.read_positions(SLUG, data_root=tmp_path)
        # Sorted by (period, cusip, security_type): older period first.
        assert [(r.period, r.cusip) for r in loaded] == [
            (date(2024, 12, 31), "00846U101"),
            (date(2025, 12, 31), "00846U101"),
            (date(2025, 12, 31), "ZZZZZ9999"),
        ]

        # Different input order -> BYTE-IDENTICAL file.
        storage.write_positions(SLUG, [c, b, a], data_root=tmp_path)
        assert path.read_text(encoding="utf-8") == first

    def test_overwrites_wholesale_no_append(self, tmp_path: Path) -> None:
        storage.write_positions(SLUG, [_position(cusip="00846U101")], data_root=tmp_path)
        storage.write_positions(SLUG, [_position(cusip="09247X101")], data_root=tmp_path)
        loaded = storage.read_positions(SLUG, data_root=tmp_path)
        assert [r.cusip for r in loaded] == ["09247X101"]

    def test_incremental_caller_pattern_missing_file_empty_history(
        self, tmp_path: Path
    ) -> None:
        # Documented caller pattern: catch the first-run DiscoveryError, start from [].
        try:
            history = storage.read_positions(SLUG, data_root=tmp_path)
        except DiscoveryError:
            history = []
        assert history == []

        new = [_position(cusip="00846U101", accession_number="acc-1")]
        # dedup-by-accession union (nothing to drop on first run).
        union = [r for r in history if r.accession_number != "acc-1"] + new
        storage.write_positions(SLUG, union, data_root=tmp_path)
        assert [r.cusip for r in storage.read_positions(SLUG, data_root=tmp_path)] == [
            "00846U101"
        ]


def _entry(
    *,
    cusip: str,
    ticker: str | None = "AAPL",
    source: str = constants.CUSIP_SOURCE_OPENFIGI,
) -> CusipMapEntry:
    return CusipMapEntry(
        cusip=cusip,
        ticker=ticker,
        name="APPLE INC",
        exch_code="US",
        figi_security_type="Common Stock",
        figi_security_type2="Common Stock",
        market_sector="Equity",
        figi="BBG000B9XVV8",
        source=source,
        ambiguous=False,
        resolved_at="2026-06-11T14:03:22.512000+00:00",
    )


class TestCusipMap:
    def test_round_trip(self, tmp_path: Path) -> None:
        entries = {
            "594918104": _entry(cusip="594918104", ticker="MSFT"),
            "037833100": _entry(cusip="037833100", ticker="AAPL"),
        }
        storage.write_cusip_map(entries, data_root=tmp_path)
        loaded = storage.read_cusip_map(data_root=tmp_path)
        assert loaded == entries

    def test_on_disk_is_sorted_bare_list(self, tmp_path: Path) -> None:
        entries = {
            "594918104": _entry(cusip="594918104", ticker="MSFT"),
            "037833100": _entry(cusip="037833100", ticker="AAPL"),
        }
        path = storage.write_cusip_map(entries, data_root=tmp_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(raw, list)
        assert [r["cusip"] for r in raw] == ["037833100", "594918104"]

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert storage.read_cusip_map(data_root=tmp_path) == {}

    def test_duplicate_cusip_in_file_raises(self, tmp_path: Path) -> None:
        path = constants.cusip_map_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        dup = _entry(cusip="037833100").to_dict()
        path.write_text(json.dumps([dup, dup]), encoding="utf-8")
        with pytest.raises(DiscoveryError):
            storage.read_cusip_map(data_root=tmp_path)

    def test_non_list_top_level_raises(self, tmp_path: Path) -> None:
        path = constants.cusip_map_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(DiscoveryError):
            storage.read_cusip_map(data_root=tmp_path)

    def test_write_dict_miskeyed_raises(self, tmp_path: Path) -> None:
        entries = {"WRONGKEY1": _entry(cusip="037833100")}
        with pytest.raises(DiscoveryError):
            storage.write_cusip_map(entries, data_root=tmp_path)

    def test_write_list_duplicate_raises(self, tmp_path: Path) -> None:
        entries = [_entry(cusip="037833100"), _entry(cusip="037833100")]
        with pytest.raises(DiscoveryError):
            storage.write_cusip_map(entries, data_root=tmp_path)

    def test_write_list_input_round_trip(self, tmp_path: Path) -> None:
        entries = [_entry(cusip="037833100"), _entry(cusip="594918104", ticker="MSFT")]
        storage.write_cusip_map(entries, data_root=tmp_path)
        loaded = storage.read_cusip_map(data_root=tmp_path)
        assert set(loaded) == {"037833100", "594918104"}

    def test_forward_compat_missing_optional_fields(self, tmp_path: Path) -> None:
        path = constants.cusip_map_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        minimal = [{"cusip": "037833100", "ticker": "AAPL", "source": "manual"}]
        path.write_text(json.dumps(minimal), encoding="utf-8")
        loaded = storage.read_cusip_map(data_root=tmp_path)
        assert loaded["037833100"].figi_security_type2 is None
        assert loaded["037833100"].market_sector is None


class TestAssertUnderRoot:
    def test_traversal_escape_raises(self, tmp_path: Path) -> None:
        root = tmp_path / "data"
        root.mkdir()
        escaping = root / ".." / "outside" / "x.json"
        with pytest.raises(DiscoveryError):
            storage._assert_under_root(root, escaping)

    def test_under_root_ok(self, tmp_path: Path) -> None:
        root = tmp_path / "data"
        root.mkdir()
        storage._assert_under_root(root, root / "sub" / "x.json")
        storage._assert_under_root(root, root)  # root itself is allowed


# --------------------------------------------------------------------------- #
# Changes (Prompt 4)
# --------------------------------------------------------------------------- #

_CH_PRIOR = date(2025, 3, 31)
_CH_CUR = date(2025, 6, 30)
_CH_FP = date(2025, 5, 15)
_CH_FC = date(2025, 8, 14)


def _change(
    *,
    cusip: str = "00846U101",
    period: date = _CH_CUR,
    security_type: str = constants.SECURITY_TYPE_COMMON,
    cik: str = "0001777813",
    change_type: ChangeType = ChangeType.ACTIVE_ADD,
) -> PositionChange:
    return PositionChange(
        cik=cik,
        period=period,
        filing_date=_CH_FC,
        prior_period=_CH_PRIOR,
        prior_filing_date=_CH_FP,
        cusip=cusip,
        security_type=security_type,
        ticker="X",
        current_shares=1200,
        current_value_reported=620_000,
        current_weight_pct=50.6,
        prior_shares=1000,
        prior_value_reported=500_000,
        prior_weight_pct=50.0,
        shares_delta=200,
        shares_delta_pct=20.0,
        weight_delta_bps=60.0,
        value_delta=120_000,
        value_delta_pct=24.0,
        change_type=change_type,
        split_suspected=False,
        corporate_action_note="",
    )


class TestChanges:
    def test_round_trip(self, tmp_path: Path) -> None:
        records = [
            _change(cusip="00846U101"),
            _change(cusip="037833100"),
        ]
        storage.write_changes(SLUG, records, data_root=tmp_path)
        loaded = storage.read_changes(SLUG, data_root=tmp_path)
        assert loaded == sorted(
            records, key=lambda r: (r.period, r.cusip, r.security_type)
        )

    def test_deterministic_sort(self, tmp_path: Path) -> None:
        a = _change(cusip="09247X101")
        b = _change(cusip="00846U101")
        storage.write_changes(SLUG, [a, b], data_root=tmp_path)
        loaded = storage.read_changes(SLUG, data_root=tmp_path)
        assert [r.cusip for r in loaded] == ["00846U101", "09247X101"]

    def test_bare_list_on_disk(self, tmp_path: Path) -> None:
        storage.write_changes(SLUG, [_change()], data_root=tmp_path)
        path = constants.changes_path(SLUG, data_root=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["change_type"] == "ACTIVE_ADD"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.read_changes("never_written", data_root=tmp_path)

    def test_traversal_slug_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.write_changes("../escape", [], data_root=tmp_path)

    def test_duplicate_sort_key_rejected(self, tmp_path: Path) -> None:
        dup = [_change(cusip="00846U101"), _change(cusip="00846U101")]
        with pytest.raises(DiscoveryError):
            storage.write_changes(SLUG, dup, data_root=tmp_path)

    def test_multi_cik_rejected(self, tmp_path: Path) -> None:
        records = [
            _change(cusip="00846U101", cik="0001777813"),
            _change(cusip="037833100", cik="0000000001"),
        ]
        with pytest.raises(DiscoveryError):
            storage.write_changes(SLUG, records, data_root=tmp_path)

    def _write_raw(self, tmp_path: Path, payload: object) -> None:
        path = constants.changes_path(SLUG, data_root=tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_read_root_not_list_raises(self, tmp_path: Path) -> None:
        self._write_raw(tmp_path, {"not": "a list"})
        with pytest.raises(DiscoveryError):
            storage.read_changes(SLUG, data_root=tmp_path)

    def test_read_item_not_object_raises(self, tmp_path: Path) -> None:
        self._write_raw(tmp_path, ["not an object"])
        with pytest.raises(DiscoveryError):
            storage.read_changes(SLUG, data_root=tmp_path)

    def test_read_invalid_enum_raises(self, tmp_path: Path) -> None:
        d = _change().to_dict()
        d["change_type"] = "BOGUS"
        self._write_raw(tmp_path, [d])
        with pytest.raises(DiscoveryError):
            storage.read_changes(SLUG, data_root=tmp_path)

    def test_read_bad_date_raises(self, tmp_path: Path) -> None:
        d = _change().to_dict()
        d["period"] = "not-a-date"
        self._write_raw(tmp_path, [d])
        with pytest.raises(DiscoveryError):
            storage.read_changes(SLUG, data_root=tmp_path)

    def test_read_missing_required_field_raises(self, tmp_path: Path) -> None:
        d = _change().to_dict()
        del d["prior_period"]
        self._write_raw(tmp_path, [d])
        with pytest.raises(DiscoveryError):
            storage.read_changes(SLUG, data_root=tmp_path)

    def test_read_back_change_type_is_member(self, tmp_path: Path) -> None:
        storage.write_changes(SLUG, [_change()], data_root=tmp_path)
        loaded = storage.read_changes(SLUG, data_root=tmp_path)
        assert isinstance(loaded[0].change_type, ChangeType)


def _return(
    *,
    cusip: str = "037833100",
    cik: str = "0001777813",
    change_type: ChangeType = ChangeType.HOLD,
    security_type: str = constants.SECURITY_TYPE_COMMON,
    filing_date: date = date(2024, 5, 15),
) -> ReturnRecord:
    return ReturnRecord(
        cik=cik,
        cusip=cusip,
        ticker="X",
        eodhd_symbol="X.US",
        security_type=security_type,
        change_type=change_type,
        period=date(2024, 3, 31),
        filing_date=filing_date,
        next_filing_date=date(2024, 8, 14),
        priced=True,
        is_underlying_price=security_type in {"PUT", "CALL"},
        price_on_filing_date=100.0,
        price_on_next_filing_date=110.0,
        next_period_high=120.0,
        next_period_low=90.0,
        next_period_high_date=date(2024, 6, 1),
        next_period_low_date=date(2024, 7, 1),
        filing_to_filing_return_pct=10.0,
        filing_to_next_period_high_pct=20.0,
        filing_to_next_period_low_pct=-10.0,
        entry_quarter_high=None,
        entry_quarter_low=None,
        best_case_entry_price=None,
        worst_case_entry_price=None,
        best_case_entry_return_pct=None,
        worst_case_entry_return_pct=None,
        cumulative_return_pct=None,
        cumulative_from_filing_date=None,
        cumulative_to_filing_date=None,
        spy_filing_to_filing_return_pct=5.0,
        spy_next_period_high_pct=8.0,
        spy_next_period_low_pct=-2.0,
        smh_filing_to_filing_return_pct=6.0,
        smh_next_period_high_pct=9.0,
        smh_next_period_low_pct=-3.0,
    )


class TestReturns:
    def test_round_trip(self, tmp_path: Path) -> None:
        records = [_return(cusip="037833100"), _return(cusip="00846U101")]
        storage.write_returns(SLUG, records, data_root=tmp_path)
        loaded = storage.read_returns(SLUG, data_root=tmp_path)
        assert {r.cusip for r in loaded} == {"037833100", "00846U101"}

    def test_empty_writes_and_reads_empty(self, tmp_path: Path) -> None:
        path = storage.write_returns(SLUG, [], data_root=tmp_path)
        assert json.loads(path.read_text(encoding="utf-8")) == []
        assert storage.read_returns(SLUG, data_root=tmp_path) == []

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.read_returns(SLUG, data_root=tmp_path)

    def test_multi_cik_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.write_returns(
                SLUG,
                [_return(cik="0001777813"), _return(cik="0009999999")],
                data_root=tmp_path,
            )

    def test_dup_4tuple_raises(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.write_returns(
                SLUG, [_return(), _return()], data_root=tmp_path
            )

    def test_dup_4tuple_distinguished_by_change_type(self, tmp_path: Path) -> None:
        # same (filing_date, cusip, security_type) but different change_type -> NOT a dup.
        storage.write_returns(
            SLUG,
            [_return(change_type=ChangeType.HOLD), _return(change_type=ChangeType.NEW)],
            data_root=tmp_path,
        )
        # NEW with no entry fields is valid; just confirm no raise + both persisted.
        assert len(storage.read_returns(SLUG, data_root=tmp_path)) == 2

    def test_deterministic_sort(self, tmp_path: Path) -> None:
        a = _return(cusip="037833100", filing_date=date(2024, 5, 15))
        b = _return(cusip="00846U101", filing_date=date(2024, 2, 14))
        storage.write_returns(SLUG, [a, b], data_root=tmp_path)
        loaded = storage.read_returns(SLUG, data_root=tmp_path)
        # sorted by filing_date first.
        assert loaded[0].filing_date == date(2024, 2, 14)

    def test_no_schema_version_key(self, tmp_path: Path) -> None:
        path = storage.write_returns(SLUG, [_return()], data_root=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert "schema_version" not in data[0]

    def test_path_safety(self, tmp_path: Path) -> None:
        with pytest.raises(DiscoveryError):
            storage.write_returns("../escape", [_return()], data_root=tmp_path)


def _fund(symbol: str, *, sector: str | None, resolved: bool) -> FundamentalsEntry:
    return FundamentalsEntry(
        eodhd_symbol=symbol,
        sector=sector,
        industry=None,
        instrument_type=None,
        resolved=resolved,
        fetched_at="2024-01-01T00:00:00+00:00",
    )


class TestFundamentalsCache:
    def test_round_trip(self, tmp_path: Path) -> None:
        cache = {
            "AAA.US": _fund("AAA.US", sector="Technology", resolved=True),
            "GONE.US": _fund("GONE.US", sector=None, resolved=False),
        }
        storage.write_fundamentals_cache(cache, data_root=tmp_path)
        loaded = storage.read_fundamentals_cache(tmp_path)
        assert loaded == cache

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert storage.read_fundamentals_cache(tmp_path) == {}

    def test_bare_list_sorted_by_symbol(self, tmp_path: Path) -> None:
        cache = {
            "ZZZ.US": _fund("ZZZ.US", sector="X", resolved=True),
            "AAA.US": _fund("AAA.US", sector="Y", resolved=True),
        }
        path = storage.write_fundamentals_cache(cache, data_root=tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert [d["eodhd_symbol"] for d in data] == ["AAA.US", "ZZZ.US"]

    def test_mis_keyed_dict_rejected(self, tmp_path: Path) -> None:
        bad = {"WRONG.US": _fund("AAA.US", sector="X", resolved=True)}
        with pytest.raises(DiscoveryError):
            storage.write_fundamentals_cache(bad, data_root=tmp_path)

    def test_duplicate_symbol_on_read_rejected(self, tmp_path: Path) -> None:
        path = constants.fundamentals_cache_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                [
                    {"eodhd_symbol": "AAA.US", "sector": "X", "industry": None,
                     "instrument_type": None, "resolved": True, "fetched_at": None},
                    {"eodhd_symbol": "AAA.US", "sector": "Y", "industry": None,
                     "instrument_type": None, "resolved": True, "fetched_at": None},
                ]
            ),
            encoding="utf-8",
        )
        with pytest.raises(DiscoveryError):
            storage.read_fundamentals_cache(tmp_path)

    def test_non_list_root_rejected(self, tmp_path: Path) -> None:
        path = constants.fundamentals_cache_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        with pytest.raises(DiscoveryError):
            storage.read_fundamentals_cache(tmp_path)


class TestTickerClassifications:
    def _write(self, tmp_path: Path, obj: object) -> None:
        path = constants.ticker_classifications_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding="utf-8")

    def test_round_trip(self, tmp_path: Path) -> None:
        self._write(
            tmp_path,
            {
                "AMD": {"sector": "Semiconductors", "industry": "Chip Design", "theme": "AI"},
                "CIEN": {"sector": "Networking", "industry": "Optical", "theme": "AI Optical"},
            },
        )
        out = storage.read_ticker_classifications(tmp_path)
        assert out["AMD"] == {
            "sector": "Semiconductors", "industry": "Chip Design", "theme": "AI"
        }
        assert out["CIEN"]["theme"] == "AI Optical"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert storage.read_ticker_classifications(tmp_path) == {}

    def test_missing_fields_become_none(self, tmp_path: Path) -> None:
        self._write(tmp_path, {"X": {"sector": "Tech"}})  # industry/theme absent
        out = storage.read_ticker_classifications(tmp_path)
        assert out["X"] == {"sector": "Tech", "industry": None, "theme": None}

    def test_explicit_null_field(self, tmp_path: Path) -> None:
        self._write(tmp_path, {"X": {"sector": None, "industry": None, "theme": "Macro"}})
        out = storage.read_ticker_classifications(tmp_path)
        assert out["X"]["sector"] is None
        assert out["X"]["theme"] == "Macro"

    def test_non_object_root_rejected(self, tmp_path: Path) -> None:
        self._write(tmp_path, [{"AMD": "x"}])
        with pytest.raises(DiscoveryError):
            storage.read_ticker_classifications(tmp_path)

    def test_non_object_value_rejected(self, tmp_path: Path) -> None:
        self._write(tmp_path, {"AMD": "Semiconductors"})
        with pytest.raises(DiscoveryError):
            storage.read_ticker_classifications(tmp_path)

    def test_non_string_field_rejected(self, tmp_path: Path) -> None:
        self._write(tmp_path, {"AMD": {"sector": 123}})
        with pytest.raises(DiscoveryError):
            storage.read_ticker_classifications(tmp_path)
