"""Summary-sheet helpers in the trigger workbook."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.transcripts import build_trigger_workbook as wb  # noqa: E402


def test_reclass_share_trade_ipo_quarter_counts_whole_position() -> None:
    # IPO quarter: no prior row -> shares_delta is None -> whole position.
    assert wb.reclass_share_trade({"shares": 100.0, "value": 5_000.0, "shares_delta": None}) == 5_000.0


def test_reclass_share_trade_later_quarter_counts_only_share_change() -> None:
    # 10 more shares at the quarter-end mark of $50 -> $500, not the $5,500 position value.
    h = {"shares": 110.0, "value": 5_500.0, "shares_delta": 10.0}
    assert wb.reclass_share_trade(h) == pytest.approx(500.0)
