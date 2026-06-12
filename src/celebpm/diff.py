"""QoQ diff & change classification (spec §1.4). Disk-free / deterministic.

classify_change applies the spec §1.4 table IN ORDER; diff_quarters diffs one adjacent pair;
compute_changes orchestrates the multi-quarter timeline (the earliest quarter is a BASELINE and
emits NO change records). No disk, no network. See plan §4.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from celebpm import constants
from celebpm.errors import DiscoveryError
from celebpm.models import ChangeType, PositionChange, PositionRecord


def classify_change(
    *,
    shares_delta_pct: float | None,
    weight_delta_bps: float,
    value_delta_pct: float | None,
    security_type: str,
) -> tuple[ChangeType, bool]:
    """Return (change_type, split_suspected) for a MATCHED position (present both quarters).

    NEW/EXIT are decided by presence in diff_quarters, NOT here. This function only handles the
    matched case and applies the spec §1.4 table IN ORDER (ACTIVE_ADD, ACTIVE_TRIM, DRIFT_UP,
    DRIFT_DOWN, HOLD). split_suspected can be True ONLY when security_type == COMMON, and a
    suspected split SHORT-CIRCUITS to (HOLD, True) before the cascade.

    Trusts its validated inputs: called only by diff_quarters with finite, PositionRecord-derived
    values; does not re-validate finiteness or types.
    """
    # 1. Split detection FIRST (COMMON only), then SHORT-CIRCUIT to HOLD so the
    #    split_suspected ⇒ HOLD invariant is robust to any future threshold/band tuning.
    split_suspected = (
        security_type == constants.SECURITY_TYPE_COMMON
        and shares_delta_pct is not None
        and abs(shares_delta_pct - constants.SPLIT_SHARES_DELTA_PCT_CENTER)
        <= constants.SPLIT_SHARES_DELTA_PCT_TOLERANCE
        and value_delta_pct is not None
        and abs(value_delta_pct) <= constants.SPLIT_VALUE_DELTA_PCT_MAX_ABS
    )
    if split_suspected:
        return (ChangeType.HOLD, True)

    shares_thresh = constants.CHANGE_SHARES_DELTA_PCT_THRESHOLD
    weight_thresh = constants.CHANGE_WEIGHT_DELTA_BPS_THRESHOLD

    # 2. ACTIVE_ADD: STRICT > on both shares and weight.
    if (
        shares_delta_pct is not None
        and shares_delta_pct > shares_thresh
        and weight_delta_bps > weight_thresh
    ):
        return (ChangeType.ACTIVE_ADD, False)
    # 3. ACTIVE_TRIM: STRICT < on both.
    if (
        shares_delta_pct is not None
        and shares_delta_pct < -shares_thresh
        and weight_delta_bps < -weight_thresh
    ):
        return (ChangeType.ACTIVE_TRIM, False)
    # 4. DRIFT_UP: weight up beyond threshold, shares within the inclusive band (and not None).
    if (
        weight_delta_bps > weight_thresh
        and shares_delta_pct is not None
        and abs(shares_delta_pct) <= shares_thresh
    ):
        return (ChangeType.DRIFT_UP, False)
    # 5. DRIFT_DOWN.
    if (
        weight_delta_bps < -weight_thresh
        and shares_delta_pct is not None
        and abs(shares_delta_pct) <= shares_thresh
    ):
        return (ChangeType.DRIFT_DOWN, False)
    # 6. HOLD: everything else (incl. shares_delta_pct is None — share intent unprovable).
    return (ChangeType.HOLD, False)


def _compute_deltas(
    current: PositionRecord, prior: PositionRecord
) -> tuple[int, float | None, float, int, float | None]:
    """Return (shares_delta, shares_delta_pct, weight_delta_bps, value_delta, value_delta_pct).

    shares / value_reported / weight_pct_reported are NON-nullable on PositionRecord, so the
    subtractions never see None. Only the division denominators are guarded (prior == 0 -> None).
    """
    shares_delta = current.shares - prior.shares
    shares_delta_pct = (
        (shares_delta / prior.shares) * 100.0 if prior.shares != 0 else None
    )
    weight_delta_bps = (
        current.weight_pct_reported - prior.weight_pct_reported
    ) * constants.PCT_TO_BPS
    value_delta = current.value_reported - prior.value_reported
    value_delta_pct = (
        (value_delta / prior.value_reported) * 100.0
        if prior.value_reported != 0
        else None
    )
    return (shares_delta, shares_delta_pct, weight_delta_bps, value_delta, value_delta_pct)


def _side_anchor(
    positions: list[PositionRecord],
) -> tuple[str, date, date, dict[tuple[str, str], PositionRecord]]:
    """Validate one (non-empty) quarter side and return (cik, period, filing_date, key_map).

    Each side must contain a single cik, a single period, a single filing_date, and a single
    accession_number; (cusip, security_type) must be unique within the side. Any violation ->
    DiscoveryError.
    """
    ciks = {p.cik for p in positions}
    if len(ciks) != 1:
        raise DiscoveryError(f"a quarter side must have a single cik, got {sorted(ciks)}")
    periods = {p.period for p in positions}
    if len(periods) != 1:
        raise DiscoveryError(
            f"a quarter side must have a single period, got {sorted(periods)}"
        )
    filing_dates = {p.filing_date for p in positions}
    if len(filing_dates) != 1:
        raise DiscoveryError(
            f"a quarter side must have a single filing_date, got {sorted(filing_dates)}"
        )
    accessions = {p.accession_number for p in positions}
    if len(accessions) != 1:
        raise DiscoveryError(
            f"a quarter side must have a single accession_number, got {sorted(accessions)}"
        )
    key_map: dict[tuple[str, str], PositionRecord] = {}
    for p in positions:
        key = (p.cusip, p.security_type)
        if key in key_map:
            raise DiscoveryError(
                f"duplicate (cusip, security_type) {key} within a quarter side"
            )
        key_map[key] = p
    cik = next(iter(ciks))
    period = next(iter(periods))
    filing_date = next(iter(filing_dates))
    return (cik, period, filing_date, key_map)


def diff_quarters(
    prior_positions: list[PositionRecord],
    current_positions: list[PositionRecord],
) -> list[PositionChange]:
    """Diff two adjacent quarters. One PositionChange per (cusip, security_type) in the UNION.

    matched (in both) -> classify_change; only-current -> NEW; only-prior -> EXIT.
    BOTH sides MUST be non-empty (else DiscoveryError) -- emitted rows must carry a real
    prior_period/filing_date AND a real current period/filing_date. Each side must share one
    (period, filing_date, cik, accession_number); the two sides must share the SAME cik. Within
    a side, (cusip, security_type) MUST be unique. See plan §4c.
    """
    # 1. Empty-input cases all RAISE (symmetric fail-loud).
    if not prior_positions or not current_positions:
        raise DiscoveryError(
            "diff_quarters requires BOTH a non-empty prior and current quarter"
        )

    # 2/3. Per-side validation + anchors.
    prior_cik, prior_period, prior_filing_date, prior_map = _side_anchor(prior_positions)
    cur_cik, cur_period, cur_filing_date, current_map = _side_anchor(current_positions)
    if prior_cik != cur_cik:
        raise DiscoveryError(
            f"prior cik {prior_cik!r} != current cik {cur_cik!r}"
        )

    # 4. Union of keys in DETERMINISTIC sorted order.
    keys = sorted(set(prior_map) | set(current_map))

    changes: list[PositionChange] = []
    for key in keys:
        cusip, security_type = key
        prior = prior_map.get(key)
        current = current_map.get(key)
        if current is not None and prior is not None:
            # both present -> matched
            (
                shares_delta,
                shares_delta_pct,
                weight_delta_bps,
                value_delta,
                value_delta_pct,
            ) = _compute_deltas(current, prior)
            change_type, split_suspected = classify_change(
                shares_delta_pct=shares_delta_pct,
                weight_delta_bps=weight_delta_bps,
                value_delta_pct=value_delta_pct,
                security_type=security_type,
            )
            ticker = current.ticker if current.ticker is not None else prior.ticker
            changes.append(
                PositionChange(
                    cik=cur_cik,
                    period=cur_period,
                    filing_date=cur_filing_date,
                    prior_period=prior_period,
                    prior_filing_date=prior_filing_date,
                    cusip=cusip,
                    security_type=security_type,
                    ticker=ticker,
                    current_shares=current.shares,
                    current_value_reported=current.value_reported,
                    current_weight_pct=current.weight_pct_reported,
                    prior_shares=prior.shares,
                    prior_value_reported=prior.value_reported,
                    prior_weight_pct=prior.weight_pct_reported,
                    shares_delta=shares_delta,
                    shares_delta_pct=shares_delta_pct,
                    weight_delta_bps=weight_delta_bps,
                    value_delta=value_delta,
                    value_delta_pct=value_delta_pct,
                    change_type=change_type,
                    split_suspected=split_suspected,
                    corporate_action_note="",
                )
            )
        elif current is not None:
            # only current -> NEW (relative to the prior quarter where it was absent)
            changes.append(
                PositionChange(
                    cik=cur_cik,
                    period=cur_period,
                    filing_date=cur_filing_date,
                    prior_period=prior_period,
                    prior_filing_date=prior_filing_date,
                    cusip=cusip,
                    security_type=security_type,
                    ticker=current.ticker,
                    current_shares=current.shares,
                    current_value_reported=current.value_reported,
                    current_weight_pct=current.weight_pct_reported,
                    prior_shares=None,
                    prior_value_reported=None,
                    prior_weight_pct=None,
                    shares_delta=None,
                    shares_delta_pct=None,
                    weight_delta_bps=None,
                    value_delta=None,
                    value_delta_pct=None,
                    change_type=ChangeType.NEW,
                    split_suspected=False,
                    corporate_action_note="",
                )
            )
        else:
            # only prior -> EXIT (anchored at the CURRENT/observing quarter)
            assert prior is not None  # mypy: union guarantees prior present here
            changes.append(
                PositionChange(
                    cik=prior.cik,
                    period=cur_period,
                    filing_date=cur_filing_date,
                    prior_period=prior_period,
                    prior_filing_date=prior_filing_date,
                    cusip=cusip,
                    security_type=security_type,
                    ticker=prior.ticker,
                    current_shares=None,
                    current_value_reported=None,
                    current_weight_pct=None,
                    prior_shares=prior.shares,
                    prior_value_reported=prior.value_reported,
                    prior_weight_pct=prior.weight_pct_reported,
                    shares_delta=None,
                    shares_delta_pct=None,
                    weight_delta_bps=None,
                    value_delta=None,
                    value_delta_pct=None,
                    change_type=ChangeType.EXIT,
                    split_suspected=False,
                    corporate_action_note="",
                )
            )
    return changes


def _validate_period_group(period: date, positions: list[PositionRecord]) -> None:
    """Validate one grouped period's row list: unique (cusip, security_type), single
    filing_date, single accession_number. Any violation -> DiscoveryError.
    """
    seen: set[tuple[str, str]] = set()
    for p in positions:
        key = (p.cusip, p.security_type)
        if key in seen:
            raise DiscoveryError(
                f"duplicate (cusip, security_type) {key} within period {period}"
            )
        seen.add(key)
    filing_dates = {p.filing_date for p in positions}
    if len(filing_dates) != 1:
        raise DiscoveryError(
            f"period {period} spans multiple filing_dates: {sorted(filing_dates)}"
        )
    accessions = {p.accession_number for p in positions}
    if len(accessions) != 1:
        raise DiscoveryError(
            f"period {period} spans multiple accession_numbers: {sorted(accessions)}"
        )


def compute_changes(all_positions: list[PositionRecord]) -> list[PositionChange]:
    """Group an investor's positions into per-period sets, order periods ASCENDING, diff each
    adjacent pair Q[i-1]->Q[i] (i >= 1). The FIRST (earliest) period is the BASELINE and emits
    NO change records. Returns all PositionChanges across all transitions, deterministically
    ordered by (period, cusip, security_type). See plan §4d.
    """
    # 1. Empty input.
    if not all_positions:
        return []

    # 2. Single-cik assertion + group by period.
    ciks = {p.cik for p in all_positions}
    if len(ciks) != 1:
        raise DiscoveryError(
            f"compute_changes requires a single cik (per-investor data), got {sorted(ciks)}"
        )
    grouped: dict[date, list[PositionRecord]] = defaultdict(list)
    for p in all_positions:
        grouped[p.period].append(p)

    # 3. Validate EVERY grouped period BEFORE the <2-periods short-circuit (a corrupt
    #    baseline-only investor must fail loud, not silently return []).
    for period, rows in grouped.items():
        _validate_period_group(period, rows)

    # 4. Order periods ascending.
    periods = sorted(grouped)

    # 5. Fewer than 2 periods -> baseline only, no transitions.
    if len(periods) < 2:
        return []

    # 6. Diff each adjacent pair.
    changes: list[PositionChange] = []
    for i in range(1, len(periods)):
        changes.extend(diff_quarters(grouped[periods[i - 1]], grouped[periods[i]]))

    # 7. Final deterministic sort.
    changes.sort(key=lambda c: (c.period, c.cusip, c.security_type))
    return changes
