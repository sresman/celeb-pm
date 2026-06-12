"""View 1 — New Ideas Feed builder.

DISK-FREE / DETERMINISTIC (no disk, network, or pandas; MAY log WARN — mirrors diff.py).
Builds one NewIdeaRow per NEW PositionChange with hold-chain + return analytics, plus a
NewIdeasSummary of population statistics. The pandas/CSV/JSON I/O lives in view_io.py so the
builder stays pure business logic and mypy-strict clean. See Prompt-6 plan §1–§2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from celebpm import constants
from celebpm.config_loader import InvestorConfig
from celebpm.errors import DiscoveryError
from celebpm.models import (
    ChangeType,
    PositionChange,
    PositionRecord,
    ReturnRecord,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class NewIdeaRow:
    """One NEW position across all quarters, with hold-chain + return analytics."""

    # --- identity / display ---
    quarter: date  # the NEW's period (quarter-end)
    filing_date: date  # the NEW's filing_date (the anchor)
    ticker_display: str  # ticker, else CUSIP fallback (NEVER "" or "None")
    company: str  # NEW's PositionRecord.company_name; fallback ticker_display->CUSIP
    cusip: str
    security_type: str  # COMMON / PUT / CALL
    is_option: bool  # security_type in {PUT, CALL} -- derived from the NEW, NOT the ReturnRecord
    is_underlying_price: bool  # == is_option (derived from the NEW's security_type)
    # --- entry weight ---
    initial_weight_pct: float  # the NEW's current_weight_pct (== weight_pct_reported)
    # --- entry-band returns (NEW-only; None if unpriced/no entry window) ---
    best_case_entry_return_pct: float | None
    worst_case_entry_return_pct: float | None
    # --- forward (1Q) returns from filing date ---
    filing_to_filing_return_pct: float | None
    filing_to_next_period_high_pct: float | None
    filing_to_next_period_low_pct: float | None
    # --- SPY-excess (position - SPY) for the three forward measures ---
    excess_filing_to_filing_pct: float | None
    excess_next_period_high_pct: float | None
    excess_next_period_low_pct: float | None
    # --- cumulative (first->last filing if held multi-Q) ---
    cumulative_return_pct: float | None
    # --- hold-chain analytics ---
    quarters_held: int  # OBSERVED reporting periods present; NEW quarter = 1
    max_weight_pct: float  # peak current_weight_pct across the hold (>= initial)
    exit_quarter: date | None  # period of this cycle's first EXIT; None => "CURRENT"
    became_active_add: bool  # any ACTIVE_ADD in a later quarter of THIS cycle
    priced: bool  # from the NEW's ReturnRecord (False/missing => all return cols NA)


@dataclass(frozen=True, kw_only=True)
class NewIdeasSummary:
    """Summary statistics. ALL rates None on an empty (sub-)population. See §2."""

    total_new: int  # count of all NEW rows (incl. unpriced/options)
    priced_new: int  # count of NEW rows with priced=True (audit/denominator context)
    win_rate_pct: float | None
    avg_winner_return_pct: float | None
    avg_loser_return_pct: float | None
    median_holding_quarters: float | None  # median quarters_held over CLOSED NEWs only
    pct_became_active_add: float | None  # % of ALL NEW that became ACTIVE_ADD
    notes: str  # SD-5 caveat one-liner

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-ready dict keyed by the SUMMARY_KEY_* constants."""
        return {
            constants.SUMMARY_KEY_TOTAL_NEW: self.total_new,
            constants.SUMMARY_KEY_PRICED_NEW: self.priced_new,
            constants.SUMMARY_KEY_WIN_RATE_PCT: self.win_rate_pct,
            constants.SUMMARY_KEY_AVG_WINNER: self.avg_winner_return_pct,
            constants.SUMMARY_KEY_AVG_LOSER: self.avg_loser_return_pct,
            constants.SUMMARY_KEY_MEDIAN_HOLDING_QUARTERS: self.median_holding_quarters,
            constants.SUMMARY_KEY_PCT_BECAME_ACTIVE_ADD: self.pct_became_active_add,
            constants.SUMMARY_KEY_NOTES: self.notes,
        }


@dataclass(frozen=True, kw_only=True)
class NewIdeasView:
    cik: str
    slug: str
    rows: tuple[NewIdeaRow, ...]  # sorted by initial_weight_pct DESC (tiebreak cusip, sec_type)
    summary: NewIdeasSummary


def _is_option(security_type: str) -> bool:
    return security_type in {constants.SECURITY_TYPE_PUT, constants.SECURITY_TYPE_CALL}


