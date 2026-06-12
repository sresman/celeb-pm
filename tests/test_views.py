"""Builder + summary-stats unit tests for View 1 (synthetic records, no network)."""

from __future__ import annotations

from datetime import date

import pytest

from celebpm.config_loader import InvestorConfig
from celebpm.errors import DiscoveryError
from celebpm.models import (
    ChangeType,
    PositionChange,
    PositionRecord,
    ReturnRecord,
)
from celebpm.views import build_new_ideas_view

CIK = "0001777813"
CUSIP_A = "00846U101"  # ALPHABET / GOOGL-like
CUSIP_B = "09247X101"
CUSIP_C = "037833100"  # AAPL

CONFIG = InvestorConfig(
    cik=CIK, name="Test", fund="Test LP", slug="test_slug", notes="", is_known=True
)


# --------------------------------------------------------------------------------------
# factories
# --------------------------------------------------------------------------------------
def position(
    *,
    cusip: str = CUSIP_A,
    security_type: str = "COMMON",
    period: date,
    filing_date: date,
    company_name: str = "ALPHA CORP",
    ticker: str | None = "ALPHA",
    weight: float = 5.0,
) -> PositionRecord:
    put_call = {"COMMON": "", "PUT": "PUT", "CALL": "CALL"}[security_type]
    equity_weight = weight if security_type == "COMMON" else None
    return PositionRecord(
        cik=CIK,
        accession_number="0001777813-25-000001",
        period=period,
        filing_date=filing_date,
        cusip=cusip,
        company_name=company_name,
        title_of_class="COM",
        security_type=security_type,
        put_call=put_call,
        ticker=ticker,
        shares=1000,
        ssh_prnamt_type="SH",
        value_reported=100000,
        investment_discretion="SOLE",
        weight_pct_reported=weight,
        weight_pct_equity_only=equity_weight,
    )


def new_change(
    *,
    cusip: str = CUSIP_A,
    security_type: str = "COMMON",
    period: date,
    filing_date: date,
    prior_period: date,
    prior_filing_date: date,
    ticker: str | None = "ALPHA",
    weight: float = 5.0,
) -> PositionChange:
    return PositionChange(
        cik=CIK,
        period=period,
        filing_date=filing_date,
        prior_period=prior_period,
        prior_filing_date=prior_filing_date,
        cusip=cusip,
        security_type=security_type,
        ticker=ticker,
        current_shares=1000,
        current_value_reported=100000,
        current_weight_pct=weight,
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
    )


def matched_change(
    *,
    change_type: ChangeType,
    cusip: str = CUSIP_A,
    security_type: str = "COMMON",
    period: date,
    filing_date: date,
    prior_period: date,
    prior_filing_date: date,
    ticker: str | None = "ALPHA",
    weight: float = 5.0,
    prior_weight: float = 4.0,
) -> PositionChange:
    return PositionChange(
        cik=CIK,
        period=period,
        filing_date=filing_date,
        prior_period=prior_period,
        prior_filing_date=prior_filing_date,
        cusip=cusip,
        security_type=security_type,
        ticker=ticker,
        current_shares=1200,
        current_value_reported=120000,
        current_weight_pct=weight,
        prior_shares=1000,
        prior_value_reported=100000,
        prior_weight_pct=prior_weight,
        shares_delta=200,
        shares_delta_pct=20.0,
        weight_delta_bps=(weight - prior_weight) * 100,
        value_delta=20000,
        value_delta_pct=20.0,
        change_type=change_type,
        split_suspected=False,
    )


def exit_change(
    *,
    cusip: str = CUSIP_A,
    security_type: str = "COMMON",
    period: date,
    filing_date: date,
    prior_period: date,
    prior_filing_date: date,
    ticker: str | None = "ALPHA",
) -> PositionChange:
    return PositionChange(
        cik=CIK,
        period=period,
        filing_date=filing_date,
        prior_period=prior_period,
        prior_filing_date=prior_filing_date,
        cusip=cusip,
        security_type=security_type,
        ticker=ticker,
        current_shares=None,
        current_value_reported=None,
        current_weight_pct=None,
        prior_shares=1000,
        prior_value_reported=100000,
        prior_weight_pct=4.0,
        shares_delta=None,
        shares_delta_pct=None,
        weight_delta_bps=None,
        value_delta=None,
        value_delta_pct=None,
        change_type=ChangeType.EXIT,
        split_suspected=False,
    )


