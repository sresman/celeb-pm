"""Filing-date-anchored forward-returns engine. DISK-FREE; takes a PriceProvider.

compute_returns produces one ReturnRecord per PositionChange. It passes RAW change.ticker values
to the provider (which OWNS normalization, overrides, the cache, and `today`); it never imports
symbol_map, never loads overrides, and never touches disk. It imports only {price_types, models,
constants, errors} (errors for the SPY raise).

Cross-cutting rules: filing date is the anchor for FORWARD returns; the entry window is the
CALENDAR QUARTER of `period`; equity and options are chained SEPARATELY; options are priced on the
UNDERLYING (directional signal, never option P&L); returns come from EODHD prices ONLY. SPY is the
PRIMARY benchmark: the engine passes the literal SPY_BENCHMARK_SYMBOL as the ticker (no sentinel).
A missing SPY benchmark (has_series_data False or a transport error in the preflight) is fatal.
SMH (VanEck Semiconductor ETF) is a SECONDARY benchmark computed the same way per-window, but with
NO fatal preflight — a fully-absent SMH simply yields all-None SMH trios. A NON-benchmark symbol's
transport EodhdError is isolated per-record (priced=False + log + continue).
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import date

from celebpm import constants
from celebpm.errors import DiscoveryError, EodhdError
from celebpm.models import ChangeType, PositionChange, ReturnRecord
from celebpm.price_types import PriceProvider, WindowExtrema

logger = logging.getLogger(__name__)

_HELD_TYPES = frozenset(
    {
        ChangeType.NEW,
        ChangeType.ACTIVE_ADD,
        ChangeType.ACTIVE_TRIM,
        ChangeType.DRIFT_UP,
        ChangeType.DRIFT_DOWN,
        ChangeType.HOLD,
    }
)


def quarter_start(period: date) -> date:
    """Calendar-quarter start for any date: Q1->Jan1, Q2->Apr1, Q3->Jul1, Q4->Oct1."""
    month = ((period.month - 1) // 3) * 3 + 1
    return date(period.year, month, 1)


def _pct(from_price: float, to_price: float) -> float:
    """(to/from - 1) * 100. The caller guarantees from_price > 0; a 0 numerator is allowed."""
    return (to_price / from_price - 1.0) * 100.0


def _next_filing_date(filing_date: date, timeline: list[date], today: date) -> date:
    """Smallest distinct filing date strictly > filing_date, else `today` (most-recent filing)."""
    later = [d for d in timeline if d > filing_date]
    return min(later) if later else today


def compute_returns(
    changes: list[PositionChange],
    provider: PriceProvider,
) -> list[ReturnRecord]:
    """Build one ReturnRecord per PositionChange, anchored on its filing_date.

    Single-CIK input (mixed -> DiscoveryError). Reads provider.today (no today param). Empty
    input -> []. Raises EodhdError if the SPY benchmark has no series data at all (preflight).
    """
    if not changes:
        return []

    ciks = {c.cik for c in changes}
    if len(ciks) > 1:
        raise DiscoveryError(f"compute_returns input spans multiple ciks: {sorted(ciks)}")

    today = provider.today

    # SPY preflight — the ONLY fatal symbol failure. A transport EodhdError here ALSO propagates.
    if not provider.has_series_data(constants.SPY_BENCHMARK_SYMBOL):
        raise EodhdError(
            f"required SPY benchmark {constants.SPY_BENCHMARK_SYMBOL!r} has no usable series data"
        )

    timeline = sorted({c.filing_date for c in changes})

    # Pre-compute the cumulative trio per chain, keyed by the (id of the) last-held change.
    cumulative_by_change = _compute_cumulatives(changes, provider, today)

    records: list[ReturnRecord] = []
    for change in changes:
        next_filing = _next_filing_date(change.filing_date, timeline, today)
        cumulative = cumulative_by_change.get(id(change))
        try:
            records.append(_compute_one(change, provider, next_filing, today, cumulative))
        except EodhdError as exc:
            # Per-symbol transport-error isolation (NON-SPY): priced=False + loud log + continue.
            logger.error(
                "EODHD transport error pricing %s (cusip %s); marking record unpriced: %s",
                change.ticker,
                change.cusip,
                exc,
            )
            records.append(_unpriced_record(change, next_filing))
    return records


def _is_option(security_type: str) -> bool:
    return security_type in {constants.SECURITY_TYPE_PUT, constants.SECURITY_TYPE_CALL}


def _unpriced_record(change: PositionChange, next_filing: date) -> ReturnRecord:
    """A fully-null priced=False record (identity/audit only). eodhd_symbol left None: a transport
    failure means we cannot trust resolution either, and the audit value is best-effort."""
    return ReturnRecord(
        cik=change.cik,
        cusip=change.cusip,
        ticker=change.ticker,
        eodhd_symbol=None,
        security_type=change.security_type,
        change_type=change.change_type,
        period=change.period,
        filing_date=change.filing_date,
        next_filing_date=next_filing,
        priced=False,
        is_underlying_price=_is_option(change.security_type),
        price_on_filing_date=None,
        price_on_next_filing_date=None,
        next_period_high=None,
        next_period_low=None,
        next_period_high_date=None,
        next_period_low_date=None,
        filing_to_filing_return_pct=None,
        filing_to_next_period_high_pct=None,
        filing_to_next_period_low_pct=None,
        entry_quarter_high=None,
        entry_quarter_low=None,
        best_case_entry_price=None,
        worst_case_entry_price=None,
        best_case_entry_return_pct=None,
        worst_case_entry_return_pct=None,
        cumulative_return_pct=None,
        cumulative_from_filing_date=None,
        cumulative_to_filing_date=None,
        spy_filing_to_filing_return_pct=None,
        spy_next_period_high_pct=None,
        spy_next_period_low_pct=None,
        smh_filing_to_filing_return_pct=None,
        smh_next_period_high_pct=None,
        smh_next_period_low_pct=None,
    )


def _compute_one(
    change: PositionChange,
    provider: PriceProvider,
    next_filing: date,
    today: date,
    cumulative: tuple[float | None, date | None, date | None] | None,
) -> ReturnRecord:
    """Compute one record. May raise EodhdError (caught by the loop for per-symbol isolation)."""
    eodhd_symbol = provider.resolve_symbol(change.ticker)
    is_underlying = _is_option(change.security_type)

    # EXIT: no forward window -> priced=False row (cumulative is placed on the preceding held row).
    if change.change_type == ChangeType.EXIT:
        rec = _unpriced_record(change, next_filing)
        # restore the resolved symbol for audit (resolution succeeded for an EXIT row).
        return _with_symbol(rec, eodhd_symbol)

    filing_date = change.filing_date
    price_filing = provider.price_asof(change.ticker, filing_date)
    price_next = provider.price_asof(change.ticker, next_filing)

    # Unpriced triggers (extrema is NOT a trigger): symbol None, denominator None/<=0, next None.
    if (
        eodhd_symbol is None
        or price_filing is None
        or price_filing <= 0
        or price_next is None
    ):
        return _with_symbol(_unpriced_record(change, next_filing), eodhd_symbol)

    extrema = provider.window_extrema(change.ticker, filing_date, next_filing)
    if extrema is not None:
        np_high, np_high_date = extrema.high, extrema.high_date
        np_low, np_low_date = extrema.low, extrema.low_date
    else:
        # No in-range bars (e.g. delisting before the window) but both endpoints carried forward.
        logger.warning(
            "no in-range bars for %s [%s, %s]; deriving next-period extrema from endpoints",
            eodhd_symbol,
            filing_date,
            next_filing,
        )
        if price_filing >= price_next:
            np_high, np_high_date = price_filing, filing_date
            np_low, np_low_date = price_next, next_filing
        else:
            np_high, np_high_date = price_next, next_filing
            np_low, np_low_date = price_filing, filing_date

    f2f = _pct(price_filing, price_next)
    f2high = _pct(price_filing, np_high)
    f2low = _pct(price_filing, np_low)

    # Entry estimate (NEW only) over the calendar quarter of `period`.
    (
        entry_high,
        entry_low,
        best_price,
        worst_price,
        best_ret,
        worst_ret,
    ) = _entry_estimate(change, provider, price_next)

    # SPY + SMH over the same forward window (same coverage + denominator-> 0 formula).
    spy_f2f, spy_high, spy_low = _benchmark_window(
        provider, constants.SPY_BENCHMARK_SYMBOL, filing_date, next_filing
    )
    smh_f2f, smh_high, smh_low = _benchmark_window(
        provider, constants.SMH_BENCHMARK_SYMBOL, filing_date, next_filing
    )

    cum_pct, cum_from, cum_to = (cumulative if cumulative is not None else (None, None, None))

    return ReturnRecord(
        cik=change.cik,
        cusip=change.cusip,
        ticker=change.ticker,
        eodhd_symbol=eodhd_symbol,
        security_type=change.security_type,
        change_type=change.change_type,
        period=change.period,
        filing_date=filing_date,
        next_filing_date=next_filing,
        priced=True,
        is_underlying_price=is_underlying,
        price_on_filing_date=price_filing,
        price_on_next_filing_date=price_next,
        next_period_high=np_high,
        next_period_low=np_low,
        next_period_high_date=np_high_date,
        next_period_low_date=np_low_date,
        filing_to_filing_return_pct=f2f,
        filing_to_next_period_high_pct=f2high,
        filing_to_next_period_low_pct=f2low,
        entry_quarter_high=entry_high,
        entry_quarter_low=entry_low,
        best_case_entry_price=best_price,
        worst_case_entry_price=worst_price,
        best_case_entry_return_pct=best_ret,
        worst_case_entry_return_pct=worst_ret,
        cumulative_return_pct=cum_pct,
        cumulative_from_filing_date=cum_from,
        cumulative_to_filing_date=cum_to,
        spy_filing_to_filing_return_pct=spy_f2f,
        spy_next_period_high_pct=spy_high,
        spy_next_period_low_pct=spy_low,
        smh_filing_to_filing_return_pct=smh_f2f,
        smh_next_period_high_pct=smh_high,
        smh_next_period_low_pct=smh_low,
    )


def _with_symbol(rec: ReturnRecord, eodhd_symbol: str | None) -> ReturnRecord:
    """Return a copy of an unpriced record with eodhd_symbol set (audit field is always allowed)."""
    return dataclasses.replace(rec, eodhd_symbol=eodhd_symbol)


def _entry_estimate(
    change: PositionChange,
    provider: PriceProvider,
    price_next: float,
) -> tuple[
    float | None, float | None, float | None, float | None, float | None, float | None
]:
    """Entry estimate for a NEW change over [quarter_start(period), period]. Non-NEW or an empty
    entry window or an entry-low denominator <= 0 -> all six None (+ WARN for the priced-NEW case).
    """
    none6: tuple[None, None, None, None, None, None] = (None, None, None, None, None, None)
    if change.change_type != ChangeType.NEW:
        return none6
    q_start = quarter_start(change.period)
    entry_extrema = provider.window_extrema(change.ticker, q_start, change.period)
    if entry_extrema is None or entry_extrema.low <= 0:
        logger.warning(
            "NEW %s: empty/unusable entry quarter [%s, %s]; entry fields None",
            change.ticker,
            q_start,
            change.period,
        )
        return none6
    entry_high = entry_extrema.high
    entry_low = entry_extrema.low
    best_price = entry_low  # bought at the quarter low
    worst_price = entry_high  # bought at the quarter high
    best_ret = _pct(best_price, price_next)
    worst_ret = _pct(worst_price, price_next)
    return entry_high, entry_low, best_price, worst_price, best_ret, worst_ret


def _benchmark_window(
    provider: PriceProvider, symbol: str, filing_date: date, next_filing: date
) -> tuple[float | None, float | None, float | None]:
    """Benchmark return trio for `symbol` over [filing_date, next_filing]. A per-window gap
    (endpoint None / filing denominator <= 0) -> all-None + WARN. Mirrors the position path
    including endpoint-derived extrema. Used for both SPY (after its fatal preflight) and SMH
    (no preflight: a fully-absent SMH simply yields all-None windows — task spec)."""
    bench_filing = provider.price_asof(symbol, filing_date)
    bench_next = provider.price_asof(symbol, next_filing)
    if bench_filing is None or bench_filing <= 0 or bench_next is None:
        logger.warning(
            "%s per-window gap over [%s, %s]; benchmark trio N/A for this window",
            symbol,
            filing_date,
            next_filing,
        )
        return None, None, None
    extrema = provider.window_extrema(symbol, filing_date, next_filing)
    if extrema is not None:
        bench_high_price, bench_low_price = extrema.high, extrema.low
    else:
        bench_high_price = max(bench_filing, bench_next)
        bench_low_price = min(bench_filing, bench_next)
    return (
        _pct(bench_filing, bench_next),
        _pct(bench_filing, bench_high_price),
        _pct(bench_filing, bench_low_price),
    )


def _compute_cumulatives(
    changes: list[PositionChange],
    provider: PriceProvider,
    today: date,
) -> dict[int, tuple[float | None, date | None, date | None]]:
    """Pre-compute the cumulative trio for each chain, returning a map keyed by id() of the
    LAST-HELD change in each chain. Chains are runs of consecutive non-EXIT changes for the same
    (cusip, security_type) ordered by filing_date; an EXIT TERMINATES a chain and supplies the END
    date; a re-entry after an EXIT starts a NEW chain. Equity and options are chained SEPARATELY
    (the key includes security_type)."""
    out: dict[int, tuple[float | None, date | None, date | None]] = {}

    # group by (cusip, security_type), ordered by filing_date.
    groups: dict[tuple[str, str], list[PositionChange]] = {}
    for c in sorted(changes, key=lambda c: c.filing_date):
        groups.setdefault((c.cusip, c.security_type), []).append(c)

    for ordered in groups.values():
        chain: list[PositionChange] = []
        for c in ordered:
            if c.change_type == ChangeType.EXIT:
                if chain:
                    _emit_cumulative(chain, exit_change=c, provider=provider, today=today, out=out)
                    chain = []
                # an EXIT with no preceding held chain (e.g. re-entry boundary) is just ignored.
            else:
                chain.append(c)
        if chain:
            _emit_cumulative(chain, exit_change=None, provider=provider, today=today, out=out)
    return out


def _emit_cumulative(
    chain: list[PositionChange],
    *,
    exit_change: PositionChange | None,
    provider: PriceProvider,
    today: date,
    out: dict[int, tuple[float | None, date | None, date | None]],
) -> None:
    """Compute and place the cumulative trio on the LAST-HELD row of `chain`. End = the
    terminating EXIT's filing_date if present, else today. Uses the LAST-held row's ticker for
    BOTH endpoints. Endpoint unavailable (None / first <= 0) -> trio None on the last-held row."""
    first = chain[0].filing_date
    last_held = chain[-1]
    end = exit_change.filing_date if exit_change is not None else today
    last_ticker = last_held.ticker

    try:
        first_price = provider.price_asof(last_ticker, first)
        end_price = provider.price_asof(last_ticker, end)
    except EodhdError:
        # a transport failure here -> no cumulative (the per-record loop will also mark unpriced).
        out[id(last_held)] = (None, None, None)
        return

    if first_price is None or first_price <= 0 or end_price is None:
        out[id(last_held)] = (None, None, None)
        return
    out[id(last_held)] = (_pct(first_price, end_price), first, end)
