"""AI-basket ramp: full exits count as selling at their prior-quarter value (spec)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.transcripts import build_13f_analysis as b  # noqa: E402

RECLASS = {"AIX": {"ai": True, "bucket": "AI/Datacenter Chips"}}


def _pos(period: str, fd: str, cusip: str, ticker: str, shares: float, value: float) -> dict[str, Any]:
    return {"period": period, "filing_date": fd, "security_type": "COMMON", "cusip": cusip,
            "ticker": ticker, "shares": shares, "value_reported": value}


def test_only_ai_activity_is_one_full_exit_gives_negative_net_buying(tmp_path: Path) -> None:
    views = tmp_path / "views"
    views.mkdir()
    positions = [
        # prior quarter: one AI name + one unchanged non-AI name
        _pos("2026-03-31", "2026-05-15", "AAA000001", "AIX", 1_000, 100_000),
        _pos("2026-03-31", "2026-05-15", "BBB000001", "NONAI", 10_000, 900_000),
        # current quarter: AI name fully exited; non-AI name unchanged
        _pos("2026-06-30", "2026-08-14", "BBB000001", "NONAI", 10_000, 900_000),
    ]
    (tmp_path / "positions.json").write_text(json.dumps(positions), encoding="utf-8")

    out = b.compute_net_buying(views, RECLASS)["2026-08-14"]

    assert out["net_buying_dollars"] == pytest.approx(-100_000)
    assert out["net_buying_pct"] == pytest.approx(-100_000 / 900_000 * 100)
    assert out["net_buying_pct"] < 0
    assert out["tickers_exited"] == "AIX"
