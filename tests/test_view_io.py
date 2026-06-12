"""View 1 CSV/summary writer round-trip + path-safety tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from celebpm import constants
from celebpm.errors import DiscoveryError
from celebpm.view_io import write_new_ideas_view
from celebpm.views import NewIdeaRow, NewIdeasSummary, NewIdeasView

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
