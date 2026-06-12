"""LIVE smoke test — hits real EDGAR. MANUAL only; NOT in default pytest discovery.

Run with: .venv/bin/pytest tests_live/
Rate-limited live network. Reuses ONE EdgarClient across both CIKs (D0.3 single-client reuse).
Count assertions are loose/network-dependent and deliberately not part of CI.
"""

from __future__ import annotations

from celebpm import constants
from celebpm.discovery import discover_filings
from celebpm.edgar_client import EdgarClient

ATREIDES = "0001777813"
SITUATIONAL = "0002045724"


def test_discovery_live_both_ciks() -> None:
    client = EdgarClient()  # ONE shared client reused across both CIKs (D0.3)

    atreides = discover_filings(ATREIDES, client)
    situational = discover_filings(SITUATIONAL, client)

    for records in (atreides, situational):
        for rec in records:
            assert rec.form_type in constants.TARGET_FORM_TYPES
            assert rec.accepted_date.tzinfo is not None
            assert rec.filing_index_url.startswith(constants.EDGAR_ARCHIVES_BASE)
            assert rec.filing_index_url.endswith("/")

    # Loose count sanity (manual / network-dependent / NOT CI).
    assert len(atreides) >= 20  # Atreides: many quarters
    assert len(situational) >= 3  # Situational Awareness: a few quarters
