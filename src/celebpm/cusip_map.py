"""CUSIP->ticker resolver (disk-free; MUTATES the cache dict IN PLACE).

Disk lives in storage.py; this layer takes the loaded cache dict in, MUTATES IT IN PLACE
(no deep copy — avoids copying a global dict per investor), and returns the SAME object in
result.cache plus the enriched positions. The resolver OWNS chunking and partial-success.
ALIGNMENT is the client's job (its response-array length-guard) — there is NO resolver-layer
alignment re-check. See plan §4 / §6.
"""

from __future__ import annotations

import dataclasses
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from celebpm import constants
from celebpm.errors import OpenFigiError
from celebpm.models import CusipMapEntry, PositionRecord
from celebpm.openfigi_client import MapJob, MapMatch, MappingClient, MapResult

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Tz-aware UTC now (injectable in resolve_tickers for deterministic tests)."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True, kw_only=True)
class ResolveResult:
    """Bundle returned by resolve_tickers."""

    positions: list[PositionRecord]  # tickers filled where resolvable
    cache: dict[str, CusipMapEntry]  # the SAME dict passed in, mutated in place
    ambiguous_cusips: tuple[str, ...]  # ambiguous among THIS run's cusips (incl. cache hits)
    partial: bool  # True when a mid-run OpenFigiError cut the run short


@dataclass(frozen=True, kw_only=True)
class _TickeredMatch:
    """A MapMatch known (post-filter) to have a non-blank ticker, narrowed to str for mypy."""

    ticker: str
    match: MapMatch


def collect_cusips(positions: list[PositionRecord]) -> list[str]:
    """Distinct CUSIPs, sorted, deterministic."""
    return sorted({pos.cusip for pos in positions})


def select_match(matches: tuple[MapMatch, ...]) -> tuple[MapMatch | None, bool]:
    """Deterministic CUSIP->ticker selection. Returns (chosen, ambiguous). See plan §4.

    Querying is UNFILTERED, so this step does ALL the US-preference work. Each preference step
    narrows to the subset that satisfies it IF any do, else keeps the current set (a preference
    never empties the pool). Ambiguous = >1 DISTINCT ticker in the strongest surviving tier.
    """
    # Step 1: drop matches with no usable ticker (None or blank/whitespace).
    candidates: list[_TickeredMatch] = []
    for m in matches:
        if m.ticker is not None and m.ticker.strip() != "":
            candidates.append(_TickeredMatch(ticker=m.ticker.strip(), match=m))
    if not candidates:
        return None, False

    # Steps 2-5: preference filters (narrow-if-any-satisfy).
    candidates = _prefer(
        candidates, lambda c: c.match.exch_code == constants.OPENFIGI_PREFERRED_EXCH_CODE
    )
    candidates = _prefer(
        candidates,
        lambda c: c.match.security_type2 in constants.OPENFIGI_PREFERRED_SECURITY_TYPE2,
    )
    candidates = _prefer(
        candidates,
        lambda c: c.match.market_sector == constants.OPENFIGI_PREFERRED_MARKET_SECTOR,
    )
    candidates = _prefer(candidates, lambda c: c.match.composite_figi is not None)

    # Ambiguity: >1 distinct ticker in the strongest surviving tier (before the tie-break).
    distinct_tickers = {c.ticker for c in candidates}
    ambiguous = len(distinct_tickers) > 1

    # Step 6: fully deterministic tie-break.
    chosen = min(
        candidates,
        key=lambda c: (c.ticker, c.match.exch_code or "", c.match.figi or ""),
    )
    return chosen.match, ambiguous


def _prefer(
    candidates: list[_TickeredMatch], predicate: Callable[[_TickeredMatch], bool]
) -> list[_TickeredMatch]:
    """Narrow to the subset satisfying predicate IF any do; else keep the current set."""
    subset = [c for c in candidates if predicate(c)]
    return subset if subset else candidates