def return_rec(
    *,
    cusip: str = CUSIP_A,
    security_type: str = "COMMON",
    filing_date: date,
    period: date,
    next_filing_date: date,
    ticker: str | None = "ALPHA",
    priced: bool = True,
    f2f: float | None = 10.0,
    f2h: float | None = 15.0,
    f2l: float | None = -5.0,
    spy_f2f: float | None = 4.0,
    spy_h: float | None = 6.0,
    spy_l: float | None = -2.0,
    best_entry: float | None = 12.0,
    worst_entry: float | None = 8.0,
    cumulative: float | None = 20.0,
    change_type: ChangeType = ChangeType.NEW,
) -> ReturnRecord:
    is_opt = security_type in {"PUT", "CALL"}
    if not priced:
        return ReturnRecord(
            cik=CIK,
            cusip=cusip,
            ticker=ticker,
            eodhd_symbol=None,
            security_type=security_type,
            change_type=change_type,
            period=period,
            filing_date=filing_date,
            next_filing_date=next_filing_date,
            priced=False,
            is_underlying_price=is_opt,
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
        )
    entry_set = best_entry is not None and worst_entry is not None
    return ReturnRecord(
        cik=CIK,
        cusip=cusip,
        ticker=ticker,
        eodhd_symbol=f"{ticker}.US" if ticker else None,
        security_type=security_type,
        change_type=change_type,
        period=period,
        filing_date=filing_date,
        next_filing_date=next_filing_date,
        priced=True,
        is_underlying_price=is_opt,
        price_on_filing_date=100.0,
        price_on_next_filing_date=110.0,
        next_period_high=115.0,
        next_period_low=95.0,
        next_period_high_date=filing_date,
        next_period_low_date=filing_date,
        filing_to_filing_return_pct=f2f,
        filing_to_next_period_high_pct=f2h,
        filing_to_next_period_low_pct=f2l,
        entry_quarter_high=105.0 if entry_set else None,
        entry_quarter_low=90.0 if entry_set else None,
        best_case_entry_price=90.0 if entry_set else None,
        worst_case_entry_price=105.0 if entry_set else None,
        best_case_entry_return_pct=best_entry,
        worst_case_entry_return_pct=worst_entry,
        cumulative_return_pct=cumulative,
        cumulative_from_filing_date=filing_date if cumulative is not None else None,
        cumulative_to_filing_date=next_filing_date if cumulative is not None else None,
        spy_filing_to_filing_return_pct=spy_f2f,
        spy_next_period_high_pct=spy_h,
        spy_next_period_low_pct=spy_l,
    )


Q1 = date(2024, 3, 31)
Q1F = date(2024, 5, 15)
Q2 = date(2024, 6, 30)
Q2F = date(2024, 8, 14)
Q3 = date(2024, 9, 30)
Q3F = date(2024, 11, 14)
Q4 = date(2024, 12, 31)
Q4F = date(2025, 2, 14)
Q5 = date(2025, 3, 31)
Q5F = date(2025, 5, 15)
Q0 = date(2023, 12, 31)
Q0F = date(2024, 2, 14)


# --------------------------------------------------------------------------------------
# (a) priced NEW equity, full returns + excess
# --------------------------------------------------------------------------------------
def test_priced_new_equity_full_returns_and_excess() -> None:
    ch = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    pos = position(period=Q1, filing_date=Q1F)
    ret = return_rec(filing_date=Q1F, period=Q1, next_filing_date=Q2F)
    view = build_new_ideas_view(
        config=CONFIG, positions=[pos], changes=[ch], returns=[ret]
    )
    assert len(view.rows) == 1
    row = view.rows[0]
    assert row.is_option is False
    assert row.is_underlying_price is False
    assert row.priced is True
    assert row.filing_to_filing_return_pct == 10.0
    assert row.excess_filing_to_filing_pct == pytest.approx(10.0 - 4.0)
    assert row.excess_next_period_high_pct == pytest.approx(15.0 - 6.0)
    assert row.excess_next_period_low_pct == pytest.approx(-5.0 - (-2.0))
    assert row.best_case_entry_return_pct == 12.0
    assert row.worst_case_entry_return_pct == 8.0
    assert row.cumulative_return_pct == 20.0
    assert row.company == "ALPHA CORP"
    assert row.ticker_display == "ALPHA"


