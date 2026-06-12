"""Tests for celebpm.diff — classify_change, diff_quarters, compute_changes (spec §1.4).

Pure unit tests, no network, no disk.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from celebpm import constants
from celebpm.diff import (
    _compute_deltas,
    classify_change,
    compute_changes,
    diff_quarters,
)
from celebpm.errors import DiscoveryError
from celebpm.models import ChangeType, PositionChange, PositionRecord

COMMON = constants.SECURITY_TYPE_COMMON
PUT = constants.SECURITY_TYPE_PUT
CALL = constants.SECURITY_TYPE_CALL

Q1 = date(2025, 3, 31)
Q2 = date(2025, 6, 30)
Q3 = date(2025, 9, 30)
F1 = date(2025, 5, 15)
F2 = date(2025, 8, 14)
F3 = date(2025, 11, 14)


def _pos(**overrides: Any) -> PositionRecord:
    """Build a valid PositionRecord; override only the fields under test."""
    sec = overrides.get("security_type", COMMON)
    base: dict[str, Any] = dict(
        cik="0001777813",
        accession_number="0001777813-25-000001",
        period=Q1,
        filing_date=F1,
        cusip="00846U101",
        company_name="ALPHA CORP",
        title_of_class="COM",
        security_type=sec,
        put_call=("" if sec == COMMON else sec),
        shares=1000,
        ssh_prnamt_type=constants.SSH_TYPE_SHARES,
        value_reported=500_000,
        investment_discretion="SOLE",
        weight_pct_reported=50.0,
        weight_pct_equity_only=(50.0 if sec == COMMON else None),
    )
    base.update(overrides)
    # keep put_call consistent if security_type overridden without put_call
    if "security_type" in overrides and "put_call" not in overrides:
        base["put_call"] = "" if overrides["security_type"] == COMMON else overrides[
            "security_type"
        ]
    if "security_type" in overrides and "weight_pct_equity_only" not in overrides:
        base["weight_pct_equity_only"] = (
            base["weight_pct_reported"] if overrides["security_type"] == COMMON else None
        )
    return PositionRecord(**base)


# --------------------------------------------------------------------------- #
# 6a. classify_change threshold matrix (security_type=COMMON unless noted)
# --------------------------------------------------------------------------- #


class TestClassifyThresholds:
    def test_active_add(self) -> None:
        assert classify_change(
            shares_delta_pct=20.0, weight_delta_bps=60.0, value_delta_pct=20.0,
            security_type=COMMON,
        ) == (ChangeType.ACTIVE_ADD, False)

    def test_active_add_boundary_shares_exactly_10(self) -> None:
        # shares exactly +10.0 -> NOT > 10 (strict) -> not ACTIVE_ADD; abs(10)<=10 -> DRIFT_UP
        assert classify_change(
            shares_delta_pct=10.0, weight_delta_bps=60.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.DRIFT_UP, False)

    def test_active_add_boundary_weight_exactly_50(self) -> None:
        # shares +11%, weight exactly +50.0 -> not ACTIVE_ADD; weight not > 50 -> not DRIFT_UP
        assert classify_change(
            shares_delta_pct=11.0, weight_delta_bps=50.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_active_trim(self) -> None:
        assert classify_change(
            shares_delta_pct=-20.0, weight_delta_bps=-60.0, value_delta_pct=-20.0,
            security_type=COMMON,
        ) == (ChangeType.ACTIVE_TRIM, False)

    def test_active_trim_boundary_shares_exactly_neg10(self) -> None:
        assert classify_change(
            shares_delta_pct=-10.0, weight_delta_bps=-60.0, value_delta_pct=-5.0,
            security_type=COMMON,
        ) == (ChangeType.DRIFT_DOWN, False)

    def test_active_trim_boundary_weight_exactly_neg50(self) -> None:
        assert classify_change(
            shares_delta_pct=-20.0, weight_delta_bps=-50.0, value_delta_pct=-5.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_drift_up(self) -> None:
        assert classify_change(
            shares_delta_pct=5.0, weight_delta_bps=60.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.DRIFT_UP, False)

    def test_drift_up_zero_shares_delta(self) -> None:
        assert classify_change(
            shares_delta_pct=0.0, weight_delta_bps=60.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.DRIFT_UP, False)

    def test_drift_down(self) -> None:
        assert classify_change(
            shares_delta_pct=-5.0, weight_delta_bps=-60.0, value_delta_pct=-5.0,
            security_type=COMMON,
        ) == (ChangeType.DRIFT_DOWN, False)

    def test_hold_subthreshold_weight(self) -> None:
        assert classify_change(
            shares_delta_pct=5.0, weight_delta_bps=10.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_hold_active_shares_subthreshold_weight(self) -> None:
        # active share move but sub-threshold weight -> HOLD
        assert classify_change(
            shares_delta_pct=20.0, weight_delta_bps=10.0, value_delta_pct=20.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_hold_shares_up_weight_down_small(self) -> None:
        assert classify_change(
            shares_delta_pct=5.0, weight_delta_bps=-10.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_exact_pos_50_bps_with_big_shares_is_hold(self) -> None:
        assert classify_change(
            shares_delta_pct=20.0, weight_delta_bps=50.0, value_delta_pct=20.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_exact_neg_50_bps_with_big_shares_is_hold(self) -> None:
        assert classify_change(
            shares_delta_pct=-20.0, weight_delta_bps=-50.0, value_delta_pct=-20.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_shares_delta_pct_none_up_is_hold(self) -> None:
        # weight moved but share intent unprovable -> HOLD, NOT DRIFT_UP
        assert classify_change(
            shares_delta_pct=None, weight_delta_bps=60.0, value_delta_pct=5.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)

    def test_shares_delta_pct_none_down_is_hold(self) -> None:
        assert classify_change(
            shares_delta_pct=None, weight_delta_bps=-60.0, value_delta_pct=-5.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, False)


# --------------------------------------------------------------------------- #
# 6b. split detection -> HOLD via short-circuit
# --------------------------------------------------------------------------- #


class TestSplitDetection:
    def test_split_basic(self) -> None:
        assert classify_change(
            shares_delta_pct=100.0, weight_delta_bps=200.0, value_delta_pct=0.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, True)

    def test_split_within_bands(self) -> None:
        assert classify_change(
            shares_delta_pct=98.0, weight_delta_bps=150.0, value_delta_pct=3.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, True)

    def test_split_weight_fell(self) -> None:
        assert classify_change(
            shares_delta_pct=100.0, weight_delta_bps=-200.0, value_delta_pct=0.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, True)

    def test_split_short_circuit_extreme_weight(self) -> None:
        # extreme weight that any band-tuning could not redirect -> still (HOLD, True)
        assert classify_change(
            shares_delta_pct=100.0, weight_delta_bps=9999.0, value_delta_pct=0.0,
            security_type=COMMON,
        ) == (ChangeType.HOLD, True)

    def test_value_gate_exceeded_is_active_add(self) -> None:
        # genuine doubling that also doubled value -> not a split -> ACTIVE_ADD
        assert classify_change(
            shares_delta_pct=100.0, weight_delta_bps=200.0, value_delta_pct=40.0,
            security_type=COMMON,
        ) == (ChangeType.ACTIVE_ADD, False)

    def test_shares_band_not_met_is_active_add(self) -> None:
        assert classify_change(
            shares_delta_pct=30.0, weight_delta_bps=200.0, value_delta_pct=0.0,
            security_type=COMMON,
        ) == (ChangeType.ACTIVE_ADD, False)

    def test_split_common_only_call(self) -> None:
        assert classify_change(
            shares_delta_pct=100.0, weight_delta_bps=200.0, value_delta_pct=0.0,
            security_type=CALL,
        ) == (ChangeType.ACTIVE_ADD, False)

    def test_split_common_only_put(self) -> None:
        assert classify_change(
            shares_delta_pct=100.0, weight_delta_bps=200.0, value_delta_pct=0.0,
            security_type=PUT,
        ) == (ChangeType.ACTIVE_ADD, False)


# --------------------------------------------------------------------------- #
# 6c. diff_quarters NEW/EXIT + validation
# --------------------------------------------------------------------------- #


class TestDiffQuartersNewExit:
    def test_only_current_is_new_with_real_prior_period(self) -> None:
        prior = [_pos(cusip="00846U101", period=Q1, filing_date=F1)]
        current = [
            _pos(cusip="00846U101", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            _pos(cusip="037833100", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        out = diff_quarters(prior, current)
        new_rows = [c for c in out if c.change_type == ChangeType.NEW]
        assert len(new_rows) == 1
        n = new_rows[0]
        assert n.cusip == "037833100"
        assert n.prior_period == Q1
        assert n.prior_filing_date == F1
        assert n.prior_shares is None
        assert n.prior_value_reported is None
        assert n.prior_weight_pct is None
        assert n.shares_delta is None and n.value_delta is None
        assert n.weight_delta_bps is None
        assert n.current_shares is not None
        assert n.split_suspected is False
        assert n.prior_period < n.period

    def test_only_prior_is_exit_anchored_at_current(self) -> None:
        prior = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="037833100", period=Q1, filing_date=F1),
        ]
        current = [
            _pos(cusip="00846U101", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        out = diff_quarters(prior, current)
        exit_rows = [c for c in out if c.change_type == ChangeType.EXIT]
        assert len(exit_rows) == 1
        e = exit_rows[0]
        assert e.cusip == "037833100"
        assert e.period == Q2 and e.filing_date == F2
        assert e.prior_period == Q1
        assert e.current_shares is None
        assert e.prior_shares is not None
        assert e.shares_delta is None and e.value_delta is None
        assert e.prior_period < e.period

    def test_first_time_put_is_new(self) -> None:
        prior = [_pos(cusip="00846U101", period=Q1, filing_date=F1)]
        current = [
            _pos(cusip="00846U101", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            _pos(cusip="037833100", security_type=PUT, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        out = diff_quarters(prior, current)
        new_put = [
            c for c in out if c.change_type == ChangeType.NEW and c.security_type == PUT
        ]
        assert len(new_put) == 1
        assert new_put[0].cusip == "037833100"

    def test_both_empty_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            diff_quarters([], [])

    def test_empty_prior_raises(self) -> None:
        current = [_pos(period=Q2, filing_date=F2)]
        with pytest.raises(DiscoveryError):
            diff_quarters([], current)

    def test_empty_current_raises(self) -> None:
        prior = [_pos(period=Q1, filing_date=F1)]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, [])

    def test_mixed_cik_across_sides_raises(self) -> None:
        prior = [_pos(cik="0001777813", period=Q1, filing_date=F1)]
        current = [
            _pos(cik="0000000001", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002")
        ]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, current)

    def test_mixed_cik_within_side_raises(self) -> None:
        prior = [
            _pos(cik="0001777813", cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cik="0000000001", cusip="037833100", period=Q1, filing_date=F1),
        ]
        current = [_pos(period=Q2, filing_date=F2, accession_number="0001777813-25-000002")]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, current)

    def test_mixed_period_within_side_raises(self) -> None:
        prior = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="037833100", period=Q2, filing_date=F1),
        ]
        current = [_pos(period=Q3, filing_date=F3, accession_number="0001777813-25-000003")]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, current)

    def test_mixed_filing_date_within_side_raises(self) -> None:
        prior = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="037833100", period=Q1, filing_date=date(2025, 5, 16)),
        ]
        current = [_pos(period=Q2, filing_date=F2, accession_number="0001777813-25-000002")]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, current)

    def test_mixed_accession_within_side_raises(self) -> None:
        prior = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000001"),
            _pos(cusip="037833100", period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000009"),
        ]
        current = [_pos(period=Q2, filing_date=F2, accession_number="0001777813-25-000002")]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, current)

    def test_duplicate_key_within_side_raises(self) -> None:
        prior = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
        ]
        current = [_pos(period=Q2, filing_date=F2, accession_number="0001777813-25-000002")]
        with pytest.raises(DiscoveryError):
            diff_quarters(prior, current)


# --------------------------------------------------------------------------- #
# 6d. equity / options independence
# --------------------------------------------------------------------------- #


class TestEquityOptionsIndependence:
    def test_common_and_call_same_cusip_two_rows(self) -> None:
        prior = [
            _pos(cusip="00846U101", security_type=COMMON, shares=1000,
                 value_reported=500_000, weight_pct_reported=50.0, period=Q1, filing_date=F1),
            _pos(cusip="00846U101", security_type=CALL, shares=100,
                 value_reported=10_000, weight_pct_reported=1.0, period=Q1, filing_date=F1),
        ]
        current = [
            _pos(cusip="00846U101", security_type=COMMON, shares=1300,
                 value_reported=650_000, weight_pct_reported=51.0, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            _pos(cusip="00846U101", security_type=CALL, shares=50,
                 value_reported=5_000, weight_pct_reported=0.4, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        out = diff_quarters(prior, current)
        x_rows = [c for c in out if c.cusip == "00846U101"]
        assert len(x_rows) == 2
        common_row = next(c for c in x_rows if c.security_type == COMMON)
        call_row = next(c for c in x_rows if c.security_type == CALL)
        # COMMON: +30% shares, +100bps -> ACTIVE_ADD
        assert common_row.change_type == ChangeType.ACTIVE_ADD
        assert common_row.weight_delta_bps == pytest.approx(100.0)
        # CALL: -50% shares, -60bps -> ACTIVE_TRIM, on its OWN weight
        assert call_row.change_type == ChangeType.ACTIVE_TRIM
        assert call_row.weight_delta_bps == pytest.approx(-60.0)
        assert call_row.prior_weight_pct == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# 6e. division-by-zero / edge cases
# --------------------------------------------------------------------------- #


class TestDivisionByZeroEdges:
    def test_prior_shares_zero_matched_is_hold(self) -> None:
        prior = [_pos(cusip="00846U101", shares=0, value_reported=500_000,
                      weight_pct_reported=50.0, period=Q1, filing_date=F1)]
        current = [_pos(cusip="00846U101", shares=1000, value_reported=600_000,
                        weight_pct_reported=55.0, period=Q2, filing_date=F2,
                        accession_number="0001777813-25-000002")]
        out = diff_quarters(prior, current)
        assert len(out) == 1
        assert out[0].shares_delta_pct is None
        assert out[0].change_type == ChangeType.HOLD

    def test_prior_value_zero_no_split_asserted(self) -> None:
        # shares ~+100% but prior value 0 -> value_delta_pct None -> split False
        prior = [_pos(cusip="00846U101", shares=1000, value_reported=0,
                      weight_pct_reported=50.0, period=Q1, filing_date=F1)]
        current = [_pos(cusip="00846U101", shares=2000, value_reported=500_000,
                        weight_pct_reported=50.0, period=Q2, filing_date=F2,
                        accession_number="0001777813-25-000002")]
        out = diff_quarters(prior, current)
        assert len(out) == 1
        assert out[0].value_delta_pct is None
        assert out[0].split_suspected is False
        # +100% shares, weight flat (0bps) -> not active add (weight not > 50) -> HOLD
        assert out[0].change_type == ChangeType.HOLD

    def test_zero_share_current_is_holding_not_exit(self) -> None:
        # present in BOTH, current.shares==0 -> matched, ~ACTIVE_TRIM (-100% + weight down)
        prior = [_pos(cusip="00846U101", shares=1000, value_reported=500_000,
                      weight_pct_reported=50.0, period=Q1, filing_date=F1)]
        current = [_pos(cusip="00846U101", shares=0, value_reported=0,
                        weight_pct_reported=0.0, period=Q2, filing_date=F2,
                        accession_number="0001777813-25-000002")]
        out = diff_quarters(prior, current)
        assert len(out) == 1
        assert out[0].change_type != ChangeType.EXIT
        assert out[0].shares_delta_pct == pytest.approx(-100.0)
        assert out[0].change_type == ChangeType.ACTIVE_TRIM
        assert out[0].current_shares == 0

    def test_zero_share_both_quarters_is_hold(self) -> None:
        prior = [_pos(cusip="00846U101", shares=0, value_reported=500_000,
                      weight_pct_reported=50.0, period=Q1, filing_date=F1)]
        current = [_pos(cusip="00846U101", shares=0, value_reported=510_000,
                        weight_pct_reported=51.0, period=Q2, filing_date=F2,
                        accession_number="0001777813-25-000002")]
        out = diff_quarters(prior, current)
        assert out[0].shares_delta_pct is None
        assert out[0].change_type == ChangeType.HOLD

    def test_compute_deltas_zero_denominators(self) -> None:
        prior = _pos(shares=0, value_reported=0, weight_pct_reported=10.0)
        current = _pos(shares=5, value_reported=100, weight_pct_reported=12.0,
                       period=Q2, filing_date=F2)
        sd, sdp, wbps, vd, vdp = _compute_deltas(current, prior)
        assert sd == 5 and sdp is None
        assert wbps == pytest.approx(200.0)
        assert vd == 100 and vdp is None


# --------------------------------------------------------------------------- #
# 6f. compute_changes multi-quarter
# --------------------------------------------------------------------------- #


class TestComputeChanges:
    def test_three_periods_baseline_and_transitions(self) -> None:
        a_acc1 = "0001777813-25-000001"
        a_acc2 = "0001777813-25-000002"
        a_acc3 = "0001777813-25-000003"
        positions = [
            # A: baseline Q1, held Q2 (slight drift), grown Q3 (ACTIVE_ADD)
            _pos(cusip="00846U101", shares=1000, value_reported=500_000,
                 weight_pct_reported=50.0, period=Q1, filing_date=F1, accession_number=a_acc1),
            _pos(cusip="00846U101", shares=1020, value_reported=520_000,
                 weight_pct_reported=50.6, period=Q2, filing_date=F2, accession_number=a_acc2),
            _pos(cusip="00846U101", shares=1300, value_reported=700_000,
                 weight_pct_reported=51.5, period=Q3, filing_date=F3, accession_number=a_acc3),
            # B: appears Q2 (NEW), gone Q3 (EXIT)
            _pos(cusip="037833100", shares=500, value_reported=100_000,
                 weight_pct_reported=10.0, period=Q2, filing_date=F2, accession_number=a_acc2),
        ]
        out = compute_changes(positions)
        # Q1 emits nothing: no row has period == Q1
        assert all(c.period != Q1 for c in out)
        # first emitted rows are Q1->Q2 transition (period == Q2)
        periods_emitted = sorted({c.period for c in out})
        assert periods_emitted == [Q2, Q3]
        # B's Q2 row is NEW with prior_period == Q1
        b_q2 = next(c for c in out if c.cusip == "037833100" and c.period == Q2)
        assert b_q2.change_type == ChangeType.NEW
        assert b_q2.prior_period == Q1
        # B's EXIT anchored at Q3
        b_q3 = next(c for c in out if c.cusip == "037833100" and c.period == Q3)
        assert b_q3.change_type == ChangeType.EXIT
        assert b_q3.period == Q3 and b_q3.filing_date == F3
        # A Q3 transition -> ACTIVE_ADD
        a_q3 = next(c for c in out if c.cusip == "00846U101" and c.period == Q3)
        assert a_q3.change_type == ChangeType.ACTIVE_ADD
        # sorted by (period, cusip, security_type)
        assert out == sorted(out, key=lambda c: (c.period, c.cusip, c.security_type))

    def test_minimal_two_period_single_transition(self) -> None:
        positions = [
            _pos(cusip="00846U101", shares=1000, value_reported=500_000,
                 weight_pct_reported=50.0, period=Q1, filing_date=F1),
            _pos(cusip="00846U101", shares=1200, value_reported=620_000,
                 weight_pct_reported=50.6, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        out = compute_changes(positions)
        assert len(out) == 1
        assert out[0].change_type == ChangeType.ACTIVE_ADD  # +20% shares, +60bps
        assert out[0].prior_period == Q1
        assert out[0].period == Q2

    def test_deterministic_ordering_same_cusip_across_quarters(self) -> None:
        positions = [
            _pos(cusip="00846U101", shares=1000, weight_pct_reported=50.0,
                 period=Q1, filing_date=F1),
            _pos(cusip="00846U101", shares=1010, weight_pct_reported=50.1,
                 period=Q2, filing_date=F2, accession_number="0001777813-25-000002"),
            _pos(cusip="00846U101", shares=1020, weight_pct_reported=50.2,
                 period=Q3, filing_date=F3, accession_number="0001777813-25-000003"),
        ]
        out = compute_changes(positions)
        assert len(out) == 2
        assert out[0].period == Q2
        assert out[1].period == Q3
        assert out == sorted(out, key=lambda c: (c.period, c.cusip, c.security_type))

    def test_clean_single_quarter_returns_empty(self) -> None:
        positions = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="037833100", period=Q1, filing_date=F1),
        ]
        assert compute_changes(positions) == []

    def test_gap_tolerance(self) -> None:
        # Q1 and Q3 only (Q2 missing) -> Q3 diffed against Q1
        positions = [
            _pos(cusip="00846U101", shares=1000, weight_pct_reported=50.0,
                 period=Q1, filing_date=F1),
            _pos(cusip="00846U101", shares=1500, value_reported=750_000,
                 weight_pct_reported=51.0, period=Q3, filing_date=F3,
                 accession_number="0001777813-25-000003"),
        ]
        out = compute_changes(positions)
        assert all(c.period != Q1 for c in out)
        assert len(out) == 1
        assert out[0].period == Q3
        assert out[0].prior_period == Q1

    def test_empty_input_returns_empty(self) -> None:
        assert compute_changes([]) == []

    def test_mixed_cik_raises(self) -> None:
        positions = [
            _pos(cik="0001777813", cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cik="0000000001", cusip="00846U101", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        with pytest.raises(DiscoveryError):
            compute_changes(positions)

    def test_duplicate_key_within_period_raises(self) -> None:
        positions = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="037833100", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        with pytest.raises(DiscoveryError):
            compute_changes(positions)

    def test_multi_accession_within_period_raises(self) -> None:
        positions = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000001"),
            _pos(cusip="037833100", period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000099"),
            _pos(cusip="00846U101", period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
        ]
        with pytest.raises(DiscoveryError):
            compute_changes(positions)

    # --- v4-3: corrupt single-quarter baseline fails loud ---

    def test_corrupt_baseline_duplicate_key_raises(self) -> None:
        positions = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
        ]
        with pytest.raises(DiscoveryError):
            compute_changes(positions)

    def test_corrupt_baseline_multi_accession_raises(self) -> None:
        positions = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000001"),
            _pos(cusip="037833100", period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000002"),
        ]
        with pytest.raises(DiscoveryError):
            compute_changes(positions)

    def test_corrupt_baseline_mixed_filing_date_raises(self) -> None:
        positions = [
            _pos(cusip="00846U101", period=Q1, filing_date=F1),
            _pos(cusip="037833100", period=Q1, filing_date=date(2025, 5, 16)),
        ]
        with pytest.raises(DiscoveryError):
            compute_changes(positions)


# --------------------------------------------------------------------------- #
# 6i. integration over a synthetic multi-quarter fixture
# --------------------------------------------------------------------------- #


class TestIntegration:
    def test_full_pipeline_classification_and_flags(self, tmp_path: Any) -> None:
        from celebpm import storage

        slug = "test_investor"
        # split center: 1000 -> 2000 shares (+100%), value ~flat
        positions = [
            # Q1 baseline: A (common), C (the split candidate), and a CALL on A
            _pos(cusip="00846U101", shares=1000, value_reported=500_000,
                 weight_pct_reported=40.0, period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000001"),
            _pos(cusip="037833100", shares=1000, value_reported=300_000,
                 weight_pct_reported=24.0, period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000001"),
            _pos(cusip="00846U101", security_type=CALL, shares=100, value_reported=20_000,
                 weight_pct_reported=2.0, period=Q1, filing_date=F1,
                 accession_number="0001777813-25-000001"),
            # Q2: A drifts up, C splits (~+100% shares, flat value), B appears (NEW)
            _pos(cusip="00846U101", shares=1010, value_reported=560_000,
                 weight_pct_reported=40.7, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            _pos(cusip="037833100", shares=2000, value_reported=300_000,
                 weight_pct_reported=24.0, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            _pos(cusip="00846U101", security_type=CALL, shares=100, value_reported=20_000,
                 weight_pct_reported=2.0, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            _pos(cusip="594918104", shares=400, value_reported=80_000,
                 weight_pct_reported=6.0, period=Q2, filing_date=F2,
                 accession_number="0001777813-25-000002"),
            # Q3: A grows big (ACTIVE_ADD), B exits, C/CALL held
            _pos(cusip="00846U101", shares=1300, value_reported=900_000,
                 weight_pct_reported=42.0, period=Q3, filing_date=F3,
                 accession_number="0001777813-25-000003"),
            _pos(cusip="037833100", shares=2000, value_reported=310_000,
                 weight_pct_reported=24.1, period=Q3, filing_date=F3,
                 accession_number="0001777813-25-000003"),
            _pos(cusip="00846U101", security_type=CALL, shares=100, value_reported=20_000,
                 weight_pct_reported=2.0, period=Q3, filing_date=F3,
                 accession_number="0001777813-25-000003"),
        ]
        out = compute_changes(positions)
        # Q1 emits nothing
        assert all(c.period != Q1 for c in out)
        # split row in Q2: HOLD + split_suspected
        split_row = next(
            c for c in out if c.cusip == "037833100" and c.period == Q2
        )
        assert split_row.change_type == ChangeType.HOLD
        assert split_row.split_suspected is True
        # B NEW in Q2
        b_new = next(c for c in out if c.cusip == "594918104" and c.period == Q2)
        assert b_new.change_type == ChangeType.NEW
        # B EXIT in Q3
        b_exit = next(c for c in out if c.cusip == "594918104" and c.period == Q3)
        assert b_exit.change_type == ChangeType.EXIT
        # A ACTIVE_ADD in Q3
        a_q3 = next(
            c for c in out if c.cusip == "00846U101"
            and c.security_type == COMMON and c.period == Q3
        )
        assert a_q3.change_type == ChangeType.ACTIVE_ADD

        # write + read back
        storage.write_changes(slug, out, data_root=tmp_path)
        loaded = storage.read_changes(slug, data_root=tmp_path)
        assert loaded == out
        for r in loaded:
            assert isinstance(r.change_type, ChangeType)
            assert r.cik is not None
            assert r.period is not None and r.filing_date is not None
            assert r.prior_period is not None and r.prior_filing_date is not None
            assert r.cusip is not None and r.security_type is not None
            assert isinstance(r.split_suspected, bool)
            assert isinstance(r.corporate_action_note, str)


def test_position_change_is_importable() -> None:
    assert PositionChange is not None
