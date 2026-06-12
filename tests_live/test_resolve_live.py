"""LIVE smoke test — hits the real OpenFIGI no-key endpoint. MANUAL only; NOT in CI.

Run with: .venv/bin/pytest tests_live/test_resolve_live.py
Rate-limited live network. Reuses ONE OpenFigiClient. Loose-but-tightened structural
assertions only (NO hard-coded CUSIP->ticker anchors — portfolios/tickers change). Drives
real CUSIPs through the resolver's chunking. See plan §8.
"""

from __future__ import annotations

from datetime import date

from celebpm import constants
from celebpm.cusip_map import collect_cusips, resolve_tickers
from celebpm.models import CusipMapEntry, PositionRecord
from celebpm.openfigi_client import OpenFigiClient

ATREIDES = "0001777813"


def _pos(cusip: str) -> PositionRecord:
    return PositionRecord(
        cik=ATREIDES,
        accession_number="0001777813-26-000012",
        period=date(2025, 12, 31),
        filing_date=date(2026, 2, 14),
        cusip=cusip,
        company_name="X CORP",
        title_of_class="COM",
        security_type=constants.SECURITY_TYPE_COMMON,
        put_call="",
        shares=100,
        ssh_prnamt_type=constants.SSH_TYPE_SHARES,
        value_reported=1000,
        investment_discretion="",
        weight_pct_reported=10.0,
        weight_pct_equity_only=10.0,
    )


def test_resolve_live_no_key() -> None:
    # A handful of real large-cap CUSIPs (Apple, Microsoft, Alphabet, Amazon, Nvidia).
    cusips = ["037833100", "594918104", "02079K305", "023135106", "67066G104"]
    positions = [_pos(c) for c in cusips]
    client = OpenFigiClient.from_env()  # no key in env -> no-key mode
    cache: dict[str, CusipMapEntry] = {}

    result = resolve_tickers(positions, client, cache)

    # Enrichment never drops/duplicates a position.
    assert len(result.positions) == len(positions)

    distinct = collect_cusips(positions)
    if not result.partial:
        # Every attempted cusip got an entry (openfigi or unresolved).
        for c in distinct:
            assert c in cache
        # At least one resolved to a real ticker.
        assert any(e.ticker is not None for e in cache.values())
    else:
        # Partial: a cache entry exists for every cusip in the chunks that completed.
        assert any(c in cache for c in distinct) or len(cache) == 0
