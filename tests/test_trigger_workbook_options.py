"""Guard: options never enter Baker's equity money-flow totals in the trigger workbook.

Options are informational only. A closed option line must never be counted as equity
selling (its notional is not a position size). Regression for the Q2/Q3 2026 bug where
option exits (RBLX/U calls in Q2, the CBRS call in Q3) were subtracted from net trading.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.transcripts import build_trigger_workbook as wb  # noqa: E402


def _chg(period: str, change_type: str, security_type: str, cusip: str) -> dict[str, Any]:
    return {"period": period, "change_type": change_type,
            "security_type": security_type, "cusip": cusip}


def test_partition_exits_routes_options_away_from_equity() -> None:
    rows = [
        _chg("2026-09-30", "EXIT", "COMMON", "A"),
        _chg("2026-09-30", "EXIT", "CALL", "B"),
        _chg("2026-09-30", "EXIT", "PUT", "C"),
        _chg("2026-09-30", "ACTIVE_TRIM", "COMMON", "D"),  # not an exit
        _chg("2026-06-30", "EXIT", "COMMON", "E"),  # other period
    ]
    equity, option = wb.partition_exits(rows, "2026-09-30")
    assert [c["cusip"] for c in equity] == ["A"]
    assert sorted(c["cusip"] for c in option) == ["B", "C"]


_DATA = REPO_ROOT / "data" / "atreides_management" / "positions.json"


@pytest.mark.skipif(not _DATA.exists(), reason="local 13F data not present (data/ is gitignored)")
def test_baker_context_equity_totals_exclude_options(tmp_path: Path) -> None:
    ctx = wb.build_baker_context()
    assert all(e["security_type"] == "COMMON" for e in ctx["exits"])
    assert all(o["security_type"] != "COMMON" for o in ctx["option_exits"])
    assert all(h["security_type"] == "COMMON" for h in ctx["holdings"])

    # The decomposition CSV is the audit trail for every equity flow total.
    out = tmp_path / "decomp.csv"
    wb.write_baker_decomp_csv(ctx, out)
    with out.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(r["security_type"] == "COMMON" for r in rows)