def _nonblank(value: str | None) -> str | None:
    """Stripped value if non-None and non-blank after strip; else None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _ticker_display(change_ticker: str | None, pos_ticker: str | None, cusip: str) -> str:
    """change.ticker -> PositionRecord.ticker -> CUSIP. Never "" or the literal "None"."""
    return _nonblank(change_ticker) or _nonblank(pos_ticker) or cusip


def _excess(position: float | None, spy: float | None) -> float | None:
    """position - SPY, but only when BOTH operands are non-None (else None)."""
    if position is None or spy is None:
        return None
    return position - spy


def _median(values: list[float]) -> float | None:
    """Pure median (sort + middle / mean-of-two). None on empty (guarded by caller too)."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _validate_cik(
    config: InvestorConfig,
    positions: list[PositionRecord],
    changes: list[PositionChange],
    returns: list[ReturnRecord],
) -> None:
    """Single-CIK AND every record.cik == config.cik (mirrors compute_changes/returns)."""
    for label, ciks in (
        ("positions", {p.cik for p in positions}),
        ("changes", {c.cik for c in changes}),
        ("returns", {r.cik for r in returns}),
    ):
        for found in ciks:
            if found != config.cik:
                raise DiscoveryError(
                    f"build_new_ideas_view {label} cik {found!r} != config.cik "
                    f"{config.cik!r}"
                )


def _position_by_key(
    positions: list[PositionRecord],
) -> dict[tuple[str, str, date], PositionRecord]:
    """{(cusip, security_type, period): PositionRecord}. Keep-first + WARN on duplicate key."""
    out: dict[tuple[str, str, date], PositionRecord] = {}
    for pos in positions:
        key = (pos.cusip, pos.security_type, pos.period)
        if key in out:
            logger.warning(
                "duplicate PositionRecord key %s; keeping first, ignoring later", key
            )
            continue
        out[key] = pos
    return out


def _return_by_key(
    returns: list[ReturnRecord],
) -> dict[tuple[str, str, date, ChangeType], ReturnRecord]:
    """{(cusip, security_type, filing_date, change_type): ReturnRecord}."""
    out: dict[tuple[str, str, date, ChangeType], ReturnRecord] = {}
    for rec in returns:
        out[(rec.cusip, rec.security_type, rec.filing_date, rec.change_type)] = rec
    return out


def _chain_by_key(
    changes: list[PositionChange],
) -> dict[tuple[str, str], list[PositionChange]]:
    """Group changes by (cusip, security_type), each list sorted by period ascending."""
    grouped: dict[tuple[str, str], list[PositionChange]] = {}
    for change in changes:
        grouped.setdefault((change.cusip, change.security_type), []).append(change)
    for chain in grouped.values():
        chain.sort(key=lambda c: c.period)
    return grouped


@dataclass(frozen=True)
class _HoldChain:
    quarters_held: int
    max_weight_pct: float
    exit_quarter: date | None
    became_active_add: bool


def _walk_hold_chain(new_change: PositionChange, chain: list[PositionChange]) -> _HoldChain:
    """Strict per-cycle slice: only period >= NEW.period, stop at this cycle's first EXIT.

    quarters_held = 1 (the NEW) + subsequent HELD changes (non-None current_weight_pct)
    before the first EXIT. max_weight_pct = max current_weight_pct over NEW + held.
    exit_quarter = first EXIT period after the NEW (else None). became_active_add = any
    ACTIVE_ADD with period > NEW.period in this cycle.
    """
    initial_weight = new_change.current_weight_pct
    assert initial_weight is not None  # a NEW always has current_weight_pct set
    quarters_held = 1
    max_weight = initial_weight
    exit_quarter: date | None = None
    became_active_add = False

    for change in chain:
        if change.period <= new_change.period:
            continue  # before / at the NEW (the NEW itself is the floor)
        if change.change_type == ChangeType.EXIT:
            exit_quarter = change.period
            break  # first EXIT terminates this cycle
        # A HELD change (still on the books) has a non-None current_weight_pct.
        if change.current_weight_pct is not None:
            quarters_held += 1
            if change.current_weight_pct > max_weight:
                max_weight = change.current_weight_pct
        if change.change_type == ChangeType.ACTIVE_ADD:
            became_active_add = True

    return _HoldChain(
        quarters_held=quarters_held,
        max_weight_pct=max_weight,
        exit_quarter=exit_quarter,
        became_active_add=became_active_add,
    )


