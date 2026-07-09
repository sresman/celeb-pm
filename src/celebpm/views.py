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
    FundamentalsEntry,
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
    # --- SMH-excess (position - SMH) for the three forward measures ---
    smh_excess_filing_to_filing_pct: float | None
    smh_excess_next_period_high_pct: float | None
    smh_excess_next_period_low_pct: float | None
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
        smh_f2f = ret.smh_filing_to_filing_return_pct
        smh_h = ret.smh_next_period_high_pct
        smh_l = ret.smh_next_period_low_pct
    else:
        best_entry = worst_entry = None
        f2f = f2h = f2l = cumulative = None
        spy_f2f = spy_h = spy_l = None
        smh_f2f = smh_h = smh_l = None

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
        smh_excess_filing_to_filing_pct=_excess(f2f, smh_f2f),
        smh_excess_next_period_high_pct=_excess(f2h, smh_h),
        smh_excess_next_period_low_pct=_excess(f2l, smh_l),
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


# ======================================================================================
# View 2 — Conviction Tracker (one row per ACTIVE_ADD event).
# PURE / DISK-FREE (no disk, network, or pandas; MAY log WARN). Reuses View-1 helpers.
# ======================================================================================


@dataclass(frozen=True, kw_only=True)
class ConvictionAddRow:
    """One ACTIVE_ADD event with prior-window context, hold-chain, and forward returns."""

    # --- identity / display ---
    quarter: date  # change.period (the ADD's quarter-end)
    ticker_display: str  # ticker fallback chain; CSV header "ticker"
    company: str  # positions lookup; fallback ticker_display->cusip
    cusip: str  # change.cusip
    security_type: str  # COMMON / CALL / PUT
    is_option: bool  # security_type in {PUT, CALL}
    # --- weights (ACTIVE_ADD => all three non-None per model invariant) ---
    weight_before_pct: float  # change.prior_weight_pct (non-None for ACTIVE_ADD)
    weight_after_pct: float  # change.current_weight_pct (non-None for ACTIVE_ADD)
    weight_delta_pct: float  # change.weight_delta_bps / PCT_TO_BPS (non-None)
    shares_delta_pct: float | None  # MAY be None (prior denominator 0)
    # --- prior-quarter context ---
    prior_quarter_return_pct: float | None  # prior change's f2f; None if absent/unpriced
    add_type: str | None  # ADD_TYPE_WINNER / ADD_TYPE_AVERAGING_DOWN / None
    quarters_held_before_add: int  # consecutive on-book quarters BEFORE this add
    nth_add: int  # 1-based add count within current cycle (this add incl.)
    original_entry_quarter: date | None  # cycle's NEW.period; None if held before dataset
    cumulative_return_since_entry_pct: float | None  # entry-price -> add-price ratio
    # --- forward (1Q) returns from the ADD's filing date ---
    filing_to_filing_return_pct: float | None
    filing_to_next_period_high_pct: float | None
    filing_to_next_period_low_pct: float | None
    # --- SPY-excess (position - SPY) ---
    excess_filing_to_filing_pct: float | None
    excess_next_period_high_pct: float | None
    excess_next_period_low_pct: float | None
    # --- SMH-excess (position - SMH) ---
    smh_excess_filing_to_filing_pct: float | None
    smh_excess_next_period_high_pct: float | None
    smh_excess_next_period_low_pct: float | None
    # --- derived lookahead / hold state ---
    followed_by_exit: bool
    followed_by_another_add: bool
    still_held: bool  # per-CHAIN: chain's last entry at latest_period and non-EXIT (SD-V2-1)
    priced: bool  # from the ADD's own ReturnRecord
    # --- audit tail ---
    filing_date: date  # change.filing_date (the anchor)


@dataclass(frozen=True, kw_only=True)
class ConvictionAddTypeStats:
    """Sub-stats for one add-type cohort (adding-to-winners OR averaging-down)."""

    count: int  # cohort size (>= 0); ALWAYS an int
    win_rate_pct: float | None  # over priced cohort members; None if none priced
    avg_return_pct: float | None  # mean filing_to_filing over priced cohort; None if empty
    avg_next_period_high_pct: float | None  # mean f2h over priced cohort; None if empty

    def to_dict(self) -> dict[str, object]:
        """Serialize the cohort sub-object keyed by the CONVICTION_SUBKEY_* constants."""
        return {
            constants.CONVICTION_SUBKEY_COUNT: self.count,
            constants.CONVICTION_SUBKEY_WIN_RATE_PCT: self.win_rate_pct,
            constants.CONVICTION_SUBKEY_AVG_RETURN_PCT: self.avg_return_pct,
            constants.CONVICTION_SUBKEY_AVG_NEXT_PERIOD_HIGH_PCT: self.avg_next_period_high_pct,
        }


