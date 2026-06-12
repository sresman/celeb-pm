"""Exception taxonomy for celeb-pm.

See plan §6 for the error-taxonomy contract:
  - EdgarClient.get_json/get_text raise EdgarError (transport, retry-exhaustion,
    non-retryable 4xx including 403, JSON decode).
  - discover_filings wraps malformed-data problems in DiscoveryError and lets
    EdgarError propagate.
  - FilingRecord.__post_init__ raises DiscoveryError on invalid input.
  - cik_to_padded raises ValueError; the config loader surfaces bad CIKs as ConfigError.
  - submissions_overflow_url raises DiscoveryError on a bad name (path-safety).
  - storage.read_filings raises DiscoveryError on a missing filings.json.
  - OpenFigiClient.map_jobs raises OpenFigiError on transport/HTTP/JSON-decode/shape
    failures, the response-array length-guard (alignment), an in-payload `error` string,
    and an UNRECOGNIZED in-payload `warning` (all TRANSIENT — retry next run). A whitelisted
    in-payload miss warning or empty `data: []` is NOT an error (it is a permanent unresolved).
  - EodhdClient raises EodhdError on HTTP/transport/JSON-decode/shape failures, retry
    exhaustion, and non-retryable 4xx OTHER THAN 404 (401/403/422). A 404 is NOT an error —
    it means the symbol is unknown/never-listed and resolves to an empty series (unpriceable).
    EodhdError is a SINGLE class (NOT subclassed — no transient/permanent split). The returns
    engine ALSO raises EodhdError when the REQUIRED SPY benchmark has NO series data at all
    (detected via provider.has_series_data(SPY)); that is the only fatal symbol failure. The
    engine isolates ANY mid-loop EodhdError for a NON-SPY symbol as a soft per-record failure
    (priced=False + log + continue) — transient handling is the engine's responsibility, not a
    subclass distinction.
"""

from __future__ import annotations


class CelebPMError(Exception):
    """Base class for all celeb-pm errors."""


class ConfigError(CelebPMError):
    """Bad investors.json / bad CIK at the config boundary."""


class EdgarError(CelebPMError):
    """HTTP/transport/JSON-decode failures in EdgarClient."""


class DiscoveryError(CelebPMError):
    """Malformed submissions data / schema violations in discovery (or storage)."""


class OpenFigiError(CelebPMError):
    """HTTP/transport/JSON-decode/shape failures in OpenFigiClient, the response-array
    length-guard (alignment), an in-payload `error` string, and an UNRECOGNIZED in-payload
    `warning` (all TRANSIENT — retry next run)."""


class EodhdError(CelebPMError):
    """HTTP/transport/JSON-decode/shape failures in EodhdClient, retry-exhaustion, and
    non-retryable 4xx OTHER THAN 404 (incl. 401 bad/blank/omitted token, 403, 422).

    A 404 is NOT an error — it means the symbol is unknown/never-listed and is handled as
    'unpriceable' (empty series, bars=()). SINGLE class — NOT subclassed: there is no
    EodhdTransientError/EodhdPermanentError split; the returns engine's per-symbol isolation
    treats ANY EodhdError raised mid-loop for a NON-SPY symbol as a soft per-record failure
    (priced=False + log + continue). ALSO raised by the returns engine when the REQUIRED SPY
    benchmark has NO series data at all (a missing benchmark is unrecoverable; detected via
    provider.has_series_data(SPY)) — the only fatal symbol failure."""