def _build_row(
    new_change: PositionChange,
    *,
    ret: ReturnRecord | None,
    pos: PositionRecord | None,
    chain: list[PositionChange],
) -> NewIdeaRow:
    cusip = new_change.cusip
    security_type = new_change.security_type
    is_option = _is_option(security_type)

    ticker_display = _ticker_display(
        new_change.ticker, pos.ticker if pos is not None else None, cusip
    )
    company = (
        _nonblank(pos.company_name) if pos is not None else None
    ) or ticker_display

    initial_weight = new_change.current_weight_pct
    assert initial_weight is not None  # NEW invariant

    # Return / excess derivation (all-None when unpriced or no matching ReturnRecord).
    priced = ret is not None and ret.priced
    if ret is not None:
        best_entry = ret.best_case_entry_return_pct
        worst_entry = ret.worst_case_entry_return_pct
        f2f = ret.filing_to_filing_return_pct
        f2h = ret.filing_to_next_period_high_pct
        f2l = ret.filing_to_next_period_low_pct
        cumulative = ret.cumulative_return_pct
        spy_f2f = ret.spy_filing_to_filing_return_pct
        spy_h = ret.spy_next_period_high_pct
        spy_l = ret.spy_next_period_low_pct
    else:
        best_entry = worst_entry = None
        f2f = f2h = f2l = cumulative = None
        spy_f2f = spy_h = spy_l = None

    chain_result = _walk_hold_chain(new_change, chain)

    return NewIdeaRow(
        quarter=new_change.period,
        filing_date=new_change.filing_date,
        ticker_display=ticker_display,
        company=company,
        cusip=cusip,
        security_type=security_type,
        is_option=is_option,
        is_underlying_price=is_option,
        initial_weight_pct=initial_weight,
        best_case_entry_return_pct=best_entry,
        worst_case_entry_return_pct=worst_entry,
        filing_to_filing_return_pct=f2f,
        filing_to_next_period_high_pct=f2h,
        filing_to_next_period_low_pct=f2l,
        excess_filing_to_filing_pct=_excess(f2f, spy_f2f),
        excess_next_period_high_pct=_excess(f2h, spy_h),
        excess_next_period_low_pct=_excess(f2l, spy_l),
        cumulative_return_pct=cumulative,
        quarters_held=chain_result.quarters_held,
        max_weight_pct=chain_result.max_weight_pct,
        exit_quarter=chain_result.exit_quarter,
        became_active_add=chain_result.became_active_add,
        priced=priced,
    )


def _build_summary(rows: tuple[NewIdeaRow, ...]) -> NewIdeasSummary:
    total_new = len(rows)
    priced_new = sum(1 for r in rows if r.priced)

    # Win-rate population = NEW with non-None filing_to_filing_return_pct.
    returns_pop = [
        r.filing_to_filing_return_pct
        for r in rows
        if r.filing_to_filing_return_pct is not None
    ]
    if returns_pop:
        wins = sum(1 for v in returns_pop if v > 0)
        win_rate_pct: float | None = wins / len(returns_pop) * 100.0
    else:
        win_rate_pct = None

    winners = [v for v in returns_pop if v > 0]
    losers = [v for v in returns_pop if v < 0]
    avg_winner = _mean(winners)
    avg_loser = _mean(losers)

    # Median holding quarters over CLOSED NEWs only (exit_quarter is not None).
    closed_holds = [float(r.quarters_held) for r in rows if r.exit_quarter is not None]
    median_holding = _median(closed_holds)

    # % became ACTIVE_ADD over ALL NEW.
    if total_new:
        became = sum(1 for r in rows if r.became_active_add)
        pct_became_active_add: float | None = became / total_new * 100.0
    else:
        pct_became_active_add = None

    return NewIdeasSummary(
        total_new=total_new,
        priced_new=priced_new,
        win_rate_pct=win_rate_pct,
        avg_winner_return_pct=avg_winner,
        avg_loser_return_pct=avg_loser,
        median_holding_quarters=median_holding,
        pct_became_active_add=pct_became_active_add,
        notes=constants.SUMMARY_NOTES,
    )


def build_new_ideas_view(
    *,
    config: InvestorConfig,
    positions: list[PositionRecord],
    changes: list[PositionChange],
    returns: list[ReturnRecord],
) -> NewIdeasView:
    """Build View 1 (New Ideas Feed) from positions/changes/returns. Disk-free; may WARN.

    For each NEW PositionChange: join its ReturnRecord by (cusip, security_type, filing_date,
    NEW), its originating PositionRecord (company) by (cusip, security_type, period), and walk
    the (cusip, security_type) change chain (strictly sliced per cycle) for hold-chain stats.
    Rows sorted by initial_weight_pct DESC (tiebreak cusip asc, security_type asc). Raises
    DiscoveryError on any cik mismatch with config.cik.
    """
    _validate_cik(config, positions, changes, returns)

    pos_by_key = _position_by_key(positions)
    ret_by_key = _return_by_key(returns)
    chains = _chain_by_key(changes)

    rows: list[NewIdeaRow] = []
    for change in changes:
        if change.change_type != ChangeType.NEW:
            continue
        ret = ret_by_key.get(
            (change.cusip, change.security_type, change.filing_date, ChangeType.NEW)
        )
        if ret is None:
            logger.warning(
                "no ReturnRecord for NEW %s/%s @ %s; treating as unpriced",
                change.cusip,
                change.security_type,
                change.filing_date,
            )
        pos = pos_by_key.get((change.cusip, change.security_type, change.period))
        chain = chains.get((change.cusip, change.security_type), [])
        rows.append(_build_row(change, ret=ret, pos=pos, chain=chain))

    rows.sort(key=lambda r: (-r.initial_weight_pct, r.cusip, r.security_type))
    rows_tuple = tuple(rows)

    return NewIdeasView(
        cik=config.cik,
        slug=config.slug,
        rows=rows_tuple,
        summary=_build_summary(rows_tuple),
    )