# --------------------------------------------------------------------------------------
# (b) multi-quarter held NEW (NEW, ACTIVE_ADD, DRIFT_UP)
# --------------------------------------------------------------------------------------
def test_multi_quarter_held() -> None:
    ch_new = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=5.0)
    ch_add = matched_change(
        change_type=ChangeType.ACTIVE_ADD,
        period=Q2,
        filing_date=Q2F,
        prior_period=Q1,
        prior_filing_date=Q1F,
        weight=7.0,
        prior_weight=5.0,
    )
    ch_drift = matched_change(
        change_type=ChangeType.DRIFT_UP,
        period=Q3,
        filing_date=Q3F,
        prior_period=Q2,
        prior_filing_date=Q2F,
        weight=6.0,
        prior_weight=7.0,
    )
    pos = position(period=Q1, filing_date=Q1F)
    ret = return_rec(filing_date=Q1F, period=Q1, next_filing_date=Q2F, cumulative=33.0)
    view = build_new_ideas_view(
        config=CONFIG, positions=[pos], changes=[ch_new, ch_add, ch_drift], returns=[ret]
    )
    row = view.rows[0]
    assert row.quarters_held == 3
    assert row.max_weight_pct == 7.0
    assert row.cumulative_return_pct == 33.0
    assert row.became_active_add is True
    assert row.exit_quarter is None


# --------------------------------------------------------------------------------------
# (c) NEW that EXITed (NEW, HOLD, EXIT)
# --------------------------------------------------------------------------------------
def test_new_that_exited() -> None:
    ch_new = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    ch_hold = matched_change(
        change_type=ChangeType.HOLD,
        period=Q2,
        filing_date=Q2F,
        prior_period=Q1,
        prior_filing_date=Q1F,
        weight=5.0,
        prior_weight=5.0,
    )
    ch_exit = exit_change(period=Q3, filing_date=Q3F, prior_period=Q2, prior_filing_date=Q2F)
    pos = position(period=Q1, filing_date=Q1F)
    ret = return_rec(filing_date=Q1F, period=Q1, next_filing_date=Q2F)
    view = build_new_ideas_view(
        config=CONFIG, positions=[pos], changes=[ch_new, ch_hold, ch_exit], returns=[ret]
    )
    row = view.rows[0]
    assert row.exit_quarter == Q3
    assert row.quarters_held == 2  # EXIT quarter not counted
    assert row.became_active_add is False


# --------------------------------------------------------------------------------------
# (d) still-held NEW -> exit_quarter None
# --------------------------------------------------------------------------------------
def test_still_held() -> None:
    ch = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    pos = position(period=Q1, filing_date=Q1F)
    ret = return_rec(filing_date=Q1F, period=Q1, next_filing_date=Q2F)
    view = build_new_ideas_view(config=CONFIG, positions=[pos], changes=[ch], returns=[ret])
    assert view.rows[0].exit_quarter is None


# --------------------------------------------------------------------------------------
# (e) unpriced NEW (no matching ReturnRecord)
# --------------------------------------------------------------------------------------
def test_unpriced_new_no_return_record() -> None:
    ch = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    pos = position(period=Q1, filing_date=Q1F)
    view = build_new_ideas_view(config=CONFIG, positions=[pos], changes=[ch], returns=[])
    row = view.rows[0]
    assert row.priced is False
    assert row.filing_to_filing_return_pct is None
    assert row.excess_filing_to_filing_pct is None
    assert row.cumulative_return_pct is None
    assert row.best_case_entry_return_pct is None


# --------------------------------------------------------------------------------------
# (e2) unpriced OPTION NEW -- flags derived from security_type
# --------------------------------------------------------------------------------------
def test_unpriced_option_new_flagged() -> None:
    ch = new_change(
        cusip=CUSIP_A,
        security_type="PUT",
        period=Q1,
        filing_date=Q1F,
        prior_period=Q0,
        prior_filing_date=Q0F,
        ticker="ALPHA",
    )
    pos = position(security_type="PUT", period=Q1, filing_date=Q1F)
    view = build_new_ideas_view(config=CONFIG, positions=[pos], changes=[ch], returns=[])
    row = view.rows[0]
    assert row.is_option is True
    assert row.is_underlying_price is True
    assert row.priced is False


