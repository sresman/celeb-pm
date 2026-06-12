"""LIVE smoke test — hits real EDGAR. MANUAL only; NOT in default pytest discovery.

Run with: .venv/bin/pytest tests_live/test_parse_live.py
Rate-limited live network. Reuses ONE EdgarClient (D0.3). Loose structural assertions only.
"""

from __future__ import annotations

from celebpm import constants
from celebpm.discovery import discover_filings, latest_filing_per_period
from celebpm.edgar_client import EdgarClient
from celebpm.parser import locate_and_fetch_infotable, parse_positions_from_xml

ATREIDES = "0001777813"
SITUATIONAL = "0002045724"


def test_parse_live_both_ciks() -> None:
    client = EdgarClient()  # ONE shared client reused across both CIKs (D0.3)

    # --- Atreides: expect ~COMMON-only (reported weights ~= equity-only weights). ---
    atreides = latest_filing_per_period(discover_filings(ATREIDES, client))
    a_filing = atreides[0]
    a_xml, _ = locate_and_fetch_infotable(a_filing, client)
    a_updated, a_positions = parse_positions_from_xml(a_filing, a_xml)
    assert a_positions
    assert a_updated.total_portfolio_value is not None
    assert a_updated.total_equity_value is not None
    # Common-heavy: reported and equity-only weights track closely for COMMON.
    commons = [p for p in a_positions if p.security_type == constants.SECURITY_TYPE_COMMON]
    assert commons

    # --- Situational Awareness: expect PUT/CALL rows with None equity weight. ---
    situational = latest_filing_per_period(discover_filings(SITUATIONAL, client))
    s_filing = situational[0]
    s_xml, _ = locate_and_fetch_infotable(s_filing, client)
    s_updated, s_positions = parse_positions_from_xml(s_filing, s_xml)
    assert s_positions
    options = [p for p in s_positions if p.security_type != constants.SECURITY_TYPE_COMMON]
    if options:
        assert all(p.weight_pct_equity_only is None for p in options)
        assert s_updated.total_portfolio_value is not None
        assert s_updated.total_equity_value is not None
        assert s_updated.total_portfolio_value >= s_updated.total_equity_value