@dataclass(frozen=True, kw_only=True)
class ConvictionAddsSummary:
    """Summary statistics. ALL rates None on an empty (sub-)population; counts are ints."""

    total_adds: int
    priced_adds: int
    win_rate_pct: float | None
    avg_winner_return_pct: float | None
    avg_loser_return_pct: float | None
    avg_weight_delta_pct: float | None  # mean over ALL adds; None only if zero adds
    adding_to_winners: ConvictionAddTypeStats
    averaging_down: ConvictionAddTypeStats
    pct_followed_by_exit: float | None
    pct_followed_by_another_add: float | None
    median_quarters_held_before_add: float | None
    pct_first_add: float | None
    notes: str

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-ready dict keyed by the CONVICTION_KEY_* constants."""
        return {
            constants.CONVICTION_KEY_TOTAL_ADDS: self.total_adds,
            constants.CONVICTION_KEY_PRICED_ADDS: self.priced_adds,
            constants.CONVICTION_KEY_WIN_RATE_PCT: self.win_rate_pct,
            constants.CONVICTION_KEY_AVG_WINNER: self.avg_winner_return_pct,
            constants.CONVICTION_KEY_AVG_LOSER: self.avg_loser_return_pct,
            constants.CONVICTION_KEY_AVG_WEIGHT_DELTA: self.avg_weight_delta_pct,
            constants.CONVICTION_KEY_ADDING_TO_WINNERS: self.adding_to_winners.to_dict(),
            constants.CONVICTION_KEY_AVERAGING_DOWN: self.averaging_down.to_dict(),
            constants.CONVICTION_KEY_PCT_FOLLOWED_BY_EXIT: self.pct_followed_by_exit,
            constants.CONVICTION_KEY_PCT_FOLLOWED_BY_ANOTHER_ADD: self.pct_followed_by_another_add,
            constants.CONVICTION_KEY_MEDIAN_QUARTERS_HELD_BEFORE_ADD: (
                self.median_quarters_held_before_add
            ),
            constants.CONVICTION_KEY_PCT_FIRST_ADD: self.pct_first_add,
            constants.CONVICTION_KEY_NOTES: self.notes,
        }


@dataclass(frozen=True, kw_only=True)
class ConvictionAddsView:
    cik: str
    slug: str
    rows: tuple[ConvictionAddRow, ...]  # sorted weight_delta DESC, quarter DESC, cusip/sec_type
    summary: ConvictionAddsSummary


def _build_conviction_row(
    change: PositionChange,
    *,
    idx: int,
    chain: list[PositionChange],
    add_ret: ReturnRecord | None,
    pos: PositionRecord | None,
    ret_by_key: dict[tuple[str, str, date, ChangeType], ReturnRecord],
    latest_period: date | None,
) -> ConvictionAddRow:
    cusip = change.cusip
    security_type = change.security_type
    is_option = _is_option(security_type)

    ticker_display = _ticker_display(
        change.ticker, pos.ticker if pos is not None else None, cusip
    )
    company = (_nonblank(pos.company_name) if pos is not None else None) or ticker_display

    # --- weights (ACTIVE_ADD invariant: prior/current weight + weight_delta_bps non-None) ---
    weight_before = change.prior_weight_pct
    weight_after = change.current_weight_pct
    weight_delta_bps = change.weight_delta_bps
    assert weight_before is not None  # ACTIVE_ADD invariant
    assert weight_after is not None  # ACTIVE_ADD invariant
    assert weight_delta_bps is not None  # ACTIVE_ADD invariant
    weight_delta_pct = weight_delta_bps / constants.PCT_TO_BPS

    # --- per-cycle slice (single backward pass from the ADD) ---
    cycle_new_idx: int | None = None
    cycle_first_idx = idx
    for j in range(idx, -1, -1):
        cj = chain[j]
        if j != idx and cj.change_type == ChangeType.EXIT:
            break  # run ended; cycle_first_idx already points one past the EXIT
        cycle_first_idx = j  # extend the run downward
        if cj.change_type == ChangeType.NEW:
            cycle_new_idx = j
            break  # NEW is the cycle floor

    original_entry_quarter = (
        chain[cycle_new_idx].period if cycle_new_idx is not None else None
    )

    # --- nth_add (1-based; ACTIVE_ADDs in this cycle at or before the ADD) ---
    nth_add = sum(
        1
        for k in range(cycle_first_idx, idx + 1)
        if chain[k].change_type == ChangeType.ACTIVE_ADD
    )

    # --- quarters_held_before_add (on-book cycle entries strictly before the ADD) ---
    quarters_held_before_add = sum(
        1
        for k in range(cycle_first_idx, idx)
        if chain[k].change_type != ChangeType.EXIT
    )

    # --- prior_quarter_return_pct + add_type ---
    prior_change: PositionChange | None = None
    if idx - 1 >= 0 and chain[idx - 1].period == change.prior_period:
        prior_change = chain[idx - 1]
    prior_quarter_return_pct: float | None = None
    if prior_change is not None:
        prior_ret = ret_by_key.get(
            (
                prior_change.cusip,
                prior_change.security_type,
                prior_change.filing_date,
                prior_change.change_type,
            )
        )
        if prior_ret is not None and prior_ret.priced:
            prior_quarter_return_pct = prior_ret.filing_to_filing_return_pct

    add_type: str | None
    if prior_quarter_return_pct is None:
        add_type = None
    elif prior_quarter_return_pct > 0:
        add_type = constants.ADD_TYPE_WINNER
    else:  # <= 0
        add_type = constants.ADD_TYPE_AVERAGING_DOWN

    # --- cumulative_return_since_entry_pct (entry-price -> add-price) ---
    entry_change = chain[cycle_first_idx]
    entry_ret = ret_by_key.get(
        (
            entry_change.cusip,
            entry_change.security_type,
            entry_change.filing_date,
            entry_change.change_type,
        )
    )
    cumulative_return_since_entry_pct: float | None = None
    if (
        add_ret is not None
        and add_ret.priced
        and add_ret.price_on_filing_date is not None
        and entry_ret is not None
        and entry_ret.priced
        and entry_ret.price_on_filing_date is not None
    ):
        cumulative_return_since_entry_pct = (
            add_ret.price_on_filing_date / entry_ret.price_on_filing_date - 1.0
        ) * 100.0

    # --- forward returns + excess (from the ADD's own ReturnRecord) ---
    priced = add_ret is not None and add_ret.priced
    if add_ret is not None:
        f2f = add_ret.filing_to_filing_return_pct
        f2h = add_ret.filing_to_next_period_high_pct
        f2l = add_ret.filing_to_next_period_low_pct
        spy_f2f = add_ret.spy_filing_to_filing_return_pct
        spy_h = add_ret.spy_next_period_high_pct
        spy_l = add_ret.spy_next_period_low_pct
        smh_f2f = add_ret.smh_filing_to_filing_return_pct
        smh_h = add_ret.smh_next_period_high_pct
        smh_l = add_ret.smh_next_period_low_pct
    else:
        f2f = f2h = f2l = None
        spy_f2f = spy_h = spy_l = None
        smh_f2f = smh_h = smh_l = None

    # --- lookahead: followed_by_exit / followed_by_another_add (next chain entry) ---
    followed_by_exit = False
    followed_by_another_add = False
    if idx + 1 < len(chain):
        nxt = chain[idx + 1]
        if nxt.change_type == ChangeType.EXIT:
            followed_by_exit = True
        elif nxt.change_type == ChangeType.ACTIVE_ADD:
            followed_by_another_add = True

    # --- still_held: per-CHAIN (security-level), SD-V2-1 ---
    still_held = (
        latest_period is not None
        and chain[-1].period == latest_period
        and chain[-1].change_type != ChangeType.EXIT
    )

    return ConvictionAddRow(
        quarter=change.period,
        ticker_display=ticker_display,
        company=company,
        cusip=cusip,
        security_type=security_type,
        is_option=is_option,
        weight_before_pct=weight_before,
        weight_after_pct=weight_after,
        weight_delta_pct=weight_delta_pct,
        shares_delta_pct=change.shares_delta_pct,
        prior_quarter_return_pct=prior_quarter_return_pct,
        add_type=add_type,
        quarters_held_before_add=quarters_held_before_add,
        nth_add=nth_add,
        original_entry_quarter=original_entry_quarter,
        cumulative_return_since_entry_pct=cumulative_return_since_entry_pct,
        filing_to_filing_return_pct=f2f,
        filing_to_next_period_high_pct=f2h,
        filing_to_next_period_low_pct=f2l,
        excess_filing_to_filing_pct=_excess(f2f, spy_f2f),
        excess_next_period_high_pct=_excess(f2h, spy_h),
        excess_next_period_low_pct=_excess(f2l, spy_l),
        smh_excess_filing_to_filing_pct=_excess(f2f, smh_f2f),
        smh_excess_next_period_high_pct=_excess(f2h, smh_h),
        smh_excess_next_period_low_pct=_excess(f2l, smh_l),
        followed_by_exit=followed_by_exit,
        followed_by_another_add=followed_by_another_add,
        still_held=still_held,
        priced=priced,
        filing_date=change.filing_date,
    )


def _add_type_stats(cohort_rows: list[ConvictionAddRow]) -> ConvictionAddTypeStats:
    """Forward-return stats over one add-type cohort (count always int; rates None on empty)."""
    count = len(cohort_rows)
    priced_forward = [
        r.filing_to_filing_return_pct
        for r in cohort_rows
        if r.filing_to_filing_return_pct is not None
    ]
    if priced_forward:
        wins = sum(1 for v in priced_forward if v > 0)
        win_rate_pct: float | None = wins / len(priced_forward) * 100.0
    else:
        win_rate_pct = None
    avg_return_pct = _mean(priced_forward)
    highs = [
        r.filing_to_next_period_high_pct
        for r in cohort_rows
        if r.filing_to_next_period_high_pct is not None
    ]
    avg_next_period_high_pct = _mean(highs)
    return ConvictionAddTypeStats(
        count=count,
        win_rate_pct=win_rate_pct,
        avg_return_pct=avg_return_pct,
        avg_next_period_high_pct=avg_next_period_high_pct,
    )


def _build_conviction_summary(rows: tuple[ConvictionAddRow, ...]) -> ConvictionAddsSummary:
    total_adds = len(rows)
    priced_adds = sum(1 for r in rows if r.priced)

    # Win-rate population = adds with non-None filing_to_filing_return_pct.
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
    avg_winner = _mean([v for v in returns_pop if v > 0])
    avg_loser = _mean([v for v in returns_pop if v < 0])

    avg_weight_delta_pct = _mean([r.weight_delta_pct for r in rows])

    winners_cohort = [r for r in rows if r.add_type == constants.ADD_TYPE_WINNER]
    losers_cohort = [r for r in rows if r.add_type == constants.ADD_TYPE_AVERAGING_DOWN]
    adding_to_winners = _add_type_stats(winners_cohort)
    averaging_down = _add_type_stats(losers_cohort)

    if total_adds:
        exits = sum(1 for r in rows if r.followed_by_exit)
        pct_followed_by_exit: float | None = exits / total_adds * 100.0
        adds = sum(1 for r in rows if r.followed_by_another_add)
        pct_followed_by_another_add: float | None = adds / total_adds * 100.0
        firsts = sum(1 for r in rows if r.nth_add == 1)
        pct_first_add: float | None = firsts / total_adds * 100.0
    else:
        pct_followed_by_exit = None
        pct_followed_by_another_add = None
        pct_first_add = None

    median_quarters_held_before_add = _median(
        [float(r.quarters_held_before_add) for r in rows]
    )

    return ConvictionAddsSummary(
        total_adds=total_adds,
        priced_adds=priced_adds,
        win_rate_pct=win_rate_pct,
        avg_winner_return_pct=avg_winner,
        avg_loser_return_pct=avg_loser,
        avg_weight_delta_pct=avg_weight_delta_pct,
        adding_to_winners=adding_to_winners,
        averaging_down=averaging_down,
        pct_followed_by_exit=pct_followed_by_exit,
        pct_followed_by_another_add=pct_followed_by_another_add,
        median_quarters_held_before_add=median_quarters_held_before_add,
        pct_first_add=pct_first_add,
        notes=constants.CONVICTION_SUMMARY_NOTES,
    )


def build_conviction_adds_view(
    *,
    config: InvestorConfig,
    positions: list[PositionRecord],
    changes: list[PositionChange],
    returns: list[ReturnRecord],
) -> ConvictionAddsView:
    """Build View 2 (Conviction Tracker) from positions/changes/returns. Disk-free; may WARN.

    Emits one ConvictionAddRow per ACTIVE_ADD PositionChange (re-adds in different quarters are
    separate rows). For each ADD: locates its chain index by object identity, walks the per-cycle
    slice (NEW floor, EXIT terminator) for entry/hold context, joins the prior-period change's
    ReturnRecord for prior_quarter_return_pct/add_type, the cycle-entry record for
    cumulative_return_since_entry_pct, and the ADD's own record for forward/excess returns. Warns
    ONLY when the ADD's own ReturnRecord is missing. Rows sorted weight_delta_pct DESC, quarter
    DESC (tiebreak cusip asc, security_type asc). Raises DiscoveryError on any cik mismatch.
    """
    _validate_cik(config, positions, changes, returns)

    pos_by_key = _position_by_key(positions)
    ret_by_key = _return_by_key(returns)
    chains = _chain_by_key(changes)
    latest_period = max((c.period for c in changes), default=None)

    rows: list[ConvictionAddRow] = []
    for change in changes:
        if change.change_type != ChangeType.ACTIVE_ADD:
            continue
        chain = chains[(change.cusip, change.security_type)]
        idx = next(i for i, c in enumerate(chain) if c is change)
        add_ret = ret_by_key.get(
            (change.cusip, change.security_type, change.filing_date, ChangeType.ACTIVE_ADD)
        )
        if add_ret is None:
            logger.warning(
                "no ReturnRecord for ACTIVE_ADD %s/%s @ %s; treating as unpriced",
                change.cusip,
                change.security_type,
                change.filing_date,
            )
        pos = pos_by_key.get((change.cusip, change.security_type, change.period))
        rows.append(
            _build_conviction_row(
                change,
                idx=idx,
                chain=chain,
                add_ret=add_ret,
                pos=pos,
                ret_by_key=ret_by_key,
                latest_period=latest_period,
            )
        )

    rows.sort(
        key=lambda r: (
            -r.weight_delta_pct,
            -r.quarter.toordinal(),
            r.cusip,
            r.security_type,
        )
    )
    rows_tuple = tuple(rows)

    return ConvictionAddsView(
        cik=config.cik,
        slug=config.slug,
        rows=rows_tuple,
        summary=_build_conviction_summary(rows_tuple),
    )


# ======================================================================================
# View 3 — Position Lifecycle (one row per (cusip, security_type) per quarter held).
# PURE / DISK-FREE (no disk, network, or pandas; MAY log WARN). Reshapes changes+returns into
# entry->exit cycles. sector/industry come from a PRE-RESOLVED fundamentals map (the network
# fetch is a separate cacheable step — NOT embedded here). CSV-only (no summary). See plan.
# ======================================================================================


@dataclass(frozen=True, kw_only=True)
class PositionLifecycleRow:
    """One (cusip, security_type) in one quarter held, inside its entry->exit cycle."""

    cycle_id: str  # f"{entry_ticker}_{security_type}_{n}" (n increments per re-entry)
    ticker_display: str  # this row's ticker fallback chain; CSV header "ticker"
    company: str  # positions lookup; fallback ticker_display->cusip
    cusip: str
    security_type: str  # COMMON / PUT / CALL
    sector: str | None  # manual classification, else EODHD General.Sector ("ETF" for funds)
    industry: str | None  # manual classification, else EODHD General.Industry
    theme: str | None  # manual classification only (no EODHD equivalent); None if uncovered
    period: date  # quarter-end
    filing_date: date  # this quarter's 13F filing date (the anchor)
    change_type: str  # ChangeType.value (NEW / EXIT / ACTIVE_ADD / ... / HOLD)
    quarters_since_entry: int  # 0 at the cycle's entry quarter, +1 each subsequent quarter
    weight_pct: float | None  # current_weight_pct (None for EXIT)
    weight_delta_bps: float | None  # weight change from prior quarter, bps
    shares_delta_pct: float | None  # share-count change from prior quarter
    period_return_pct: float | None  # filing-date -> next filing-date return
    period_high_pct: float | None  # best price next period vs this filing date
    period_low_pct: float | None  # worst price next period vs this filing date
    cum_return_from_entry_pct: float | None  # entry-price -> this-quarter price; 0.0 at entry
    spy_period_return_pct: float | None  # SPY return over the same window
    excess_period_return_pct: float | None  # period_return - spy_period_return (both non-None)
    smh_period_return_pct: float | None  # SMH return over the same window
    excess_vs_smh_pct: float | None  # period_return - smh_period_return (both non-None)
    price_on_filing_date: float | None  # close on this filing date
    entry_price: float | None  # price_on_filing_date of the cycle's first record
    priced: bool  # whether returns could be computed for this quarter


@dataclass(frozen=True, kw_only=True)
class PositionLifecycleView:
    cik: str
    slug: str
    rows: tuple[PositionLifecycleRow, ...]  # sorted cycle_id ASC, quarters_since_entry ASC


def _return_by_period_key(
    returns: list[ReturnRecord],
) -> dict[tuple[str, str, date], ReturnRecord]:
    """{(cusip, security_type, period): ReturnRecord}. Unique per change (changes<->returns 1:1).

    Keyed on `period` (not filing_date+change_type) so a lifecycle row joins its return by the
    same total key the change is identified by. Keep-first + WARN on a duplicate key."""
    out: dict[tuple[str, str, date], ReturnRecord] = {}
    for rec in returns:
        key = (rec.cusip, rec.security_type, rec.period)
        if key in out:
            logger.warning(
                "duplicate ReturnRecord period-key %s; keeping first, ignoring later", key
            )
            continue
        out[key] = rec
    return out


def _lookup_sector_industry(
    ret: ReturnRecord | None,
    fundamentals: dict[str, FundamentalsEntry],
) -> tuple[str | None, str | None]:
    """(sector, industry) via the row's eodhd_symbol; (None, None) if unpriced/unmapped/uncached."""
    if ret is None or ret.eodhd_symbol is None:
        return None, None
    entry = fundamentals.get(ret.eodhd_symbol)
    if entry is None:
        return None, None
    return entry.sector, entry.industry