# --------------------------------------------------------------------------------------
# (f) NEW option (PUT and CALL, priced) -- kept in feed, flagged
# --------------------------------------------------------------------------------------
def test_priced_option_new() -> None:
    ch_put = new_change(
        cusip=CUSIP_A, security_type="PUT", period=Q1, filing_date=Q1F,
        prior_period=Q0, prior_filing_date=Q0F, weight=3.0,
    )
    ch_call = new_change(
        cusip=CUSIP_B, security_type="CALL", period=Q1, filing_date=Q1F,
        prior_period=Q0, prior_filing_date=Q0F, weight=2.0, ticker="BETA",
    )
    pos_put = position(cusip=CUSIP_A, security_type="PUT", period=Q1, filing_date=Q1F)
    pos_call = position(
        cusip=CUSIP_B, security_type="CALL", period=Q1, filing_date=Q1F,
        company_name="BETA INC", ticker="BETA",
    )
    ret_put = return_rec(
        cusip=CUSIP_A, security_type="PUT", filing_date=Q1F, period=Q1,
        next_filing_date=Q2F, best_entry=None, worst_entry=None,
    )
    ret_call = return_rec(
        cusip=CUSIP_B, security_type="CALL", filing_date=Q1F, period=Q1,
        next_filing_date=Q2F, ticker="BETA", best_entry=None, worst_entry=None,
    )
    view = build_new_ideas_view(
        config=CONFIG,
        positions=[pos_put, pos_call],
        changes=[ch_put, ch_call],
        returns=[ret_put, ret_call],
    )
    assert len(view.rows) == 2
    for row in view.rows:
        assert row.is_option is True
        assert row.is_underlying_price is True


# --------------------------------------------------------------------------------------
# (g) unresolved ticker -> ticker_display == cusip, company == cusip
# --------------------------------------------------------------------------------------
def test_unresolved_ticker_falls_back_to_cusip() -> None:
    ch = new_change(
        period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, ticker=None
    )
    # PositionRecord join MISSING (no positions provided)
    view = build_new_ideas_view(config=CONFIG, positions=[], changes=[ch], returns=[])
    row = view.rows[0]
    assert row.ticker_display == CUSIP_A
    assert row.company == CUSIP_A


# --------------------------------------------------------------------------------------
# (g2) ticker from PositionRecord fallback
# --------------------------------------------------------------------------------------
def test_ticker_from_position_record() -> None:
    ch = new_change(
        period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, ticker=None
    )
    pos = position(period=Q1, filing_date=Q1F, ticker="  ALPHA  ")
    view = build_new_ideas_view(config=CONFIG, positions=[pos], changes=[ch], returns=[])
    assert view.rows[0].ticker_display == "ALPHA"


# --------------------------------------------------------------------------------------
# (h) sort by initial weight desc, tiebreak cusip then security_type
# --------------------------------------------------------------------------------------
def test_sort_by_weight_desc() -> None:
    big = new_change(
        cusip=CUSIP_C, period=Q1, filing_date=Q1F, prior_period=Q0,
        prior_filing_date=Q0F, weight=9.0, ticker="AAPL",
    )
    # two equal-weight NEWs, different cusip -> cusip asc tiebreak
    eq_a = new_change(
        cusip=CUSIP_A, period=Q1, filing_date=Q1F, prior_period=Q0,
        prior_filing_date=Q0F, weight=3.0,
    )
    eq_b = new_change(
        cusip=CUSIP_B, period=Q1, filing_date=Q1F, prior_period=Q0,
        prior_filing_date=Q0F, weight=3.0, ticker="BETA",
    )
    view = build_new_ideas_view(
        config=CONFIG, positions=[], changes=[eq_b, eq_a, big], returns=[]
    )
    assert [r.cusip for r in view.rows] == [CUSIP_C, CUSIP_A, CUSIP_B]