def resolve_tickers(
    positions: list[PositionRecord],
    client: MappingClient,
    cache: dict[str, CusipMapEntry],
    *,
    now: Callable[[], datetime] = _utc_now,
) -> ResolveResult:
    """Resolve CUSIP->ticker for `positions`, MUTATING `cache` IN PLACE (result.cache is cache).

    `cache` MUST be read_cusip_map() output (keyed by cusip; reader guarantees key == entry.cusip
    and no duplicates) — the resolver trusts that invariant and does NOT re-validate it.

    Cache-first: hits (any source incl. `unresolved` and `manual`) are NOT re-queried; `manual`
    wins and is never overwritten. The resolver OWNS chunking (by client.max_jobs_per_request)
    and partial-success: a mid-run OpenFigiError -> WARN, partial=True, BREAK (prior fully-parsed
    chunks kept; the failing/remaining chunks retry next run). Any OTHER exception propagates.

    A partial result is NOT an error — it may cover fewer cusips than requested; the caller still
    writes the cache (persisting progress) and the misses retry next run.
    """
    cusips = collect_cusips(positions)
    run_timestamp = now().isoformat()  # ONE timestamp per run (plan §6)

    # Cache-first partition + ambiguity-staleness scan over THIS run's cusips.
    misses: list[str] = []
    ambiguous_set: set[str] = set()
    for cusip in cusips:
        entry = cache.get(cusip)
        if entry is None:
            misses.append(cusip)
            continue
        if entry.ambiguous:
            ambiguous_set.add(cusip)  # surface known-ambiguous hits every run (plan §6)

    partial = False
    newly_resolved = 0
    newly_unresolved = 0
    not_attempted = 0

    if misses:
        rate_per_min = _client_rate_per_minute(client)
        chunk_size = client.max_jobs_per_request
        est_min = (
            math.ceil(len(misses) / chunk_size) / rate_per_min if rate_per_min else 0.0
        )
        logger.info(
            "cold cache: resolving %d CUSIPs (~%.1f min at the no-key rate)",
            len(misses),
            est_min,
        )

        jobs = [MapJob(cusip=cusip) for cusip in misses]
        chunks = [
            jobs[i : i + chunk_size] for i in range(0, len(jobs), chunk_size)
        ]
        resolved_count = 0
        for idx, chunk in enumerate(chunks):
            try:
                results = client.map_jobs(chunk)
                # Build ALL of this chunk's entries locally; merge only after full parse.
                local: dict[str, CusipMapEntry] = {}
                for result in results:
                    entry, is_ambiguous, resolved = _build_entry(result, run_timestamp)
                    local[result.cusip] = entry
                    if is_ambiguous:
                        ambiguous_set.add(result.cusip)
                    if resolved:
                        newly_resolved += 1
                    else:
                        newly_unresolved += 1
                cache.update(local)  # whole-chunk-then-merge (plan §6)
                resolved_count += len(chunk)
            except OpenFigiError as err:
                logger.warning(
                    "OpenFIGI resolution stopped after %d/%d cusips: %s",
                    resolved_count,
                    len(misses),
                    err,
                )
                partial = True
                not_attempted = len(misses) - resolved_count
                break

    # Enrichment — DON'T clobber an existing ticker with None.
    enriched: list[PositionRecord] = []
    for pos in positions:
        entry = cache.get(pos.cusip)
        if entry is not None and entry.ticker is not None:
            enriched.append(dataclasses.replace(pos, ticker=entry.ticker))
        else:
            enriched.append(pos)  # unresolved or not-yet-reached -> leave ticker unchanged

    # De-overlapped summary buckets.
    cached_resolved = 0
    cached_unresolved = 0
    for cusip in cusips:
        if cusip in misses:
            continue
        entry = cache.get(cusip)
        if entry is None:
            continue  # defensive; a non-miss always has an entry
        if entry.source == constants.CUSIP_SOURCE_UNRESOLVED:
            cached_unresolved += 1
        else:
            cached_resolved += 1

    summary = (
        f"resolved: cached_resolved={cached_resolved} "
        f"cached_unresolved={cached_unresolved} newly_resolved={newly_resolved} "
        f"newly_unresolved={newly_unresolved} not_attempted={not_attempted} "
        f"ambiguous={len(ambiguous_set)} (of {len(cusips)} cusips)"
    )
    if partial:
        summary += " [PARTIAL]"
    logger.info(summary)

    return ResolveResult(
        positions=enriched,
        cache=cache,
        ambiguous_cusips=tuple(sorted(ambiguous_set)),
        partial=partial,
    )


def _build_entry(
    result: MapResult, run_timestamp: str
) -> tuple[CusipMapEntry, bool, bool]:
    """Build a CusipMapEntry from a MapResult. Returns (entry, ambiguous, resolved)."""
    chosen, ambiguous = select_match(result.matches)
    if chosen is not None:
        # ticker is guaranteed non-blank (blanks dropped in §3/§4); narrow to str for mypy.
        ticker = chosen.ticker
        assert ticker is not None and ticker.strip() != ""
        if ambiguous:
            logger.warning(
                "ambiguous CUSIP->ticker for %s: chose %r (>1 distinct ticker in tier)",
                result.cusip,
                ticker.strip(),
            )
        entry = CusipMapEntry(
            cusip=result.cusip,
            ticker=ticker.strip(),
            name=chosen.name,
            exch_code=chosen.exch_code,
            figi_security_type=chosen.security_type,
            figi_security_type2=chosen.security_type2,
            market_sector=chosen.market_sector,
            figi=chosen.figi,
            source=constants.CUSIP_SOURCE_OPENFIGI,
            ambiguous=ambiguous,
            resolved_at=run_timestamp,
        )
        return entry, ambiguous, True

    # No usable match (whitelisted miss / empty data / all tickers blank/absent) -> unresolved.
    logger.warning(
        "unresolved CUSIP %s: no usable ticker (warning=%r)",
        result.cusip,
        result.warning,
    )
    entry = CusipMapEntry(
        cusip=result.cusip,
        ticker=None,
        name=None,
        exch_code=None,
        figi_security_type=None,
        figi_security_type2=None,
        market_sector=None,
        figi=None,
        source=constants.CUSIP_SOURCE_UNRESOLVED,
        ambiguous=False,
        resolved_at=run_timestamp,
    )
    return entry, False, False


def _client_rate_per_minute(client: MappingClient) -> float:
    """Best-effort per-minute rate for the cold-start estimate (no hard dependency)."""
    rate = getattr(client, "_bucket", None)
    rate_per_sec = getattr(rate, "_rate", None)
    if isinstance(rate_per_sec, (int, float)) and rate_per_sec > 0:
        return float(rate_per_sec) * 60.0
    return constants.OPENFIGI_REQUESTS_PER_MINUTE_NO_KEY
