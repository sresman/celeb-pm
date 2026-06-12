"""OpenFIGI ticker -> EODHD 'TICKER.EXCHANGE' symbol normalization + override loading.

returns.py is DISK-FREE and does NOT load overrides; the PROVIDER (price_cache.CachingPriceProvider)
loads overrides ONCE and calls to_eodhd_symbol. This module imports only {constants}.

Override values are FULL EODHD symbols (e.g. BRK-B.US) — the operator is responsible for the
complete TICKER.EXCHANGE form; they are returned AS-IS (NOT re-suffixed).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Mapping

from celebpm import constants

logger = logging.getLogger(__name__)

# Single-pass translation table: each class-share separator char -> '-'.
_CLASS_TRANSLATION = str.maketrans(
    {sep: constants.EODHD_CLASS_SHARE_SEPARATOR for sep in constants.EODHD_CLASS_SEPARATORS_IN}
)


def to_eodhd_symbol(
    ticker: str | None,
    overrides: Mapping[str, str] | None = None,
) -> str | None:
    """OpenFIGI ticker -> EODHD 'TICKER.EXCHANGE' symbol, or None if unmappable.

    Order matters:
      1. None / blank (after strip) -> None (unpriceable).
      2. t = ticker.strip().upper().
      3. Override first: t in overrides -> the override value AS-IS (already validated at load).
      4. Already-suffixed passthrough: t matches '\\.[A-Z]{2}$' (a true 2-letter exchange suffix)
         -> pass through unchanged. A non-.US passthrough emits a WARN (likely-unpriceable foreign
         listing). '.US' does NOT warn. ('BF.B' does NOT match -> class-share handling.)
      5. Class-share separators -> '-' in a SINGLE pass (str.translate; consecutive separators are
         NOT collapsed -> 'BRK. B' -> 'BRK--B' -> unpriceable, a SAFE failure).
      6. Append '.US'.
      7. Validate the result vs EODHD_SYMBOL_PATTERN; mismatch -> None + WARN.
    """
    if ticker is None:
        return None
    t = ticker.strip().upper()
    if not t:
        return None

    if overrides is not None and t in overrides:
        return overrides[t]  # full EODHD symbol, validated at load time

    if constants.EODHD_EXCHANGE_SUFFIX_PATTERN.search(t) is not None:
        if not t.endswith(constants.EODHD_US_EXCHANGE_SUFFIX):
            logger.warning(
                "ticker %r already carries a non-%s exchange suffix; passing through "
                "(likely unpriceable in the US-only universe)",
                t,
                constants.EODHD_US_EXCHANGE_SUFFIX,
            )
        if constants.EODHD_SYMBOL_PATTERN.fullmatch(t) is None:
            logger.warning("normalized symbol %r fails EODHD_SYMBOL_PATTERN; unmappable", t)
            return None
        return t

    base = t.translate(_CLASS_TRANSLATION)
    symbol = f"{base}{constants.EODHD_US_EXCHANGE_SUFFIX}"
    if constants.EODHD_SYMBOL_PATTERN.fullmatch(symbol) is None:
        logger.warning(
            "ticker %r normalized to %r which fails EODHD_SYMBOL_PATTERN; unmappable",
            ticker,
            symbol,
        )
        return None
    return symbol


def load_symbol_overrides(data_root: Path | str | None = None) -> dict[str, str]:
    """Load the optional <data_root>/price_cache/symbol_overrides.json map (never crashes).

    missing file -> {} (no overrides). unreadable / not-JSON / not a dict -> {} + WARN.
    Keys are STRIPPED + UPPERCASED. Values are FULL EODHD symbols: STRIPPED + UPPERCASED, then
    validated against EODHD_SYMBOL_PATTERN, stored AS-IS (NOT re-suffixed). A non-string value
    OR one failing the pattern -> that ENTRY ignored + WARN (the rest loads). A key collision
    after uppercasing -> WARN, last-loaded value kept.
    """
    path = constants.symbol_overrides_path(data_root)
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        raw: object = json.loads(text)
    except (OSError, ValueError) as exc:
        logger.warning("could not read symbol overrides %s: %s; ignoring", path, exc)
        return {}
    if not isinstance(raw, dict):
        logger.warning(
            "symbol overrides %s is not a JSON object (got %s); ignoring",
            path,
            type(raw).__name__,
        )
        return {}

    overrides: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        if not isinstance(raw_key, str):
            logger.warning("symbol override key %r is not a string; ignoring entry", raw_key)
            continue
        key = raw_key.strip().upper()
        if not key:
            logger.warning("symbol override has a blank key; ignoring entry")
            continue
        if not isinstance(raw_value, str):
            logger.warning(
                "symbol override value for %r is not a string (got %s); ignoring entry",
                key,
                type(raw_value).__name__,
            )
            continue
        value = raw_value.strip().upper()
        if constants.EODHD_SYMBOL_PATTERN.fullmatch(value) is None:
            logger.warning(
                "symbol override value %r for %r is not a valid EODHD symbol; ignoring entry",
                value,
                key,
            )
            continue
        if key in overrides:
            logger.warning(
                "symbol override key collision after uppercasing on %r; keeping last value %r",
                key,
                value,
            )
        overrides[key] = value
    return overrides
