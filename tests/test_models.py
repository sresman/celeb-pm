"""Tests for celebpm.models PositionRecord + numeric helpers + FilingRecord schema change."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime, timezone
from typing import Any

import pytest

from celebpm import constants, models
from celebpm.errors import DiscoveryError
from celebpm.models import (
    ChangeType,
    CusipMapEntry,
    FilingRecord,
    PositionChange,
    PositionRecord,
)


def _common(**overrides: Any) -> PositionRecord:
    base: dict[str, Any] = dict(
        cik="0001777813",
        accession_number="0001777813-26-000012",
        period=date(2025, 12, 31),
        filing_date=date(2026, 2, 14),
        cusip="00846U101",
        company_name="ALPHA CORP",
        title_of_class="COM",
        security_type=constants.SECURITY_TYPE_COMMON,
        put_call="",
        shares=1000,
        ssh_prnamt_type=constants.SSH_TYPE_SHARES,
        value_reported=500000,
        investment_discretion="SOLE",
        weight_pct_reported=50.0,
        weight_pct_equity_only=50.0,
    )
    base.update(overrides)
    return PositionRecord(**base)


class TestPositionRecordValidation:
    def test_valid_common(self) -> None:
        rec = _common()
        assert rec.ticker is None

    def test_security_type_putcall_consistency(self) -> None:
        with pytest.raises(DiscoveryError):
            _common(security_type=constants.SECURITY_TYPE_PUT, put_call="")

    def test_put_requires_none_equity_weight(self) -> None:
        with pytest.raises(DiscoveryError):
            _common(
                security_type=constants.SECURITY_TYPE_PUT,
                put_call=constants.PUT_CALL_PUT,
                weight_pct_equity_only=10.0,
            )

    def test_put_with_none_equity_weight_ok(self) -> None:
        rec = _common(
            security_type=constants.SECURITY_TYPE_PUT,
            put_call=constants.PUT_CALL_PUT,
            weight_pct_equity_only=None,
        )
        assert rec.weight_pct_equity_only is None

    def test_common_requires_non_none_equity_weight(self) -> None:
        with pytest.raises(DiscoveryError):
            _common(weight_pct_equity_only=None)

    def test_bad_cusip_length(self) -> None:
        with pytest.raises(DiscoveryError):
            _common(cusip="SHORT")

    def test_bad_cusip_out_of_alphabet(self) -> None:
        with pytest.raises(DiscoveryError):
            _common(cusip="00846u101")  # lowercase letter fails uppercase check

    def test_special_char_cusip_accepted(self) -> None:
        rec = _common(cusip="1234*6@#9")
        assert rec.cusip == "1234*6@#9"

    def test_empty_company_name_accepted(self) -> None:
        rec = _common(company_name="")
        assert rec.company_name == ""

    def test_negative_value_rejected(self) -> None:
        with pytest.raises(DiscoveryError):
            _common(value_reported=-1)


def _as_obj(d: dict[str, Any]) -> dict[str, object]:
    """Widen a to_dict() result to dict[str, object] for from_dict (dict is invariant)."""
    return dict(d)


class TestKwOnly:
    def test_positional_construction_typeerror(self) -> None:
        with pytest.raises(TypeError):
            PositionRecord(  # type: ignore[misc,call-arg]
                "0001777813",
                "acc",
                date(2025, 12, 31),
            )

    def test_keyword_construction_ok(self) -> None:
        assert _common().cik == "0001777813"


class TestRoundTrip:
    def test_common_round_trip(self) -> None:
        rec = _common()
        d = rec.to_dict()
        assert d["value_reported"] == 500000  # SD-3 key name
        assert "value_thousands" not in d
        assert PositionRecord.from_dict(_as_obj(d)) == rec

    def test_option_round_trip_none_fields(self) -> None:
        rec = _common(
            security_type=constants.SECURITY_TYPE_CALL,
            put_call=constants.PUT_CALL_CALL,
            weight_pct_equity_only=None,
            ticker=None,
        )
        d = rec.to_dict()
        assert d["weight_pct_equity_only"] is None
        assert d["ticker"] is None
        assert PositionRecord.from_dict(_as_obj(d)) == rec

    def test_int_weight_parses_as_float(self) -> None:
        rec = _common()
        d = rec.to_dict()
        d["weight_pct_reported"] = 50  # JSON int, not float
        parsed = PositionRecord.from_dict(_as_obj(d))
        assert parsed.weight_pct_reported == 50.0


class TestNumericHelpers:
    def test_require_float_accepts_int_and_float(self) -> None:
        assert models._require_float({"x": 1}, "x") == 1.0
        assert models._require_float({"x": 1.5}, "x") == 1.5

    def test_require_float_rejects_bool(self) -> None:
        with pytest.raises(TypeError):
            models._require_float({"x": True}, "x")

    def test_require_float_rejects_string(self) -> None:
        with pytest.raises(TypeError):
            models._require_float({"x": "1.0"}, "x")

    def test_optional_float_none(self) -> None:
        assert models._optional_float({"x": None}, "x") is None

    def test_optional_float_rejects_bool(self) -> None:
        with pytest.raises(TypeError):
            models._optional_float({"x": False}, "x")

    def test_require_int_rejects_bool(self) -> None:
        with pytest.raises(TypeError):
            models._require_int({"x": True}, "x")

    def test_optional_int_rejects_bool(self) -> None:
        with pytest.raises(TypeError):
            models._optional_int({"x": True}, "x")


def _filing(**overrides: Any) -> FilingRecord:
    base: dict[str, Any] = dict(
        cik="0001777813",
        accession_number="0001777813-25-000040",
        filing_index_url=constants.filing_index_url("0001777813", "0001777813-25-000040"),
        primary_doc="primary_doc.xml",
        fund_name="Atreides Management, LP",
        form_type=constants.FORM_13F_HR,
        period_of_report=date(2025, 9, 30),
        filing_date=date(2025, 11, 14),
        accepted_date=datetime(2025, 11, 14, 17, 5, tzinfo=timezone.utc),
        amendment=False,
        amendment_type=constants.AMENDMENT_TYPE_NONE,
    )
    base.update(overrides)
    return FilingRecord(**base)


class TestFilingRecordSchemaChange:
    def test_total_equity_value_round_trips(self) -> None:
        rec = _filing(total_portfolio_value=1000, total_equity_value=800, position_count=3)
        d = rec.to_dict()
        assert d["total_equity_value"] == 800
        assert FilingRecord.from_dict(_as_obj(d)) == rec

    def test_old_dict_without_key_parses_as_none(self) -> None:
        rec = _filing()
        d = rec.to_dict()
        del d["total_equity_value"]  # simulate a pre-Prompt-2 filings.json entry
        parsed = FilingRecord.from_dict(_as_obj(d))
        assert parsed.total_equity_value is None


VALID_CUSIP = "037833100"


def _entry(**overrides: Any) -> CusipMapEntry:
    base: dict[str, Any] = dict(
        cusip=VALID_CUSIP,
        ticker="AAPL",
        name="APPLE INC",
        exch_code="US",
        figi_security_type="Common Stock",
        figi_security_type2="Common Stock",
        market_sector="Equity",
        figi="BBG000B9XVV8",
        source=constants.CUSIP_SOURCE_OPENFIGI,
        ambiguous=False,
        resolved_at="2026-06-11T14:03:22.512000+00:00",
    )
    base.update(overrides)
    return CusipMapEntry(**base)


class TestCusipMapEntry:
    def test_round_trip(self) -> None:
        rec = _entry(ambiguous=True)
        d = rec.to_dict()
        assert d["figi_security_type2"] == "Common Stock"
        assert d["market_sector"] == "Equity"
        assert d["ambiguous"] is True
        assert d["resolved_at"] == "2026-06-11T14:03:22.512000+00:00"
        assert CusipMapEntry.from_dict(_as_obj(d)) == rec

    def test_unresolved_round_trip(self) -> None:
        rec = _entry(
            ticker=None,
            name=None,
            exch_code=None,
            figi_security_type=None,
            figi_security_type2=None,
            market_sector=None,
            figi=None,
            source=constants.CUSIP_SOURCE_UNRESOLVED,
        )
        assert CusipMapEntry.from_dict(_as_obj(rec.to_dict())) == rec

    def test_unresolved_with_ticker_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _entry(source=constants.CUSIP_SOURCE_UNRESOLVED, ticker="AAPL")

    def test_non_unresolved_with_none_ticker_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _entry(source=constants.CUSIP_SOURCE_OPENFIGI, ticker=None)

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_ticker_invariant_raises(self, blank: str) -> None:
        with pytest.raises(DiscoveryError):
            _entry(source=constants.CUSIP_SOURCE_MANUAL, ticker=blank)

    def test_bad_source_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _entry(source="bogus")

    def test_bad_cusip_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _entry(cusip="SHORT")

    def test_forward_compat_missing_optional_fields(self) -> None:
        # Old/hand-written row omits figi_security_type2 / market_sector / ambiguous.
        raw: dict[str, object] = {
            "cusip": VALID_CUSIP,
            "ticker": "AAPL",
            "source": constants.CUSIP_SOURCE_MANUAL,
        }
        parsed = CusipMapEntry.from_dict(raw)
        assert parsed.figi_security_type2 is None
        assert parsed.market_sector is None
        assert parsed.ambiguous is False
        assert parsed.resolved_at is None


# --------------------------------------------------------------------------- #
# PositionChange (Prompt 4)
# --------------------------------------------------------------------------- #

PERIOD_PRIOR = date(2025, 3, 31)
PERIOD_CUR = date(2025, 6, 30)
FILING_PRIOR = date(2025, 5, 15)
FILING_CUR = date(2025, 8, 14)
PC_CUSIP = "00846U101"


def _matched(**overrides: Any) -> PositionChange:
    base: dict[str, Any] = dict(
        cik="0001777813",
        period=PERIOD_CUR,
        filing_date=FILING_CUR,
        prior_period=PERIOD_PRIOR,
        prior_filing_date=FILING_PRIOR,
        cusip=PC_CUSIP,
        security_type=constants.SECURITY_TYPE_COMMON,
        ticker="ALPHA",
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
        change_type=ChangeType.ACTIVE_ADD,
        split_suspected=False,
        corporate_action_note="",
    )
    base.update(overrides)
    return PositionChange(**base)


def _new(**overrides: Any) -> PositionChange:
    base: dict[str, Any] = dict(
        cik="0001777813",
        period=PERIOD_CUR,
        filing_date=FILING_CUR,
        prior_period=PERIOD_PRIOR,
        prior_filing_date=FILING_PRIOR,
        cusip=PC_CUSIP,
        security_type=constants.SECURITY_TYPE_COMMON,
        ticker="ALPHA",
        current_shares=1200,
        current_value_reported=620_000,
        current_weight_pct=50.6,
        prior_shares=None,
        prior_value_reported=None,
        prior_weight_pct=None,
        shares_delta=None,
        shares_delta_pct=None,
        weight_delta_bps=None,
        value_delta=None,
        value_delta_pct=None,
        change_type=ChangeType.NEW,
        split_suspected=False,
        corporate_action_note="",
    )
    base.update(overrides)
    return PositionChange(**base)


def _exit(**overrides: Any) -> PositionChange:
    base: dict[str, Any] = dict(
        cik="0001777813",
        period=PERIOD_CUR,
        filing_date=FILING_CUR,
        prior_period=PERIOD_PRIOR,
        prior_filing_date=FILING_PRIOR,
        cusip=PC_CUSIP,
        security_type=constants.SECURITY_TYPE_COMMON,
        ticker="ALPHA",
        current_shares=None,
        current_value_reported=None,
        current_weight_pct=None,
        prior_shares=1000,
        prior_value_reported=500_000,
        prior_weight_pct=50.0,
        shares_delta=None,
        shares_delta_pct=None,
        weight_delta_bps=None,
        value_delta=None,
        value_delta_pct=None,
        change_type=ChangeType.EXIT,
        split_suspected=False,
        corporate_action_note="",
    )
    base.update(overrides)
    return PositionChange(**base)


class TestPositionChangeRoundTrip:
    def _round_trip(self, pc: PositionChange) -> PositionChange:
        return PositionChange.from_dict(json.loads(json.dumps(pc.to_dict())))

    def test_round_trip_new(self) -> None:
        pc = _new()
        assert self._round_trip(pc) == pc

    def test_round_trip_exit(self) -> None:
        pc = _exit()
        assert self._round_trip(pc) == pc

    def test_round_trip_matched(self) -> None:
        pc = _matched()
        assert self._round_trip(pc) == pc

    def test_round_trip_split_hold(self) -> None:
        pc = _matched(
            change_type=ChangeType.HOLD,
            split_suspected=True,
            shares_delta_pct=100.0,
            value_delta_pct=0.0,
            weight_delta_bps=200.0,
        )
        assert self._round_trip(pc) == pc

    def test_change_type_serializes_as_bare_string(self) -> None:
        d = _matched().to_dict()
        assert d["change_type"] == "ACTIVE_ADD"
        assert isinstance(d["change_type"], str)

    def test_from_dict_unknown_change_type_raises(self) -> None:
        d = _matched().to_dict()
        d["change_type"] = "BOGUS"
        with pytest.raises(DiscoveryError):
            PositionChange.from_dict(_as_obj(d))


class TestPositionChangeInvariants:
    def test_new_with_prior_shares_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _new(prior_shares=1000)

    def test_exit_with_current_shares_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _exit(current_shares=1000)

    def test_invalid_cusip_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(cusip="SHORT")

    def test_bad_security_type_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(security_type="BOGUS")

    def test_negative_current_shares_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(current_shares=-1)

    def test_from_dict_missing_corp_note_defaults_empty(self) -> None:
        d = _matched().to_dict()
        del d["corporate_action_note"]
        assert PositionChange.from_dict(_as_obj(d)).corporate_action_note == ""

    def test_from_dict_null_corp_note_defaults_empty(self) -> None:
        d = _matched().to_dict()
        d["corporate_action_note"] = None
        assert PositionChange.from_dict(_as_obj(d)).corporate_action_note == ""

    def test_new_carries_prior_period_ok(self) -> None:
        pc = _new()
        assert pc.prior_period == PERIOD_PRIOR
        assert pc.prior_filing_date == FILING_PRIOR

    def test_new_with_none_prior_period_does_not_silently_succeed(self) -> None:
        with pytest.raises((TypeError, DiscoveryError)):
            _new(prior_period=None)

    def test_from_dict_missing_prior_period_raises(self) -> None:
        d = _matched().to_dict()
        del d["prior_period"]
        with pytest.raises(DiscoveryError):
            PositionChange.from_dict(_as_obj(d))

    def test_split_with_active_add_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(split_suspected=True, change_type=ChangeType.ACTIVE_ADD)

    def test_split_with_drift_up_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(split_suspected=True, change_type=ChangeType.DRIFT_UP)

    def test_split_with_new_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _new(split_suspected=True)

    def test_split_with_exit_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _exit(split_suspected=True)

    def test_split_with_hold_ok(self) -> None:
        pc = _matched(
            split_suspected=True,
            change_type=ChangeType.HOLD,
            shares_delta_pct=100.0,
            value_delta_pct=0.0,
            weight_delta_bps=200.0,
        )
        assert pc.split_suspected is True
        assert pc.change_type == ChangeType.HOLD

    def test_replace_corp_note_each_change_type(self) -> None:
        instances = [
            _new(),
            _exit(),
            _matched(change_type=ChangeType.ACTIVE_ADD),
            _matched(
                change_type=ChangeType.ACTIVE_TRIM,
                shares_delta=-200, shares_delta_pct=-20.0, weight_delta_bps=-60.0,
                value_delta=-120_000, value_delta_pct=-24.0,
            ),
            _matched(change_type=ChangeType.DRIFT_UP, shares_delta_pct=5.0,
                     weight_delta_bps=60.0),
            _matched(change_type=ChangeType.DRIFT_DOWN, shares_delta_pct=-5.0,
                     weight_delta_bps=-60.0),
            _matched(change_type=ChangeType.HOLD, shares_delta_pct=1.0,
                     weight_delta_bps=5.0),
            _matched(change_type=ChangeType.HOLD, split_suspected=True,
                     shares_delta_pct=100.0, value_delta_pct=0.0, weight_delta_bps=200.0),
        ]
        for inst in instances:
            replaced = dataclasses.replace(inst, corporate_action_note="merger")
            assert replaced.corporate_action_note == "merger"
            assert isinstance(replaced, PositionChange)

    def test_raw_string_change_type_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(change_type="ACTIVE_ADD")

    def test_split_suspected_non_bool_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(split_suspected=1)

    def test_from_dict_split_suspected_int_raises(self) -> None:
        d = _matched().to_dict()
        d["split_suspected"] = 1
        with pytest.raises(DiscoveryError):
            PositionChange.from_dict(_as_obj(d))

    def test_bool_in_numeric_field_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(current_shares=True)

    def test_negative_weight_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(current_weight_pct=-1.0)

    def test_negative_prior_weight_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(prior_weight_pct=-1.0)

    def test_nan_inf_in_float_field_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(weight_delta_bps=float("inf"))
        with pytest.raises(DiscoveryError):
            _matched(shares_delta_pct=float("nan"))

    def test_large_finite_value_delta_pct_passes(self) -> None:
        # SD-2 boundary artifact (~+100,000%) is large but FINITE -> passes
        pc = _matched(value_delta_pct=100000.0)
        assert pc.value_delta_pct == pytest.approx(100000.0)

    def test_from_dict_corp_note_non_str_raises(self) -> None:
        d = _matched().to_dict()
        d["corporate_action_note"] = 123
        with pytest.raises(DiscoveryError):
            PositionChange.from_dict(_as_obj(d))

    def test_direct_non_str_corp_note_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(corporate_action_note=123)

    def test_replace_corp_note_returns_valid(self) -> None:
        pc = _matched()
        replaced = dataclasses.replace(pc, corporate_action_note="merger")
        assert replaced.corporate_action_note == "merger"

    def test_prior_period_after_period_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(prior_period=date(2025, 9, 30))  # > period

    def test_prior_period_equal_period_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _matched(prior_period=PERIOD_CUR)

    def test_prior_filing_date_after_filing_date_ok(self) -> None:
        # filing-date ordering NOT enforced (amendments/late filings)
        pc = _matched(prior_filing_date=date(2025, 9, 1))  # > filing_date but period ok
        assert pc.prior_filing_date == date(2025, 9, 1)

    def test_ticker_both_none_ok(self) -> None:
        assert _matched(ticker=None).ticker is None
        assert _new(ticker=None).ticker is None
        assert _exit(ticker=None).ticker is None


# --- ReturnRecord (Prompt 5) ---

from celebpm.models import ReturnRecord  # noqa: E402

_RR_CIK = "0001234567"
_RR_CUSIP = "037833100"
_FD = date(2024, 5, 15)
_NFD = date(2024, 8, 14)


def _priced_common(**over: Any) -> ReturnRecord:  # noqa: ANN401
    base: dict[str, Any] = dict(
        cik=_RR_CIK,
        cusip=_RR_CUSIP,
        ticker="AAPL",
        eodhd_symbol="AAPL.US",
        security_type="COMMON",
        change_type=ChangeType.HOLD,
        period=date(2024, 3, 31),
        filing_date=_FD,
        next_filing_date=_NFD,
        priced=True,
        is_underlying_price=False,
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
    base.update(over)
    return ReturnRecord(**base)


def _unpriced(**over: Any) -> ReturnRecord:  # noqa: ANN401
    base: dict[str, Any] = dict(
        cik=_RR_CIK,
        cusip=_RR_CUSIP,
        ticker="AAPL",
        eodhd_symbol="AAPL.US",
        security_type="COMMON",
        change_type=ChangeType.EXIT,
        period=date(2024, 3, 31),
        filing_date=_FD,
        next_filing_date=_NFD,
        priced=False,
        is_underlying_price=False,
        price_on_filing_date=None,
        price_on_next_filing_date=None,
        next_period_high=None,
        next_period_low=None,
        next_period_high_date=None,
        next_period_low_date=None,
        filing_to_filing_return_pct=None,
        filing_to_next_period_high_pct=None,
        filing_to_next_period_low_pct=None,
        entry_quarter_high=None,
        entry_quarter_low=None,
        best_case_entry_price=None,
        worst_case_entry_price=None,
        best_case_entry_return_pct=None,
        worst_case_entry_return_pct=None,
        cumulative_return_pct=None,
        cumulative_from_filing_date=None,
        cumulative_to_filing_date=None,
        spy_filing_to_filing_return_pct=None,
        spy_next_period_high_pct=None,
        spy_next_period_low_pct=None,
        smh_filing_to_filing_return_pct=None,
        smh_next_period_high_pct=None,
        smh_next_period_low_pct=None,
    )
    base.update(over)
    return ReturnRecord(**base)


class TestReturnRecordRoundTrip:
    def test_priced_round_trip(self) -> None:
        rec = _priced_common()
        assert ReturnRecord.from_dict(_as_obj(rec.to_dict())) == rec

    def test_unpriced_round_trip(self) -> None:
        rec = _unpriced()
        assert ReturnRecord.from_dict(_as_obj(rec.to_dict())) == rec

    def test_period_round_trips(self) -> None:
        rec = _priced_common(period=date(2024, 1, 31))
        assert ReturnRecord.from_dict(_as_obj(rec.to_dict())).period == date(2024, 1, 31)

    def test_priced_new_with_entry_round_trip(self) -> None:
        rec = _priced_common(
            change_type=ChangeType.NEW,
            entry_quarter_high=80.0,
            entry_quarter_low=50.0,
            best_case_entry_price=50.0,
            worst_case_entry_price=80.0,
            best_case_entry_return_pct=120.0,
            worst_case_entry_return_pct=37.5,
        )
        assert ReturnRecord.from_dict(_as_obj(rec.to_dict())) == rec


class TestReturnRecordInvariants:
    def test_unpriced_identity_allowed(self) -> None:
        # identity/audit fields all set, everything else None -> OK.
        assert _unpriced().priced is False

    def test_unpriced_with_price_field_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _unpriced(price_on_filing_date=10.0)

    def test_priced_missing_core_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(price_on_filing_date=None)

    def test_priced_new_all_entry_none_ok(self) -> None:
        rec = _priced_common(change_type=ChangeType.NEW)
        assert rec.entry_quarter_high is None

    def test_partial_entry_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(change_type=ChangeType.NEW, entry_quarter_high=80.0)

    def test_entry_on_non_new_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(
                entry_quarter_high=80.0,
                entry_quarter_low=50.0,
                best_case_entry_price=50.0,
                worst_case_entry_price=80.0,
                best_case_entry_return_pct=10.0,
                worst_case_entry_return_pct=5.0,
            )

    def test_underlying_mismatch_common_true_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(is_underlying_price=True)

    def test_underlying_mismatch_put_false_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(security_type="PUT", is_underlying_price=False)

    def test_zero_price_accepted(self) -> None:
        # 0.0 is accepted at the model level (the >0 denominator rule is the engine's).
        rec = _priced_common(
            price_on_filing_date=0.0,
            next_period_low=0.0,
            filing_to_next_period_low_pct=-100.0,
        )
        assert rec.price_on_filing_date == 0.0

    def test_negative_price_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(next_period_low=-1.0)

    def test_negative_return_accepted(self) -> None:
        rec = _priced_common(filing_to_filing_return_pct=-100.0)
        assert rec.filing_to_filing_return_pct == -100.0

    def test_non_finite_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(filing_to_filing_return_pct=float("inf"))

    def test_high_below_low_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(next_period_high=50.0, next_period_low=90.0)

    def test_entry_high_below_low_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(
                change_type=ChangeType.NEW,
                entry_quarter_high=10.0,
                entry_quarter_low=90.0,
                best_case_entry_price=90.0,
                worst_case_entry_price=10.0,
                best_case_entry_return_pct=1.0,
                worst_case_entry_return_pct=2.0,
            )

    def test_alias_mismatch_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(
                change_type=ChangeType.NEW,
                entry_quarter_high=80.0,
                entry_quarter_low=50.0,
                best_case_entry_price=51.0,  # != entry_quarter_low
                worst_case_entry_price=80.0,
                best_case_entry_return_pct=1.0,
                worst_case_entry_return_pct=2.0,
            )

    def test_spy_partial_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(spy_next_period_high_pct=None)

    def test_spy_all_none_with_priced_ok(self) -> None:
        rec = _priced_common(
            spy_filing_to_filing_return_pct=None,
            spy_next_period_high_pct=None,
            spy_next_period_low_pct=None,
        )
        assert rec.priced is True

    def test_bad_cik_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(cik="not-a-cik")

    def test_bad_cusip_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(cusip="short")

    def test_filing_after_next_filing_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(filing_date=date(2024, 9, 1), next_filing_date=date(2024, 8, 14))

    def test_cumulative_from_after_to_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            _priced_common(
                cumulative_return_pct=10.0,
                cumulative_from_filing_date=date(2024, 9, 1),
                cumulative_to_filing_date=date(2024, 8, 1),
            )
