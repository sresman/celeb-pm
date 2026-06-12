"""Shared price value objects + the PriceClient / PriceProvider Protocols.

Imported by the EODHD client, the cache/provider, and the returns engine. To guarantee an
ACYCLIC import graph this module imports ONLY stdlib (datetime, dataclasses, typing) — NOTHING
from constants, the client, the cache, or the engine. Response/param key spellings and defaults
are referenced in prose in the relevant modules, NOT imported here.

  - PriceBar       : one daily EOD bar (boundary-narrowed; no Any). Persisted inside SymbolSeries.
  - SymbolSeries   : a symbol's daily bars (ascending, deduped) + cache provenance. The serialized
                     unit. Carries NO schema_version (that lives in the cache-FILE wrapper).
  - WindowExtrema  : a transient compute result (high/low + dates). NEVER persisted -> NO
                     to_dict / from_dict.
  - PriceClient    : the HTTP fetch seam (takes a normalized symbol).
  - PriceProvider  : the cache-first seam the engine depends on (takes raw tickers; owns
                     normalization + today + the cache).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol


@dataclass(frozen=True, kw_only=True)
class PriceBar:
    """One daily EOD bar, boundary-narrowed (no Any).

    OHLC + adjusted_close may be None if EODHD omits or sends a non-numeric value for them
    (the boundary narrowers in eodhd_client return None rather than raising for OHLC fields).
    bar_date is REQUIRED (a bar with no parseable date is unusable -> the client raises).
    """

    bar_date: date  # parsed from the EODHD date row key
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    adjusted_close: float | None
    volume: int | None

    def to_dict(self) -> dict[str, object]:
        """Serialize one row. The on-disk row shape matches the live EODHD row shape (same keys)."""
        return {
            "date": self.bar_date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "adjusted_close": self.adjusted_close,
            "volume": self.volume,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "PriceBar":
        """Reconstruct a bar from a persisted row. RAISES (KeyError/TypeError/ValueError) on a
        shape violation; the caller (read_price_cache) catches and converts to a cache miss.
        """
        return cls(
            bar_date=date.fromisoformat(_require_str(raw, "date")),
            open=_optional_number(raw, "open"),
            high=_optional_number(raw, "high"),
            low=_optional_number(raw, "low"),
            close=_optional_number(raw, "close"),
            adjusted_close=_optional_number(raw, "adjusted_close"),
            volume=_optional_int(raw, "volume"),
        )


@dataclass(frozen=True, kw_only=True)
class SymbolSeries:
    """A symbol's daily bars (ascending by date, deduped) + cache provenance.

    The cached/serialized unit. Carries NO schema_version (that lives in the cache-file
    wrapper). requested_from / requested_to record the span the provider ASKED EODHD for
    (always [EODHD_HISTORY_START, today-at-fetch]); first_bar_date / last_bar_date are derived
    diagnostics. fetched_at is provenance-only (UTC ISO-8601 with offset).
    """

    symbol: str
    fetched_at: str  # ISO-8601 UTC w/ offset (PROVENANCE ONLY — kept as str)
    requested_from: date  # the span the provider ASKED for (always EODHD_HISTORY_START)
    requested_to: date  # the span the provider ASKED for (always today-at-fetch)
    bars: tuple[PriceBar, ...]  # ascending, deduped by date

    @property
    def first_bar_date(self) -> date | None:
        return self.bars[0].bar_date if self.bars else None

    @property
    def last_bar_date(self) -> date | None:
        return self.bars[-1].bar_date if self.bars else None

    def to_dict(self) -> dict[str, object]:
        """The INNER series object only (no schema_version — the wrapper carries that)."""
        return {
            "symbol": self.symbol,
            "fetched_at": self.fetched_at,
            "requested_from": self.requested_from.isoformat(),
            "requested_to": self.requested_to.isoformat(),
            "first_bar_date": (
                self.first_bar_date.isoformat() if self.first_bar_date is not None else None
            ),
            "last_bar_date": (
                self.last_bar_date.isoformat() if self.last_bar_date is not None else None
            ),
            "rows": [bar.to_dict() for bar in self.bars],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "SymbolSeries":
        """Reconstruct from the INNER series dict. RAISES (KeyError/TypeError/ValueError) on a
        shape violation; duplicate / non-ascending dates -> raise; a bad fetched_at -> raise.

        symbol-mismatch is NOT checked here (read_price_cache compares the symbol on the raw
        dict BEFORE calling this). read_price_cache CATCHES whatever this raises and converts it
        to a cache MISS (None). A LIVE parse path does NOT go through from_dict (eodhd_client uses
        _parse_series, which raises EodhdError) — the two have DIFFERENT error contracts.
        """
        symbol = _require_str(raw, "symbol")
        fetched_at = _require_str(raw, "fetched_at")
        # fetched_at must be parseable (provenance integrity) — bad -> raise (caller: miss).
        if _parse_fetched_at(fetched_at) is None:
            raise ValueError(f"unparseable fetched_at: {fetched_at!r}")
        requested_from = date.fromisoformat(_require_str(raw, "requested_from"))
        requested_to = date.fromisoformat(_require_str(raw, "requested_to"))
        rows = raw["rows"]
        if not isinstance(rows, list):
            raise TypeError(f"'rows' must be a list, got {type(rows).__name__}")
        bars: list[PriceBar] = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError(f"each row must be an object, got {type(row).__name__}")
            bars.append(PriceBar.from_dict(row))
        # enforce strictly-ascending, unique dates (a violation -> raise; caller: miss).
        for prev, cur in zip(bars, bars[1:]):
            if cur.bar_date <= prev.bar_date:
                raise ValueError(
                    f"rows must be strictly ascending by date; "
                    f"{cur.bar_date} <= {prev.bar_date}"
                )
        return cls(
            symbol=symbol,
            fetched_at=fetched_at,
            requested_from=requested_from,
            requested_to=requested_to,
            bars=tuple(bars),
        )


@dataclass(frozen=True, kw_only=True)
class WindowExtrema:
    """Transient compute result — high/low + their dates over a window.

    NEVER persisted -> NO to_dict / from_dict. high/low are CHOSEN-FIELD CLOSES (adjusted or
    raw, consistent with the return baseline), NOT raw intraday high/low.
    """

    high: float
    high_date: date
    low: float
    low_date: date


class PriceClient(Protocol):
    """Structural seam for daily EOD price fetch. The provider depends on THIS.

    NOT @runtime_checkable — conformance asserted statically in tests (mirrors MappingClient).
    The CLIENT seam takes a NORMALIZED symbol (a thin HTTP fetcher). The PROVIDER seam takes a
    raw ticker and does normalization.
    """

    def fetch_eod(self, symbol: str, *, from_date: date, to_date: date) -> SymbolSeries: ...


class PriceProvider(Protocol):
    """The cache-first seam the engine depends on. Takes RAW tickers; OWNS normalization
    (to_eodhd_symbol + overrides), the cache, the price-field selection, and `today`.

    THE authoritative signature list — all other modules reference this; do not restate
    divergent signatures.
    """

    @property
    def today(self) -> date: ...

    def resolve_symbol(self, ticker: str | None) -> str | None: ...

    def has_series_data(self, ticker: str) -> bool: ...

    def price_asof(self, ticker: str | None, on: date) -> float | None: ...

    def window_extrema(
        self, ticker: str | None, start: date, end: date
    ) -> WindowExtrema | None: ...


# --- module-local boundary narrowers (stdlib-only; no constants import) ---


def _require_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"field {key!r} must be str, got {type(value).__name__}")
    return value


def _optional_number(raw: dict[str, object], key: str) -> float | None:
    """A persisted OHLC/adjusted value: int/float -> float; None/missing -> None; bool/other
    -> raise (the cache is best-effort; the caller converts a raise to a miss)."""
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"field {key!r} must be a number or None, got {type(value).__name__}")
    return float(value)


def _optional_int(raw: dict[str, object], key: str) -> int | None:
    value = raw.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"field {key!r} must be int or None, got {type(value).__name__}")
    return value


def _parse_fetched_at(value: str) -> object | None:
    """Return a parsed datetime or None (provenance integrity check; never raises here)."""
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