def test_sort_tiebreak_security_type() -> None:
    # same cusip+weight, COMMON vs PUT -> security_type asc (CALL < COMMON < PUT)
    common = new_change(
        cusip=CUSIP_A, security_type="COMMON", period=Q1, filing_date=Q1F,
        prior_period=Q0, prior_filing_date=Q0F, weight=3.0,
    )
    put = new_change(
        cusip=CUSIP_A, security_type="PUT", period=Q1, filing_date=Q1F,
        prior_period=Q0, prior_filing_date=Q0F, weight=3.0,
    )
    view = build_new_ideas_view(
        config=CONFIG, positions=[], changes=[put, common], returns=[]
    )
    assert [r.security_type for r in view.rows] == ["COMMON", "PUT"]


# --------------------------------------------------------------------------------------
# (i) re-entry cycle slicing
# --------------------------------------------------------------------------------------
def test_re_entry_strict_slicing() -> None:
    c_new1 = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=5.0)
    c_hold1 = matched_change(
        change_type=ChangeType.HOLD, period=Q2, filing_date=Q2F, prior_period=Q1,
        prior_filing_date=Q1F, weight=8.0, prior_weight=5.0,
    )
    c_exit = exit_change(period=Q3, filing_date=Q3F, prior_period=Q2, prior_filing_date=Q2F)
    c_new2 = new_change(period=Q4, filing_date=Q4F, prior_period=Q3, prior_filing_date=Q3F, weight=4.0)
    c_hold2 = matched_change(
        change_type=ChangeType.HOLD, period=Q5, filing_date=Q5F, prior_period=Q4,
        prior_filing_date=Q4F, weight=6.0, prior_weight=4.0,
    )
    view = build_new_ideas_view(
        config=CONFIG,
        positions=[],
        changes=[c_new1, c_hold1, c_exit, c_new2, c_hold2],
        returns=[],
    )
    assert len(view.rows) == 2
    by_q = {r.quarter: r for r in view.rows}
    first = by_q[Q1]
    assert first.exit_quarter == Q3
    assert first.quarters_held == 2
    assert first.max_weight_pct == 8.0  # max over Q1+Q2 only, NOT Q5's 6
    second = by_q[Q4]
    assert second.exit_quarter is None
    assert second.quarters_held == 2
    assert second.max_weight_pct == 6.0  # max over Q4+Q5 only


# --------------------------------------------------------------------------------------
# (j) summary math
# --------------------------------------------------------------------------------------
def test_summary_math() -> None:
    # winners: +10, +20 ; loser: -5 ; exactly-0: 0.0 ; unpriced: None ; option winner +30
    w1 = new_change(cusip=CUSIP_A, period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=9.0)
    w2 = new_change(cusip=CUSIP_B, period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=8.0, ticker="BETA")
    loser = new_change(cusip=CUSIP_C, period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=7.0, ticker="AAPL")
    zero = new_change(cusip="037833200", period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=6.0, ticker="Z")
    unpriced = new_change(cusip="459200101", period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F, weight=5.0, ticker="IBM")

    ret_w1 = return_rec(cusip=CUSIP_A, filing_date=Q1F, period=Q1, next_filing_date=Q2F, f2f=10.0)
    ret_w2 = return_rec(cusip=CUSIP_B, filing_date=Q1F, period=Q1, next_filing_date=Q2F, f2f=20.0, ticker="BETA")
    ret_loser = return_rec(cusip=CUSIP_C, filing_date=Q1F, period=Q1, next_filing_date=Q2F, f2f=-5.0, ticker="AAPL")
    ret_zero = return_rec(cusip="037833200", filing_date=Q1F, period=Q1, next_filing_date=Q2F, f2f=0.0, ticker="Z")

    # w1 closes (EXIT), w2 still held -> only w1 in median-hold population
    w1_exit = exit_change(cusip=CUSIP_A, period=Q2, filing_date=Q2F, prior_period=Q1, prior_filing_date=Q1F)
    # w2 becomes ACTIVE_ADD later
    w2_add = matched_change(
        change_type=ChangeType.ACTIVE_ADD, cusip=CUSIP_B, period=Q2, filing_date=Q2F,
        prior_period=Q1, prior_filing_date=Q1F, weight=10.0, prior_weight=8.0, ticker="BETA",
    )

    view = build_new_ideas_view(
        config=CONFIG,
        positions=[],
        changes=[w1, w2, loser, zero, unpriced, w1_exit, w2_add],
        returns=[ret_w1, ret_w2, ret_loser, ret_zero],
    )
    s = view.summary
    assert s.total_new == 5
    assert s.priced_new == 4
    # population = 4 with non-None returns; wins = 2 (>0) -> 50%
    assert s.win_rate_pct == pytest.approx(50.0)
    assert s.avg_winner_return_pct == pytest.approx((10.0 + 20.0) / 2)
    assert s.avg_loser_return_pct == pytest.approx(-5.0)
    # closed NEWs: only w1 (exit Q2) -> quarters_held=1 -> median 1.0
    assert s.median_holding_quarters == pytest.approx(1.0)
    # became_active_add: only w2 -> 1/5
    assert s.pct_became_active_add == pytest.approx(20.0)
    assert s.notes


