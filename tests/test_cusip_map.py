"""Tests for cusip_map: collect_cusips, select_match, resolve_tickers."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pytest

from celebpm import constants
from celebpm.cusip_map import (
    ResolveResult,
    collect_cusips,
    resolve_tickers,
    select_match,
)
from celebpm.errors import OpenFigiError
from celebpm.models import CusipMapEntry, PositionRecord
from celebpm.openfigi_client import MapJob, MapMatch, MappingClient, MapResult
from tests.conftest import FakeMappingClient

# --- STATIC Protocol conformance for the fake (incl. max_jobs_per_request). ---
_check: MappingClient = FakeMappingClient()
_size: int = _check.max_jobs_per_request


CUSIP_A = "037833100"
CUSIP_B = "594918104"
CUSIP_C = "88160R101"
FIXED_NOW = datetime(2026, 6, 11, 14, 3, 22, 512000, tzinfo=timezone.utc)


def _fixed_now() -> datetime:
    return FIXED_NOW


def _match(
    *,
    ticker: str | None = "AAPL",
    exch_code: str | None = "US",
    security_type2: str | None = "Common Stock",
    market_sector: str | None = "Equity",
    composite_figi: str | None = "BBG000B9XRY4",
    figi: str | None = "BBG000B9XVV8",
    name: str | None = "APPLE INC",
    security_type: str | None = "Common Stock",
) -> MapMatch:
    return MapMatch(
        ticker=ticker,
        name=name,
        exch_code=exch_code,
        security_type=security_type,
        security_type2=security_type2,
        market_sector=market_sector,
        composite_figi=composite_figi,
        figi=figi,
    )


def _position(
    *,
    cusip: str,
    ticker: str | None = None,
    security_type: str = constants.SECURITY_TYPE_COMMON,
    put_call: str = "",
) -> PositionRecord:
    return PositionRecord(
        cik="0001777813",
        accession_number="0001777813-26-000012",
        period=date(2025, 12, 31),
        filing_date=date(2026, 2, 14),
        cusip=cusip,
        company_name="X CORP",
        title_of_class="COM",
        security_type=security_type,
        put_call=put_call,
        ticker=ticker,
        shares=100,
        ssh_prnamt_type=constants.SSH_TYPE_SHARES,
        value_reported=1000,
        investment_discretion="",
        weight_pct_reported=10.0,
        weight_pct_equity_only=10.0,
    )


def _result(cusip: str, *matches: MapMatch) -> MapResult:
    return MapResult(cusip=cusip, matches=tuple(matches))


class TestCollectCusips:
    def test_distinct_sorted(self) -> None:
        positions = [
            _position(cusip=CUSIP_B),
            _position(cusip=CUSIP_A),
            _position(cusip=CUSIP_A),  # duplicate cusip -> deduped
        ]
        assert collect_cusips(positions) == [CUSIP_A, CUSIP_B]


class TestSelectMatch:
    def test_us_common_preferred(self) -> None:
        lse = _match(ticker="AAPL", exch_code="LN", composite_figi=None)
        us = _match(ticker="AAPL", exch_code="US")
        chosen, ambiguous = select_match((lse, us))
        assert chosen is us
        assert ambiguous is False

    def test_tie_break_same_ticker_not_ambiguous(self) -> None:
        a = _match(ticker="AAPL", exch_code="US", figi="BBG1")
        b = _match(ticker="AAPL", exch_code="US", figi="BBG2")
        chosen, ambiguous = select_match((a, b))
        assert chosen is not None
        assert chosen.ticker == "AAPL"
        assert ambiguous is False

    def test_two_distinct_us_common_tickers_ambiguous(self) -> None:
        a = _match(ticker="AAPL", exch_code="US")
        b = _match(ticker="APLE", exch_code="US")
        chosen, ambiguous = select_match((a, b))
        assert ambiguous is True
        assert chosen is not None  # still chosen deterministically

    def test_all_ticker_less_returns_none(self) -> None:
        chosen, ambiguous = select_match((_match(ticker=None),))
        assert chosen is None
        assert ambiguous is False

    @pytest.mark.parametrize("blank", ["", "  "])
    def test_all_blank_tickers_returns_none(self, blank: str) -> None:
        chosen, ambiguous = select_match((_match(ticker=blank),))
        assert chosen is None
        assert ambiguous is False


class TestResolveTickers:
    def test_cache_hit_avoids_requery(self) -> None:
        cache = {
            CUSIP_A: CusipMapEntry(
                cusip=CUSIP_A, ticker="AAPL", name=None, exch_code=None,
                figi_security_type=None, figi_security_type2=None, market_sector=None,
                figi=None, source=constants.CUSIP_SOURCE_OPENFIGI,
            )
        }
        fake = FakeMappingClient({})
        result = resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert fake.call_count == 0
        assert result.positions[0].ticker == "AAPL"

    def test_cache_miss_queries_and_updates(self) -> None:
        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient({CUSIP_A: _result(CUSIP_A, _match(ticker="AAPL"))})
        result = resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert fake.call_count == 1
        assert cache[CUSIP_A].source == constants.CUSIP_SOURCE_OPENFIGI
        assert cache[CUSIP_A].ticker == "AAPL"
        assert result.positions[0].ticker == "AAPL"

    def test_in_place_mutation(self) -> None:
        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient({CUSIP_A: _result(CUSIP_A, _match())})
        result = resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert result.cache is cache
        assert CUSIP_A in cache

    def test_resolved_at_iso_string_once_per_run(self) -> None:
        calls: list[int] = []

        def counting_now() -> datetime:
            calls.append(1)
            return FIXED_NOW

        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient(
            {
                CUSIP_A: _result(CUSIP_A, _match(ticker="AAPL")),
                CUSIP_B: _result(CUSIP_B, _match(ticker="MSFT")),
            }
        )
        resolve_tickers(
            [_position(cusip=CUSIP_A), _position(cusip=CUSIP_B)],
            fake,
            cache,
            now=counting_now,
        )
        assert len(calls) == 1
        assert cache[CUSIP_A].resolved_at == FIXED_NOW.isoformat()
        assert cache[CUSIP_B].resolved_at == FIXED_NOW.isoformat()

    def test_chunking_by_max_jobs(self) -> None:
        cache: dict[str, CusipMapEntry] = {}
        cusips = [CUSIP_A, CUSIP_B, CUSIP_C]
        fake = FakeMappingClient(
            {c: _result(c, _match(ticker=f"T{i}")) for i, c in enumerate(cusips)},
            max_jobs_per_request=2,
        )
        positions = [_position(cusip=c) for c in cusips]
        result = resolve_tickers(positions, fake, cache, now=_fixed_now)
        assert fake.call_count == 2  # ceil(3/2)
        assert [len(ch) for ch in fake.chunks] == [2, 1]
        assert all(c in cache for c in cusips)
        assert not result.partial

    def test_partial_success_whole_chunk_then_merge(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cache: dict[str, CusipMapEntry] = {}
        cusips = sorted([CUSIP_A, CUSIP_B, CUSIP_C])
        fake = FakeMappingClient(
            {c: _result(c, _match(ticker="AAPL")) for c in cusips},
            max_jobs_per_request=2,
            raise_on_call=2,  # chunk 1 succeeds, chunk 2 raises
        )
        positions = [_position(cusip=c) for c in cusips]
        with caplog.at_level(logging.WARNING):
            result = resolve_tickers(positions, fake, cache, now=_fixed_now)
        assert result.partial is True
        # chunk 1's two cusips are cached; chunk 2's cusip is NOT.
        chunk1 = cusips[:2]
        chunk2 = cusips[2:]
        assert all(c in cache for c in chunk1)
        assert all(c not in cache for c in chunk2)
        assert any("stopped after" in r.message for r in caplog.records)

    def test_non_openfigi_error_propagates(self) -> None:
        class BoomClient:
            max_jobs_per_request = 10

            def map_jobs(self, jobs: list[MapJob]) -> list[MapResult]:
                raise RuntimeError("fatal")

        cache: dict[str, CusipMapEntry] = {}
        with pytest.raises(RuntimeError):
            resolve_tickers([_position(cusip=CUSIP_A)], BoomClient(), cache, now=_fixed_now)

    def test_manual_wins_never_requeried_never_overwritten(self) -> None:
        cache = {
            CUSIP_A: CusipMapEntry(
                cusip=CUSIP_A, ticker="MANUAL", name=None, exch_code=None,
                figi_security_type=None, figi_security_type2=None, market_sector=None,
                figi=None, source=constants.CUSIP_SOURCE_MANUAL,
            )
        }
        fake = FakeMappingClient({CUSIP_A: _result(CUSIP_A, _match(ticker="DIFFERENT"))})
        result = resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert fake.call_count == 0
        assert cache[CUSIP_A].ticker == "MANUAL"
        assert result.positions[0].ticker == "MANUAL"

    def test_unresolved_marker_prevents_requery(self) -> None:
        cache = {
            CUSIP_A: CusipMapEntry(
                cusip=CUSIP_A, ticker=None, name=None, exch_code=None,
                figi_security_type=None, figi_security_type2=None, market_sector=None,
                figi=None, source=constants.CUSIP_SOURCE_UNRESOLVED,
            )
        }
        fake = FakeMappingClient({})
        resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert fake.call_count == 0

    def test_in_payload_miss_becomes_unresolved(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient(
            {CUSIP_A: MapResult(cusip=CUSIP_A, matches=(), warning="No identifier found.")}
        )
        with caplog.at_level(logging.WARNING):
            resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert cache[CUSIP_A].source == constants.CUSIP_SOURCE_UNRESOLVED
        assert cache[CUSIP_A].ticker is None
        assert cache[CUSIP_A].resolved_at == FIXED_NOW.isoformat()

    def test_ambiguity_flag_and_surfacing(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cache: dict[str, CusipMapEntry] = {}
        ambiguous_result = _result(
            CUSIP_A,
            _match(ticker="AAPL", exch_code="US"),
            _match(ticker="APLE", exch_code="US"),
        )
        fake = FakeMappingClient({CUSIP_A: ambiguous_result})
        with caplog.at_level(logging.WARNING):
            result = resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert cache[CUSIP_A].ambiguous is True
        assert CUSIP_A in result.ambiguous_cusips
        assert any("ambiguous" in r.message.lower() for r in caplog.records)

    def test_ambiguity_carryover_on_cache_hit(self) -> None:
        cache = {
            CUSIP_A: CusipMapEntry(
                cusip=CUSIP_A, ticker="AAPL", name=None, exch_code=None,
                figi_security_type=None, figi_security_type2=None, market_sector=None,
                figi=None, source=constants.CUSIP_SOURCE_OPENFIGI, ambiguous=True,
            )
        }
        fake = FakeMappingClient({})
        result = resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        assert fake.call_count == 0
        assert CUSIP_A in result.ambiguous_cusips

    def test_enrichment_dont_clobber_existing_ticker(self) -> None:
        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient(
            {CUSIP_A: MapResult(cusip=CUSIP_A, matches=())}  # unresolved
        )
        pos = _position(cusip=CUSIP_A, ticker="PREEXISTING")
        result = resolve_tickers([pos], fake, cache, now=_fixed_now)
        # unresolved -> leave the pre-existing ticker unchanged.
        assert result.positions[0].ticker == "PREEXISTING"

    def test_enrichment_preserves_count_and_originals(self) -> None:
        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient({CUSIP_A: _result(CUSIP_A, _match(ticker="AAPL"))})
        positions = [_position(cusip=CUSIP_A), _position(cusip=CUSIP_B)]
        result = resolve_tickers(positions, fake, cache, now=_fixed_now)
        assert len(result.positions) == 2
        assert positions[0].ticker is None  # original unmutated (frozen)

    def test_summary_buckets_sum_to_y(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        cache = {
            CUSIP_C: CusipMapEntry(
                cusip=CUSIP_C, ticker="CACHED", name=None, exch_code=None,
                figi_security_type=None, figi_security_type2=None, market_sector=None,
                figi=None, source=constants.CUSIP_SOURCE_OPENFIGI,
            )
        }
        fake = FakeMappingClient(
            {
                CUSIP_A: _result(CUSIP_A, _match(ticker="AAPL")),
                CUSIP_B: MapResult(cusip=CUSIP_B, matches=()),  # newly unresolved
            }
        )
        positions = [_position(cusip=c) for c in (CUSIP_A, CUSIP_B, CUSIP_C)]
        with caplog.at_level(logging.INFO):
            resolve_tickers(positions, fake, cache, now=_fixed_now)
        summary = next(
            r.message for r in caplog.records if r.message.startswith("resolved:")
        )
        assert "cached_resolved=1" in summary
        assert "newly_resolved=1" in summary
        assert "newly_unresolved=1" in summary
        assert "(of 3 cusips)" in summary

    def test_compose_level_cache_threading(self) -> None:
        # Investor A resolves CUSIP_A; investor B (also holds CUSIP_A) sees it as a hit.
        cache: dict[str, CusipMapEntry] = {}
        fake = FakeMappingClient(
            {
                CUSIP_A: _result(CUSIP_A, _match(ticker="AAPL")),
                CUSIP_B: _result(CUSIP_B, _match(ticker="MSFT")),
            }
        )
        resolve_tickers([_position(cusip=CUSIP_A)], fake, cache, now=_fixed_now)
        chunks_after_a = len(fake.chunks)
        resolve_tickers(
            [_position(cusip=CUSIP_A), _position(cusip=CUSIP_B)],
            fake,
            cache,
            now=_fixed_now,
        )
        # B's pass must NOT include CUSIP_A in any chunk (it was a cache hit).
        b_pass_chunks = fake.chunks[chunks_after_a:]
        b_cusips = {job.cusip for ch in b_pass_chunks for job in ch}
        assert CUSIP_A not in b_cusips
        assert CUSIP_B in b_cusips
