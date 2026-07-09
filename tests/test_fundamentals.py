"""Unit tests for the EODHD fundamentals resolver (method-level fake client; no HTTP)."""

from __future__ import annotations

from datetime import datetime, timezone

from celebpm import constants
from celebpm.fundamentals import resolve_fundamentals
from celebpm.models import FundamentalsEntry
from celebpm.price_types import FundamentalsClient
from tests.conftest import FakeFundamentalsClient, general_fundamentals

# STATIC Protocol conformance: mypy verifies FakeFundamentalsClient satisfies FundamentalsClient.
_check: FundamentalsClient = FakeFundamentalsClient()


def _now() -> datetime:
    return datetime(2025, 1, 1, tzinfo=timezone.utc)


def _entry(symbol: str, *, sector: str | None, resolved: bool) -> FundamentalsEntry:
    return FundamentalsEntry(
        eodhd_symbol=symbol,
        sector=sector,
        industry=None,
        instrument_type=None,
        resolved=resolved,
        fetched_at=None,
    )


def test_resolves_sector_and_industry() -> None:
    client = FakeFundamentalsClient(
        {
            "AAA.US": general_fundamentals(
                sector="Technology", industry="Software", instrument_type="Common Stock"
            )
        }
    )
    cache: dict[str, FundamentalsEntry] = {}
    out = resolve_fundamentals(["AAA.US"], client, cache, now=_now)
    assert out is cache  # mutated in place; returns the SAME object
    entry = cache["AAA.US"]
    assert entry.sector == "Technology"
    assert entry.industry == "Software"
    assert entry.instrument_type == "Common Stock"
    assert entry.resolved is True
    assert entry.fetched_at == _now().isoformat()


def test_etf_sector_label() -> None:
    client = FakeFundamentalsClient({"SPY.US": general_fundamentals(instrument_type="ETF")})
    cache: dict[str, FundamentalsEntry] = {}
    resolve_fundamentals(["SPY.US"], client, cache, now=_now)
    assert cache["SPY.US"].sector == constants.SECTOR_ETF_LABEL
    assert cache["SPY.US"].instrument_type == "ETF"


def test_missing_fundamentals_cached_unresolved() -> None:
    # Unknown symbol -> client returns None (404) -> cached UNRESOLVED so it is not re-fetched.
    client = FakeFundamentalsClient({})
    cache: dict[str, FundamentalsEntry] = {}
    resolve_fundamentals(["GONE.US"], client, cache, now=_now)
    assert client.fetched == ["GONE.US"]
    assert cache["GONE.US"].resolved is False
    assert cache["GONE.US"].sector is None


def test_missing_general_object_resolved_with_none_sector() -> None:
    # An object with no usable General fields is still RESOLVED (we reached the API).
    client = FakeFundamentalsClient({"AAA.US": {}})
    cache: dict[str, FundamentalsEntry] = {}
    resolve_fundamentals(["AAA.US"], client, cache, now=_now)
    assert cache["AAA.US"].resolved is True
    assert cache["AAA.US"].sector is None
    assert cache["AAA.US"].industry is None


def test_cache_first_skips_known_hits_and_misses() -> None:
    client = FakeFundamentalsClient({"AAA.US": general_fundamentals(sector="X")})
    cache = {
        "AAA.US": _entry("AAA.US", sector="Cached", resolved=True),
        "GONE.US": _entry("GONE.US", sector=None, resolved=False),
    }
    resolve_fundamentals(["AAA.US", "GONE.US"], client, cache, now=_now)
    assert client.fetched == []  # both a resolved hit AND an unresolved miss are NOT re-queried
    assert cache["AAA.US"].sector == "Cached"  # not overwritten


def test_transport_error_skipped_not_cached() -> None:
    client = FakeFundamentalsClient(
        {"AAA.US": general_fundamentals(sector="X")}, raise_for={"AAA.US"}
    )
    cache: dict[str, FundamentalsEntry] = {}
    resolve_fundamentals(["AAA.US"], client, cache, now=_now)
    assert client.fetched == ["AAA.US"]
    assert "AAA.US" not in cache  # NOT cached -> retried next run


def test_duplicate_symbols_fetched_once() -> None:
    client = FakeFundamentalsClient({"AAA.US": general_fundamentals(sector="X")})
    cache: dict[str, FundamentalsEntry] = {}
    resolve_fundamentals(["AAA.US", "AAA.US"], client, cache, now=_now)
    assert client.fetched == ["AAA.US"]  # de-duplicated


def test_empty_symbols_noop() -> None:
    client = FakeFundamentalsClient({})
    cache: dict[str, FundamentalsEntry] = {}
    resolve_fundamentals([], client, cache, now=_now)
    assert client.fetched == []
    assert cache == {}
