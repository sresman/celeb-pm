"""EODHD fundamentals resolver: sector/industry per EODHD symbol (View 3 enrichment).

Disk-free; MUTATES the cache dict IN PLACE (mirrors cusip_map.resolve_tickers). Disk lives in
storage.py. Cache-first: hits (incl. unresolved misses) are NOT re-queried. A per-symbol
transport error -> WARN + skip (retry next run, NOT cached). A 404 / missing General fields ->
cached UNRESOLVED (resolved=False) so we don't re-fetch. ETF (General.Type == "ETF") -> sector
set to the ETF label. The cache is keyed by eodhd_symbol (the fetch unit; SD-V3-3).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Iterable

from celebpm import constants
from celebpm.errors import EodhdError
from celebpm.models import FundamentalsEntry
from celebpm.price_types import FundamentalsClient

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Tz-aware UTC now (injectable in resolve_fundamentals for deterministic tests)."""
    return datetime.now(timezone.utc)


def _coerce_str(value: object) -> str | None:
    """A non-blank str from a raw JSON value, else None (EODHD sends "" / null for absent fields)."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _parse_fundamentals(
    symbol: str, raw: dict[str, object], run_timestamp: str
) -> FundamentalsEntry:
    """Build a RESOLVED FundamentalsEntry from a raw EODHD fundamentals object.

    We reached the API and got an object -> resolved=True; sector/industry may still be None if
    absent. General.Type == 'ETF' -> sector := the ETF label (SD: ETFs carry no GICS sector).
    """
    general = raw.get(constants.EODHD_FUND_GENERAL_KEY)
    if not isinstance(general, dict):
        general = {}
    instrument_type = _coerce_str(general.get(constants.EODHD_FUND_TYPE_KEY))
    industry = _coerce_str(general.get(constants.EODHD_FUND_INDUSTRY_KEY))
    if instrument_type is not None and instrument_type.upper() == constants.EODHD_FUND_TYPE_ETF:
        sector: str | None = constants.SECTOR_ETF_LABEL
    else:
        sector = _coerce_str(general.get(constants.EODHD_FUND_SECTOR_KEY))
    return FundamentalsEntry(
        eodhd_symbol=symbol,
        sector=sector,
        industry=industry,
        instrument_type=instrument_type,
        resolved=True,
        fetched_at=run_timestamp,
    )


def _unresolved(symbol: str, run_timestamp: str) -> FundamentalsEntry:
    """An UNRESOLVED cache row (404 / no fundamentals) — cached so we do not re-fetch it."""
    return FundamentalsEntry(
        eodhd_symbol=symbol,
        sector=None,
        industry=None,
        instrument_type=None,
        resolved=False,
        fetched_at=run_timestamp,
    )


def resolve_fundamentals(
    symbols: Iterable[str],
    client: FundamentalsClient,
    cache: dict[str, FundamentalsEntry],
    *,
    now: Callable[[], datetime] = _utc_now,
) -> dict[str, FundamentalsEntry]:
    """Resolve sector/industry for `symbols`, MUTATING `cache` IN PLACE (returns the same dict).

    Cache-first: any symbol already in `cache` (resolved OR unresolved) is NOT re-queried. For
    each miss, fetch from EODHD: a returned object -> resolved entry (ETF -> sector=ETF); a 404
    (None) -> cached UNRESOLVED so it is not re-fetched. A per-symbol EodhdError is logged +
    SKIPPED (NOT cached) so it retries next run. Symbols are de-duplicated and processed in a
    deterministic (sorted) order for stable logs.
    """
    run_timestamp = now().isoformat()
    misses = sorted({s for s in symbols if s and s not in cache})
    if not misses:
        return cache

    logger.info("resolving EODHD fundamentals for %d symbol(s)", len(misses))
    newly_resolved = 0
    newly_unresolved = 0
    skipped = 0
    for symbol in misses:
        try:
            raw = client.fetch_fundamentals(symbol)
        except EodhdError as exc:
            logger.warning(
                "EODHD fundamentals fetch failed for %s; skipping (retry next run): %s",
                symbol,
                exc,
            )
            skipped += 1
            continue
        if raw is None:
            cache[symbol] = _unresolved(symbol, run_timestamp)
            newly_unresolved += 1
            continue
        cache[symbol] = _parse_fundamentals(symbol, raw, run_timestamp)
        newly_resolved += 1

    logger.info(
        "fundamentals: newly_resolved=%d newly_unresolved=%d skipped=%d (of %d misses)",
        newly_resolved,
        newly_unresolved,
        skipped,
        len(misses),
    )
    return cache
