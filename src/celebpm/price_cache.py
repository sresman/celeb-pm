"""Global per-symbol price cache + the cache-first CachingPriceProvider.

Scope: GLOBAL, one file per symbol (data/price_cache/<symbol>.json). A symbol's EOD series is
investor-agnostic (AAPL.US closes are identical for everyone; SPY fetched once, reused). Per-symbol
files give atomic per-symbol writes, no whole-file rewrite, and trivial path-safety (the symbol is
validated against EODHD_SYMBOL_PATTERN and becomes the filename).

The cache FILE wraps the SymbolSeries with a schema_version: {"schema_version": N, "series": {...}}.
read_price_cache treats ANY corrupt / version-mismatch / symbol-mismatch / unparseable cache as a
MISS (None) and NEVER raises (the cache is regenerable). The provider owns the hard-floor per-call
refetch policy, symbol normalization (overrides loaded once), the coverage-threshold price-field
selection, trading-day alignment, and `today`.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from celebpm import constants
from celebpm.errors import EodhdError
from celebpm.price_types import PriceClient, SymbolSeries, WindowExtrema
from celebpm.storage import _assert_under_root, _atomic_write_json, _resolved_root
from celebpm.symbol_map import load_symbol_overrides, to_eodhd_symbol

logger = logging.getLogger(__name__)


# --- cache I/O (reuses storage helpers) ---


def read_price_cache(
    symbol: str, data_root: Path | str | None = None
) -> SymbolSeries | None:
    """Read <data_root>/price_cache/<symbol>.json -> SymbolSeries, or None on ANY miss.

    Best-effort: NEVER raises. Returns None (a cache MISS -> refetch) when the file is missing,
    unreadable/not-JSON, not a dict, has a missing/mismatched schema_version, has a
    missing/non-dict `series`, the inner `series.symbol` != the requested symbol (checked on the
    RAW dict BEFORE from_dict), or from_dict raises (bad fetched_at / dup / non-ascending / any
    shape violation). A bad symbol (fails EODHD_SYMBOL_PATTERN) on READ -> None (never raise).
    """
    if constants.EODHD_SYMBOL_PATTERN.fullmatch(symbol) is None:
        logger.warning("read_price_cache: invalid symbol %r; treating as miss", symbol)
        return None
    root = _resolved_root(data_root)
    target_file = constants.price_cache_path(symbol, data_root).resolve()
    try:
        _assert_under_root(root, target_file)
    except Exception:
        # path escape -> treat as a miss (read is best-effort; never raise from a read).
        logger.warning("read_price_cache: %r resolves outside data_root; miss", symbol)
        return None
    if not target_file.exists():
        return None
    try:
        text = target_file.read_text(encoding="utf-8")
        wrapper: object = json.loads(text)
    except (OSError, ValueError) as exc:
        logger.warning("read_price_cache: unreadable cache for %r: %s; miss", symbol, exc)
        return None
    if not isinstance(wrapper, dict):
        return None
    version = wrapper.get(constants.PRICE_CACHE_WRAPPER_SCHEMA_KEY)
    if version != constants.PRICE_CACHE_SCHEMA_VERSION:
        logger.info(
            "read_price_cache: %r schema_version %r != %d; miss (forced refetch)",
            symbol,
            version,
            constants.PRICE_CACHE_SCHEMA_VERSION,
        )
        return None
    series_raw = wrapper.get(constants.PRICE_CACHE_WRAPPER_SERIES_KEY)
    if not isinstance(series_raw, dict):
        return None
    # symbol compared on the RAW dict BEFORE from_dict (independent of from_dict's checks).
    raw_symbol = series_raw.get("symbol")
    if not isinstance(raw_symbol, str) or raw_symbol != symbol:
        logger.warning(
            "read_price_cache: cached symbol %r != requested %r; miss",
            raw_symbol,
            symbol,
        )
        return None
    try:
        return SymbolSeries.from_dict(series_raw)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("read_price_cache: %r from_dict failed: %s; miss", symbol, exc)
        return None


def write_price_cache(
    series: SymbolSeries, data_root: Path | str | None = None
) -> Path:
    """Write the WRAPPER {"schema_version": N, "series": series.to_dict()} atomically.

    A bad symbol (fails EODHD_SYMBOL_PATTERN) on WRITE -> EodhdError (a producer-controlled write
    of an invalid symbol is a real bug). PATH-SAFE.
    """
    symbol = series.symbol
    if constants.EODHD_SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise EodhdError(f"refusing to write cache for invalid symbol: {symbol!r}")
    root = _resolved_root(data_root)
    target_file = constants.price_cache_path(symbol, data_root).resolve()
    _assert_under_root(root, target_file)
    target_dir = target_file.parent
    wrapper = {
        constants.PRICE_CACHE_WRAPPER_SCHEMA_KEY: constants.PRICE_CACHE_SCHEMA_VERSION,
        constants.PRICE_CACHE_WRAPPER_SERIES_KEY: series.to_dict(),
    }
    text = json.dumps(wrapper, indent=2)
    _atomic_write_json(
        target_dir, target_file, text, prefix=constants.PRICE_CACHE_TMP_PREFIX
    )
    logger.info("wrote price cache for %s (%d bars) to %s", symbol, len(series.bars), target_file)
    return target_file


class CachingPriceProvider:
    """Cache-first PriceProvider. Takes RAW tickers; OWNS normalization (to_eodhd_symbol +
    overrides loaded once), the global cache, the coverage-threshold price-field selection,
    trading-day alignment, and `today` (frozen at construction).

    Structurally satisfies the authoritative PriceProvider Protocol (price_types).
    """

    def __init__(
        self,
        client: PriceClient,
        *,
        data_root: Path | str | None = None,
        history_start: date = constants.EODHD_HISTORY_START,
        today: date,
    ) -> None:
        if history_start > today:
            raise ValueError(
                f"history_start {history_start} must be <= today {today}"
            )
        self._client = client
        self._data_root = data_root
        self._history_start = history_start
        self._today = today
        self._overrides = load_symbol_overrides(data_root)
        # in-memory memo of loaded series, keyed by RESOLVED symbol (one fetch/symbol/run).
        self._series_memo: dict[str, SymbolSeries] = {}
        # resolved usable-price view memo, keyed by resolved symbol.
        self._view_memo: dict[str, dict[date, float]] = {}

    @property
    def today(self) -> date:
        return self._today

    def resolve_symbol(self, ticker: str | None) -> str | None:
        return to_eodhd_symbol(ticker, self._overrides)

    # --- symbol loading (lazy, cache-first; applies the hard-floor per-call rule) ---

    def _ensure_series(self, symbol: str, *, needed_to: date | None = None) -> SymbolSeries:
        """Ensure the resolved symbol's series is loaded; apply the per-call rule-4 refetch when
        `needed_to` exceeds the cached requested_to (and <= today). Returns the (possibly
        refetched) series. Raises EodhdError on a live fetch transport failure.
        """
        series = self._series_memo.get(symbol)
        if series is None:
            series = read_price_cache(symbol, self._data_root)
            if series is not None:
                self._series_memo[symbol] = series
        if series is None:
            series = self._fetch_and_cache(symbol)
        # rule 4: a needed date beyond the cached span (but <= today) -> refetch full span.
        if (
            needed_to is not None
            and needed_to <= self._today
            and needed_to > series.requested_to
        ):
            series = self._fetch_and_cache(symbol)
        return series

    def _fetch_and_cache(self, symbol: str) -> SymbolSeries:
        """Fetch [history_start, today], persist, and UPDATE the memos. Raises EodhdError on a
        transport failure (NOT cached -> retries next run)."""
        series = self._client.fetch_eod(
            symbol, from_date=self._history_start, to_date=self._today
        )
        write_price_cache(series, self._data_root)
        self._series_memo[symbol] = series
        # invalidate the derived view so it is rebuilt from the refetched series.
        self._view_memo.pop(symbol, None)
        return series

    def _usable_view(self, series: SymbolSeries) -> dict[date, float]:
        """Build (and memoize) the resolved usable-price view for a loaded symbol.

        Coverage-threshold field selection (never mix adjusted + raw within a series):
          - coverage = (# bars with a USABLE adjusted_close) / (total # bars), where usable =
            non-None AND >= 0 (0.0 is a valid bankruptcy close).
          - coverage < ADJ_CLOSE_MIN_COVERAGE -> use raw `close` for ALL bars (WARN once).
          - else -> use adjusted_close per bar (skip the rare unusable bar).
        Per-bar usability under the chosen field: non-None AND >= 0; unusable bars are SKIPPED.
        0.0 is IN the view (usable).
        """
        cached_view = self._view_memo.get(series.symbol)
        if cached_view is not None:
            return cached_view

        total = len(series.bars)
        usable_adj = sum(
            1
            for b in series.bars
            if b.adjusted_close is not None and b.adjusted_close >= 0
        )
        coverage = (usable_adj / total) if total else 0.0
        use_adjusted = coverage >= constants.ADJ_CLOSE_MIN_COVERAGE
        if total and not use_adjusted:
            logger.warning(
                "adjusted_close coverage %.2f < %.2f; using raw close for %s",
                coverage,
                constants.ADJ_CLOSE_MIN_COVERAGE,
                series.symbol,
            )

        view: dict[date, float] = {}
        for bar in series.bars:
            chosen = bar.adjusted_close if use_adjusted else bar.close
            if chosen is None or chosen < 0:
                continue  # unusable (None / negative) -> skip
            view[bar.bar_date] = chosen
        self._view_memo[series.symbol] = view
        return view

    def has_series_data(self, ticker: str) -> bool:
        """True iff the resolved symbol has >= 1 USABLE price (after coverage-threshold selection).

        None/unmappable ticker -> False; empty series -> False; all-unusable bars -> False.
        Powers the SPY preflight. Loads the symbol (cache-first; may raise EodhdError on a live
        transport failure — the SPY preflight treats that as fatal).
        """
        symbol = self.resolve_symbol(ticker)
        if symbol is None:
            return False
        series = self._ensure_series(symbol)
        view = self._usable_view(series)
        return len(view) >= 1

    def price_asof(self, ticker: str | None, on: date) -> float | None:
        """USABLE chosen-field price on `on`, else the most-recent PRIOR usable bar (carry-forward).

        ticker None / unmappable -> None. on > today -> None (future-date; no refetch; checked
        first). on < history_start -> None (below the hard floor; NO fetch). A 0.0 is RETURNED
        (the engine decides if 0.0 is acceptable in a given role). Staleness is a SOFT WARN only
        (NEVER None purely due to age — a delisted position keeps its last available price).
        Returns None only when there is no usable bar at/before `on`.
        """
        if ticker is None:
            return None
        symbol = self.resolve_symbol(ticker)
        if symbol is None:
            return None
        if on > self._today:
            return None
        if on < self._history_start:
            return None  # below the hard floor -> unpriceable; NO fetch (cache HIT)
        series = self._ensure_series(symbol, needed_to=on)
        view = self._usable_view(series)
        if not view:
            return None
        # exact date, else most-recent prior usable bar.
        if on in view:
            resolved_date, price = on, view[on]
        else:
            prior = [d for d in view if d <= on]
            if not prior:
                return None  # before the first usable bar
            resolved_date = max(prior)
            price = view[resolved_date]
        gap = (on - resolved_date).days
        if gap > constants.PRICE_STALENESS_WARN_DAYS:
            logger.warning(
                "price_asof(%s, %s): nearest usable bar is %s (%d days stale); "
                "returning last available price",
                symbol,
                on,
                resolved_date,
                gap,
            )
        return price

    def window_extrema(
        self, ticker: str | None, start: date, end: date
    ) -> WindowExtrema | None:
        """High/low (+ their dates) over USABLE chosen-field prices with
        max(start, history_start) <= bar_date <= end.

        start > end -> ValueError. ticker None / unmappable -> None. start < floor clamps to the
        floor. end > requested_to (and <= today) triggers a refetch first. Empty window -> None.
        """
        if start > end:
            raise ValueError(f"window_extrema start {start} must be <= end {end}")
        if ticker is None:
            return None
        symbol = self.resolve_symbol(ticker)
        if symbol is None:
            return None
        effective_start = max(start, self._history_start)
        series = self._ensure_series(symbol, needed_to=end)
        view = self._usable_view(series)
        in_range = {d: p for d, p in view.items() if effective_start <= d <= end}
        if not in_range:
            return None
        high_date = max(in_range, key=lambda d: (in_range[d], d.toordinal()))
        low_date = min(in_range, key=lambda d: (in_range[d], -d.toordinal()))
        return WindowExtrema(
            high=in_range[high_date],
            high_date=high_date,
            low=in_range[low_date],
            low_date=low_date,
        )