def _lookup_classification(
    ticker_display: str,
    classifications: dict[str, dict[str, str | None]],
    ret: ReturnRecord | None,
    fundamentals: dict[str, FundamentalsEntry],
) -> tuple[str | None, str | None, str | None]:
    """(sector, industry, theme) with the manual classifications file as the PRIMARY source.

    PRIMARY: the hand-maintained classifications map keyed by ticker — if the ticker is present,
    its sector/industry/theme win outright (the EODHD cache is NOT consulted, even for fields the
    manual entry left null). FALLBACK: the EODHD fundamentals cache (sector/industry only; theme
    has no EODHD equivalent so it stays None). Blank on all three if neither source covers it.
    """
    manual = classifications.get(ticker_display)
    if manual is not None:
        return (
            manual.get(constants.CLASSIFICATION_SECTOR_KEY),
            manual.get(constants.CLASSIFICATION_INDUSTRY_KEY),
            manual.get(constants.CLASSIFICATION_THEME_KEY),
        )
    sector, industry = _lookup_sector_industry(ret, fundamentals)
    return sector, industry, None


def _build_lifecycle_row(
    change: PositionChange,
    *,
    ret: ReturnRecord | None,
    pos: PositionRecord | None,
    fundamentals: dict[str, FundamentalsEntry],
    classifications: dict[str, dict[str, str | None]],
    cycle_id: str,
    quarters_since_entry: int,
    entry_price: float | None,
) -> PositionLifecycleRow:
    cusip = change.cusip
    security_type = change.security_type

    ticker_display = _ticker_display(
        change.ticker, pos.ticker if pos is not None else None, cusip
    )
    company = (_nonblank(pos.company_name) if pos is not None else None) or ticker_display
    sector, industry, theme = _lookup_classification(
        ticker_display, classifications, ret, fundamentals
    )

    priced = ret is not None and ret.priced
    if ret is not None:
        period_return = ret.filing_to_filing_return_pct
        period_high = ret.filing_to_next_period_high_pct
        period_low = ret.filing_to_next_period_low_pct
        spy_period = ret.spy_filing_to_filing_return_pct
        smh_period = ret.smh_filing_to_filing_return_pct
        price_on_filing_date = ret.price_on_filing_date
    else:
        period_return = period_high = period_low = None
        spy_period = None
        smh_period = None
        price_on_filing_date = None

    # cum_return_from_entry_pct: 0.0 at the entry quarter (spec); else entry-price -> this price.
    if quarters_since_entry == 0:
        cum_return_from_entry_pct: float | None = 0.0
    elif entry_price is not None and price_on_filing_date is not None:
        cum_return_from_entry_pct = (price_on_filing_date / entry_price - 1.0) * 100.0
    else:
        cum_return_from_entry_pct = None

    return PositionLifecycleRow(
        cycle_id=cycle_id,
        ticker_display=ticker_display,
        company=company,
        cusip=cusip,
        security_type=security_type,
        sector=sector,
        industry=industry,
        theme=theme,
        period=change.period,
        filing_date=change.filing_date,
        change_type=change.change_type.value,
        quarters_since_entry=quarters_since_entry,
        weight_pct=change.current_weight_pct,
        weight_delta_bps=change.weight_delta_bps,
        shares_delta_pct=change.shares_delta_pct,
        period_return_pct=period_return,
        period_high_pct=period_high,
        period_low_pct=period_low,
        cum_return_from_entry_pct=cum_return_from_entry_pct,
        spy_period_return_pct=spy_period,
        excess_period_return_pct=_excess(period_return, spy_period),
        smh_period_return_pct=smh_period,
        excess_vs_smh_pct=_excess(period_return, smh_period),
        price_on_filing_date=price_on_filing_date,
        entry_price=entry_price,
        priced=priced,
    )