# --------------------------------------------------------------------------------------
# (j2) empty sub-population guards
# --------------------------------------------------------------------------------------
def test_empty_subpopulation_guards() -> None:
    # one loser only, no winners, no closed NEWs
    loser = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    ret_loser = return_rec(filing_date=Q1F, period=Q1, next_filing_date=Q2F, f2f=-3.0)
    view = build_new_ideas_view(
        config=CONFIG, positions=[], changes=[loser], returns=[ret_loser]
    )
    s = view.summary
    assert s.avg_winner_return_pct is None
    assert s.avg_loser_return_pct == pytest.approx(-3.0)
    assert s.median_holding_quarters is None
    assert s.win_rate_pct == pytest.approx(0.0)


# --------------------------------------------------------------------------------------
# (k) empty-NEW investor
# --------------------------------------------------------------------------------------
def test_empty_new_investor() -> None:
    # changes with no NEW
    hold = matched_change(
        change_type=ChangeType.HOLD, period=Q2, filing_date=Q2F, prior_period=Q1,
        prior_filing_date=Q1F, weight=5.0, prior_weight=5.0,
    )
    view = build_new_ideas_view(config=CONFIG, positions=[], changes=[hold], returns=[])
    assert view.rows == ()
    s = view.summary
    assert s.total_new == 0
    assert s.priced_new == 0
    assert s.win_rate_pct is None
    assert s.avg_winner_return_pct is None
    assert s.median_holding_quarters is None
    assert s.pct_became_active_add is None
    assert s.notes


def test_empty_changes() -> None:
    view = build_new_ideas_view(config=CONFIG, positions=[], changes=[], returns=[])
    assert view.rows == ()
    assert view.summary.total_new == 0


# --------------------------------------------------------------------------------------
# (l) mixed-CIK / wrong-cik -> DiscoveryError
# --------------------------------------------------------------------------------------
def test_mixed_cik_raises() -> None:
    ch = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    other = PositionRecord(
        cik="0002045724",
        accession_number="0002045724-25-000001",
        period=Q1,
        filing_date=Q1F,
        cusip=CUSIP_B,
        company_name="OTHER",
        title_of_class="COM",
        security_type="COMMON",
        put_call="",
        ticker="OTH",
        shares=1,
        ssh_prnamt_type="SH",
        value_reported=1,
        investment_discretion="SOLE",
        weight_pct_reported=1.0,
        weight_pct_equity_only=1.0,
    )
    with pytest.raises(DiscoveryError):
        build_new_ideas_view(config=CONFIG, positions=[other], changes=[ch], returns=[])


def test_wrong_cik_raises() -> None:
    other_config = InvestorConfig(
        cik="0002045724", name="X", fund="X", slug="x", notes="", is_known=True
    )
    ch = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    with pytest.raises(DiscoveryError):
        build_new_ideas_view(config=other_config, positions=[], changes=[ch], returns=[])


# --------------------------------------------------------------------------------------
# (m) duplicate PositionRecord key -> keep first + WARN
# --------------------------------------------------------------------------------------
def test_duplicate_position_key_keep_first(caplog: pytest.LogCaptureFixture) -> None:
    ch = new_change(period=Q1, filing_date=Q1F, prior_period=Q0, prior_filing_date=Q0F)
    pos1 = position(period=Q1, filing_date=Q1F, company_name="FIRST")
    pos2 = position(period=Q1, filing_date=Q1F, company_name="SECOND")
    import logging

    with caplog.at_level(logging.WARNING):
        view = build_new_ideas_view(
            config=CONFIG, positions=[pos1, pos2], changes=[ch], returns=[]
        )
    assert view.rows[0].company == "FIRST"
    assert any("duplicate PositionRecord key" in r.message for r in caplog.records)
