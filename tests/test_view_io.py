"""View 1 + View 2 CSV/summary writer round-trip + path-safety tests."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from celebpm import constants
from celebpm.errors import DiscoveryError
from celebpm.view_io import (
    conviction_add_row_to_dict,
    write_conviction_adds_view,
    write_new_ideas_view,
)
from celebpm.views import (
    ConvictionAddRow,
    ConvictionAddsSummary,
    ConvictionAddsView,
    ConvictionAddTypeStats,
    NewIdeaRow,
    NewIdeasSummary,
    NewIdeasView,
)

Q1F = date(2024, 5, 15)
Q1 = date(2024, 3, 31)
Q3 = date(2024, 9, 30)


def _row(
    *,
    cusip: str,
    ticker: str,
    weight: float,
    priced: bool,
    exit_quarter: date | None,
    is_option: bool = False,
    f2f: float | None = 10.0,
) -> NewIdeaRow:
    return NewIdeaRow(
        quarter=Q1,
        filing_date=Q1F,
        ticker_display=ticker,
        company=f"{ticker} CORP",
        cusip=cusip,
        security_type="PUT" if is_option else "COMMON",
        is_option=is_option,
        is_underlying_price=is_option,
        initial_weight_pct=weight,
        best_case_entry_return_pct=12.0 if priced else None,
        worst_case_entry_return_pct=8.0 if priced else None,
        filing_to_filing_return_pct=f2f if priced else None,
        filing_to_next_period_high_pct=15.0 if priced else None,
        filing_to_next_period_low_pct=-5.0 if priced else None,
        excess_filing_to_filing_pct=6.0 if priced else None,
        excess_next_period_high_pct=9.0 if priced else None,
        excess_next_period_low_pct=-3.0 if priced else None,
        cumulative_return_pct=20.0 if priced else None,
        quarters_held=2,
        max_weight_pct=weight,
        exit_quarter=exit_quarter,
        became_active_add=False,
        priced=priced,
    )


def _summary(total: int) -> NewIdeasSummary:
    return NewIdeasSummary(
        total_new=total,
        priced_new=total,
        win_rate_pct=100.0 if total else None,
        avg_winner_return_pct=10.0 if total else None,
        avg_loser_return_pct=None,
        median_holding_quarters=2.0 if total else None,
        pct_became_active_add=0.0 if total else None,
        notes=constants.SUMMARY_NOTES,
    )


def _view(rows: tuple[NewIdeaRow, ...]) -> NewIdeasView:
    return NewIdeasView(
        cik="0001777813", slug="test_slug", rows=rows, summary=_summary(len(rows))
    )


def test_csv_roundtrip(tmp_path: Path) -> None:
    rows = (
        _row(cusip="00846U101", ticker="ALPHA", weight=9.0, priced=True, exit_quarter=Q3),
        _row(cusip="09247X101", ticker="BETA", weight=5.0, priced=False, exit_quarter=None),
        _row(cusip="037833100", ticker="GAMMA", weight=3.0, priced=True, exit_quarter=None, is_option=True),
    )
    view = _view(rows)
    csv_path, summary_path = write_new_ideas_view(view, tmp_path)
    assert csv_path.exists()
    assert summary_path.exists()

    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    assert list(df.columns) == list(constants.NEW_IDEAS_COLUMNS)
    assert len(df) == 3

    # unpriced row -> NA cells empty
    beta = df[df["cusip"] == "09247X101"].iloc[0]
    assert beta["filing_to_filing_return_pct"] == ""
    assert beta["excess_filing_to_filing_pct"] == ""
    assert beta["cumulative_return_pct"] == ""
    assert beta["priced"] == "False"

    # still-held -> "CURRENT"; exited -> ISO date
    assert beta["exit_quarter"] == constants.EXIT_CURRENT_LABEL
    alpha = df[df["cusip"] == "00846U101"].iloc[0]
    assert alpha["exit_quarter"] == Q3.isoformat()
    assert alpha["quarter"] == Q1.isoformat()
    assert alpha["filing_date"] == Q1F.isoformat()
    assert alpha["priced"] == "True"

    # option row flags
    gamma = df[df["cusip"] == "037833100"].iloc[0]
    assert gamma["is_option"] == "True"
    assert gamma["is_underlying_price"] == "True"
    assert gamma["security_type"] == "PUT"


def test_summary_json(tmp_path: Path) -> None:
    view = _view((_row(cusip="00846U101", ticker="ALPHA", weight=9.0, priced=True, exit_quarter=Q3),))
    _, summary_path = write_new_ideas_view(view, tmp_path)
    data = json.loads(summary_path.read_text())
    expected_keys = {
        constants.SUMMARY_KEY_TOTAL_NEW,
        constants.SUMMARY_KEY_PRICED_NEW,
        constants.SUMMARY_KEY_WIN_RATE_PCT,
        constants.SUMMARY_KEY_AVG_WINNER,
        constants.SUMMARY_KEY_AVG_LOSER,
        constants.SUMMARY_KEY_MEDIAN_HOLDING_QUARTERS,
        constants.SUMMARY_KEY_PCT_BECAME_ACTIVE_ADD,
        constants.SUMMARY_KEY_NOTES,
    }
    assert set(data.keys()) == expected_keys
    assert data[constants.SUMMARY_KEY_NOTES] == constants.SUMMARY_NOTES


def test_empty_feed_header_only(tmp_path: Path) -> None:
    view = _view(())
    csv_path, summary_path = write_new_ideas_view(view, tmp_path)
    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    assert list(df.columns) == list(constants.NEW_IDEAS_COLUMNS)
    assert len(df) == 0
    data = json.loads(summary_path.read_text())
    assert data[constants.SUMMARY_KEY_TOTAL_NEW] == 0
    assert data[constants.SUMMARY_KEY_WIN_RATE_PCT] is None
    assert data[constants.SUMMARY_KEY_NOTES] == constants.SUMMARY_NOTES


def test_atomic_both_no_temp_leftovers(tmp_path: Path) -> None:
    view = _view((_row(cusip="00846U101", ticker="ALPHA", weight=9.0, priced=True, exit_quarter=None),))
    csv_path, summary_path = write_new_ideas_view(view, tmp_path)
    assert csv_path.exists()
    assert summary_path.exists()
    leftovers = list(csv_path.parent.glob(f"{constants.VIEW_TMP_PREFIX}*"))
    assert leftovers == []


def test_path_safety_traversal_slug(tmp_path: Path) -> None:
    view = NewIdeasView(cik="0001777813", slug="../evil", rows=(), summary=_summary(0))
    with pytest.raises(DiscoveryError):
        write_new_ideas_view(view, tmp_path)


# ======================================================================================
# View 2 (Conviction Tracker) writer tests
# ======================================================================================
def _conv_row(
    *,
    cusip: str = "00846U101",
    ticker: str = "ALPHA",
    priced: bool = True,
    original_entry_quarter: date | None = Q1,
    add_type: str | None = constants.ADD_TYPE_WINNER,
    is_option: bool = False,
    followed_by_exit: bool = False,
    followed_by_another_add: bool = True,
    still_held: bool = True,
    weight_before_pct: float = 4.0,
    weight_after_pct: float = 6.0,
    weight_delta_pct: float = 2.0,
    shares_delta_pct: float | None = 20.0,
    prior_quarter_return_pct: float | None = 11.0,
    nth_add: int = 1,
) -> ConvictionAddRow:
    return ConvictionAddRow(
        quarter=Q3,
        ticker_display=ticker,
        company=f"{ticker} CORP",
        cusip=cusip,
        security_type="PUT" if is_option else "COMMON",
        is_option=is_option,
        weight_before_pct=weight_before_pct,
        weight_after_pct=weight_after_pct,
        weight_delta_pct=weight_delta_pct,
        shares_delta_pct=shares_delta_pct,
        prior_quarter_return_pct=prior_quarter_return_pct,
        add_type=add_type,
        quarters_held_before_add=2,
        nth_add=nth_add,
        original_entry_quarter=original_entry_quarter,
        cumulative_return_since_entry_pct=25.0 if priced else None,
        filing_to_filing_return_pct=10.0 if priced else None,
        filing_to_next_period_high_pct=15.0 if priced else None,
        filing_to_next_period_low_pct=-5.0 if priced else None,
        excess_filing_to_filing_pct=6.0 if priced else None,
        excess_next_period_high_pct=9.0 if priced else None,
        excess_next_period_low_pct=-3.0 if priced else None,
        followed_by_exit=followed_by_exit,
        followed_by_another_add=followed_by_another_add,
        still_held=still_held,
        priced=priced,
        filing_date=Q1F,
    )


def _conv_stats(count: int) -> ConvictionAddTypeStats:
    return ConvictionAddTypeStats(
        count=count,
        win_rate_pct=100.0 if count else None,
        avg_return_pct=10.0 if count else None,
        avg_next_period_high_pct=15.0 if count else None,
    )


def _conv_summary(total: int) -> ConvictionAddsSummary:
    return ConvictionAddsSummary(
        total_adds=total,
        priced_adds=total,
        win_rate_pct=100.0 if total else None,
        avg_winner_return_pct=10.0 if total else None,
        avg_loser_return_pct=None,
        avg_weight_delta_pct=2.0 if total else None,
        adding_to_winners=_conv_stats(total),
        averaging_down=_conv_stats(0),
        pct_followed_by_exit=0.0 if total else None,
        pct_followed_by_another_add=100.0 if total else None,
        median_quarters_held_before_add=2.0 if total else None,
        pct_first_add=100.0 if total else None,
        notes=constants.CONVICTION_SUMMARY_NOTES,
    )


def _conv_view(rows: tuple[ConvictionAddRow, ...]) -> ConvictionAddsView:
    return ConvictionAddsView(
        cik="0001777813", slug="test_conv", rows=rows, summary=_conv_summary(len(rows))
    )


def test_conviction_row_to_dict_keys_match_columns() -> None:
    d = conviction_add_row_to_dict(_conv_row())
    assert set(d) == set(constants.CONVICTION_ADDS_COLUMNS)
    assert len(d) == 27


def test_conviction_row_to_dict_ticker_header_and_dates() -> None:
    row = _conv_row(ticker="ZETA", original_entry_quarter=Q1)
    d = conviction_add_row_to_dict(row)
    assert d["ticker"] == row.ticker_display
    assert d["quarter"] == Q3.isoformat()
    assert d["filing_date"] == Q1F.isoformat()
    assert d["original_entry_quarter"] == Q1.isoformat()


def test_conviction_row_to_dict_bools_stringified() -> None:
    row = _conv_row(
        is_option=True,
        followed_by_exit=True,
        followed_by_another_add=False,
        still_held=False,
        priced=True,
    )
    d = conviction_add_row_to_dict(row)
    assert d["is_option"] == "True"
    assert d["followed_by_exit"] == "True"
    assert d["followed_by_another_add"] == "False"
    assert d["still_held"] == "False"
    assert d["priced"] == "True"


def test_conviction_row_to_dict_none_passthrough() -> None:
    row = _conv_row(
        priced=False,
        original_entry_quarter=None,
        add_type=None,
        shares_delta_pct=None,
        prior_quarter_return_pct=None,
    )
    d = conviction_add_row_to_dict(row)
    # None carried in the dict (NOT "CURRENT", NOT ""); to_csv renders the empty cell later.
    assert d["original_entry_quarter"] is None
    assert d["add_type"] is None
    assert d["shares_delta_pct"] is None
    assert d["filing_to_filing_return_pct"] is None


def test_conviction_row_to_dict_field_values_map_to_correct_headers() -> None:
    row = _conv_row(
        weight_before_pct=1.1,
        weight_after_pct=2.2,
        weight_delta_pct=3.3,
        prior_quarter_return_pct=4.4,
        nth_add=7,
    )
    d = conviction_add_row_to_dict(row)
    assert d["weight_before_pct"] == 1.1
    assert d["weight_after_pct"] == 2.2
    assert d["weight_delta_pct"] == 3.3
    assert d["prior_quarter_return_pct"] == 4.4
    assert d["nth_add"] == 7


def test_write_conviction_adds_view_files_and_header(tmp_path: Path) -> None:
    rows = (
        _conv_row(cusip="00846U101", ticker="ALPHA"),
        _conv_row(cusip="09247X101", ticker="BETA", add_type=constants.ADD_TYPE_AVERAGING_DOWN),
    )
    view = _conv_view(rows)
    csv_path, summary_path = write_conviction_adds_view(view, tmp_path)
    assert csv_path.exists()
    assert summary_path.exists()
    assert csv_path == tmp_path / "test_conv" / constants.VIEWS_DIR / constants.CONVICTION_ADDS_FILE
    assert (
        summary_path
        == tmp_path / "test_conv" / constants.VIEWS_DIR / constants.CONVICTION_ADDS_SUMMARY_FILE
    )

    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    assert list(df.columns) == list(constants.CONVICTION_ADDS_COLUMNS)
    assert len(df) == 2


def test_write_conviction_adds_view_none_renders_empty(tmp_path: Path) -> None:
    row = _conv_row(
        priced=False,
        original_entry_quarter=None,
        add_type=None,
        shares_delta_pct=None,
        prior_quarter_return_pct=None,
    )
    csv_path, _ = write_conviction_adds_view(_conv_view((row,)), tmp_path)
    with csv_path.open(encoding="utf-8", newline="") as fh:
        data_rows = list(csv.DictReader(fh))
    assert len(data_rows) == 1
    parsed = data_rows[0]
    assert parsed["original_entry_quarter"] == ""  # NOT "CURRENT"
    assert parsed["add_type"] == ""
    assert parsed["shares_delta_pct"] == ""
    assert parsed["filing_to_filing_return_pct"] == ""


def test_write_conviction_adds_view_summary_roundtrip(tmp_path: Path) -> None:
    _, summary_path = write_conviction_adds_view(_conv_view((_conv_row(),)), tmp_path)
    data = json.loads(summary_path.read_text())
    assert constants.CONVICTION_KEY_TOTAL_ADDS in data
    assert constants.CONVICTION_KEY_PRICED_ADDS in data
    winners = data[constants.CONVICTION_KEY_ADDING_TO_WINNERS]
    avg_down = data[constants.CONVICTION_KEY_AVERAGING_DOWN]
    assert isinstance(winners, dict)
    assert isinstance(avg_down, dict)
    assert constants.CONVICTION_SUBKEY_COUNT in winners
    assert constants.CONVICTION_SUBKEY_COUNT in avg_down


def test_write_conviction_adds_view_empty_header_only(tmp_path: Path) -> None:
    csv_path, summary_path = write_conviction_adds_view(_conv_view(()), tmp_path)
    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    assert list(df.columns) == list(constants.CONVICTION_ADDS_COLUMNS)
    assert len(df) == 0
    data = json.loads(summary_path.read_text())
    assert data[constants.CONVICTION_KEY_TOTAL_ADDS] == 0


def test_write_conviction_adds_view_path_safety(tmp_path: Path) -> None:
    view = ConvictionAddsView(
        cik="0001777813", slug="../evil", rows=(), summary=_conv_summary(0)
    )
    with pytest.raises(DiscoveryError):
        write_conviction_adds_view(view, tmp_path)