def build_position_lifecycle_view(
    *,
    config: InvestorConfig,
    positions: list[PositionRecord],
    changes: list[PositionChange],
    returns: list[ReturnRecord],
    fundamentals: dict[str, FundamentalsEntry],
    classifications: dict[str, dict[str, str | None]] | None = None,
) -> PositionLifecycleView:
    """Build View 3 (Position Lifecycle) from positions/changes/returns + sector/industry sources.

    Disk-free; may WARN. Groups changes by (cusip, security_type) ascending by period, segments
    each group into entry->exit CYCLES, and emits one row per (cycle, quarter). A cycle starts at
    the group's first record (first appearance / pre-data) and at every NEW (re-entry); an EXIT
    closes the current cycle (the EXIT row belongs to it) and forces the next record to open a new
    cycle. cycle_id = f"{entry_ticker}_{security_type}_{n}" using the cycle entry record's ticker
    (CUSIP fallback). entry_price = the cycle's first record's price_on_filing_date.
    quarters_since_entry counts 0,1,2,... within the cycle. sector/industry/theme come from the
    manual `classifications` map (keyed by ticker) first, then the EODHD `fundamentals` cache as a
    fallback (sector/industry only). Rows sorted cycle_id ASC, quarters_since_entry ASC. Raises
    DiscoveryError on any cik mismatch with config.cik.
    """
    classifications = classifications if classifications is not None else {}
    _validate_cik(config, positions, changes, returns)

    pos_by_key = _position_by_key(positions)
    ret_by_period = _return_by_period_key(returns)
    chains = _chain_by_key(changes)  # grouped by (cusip, security_type), sorted by period

    rows: list[PositionLifecycleRow] = []
    for (cusip, security_type), chain in chains.items():
        cycle_seq = 0
        cycle_id = ""
        entry_price: float | None = None
        quarters_since_entry = 0
        prev_was_exit = False
        for i, change in enumerate(chain):
            ret = ret_by_period.get((cusip, security_type, change.period))
            starts_cycle = i == 0 or change.change_type == ChangeType.NEW or prev_was_exit
            if starts_cycle:
                cycle_seq += 1
                quarters_since_entry = 0
                entry_pos = pos_by_key.get((cusip, security_type, change.period))
                entry_ticker = _ticker_display(
                    change.ticker, entry_pos.ticker if entry_pos is not None else None, cusip
                )
                cycle_id = f"{entry_ticker}_{security_type}_{cycle_seq}"
                entry_price = (
                    ret.price_on_filing_date
                    if ret is not None and ret.price_on_filing_date is not None
                    else None
                )
            else:
                quarters_since_entry += 1
            pos = pos_by_key.get((cusip, security_type, change.period))
            rows.append(
                _build_lifecycle_row(
                    change,
                    ret=ret,
                    pos=pos,
                    fundamentals=fundamentals,
                    classifications=classifications,
                    cycle_id=cycle_id,
                    quarters_since_entry=quarters_since_entry,
                    entry_price=entry_price,
                )
            )
            prev_was_exit = change.change_type == ChangeType.EXIT

    rows.sort(key=lambda r: (r.cycle_id, r.quarters_since_entry))
    return PositionLifecycleView(
        cik=config.cik,
        slug=config.slug,
        rows=tuple(rows),
    )
