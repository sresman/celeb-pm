"""Domain schemas. Prompt 1 implements only FilingRecord (filing metadata).

Other schemas get a documented placement comment so later prompts extend cleanly in this
same file (one schema home). See plan §8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum

from celebpm import constants
from celebpm.errors import DiscoveryError

# Type for to_dict output / from_dict input values.
# Widened to include float (PositionRecord weights are floats). FilingRecord.to_dict emits
# only the existing subset, so its return type stays valid (verified harmless).
_Scalar = str | int | float | bool | None


@dataclass(frozen=True)
class FilingRecord:
    """Metadata for one 13F-HR (or 13F-HR/A) filing.

    frozen=True: records are write-once. Prompt 2 must produce updated records via
    dataclasses.replace(record, total_portfolio_value=..., ...), never by mutation.
    """

    # --- identity / location ---
    cik: str  # zero-padded 10-digit
    accession_number: str  # dashed form, e.g. "0001777813-26-000012"
    filing_index_url: str  # deterministic Archives index DIR url; Prompt 2 fetches
    #                        {this}index.json to locate the info-table XML
    primary_doc: str  # primary document filename from submissions JSON (NOT required; may be "")

    # --- descriptive ---
    fund_name: str  # from submissions JSON top-level `name` (D0.9)
    form_type: str  # "13F-HR" or "13F-HR/A" (must be in TARGET_FORM_TYPES)

    # --- dates (filing_date is the anchor) ---
    period_of_report: date  # quarter-end (from `reportDate`)
    filing_date: date  # public-visibility date — ANCHOR
    accepted_date: datetime  # tz-aware UTC; carries TIME despite the _date name

    # --- amendment handling ---
    amendment: bool
    amendment_type: str  # AMENDMENT_TYPE_* sentinel (unknown for amendments now)

    # --- DEFERRED to Prompt 2 (parse). None placeholders (D0.4) ---
    total_portfolio_value: int | None = None  # value AS REPORTED (incl. options notional)
    position_count: int | None = None
    # total_equity_value: sum of COMMON value_reported only (EXCLUDES options notional).
    # NO `_thousands` suffix (SD-3). UNITS CAVEAT (SD-2): value is stored as-reported; the
    # thousands-vs-dollars boundary (~Jan 2023) is unresolved — no conversion in code.
    # None-defaulted (do NOT change the decorator); historical filings re-persisted without a
    # re-parse carry None — downstream MUST tolerate None (backfill flag).
    total_equity_value: int | None = None

    def __post_init__(self) -> None:
        """Bounded validation (D8.2). Guards BOTH direct construction and from_dict.

        Checks:
          - form_type in TARGET_FORM_TYPES
          - amendment <-> amendment_type consistency
        With frozen=True we only READ fields and raise (no assignment).
        """
        if self.form_type not in constants.TARGET_FORM_TYPES:
            raise DiscoveryError(
                f"form_type {self.form_type!r} not in TARGET_FORM_TYPES "
                f"{sorted(constants.TARGET_FORM_TYPES)}"
            )
        amendment_sentinels = {
            constants.AMENDMENT_TYPE_RESTATEMENT,
            constants.AMENDMENT_TYPE_ADDS,
            constants.AMENDMENT_TYPE_UNKNOWN,
        }
        if self.amendment:
            if self.amendment_type not in amendment_sentinels:
                raise DiscoveryError(
                    f"amendment=True requires amendment_type in {sorted(amendment_sentinels)}, "
                    f"got {self.amendment_type!r}"
                )
        else:
            if self.amendment_type != constants.AMENDMENT_TYPE_NONE:
                raise DiscoveryError(
                    f"amendment=False requires amendment_type == "
                    f"{constants.AMENDMENT_TYPE_NONE!r}, got {self.amendment_type!r}"
                )

    def to_dict(self) -> dict[str, _Scalar]:
        """Serialize to a JSON-ready dict. Dates/datetimes -> ISO-8601 strings.

        accepted_date is serialized WITH offset (tz-aware UTC), so from_dict round-trips.
        """
        return {
            "cik": self.cik,
            "accession_number": self.accession_number,
            "filing_index_url": self.filing_index_url,
            "primary_doc": self.primary_doc,
            "fund_name": self.fund_name,
            "form_type": self.form_type,
            "period_of_report": self.period_of_report.isoformat(),
            "filing_date": self.filing_date.isoformat(),
            "accepted_date": self.accepted_date.isoformat(),
            "amendment": self.amendment,
            "amendment_type": self.amendment_type,
            "total_portfolio_value": self.total_portfolio_value,
            "position_count": self.position_count,
            "total_equity_value": self.total_equity_value,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FilingRecord:
        """Parse/coerce raw values (dates, datetimes) THEN construct -> __post_init__ validates.

        Raises DiscoveryError on missing required fields or unparseable dates.
        """
        try:
            cik = _require_str(raw, "cik")
            accession_number = _require_str(raw, "accession_number")
            filing_index_url = _require_str(raw, "filing_index_url")
            primary_doc = _require_str(raw, "primary_doc")
            fund_name = _require_str(raw, "fund_name")
            form_type = _require_str(raw, "form_type")
            period_of_report = date.fromisoformat(_require_str(raw, "period_of_report"))
            filing_date = date.fromisoformat(_require_str(raw, "filing_date"))
            accepted_date = _parse_dt_with_tz(_require_str(raw, "accepted_date"))
            amendment = _require_bool(raw, "amendment")
            amendment_type = _require_str(raw, "amendment_type")
            total_portfolio_value = _optional_int(raw, "total_portfolio_value")
            position_count = _optional_int(raw, "position_count")
            # None-tolerant: old filings.json lacking the key parse fine (defaults None).
            total_equity_value = (
                _optional_int(raw, "total_equity_value")
                if "total_equity_value" in raw
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"cannot parse FilingRecord from dict: {exc}") from exc

        return cls(
            cik=cik,
            accession_number=accession_number,
            filing_index_url=filing_index_url,
            primary_doc=primary_doc,
            fund_name=fund_name,
            form_type=form_type,
            period_of_report=period_of_report,
            filing_date=filing_date,
            accepted_date=accepted_date,
            amendment=amendment,
            amendment_type=amendment_type,
            total_portfolio_value=total_portfolio_value,
            position_count=position_count,
            total_equity_value=total_equity_value,
        )


def _require_str(raw: dict[str, object], key: str) -> str:
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"field {key!r} must be str, got {type(value).__name__}")
    return value


def _optional_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"field {key!r} must be str or None, got {type(value).__name__}")
    return value


def _require_bool(raw: dict[str, object], key: str) -> bool:
    value = raw[key]
    if not isinstance(value, bool):
        raise TypeError(f"field {key!r} must be bool, got {type(value).__name__}")
    return value


def _optional_int(raw: dict[str, object], key: str) -> int | None:
    value = raw[key]
    if value is None:
        return None
    # bool is a subclass of int; reject it explicitly to avoid silent coercion.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"field {key!r} must be int or None, got {type(value).__name__}")
    return value


def _require_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    # bool is a subclass of int; reject it explicitly to avoid silent coercion.
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"field {key!r} must be int, got {type(value).__name__}")
    return value


def _require_float(raw: dict[str, object], key: str) -> float:
    value = raw[key]
    # Accept JSON 1 and 1.0; reject bool (a subclass of int) explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"field {key!r} must be a number, got {type(value).__name__}")
    return float(value)


def _optional_float(raw: dict[str, object], key: str) -> float | None:
    value = raw[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"field {key!r} must be a number or None, got {type(value).__name__}"
        )
    return float(value)


def _parse_dt_with_tz(value: str) -> datetime:
    """Parse an ISO-8601 datetime; ensure tz-aware UTC (no-tz -> assume UTC)."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _require_date(raw: dict[str, object], key: str) -> date:
    """Parse a required ISO-8601 date field.

    Raises KeyError (missing), TypeError (None / non-str), or ValueError (bad format) —
    the same surface the sibling _require_* helpers use, caught by from_dict's
    `except (KeyError, TypeError, ValueError)` and re-raised as DiscoveryError.
    """
    value = raw[key]
    if not isinstance(value, str):
        raise TypeError(f"field {key!r} must be an ISO date str, got {type(value).__name__}")
    return date.fromisoformat(value)


def _optional_date(raw: dict[str, object], key: str) -> date | None:
    """Parse an optional ISO-8601 date field: null/missing -> None, else date.fromisoformat.

    Symmetric with _require_date. Raises TypeError (non-str) or ValueError (bad format), caught
    by from_dict's `except (KeyError, TypeError, ValueError)` and re-raised as DiscoveryError.
    """
    value = raw.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"field {key!r} must be an ISO date str or null, got {type(value).__name__}")
    return date.fromisoformat(value)


@dataclass(frozen=True, kw_only=True)
class PositionRecord:
    """One aggregated holding from a 13F info table, per (cusip, security_type).

    frozen=True: write-once. kw_only=True: ALL fields are keyword-only, which removes any
    default-ordering constraint (None-defaulted `ticker` can sit before required fields) and
    the long-positional-construction footgun. Construct via keywords only. Prompt 3 fills
    `ticker` via dataclasses.replace.
    """

    # --- identity / provenance ---
    cik: str  # zero-padded 10-digit (matches FilingRecord.cik)
    accession_number: str  # provenance: which filing this row came from
    period: date  # quarter-end (== filing.period_of_report)
    filing_date: date  # ANCHOR (== filing.filing_date)

    # --- security identity ---
    cusip: str  # 9-char, UPPERCASE (primary identifier)
    company_name: str  # nameOfIssuer, normalized (stripped); may be ""
    title_of_class: str  # titleOfClass, normalized (e.g. "COM", "COM CL A")
    security_type: str  # SECURITY_TYPE_* ("COMMON"/"PUT"/"CALL")
    put_call: str  # raw putCall ("PUT"/"CALL"/"") — explicit options flag

    # --- ticker DEFERRED to Prompt 3 ---
    ticker: str | None = None  # filled later via dataclasses.replace

    # --- quantities ---
    shares: int  # sshPrnamt (shares OR principal — see ssh_prnamt_type)
    ssh_prnamt_type: str  # SSH_TYPE_SHARES ("SH") / SSH_TYPE_PRINCIPAL ("PRN") / ""
    # market value AS REPORTED by EDGAR (NOTIONAL for options). UNITS CAVEAT (SD-2/SD-3):
    # SEC changed `value` from thousands to whole dollars ~Jan 2023. Stored EXACTLY as
    # reported; no conversion/cutoff guess. Spec literally names this `value_thousands`;
    # that name is wrong post-2023, so renamed to value_reported (SD-3). Do NOT derive
    # implied price from this until SD-2 is resolved (Prompt 5 flag).
    value_reported: int
    investment_discretion: str  # SOLE/DEFINED/OTHER (or "" if absent/unrecognized)

    # --- dual weights (spec §1.3 options handling) — FULL precision, no rounding here ---
    weight_pct_reported: float  # value / total_portfolio_value * 100 (incl. options)
    # value / total_equity_value * 100; None for options (not in equity denom).
    weight_pct_equity_only: float | None

    def __post_init__(self) -> None:
        """Bounded validation; mirrors FilingRecord. Reads only (frozen)."""
        if self.security_type not in constants.SECURITY_TYPES:
            raise DiscoveryError(
                f"security_type {self.security_type!r} not in "
                f"{sorted(constants.SECURITY_TYPES)}"
            )
        # security_type <-> put_call consistency.
        expected_put_call = {
            constants.SECURITY_TYPE_COMMON: "",
            constants.SECURITY_TYPE_PUT: constants.PUT_CALL_PUT,
            constants.SECURITY_TYPE_CALL: constants.PUT_CALL_CALL,
        }[self.security_type]
        if self.put_call != expected_put_call:
            raise DiscoveryError(
                f"security_type {self.security_type!r} requires put_call "
                f"{expected_put_call!r}, got {self.put_call!r}"
            )
        # CUSIP: 9 chars, uppercase, every char in the real CUSIP alphabet ([A-Z0-9*@#]).
        if (
            len(self.cusip) != constants.CUSIP_LENGTH
            or self.cusip != self.cusip.upper()
            or constants.CUSIP_PATTERN.fullmatch(self.cusip) is None
        ):
            raise DiscoveryError(f"invalid cusip {self.cusip!r}")
        if self.ssh_prnamt_type not in {
            constants.SSH_TYPE_SHARES,
            constants.SSH_TYPE_PRINCIPAL,
            "",
        }:
            raise DiscoveryError(f"invalid ssh_prnamt_type {self.ssh_prnamt_type!r}")
        if (
            self.investment_discretion not in constants.DISCRETION_VALUES
            and self.investment_discretion != ""
        ):
            raise DiscoveryError(
                f"invalid investment_discretion {self.investment_discretion!r}"
            )
        if self.value_reported < 0:
            raise DiscoveryError(f"value_reported must be >= 0, got {self.value_reported}")
        if self.shares < 0:
            raise DiscoveryError(f"shares must be >= 0, got {self.shares}")
        # Equity-only invariant (single most important): COMMON => equity weight not None;
        # PUT/CALL => equity weight IS None. Enforces equity/options separation.
        if self.security_type == constants.SECURITY_TYPE_COMMON:
            if self.weight_pct_equity_only is None:
                raise DiscoveryError(
                    "COMMON position must have a non-None weight_pct_equity_only"
                )
        else:
            if self.weight_pct_equity_only is not None:
                raise DiscoveryError(
                    f"{self.security_type} (option) must have "
                    f"weight_pct_equity_only is None, got {self.weight_pct_equity_only!r}"
                )

    def to_dict(self) -> dict[str, _Scalar]:
        """Serialize to a JSON-ready dict. Dates -> ISO strings; floats/None pass through."""
        return {
            "cik": self.cik,
            "accession_number": self.accession_number,
            "period": self.period.isoformat(),
            "filing_date": self.filing_date.isoformat(),
            "cusip": self.cusip,
            "company_name": self.company_name,
            "title_of_class": self.title_of_class,
            "security_type": self.security_type,
            "put_call": self.put_call,
            "ticker": self.ticker,
            "shares": self.shares,
            "ssh_prnamt_type": self.ssh_prnamt_type,
            "value_reported": self.value_reported,
            "investment_discretion": self.investment_discretion,
            "weight_pct_reported": self.weight_pct_reported,
            "weight_pct_equity_only": self.weight_pct_equity_only,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PositionRecord:
        """Parse/coerce raw values THEN construct -> __post_init__ validates."""
        try:
            cik = _require_str(raw, "cik")
            accession_number = _require_str(raw, "accession_number")
            period = date.fromisoformat(_require_str(raw, "period"))
            filing_date = date.fromisoformat(_require_str(raw, "filing_date"))
            cusip = _require_str(raw, "cusip")
            company_name = _require_str(raw, "company_name")
            title_of_class = _require_str(raw, "title_of_class")
            security_type = _require_str(raw, "security_type")
            put_call = _require_str(raw, "put_call")
            ticker = _optional_str(raw, "ticker")
            shares = _require_int(raw, "shares")
            ssh_prnamt_type = _require_str(raw, "ssh_prnamt_type")
            value_reported = _require_int(raw, "value_reported")
            investment_discretion = _require_str(raw, "investment_discretion")
            weight_pct_reported = _require_float(raw, "weight_pct_reported")
            weight_pct_equity_only = _optional_float(raw, "weight_pct_equity_only")
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"cannot parse PositionRecord from dict: {exc}") from exc

        return cls(
            cik=cik,
            accession_number=accession_number,
            period=period,
            filing_date=filing_date,
            cusip=cusip,
            company_name=company_name,
            title_of_class=title_of_class,
            security_type=security_type,
            put_call=put_call,
            ticker=ticker,
            shares=shares,
            ssh_prnamt_type=ssh_prnamt_type,
            value_reported=value_reported,
            investment_discretion=investment_discretion,
            weight_pct_reported=weight_pct_reported,
            weight_pct_equity_only=weight_pct_equity_only,
        )


@dataclass(frozen=True, kw_only=True)
class CusipMapEntry:
    """One CUSIP->ticker cache row (the persisted unit of cusip_ticker_map.json).

    frozen=True, kw_only=True: mirrors the other records. Provenance fields named
    `figi_*` to avoid colliding with PositionRecord.security_type (the COMMON/PUT/CALL
    classifier). `resolved_at` stays a str (ISO-8601 UTC w/ offset) — NOT a datetime field.
    See plan §5a.
    """

    cusip: str  # 9-char, validated via CUSIP_LENGTH + CUSIP_PATTERN
    ticker: str | None  # None iff source == unresolved; non-blank otherwise
    name: str | None  # issuer name from the chosen match (display only)
    exch_code: str | None
    figi_security_type: str | None  # FIGI securityType of the chosen match
    figi_security_type2: str | None  # FIGI securityType2 (audit provenance; heuristic uses it)
    market_sector: str | None  # FIGI marketSector (audit provenance; heuristic uses it)
    figi: str | None
    source: str  # CUSIP_SOURCES: openfigi / manual / unresolved
    ambiguous: bool = False  # >1 DISTINCT ticker in the strongest surviving tier (plan §4)
    resolved_at: str | None = None  # ISO-8601 UTC str WITH offset; None for manual rows that omit it

    def __post_init__(self) -> None:
        """Bounded validation; reads only (frozen). See plan §5a invariants."""
        if (
            len(self.cusip) != constants.CUSIP_LENGTH
            or self.cusip != self.cusip.upper()
            or constants.CUSIP_PATTERN.fullmatch(self.cusip) is None
        ):
            raise DiscoveryError(f"invalid cusip {self.cusip!r}")
        if self.source not in constants.CUSIP_SOURCES:
            raise DiscoveryError(
                f"source {self.source!r} not in {sorted(constants.CUSIP_SOURCES)}"
            )
        # Invariant A: source == unresolved <=> ticker is None.
        if self.source == constants.CUSIP_SOURCE_UNRESOLVED:
            if self.ticker is not None:
                raise DiscoveryError(
                    f"source 'unresolved' requires ticker is None, got {self.ticker!r}"
                )
        else:
            # Invariant B: a non-unresolved source requires a non-blank ticker.
            if self.ticker is None or self.ticker.strip() == "":
                raise DiscoveryError(
                    f"source {self.source!r} requires a non-blank ticker, got {self.ticker!r}"
                )

    def to_dict(self) -> dict[str, _Scalar]:
        """Serialize to a JSON-ready dict (all scalars; nothing to coerce)."""
        return {
            "cusip": self.cusip,
            "ticker": self.ticker,
            "name": self.name,
            "exch_code": self.exch_code,
            "figi_security_type": self.figi_security_type,
            "figi_security_type2": self.figi_security_type2,
            "market_sector": self.market_sector,
            "figi": self.figi,
            "source": self.source,
            "ambiguous": self.ambiguous,
            "resolved_at": self.resolved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> CusipMapEntry:
        """Parse raw values THEN construct -> __post_init__ validates.

        Forward-compat: figi_security_type2 / market_sector load via _optional_str and
        default None when absent, so older cache files and minimal hand-written `manual`
        rows load without error. Raises DiscoveryError on bad input.
        """
        try:
            cusip = _require_str(raw, "cusip")
            ticker = _optional_str(raw, "ticker")
            name = _optional_str(raw, "name")
            exch_code = _optional_str(raw, "exch_code")
            figi_security_type = _optional_str(raw, "figi_security_type")
            figi_security_type2 = _optional_str(raw, "figi_security_type2")
            market_sector = _optional_str(raw, "market_sector")
            figi = _optional_str(raw, "figi")
            source = _require_str(raw, "source")
            ambiguous = _require_bool(raw, "ambiguous") if "ambiguous" in raw else False
            resolved_at = _optional_str(raw, "resolved_at")
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"cannot parse CusipMapEntry from dict: {exc}") from exc

        return cls(
            cusip=cusip,
            ticker=ticker,
            name=name,
            exch_code=exch_code,
            figi_security_type=figi_security_type,
            figi_security_type2=figi_security_type2,
            market_sector=market_sector,
            figi=figi,
            source=source,
            ambiguous=ambiguous,
            resolved_at=resolved_at,
        )


@dataclass(frozen=True, kw_only=True)
class FundamentalsEntry:
    """One symbol's sector/industry from EODHD fundamentals (persisted unit of
    eodhd_fundamentals_cache.json).

    Keyed by `eodhd_symbol` — the actual EODHD fetch unit (e.g. 'GOOGL.US'), robust to ticker
    churn / null tickers (SD-V3-3). `resolved=False` caches a MISS (sector/industry None) so an
    unfundamentaled symbol is not re-fetched every run. `instrument_type` carries EODHD's
    General.Type for audit (e.g. 'Common Stock' / 'ETF'). `fetched_at` is an ISO-8601 UTC str.
    """

    eodhd_symbol: str
    sector: str | None
    industry: str | None
    instrument_type: str | None
    resolved: bool
    fetched_at: str | None = None

    def to_dict(self) -> dict[str, _Scalar]:
        """Serialize to a JSON-ready dict (all scalars; nothing to coerce)."""
        return {
            "eodhd_symbol": self.eodhd_symbol,
            "sector": self.sector,
            "industry": self.industry,
            "instrument_type": self.instrument_type,
            "resolved": self.resolved,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> FundamentalsEntry:
        """Parse raw values THEN construct. Raises DiscoveryError on bad input.

        Forward-compat: `resolved` defaults to False when absent; optional fields load via
        _optional_str and default None.
        """
        try:
            eodhd_symbol = _require_str(raw, "eodhd_symbol")
            sector = _optional_str(raw, "sector")
            industry = _optional_str(raw, "industry")
            instrument_type = _optional_str(raw, "instrument_type")
            resolved = _require_bool(raw, "resolved") if "resolved" in raw else False
            fetched_at = _optional_str(raw, "fetched_at")
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"cannot parse FundamentalsEntry from dict: {exc}") from exc

        return cls(
            eodhd_symbol=eodhd_symbol,
            sector=sector,
            industry=industry,
            instrument_type=instrument_type,
            resolved=resolved,
            fetched_at=fetched_at,
        )


# --- ReturnRecord lives at the END of this module (it depends on ChangeType, defined below). ---
# Fields per spec §1.5 + 3 SPY fields + cumulative + entry + priced + is_underlying_price.
# One schema home; gets to_dict/from_dict/__post_init__.


class ChangeType(str, Enum):
    """QoQ position-change classification (spec §1.4).

    str-Enum: members compare equal to their .value string and json.dumps serializes them as
    that string with no custom encoder. from_dict reconstructs via ChangeType(raw_string),
    which raises ValueError on an unknown value (caught + re-raised as DiscoveryError).

    NOTE: because this mixes in str, `change.change_type == "ACTIVE_ADD"` is True. Downstream
    code SHOULD compare against members (ChangeType.ACTIVE_ADD), not string literals, to avoid
    silent typo bugs. PositionChange.__post_init__ guards that the STORED value is a real member.
    """

    NEW = "NEW"
    EXIT = "EXIT"
    ACTIVE_ADD = "ACTIVE_ADD"
    ACTIVE_TRIM = "ACTIVE_TRIM"
    DRIFT_UP = "DRIFT_UP"
    DRIFT_DOWN = "DRIFT_DOWN"
    HOLD = "HOLD"


@dataclass(frozen=True, kw_only=True)
class PositionChange:
    """One QoQ change for a (cusip, security_type) across a Q[i-1] -> Q[i] transition.

    frozen=True, kw_only=True: mirrors PositionRecord. Every emitted row comes from a real
    transition, so prior_period/prior_filing_date are NON-nullable (a NEW row carries the prior
    quarter it is new RELATIVE to, with prior quantities/deltas None). EXIT rows are anchored at
    the CURRENT (observing) quarter's period/filing_date.

    __post_init__ is a VALUE-validation boundary (finiteness, sign, bool-rejection, cross-field
    invariants), NOT an exhaustive TYPE-validation boundary. The validated TYPE boundary is
    from_dict (the strict _require_* helpers). The diff engine constructs already-correct types.
    Pathological DIRECT construction with wrong field TYPES may raise TypeError rather than
    DiscoveryError — explicitly accepted for an internal model. Annotate a frozen instance via
    dataclasses.replace(change, corporate_action_note="..."), which re-runs __post_init__.
    """

    # --- provenance / identity (anchor) ---
    cik: str
    period: date  # CURRENT quarter-end
    filing_date: date  # CURRENT quarter's filing date — the ANCHOR
    prior_period: date  # NON-nullable; the prior transition quarter
    prior_filing_date: date  # NON-nullable

    # --- security identity (join key is cusip+security_type) ---
    cusip: str
    security_type: str  # in constants.SECURITY_TYPES (COMMON/PUT/CALL)
    ticker: str | None  # display only; current or prior ticker (None if both None)

    # --- current quarter (None iff change_type == EXIT) ---
    current_shares: int | None
    current_value_reported: int | None
    current_weight_pct: float | None  # == weight_pct_reported

    # --- prior quarter (None iff change_type == NEW) ---
    prior_shares: int | None
    prior_value_reported: int | None
    prior_weight_pct: float | None  # == weight_pct_reported

    # --- derived (None when one side absent — see invariants) ---
    shares_delta: int | None  # current - prior; None for NEW and EXIT
    shares_delta_pct: float | None  # % change in shares; None for NEW/EXIT or prior_shares==0
    weight_delta_bps: float | None  # (cur_wt - prior_wt) * 100; None for NEW/EXIT
    value_delta: int | None  # current - prior value_reported; None for NEW/EXIT
    value_delta_pct: float | None  # % change in value; None for NEW/EXIT or prior value==0

    # --- classification + flags ---
    change_type: ChangeType
    split_suspected: bool  # True only for matched rows meeting split bands; ⇒ HOLD
    corporate_action_note: str = ""  # manual-review free-text slot; default ""

    def __post_init__(self) -> None:
        """Bounded VALUE validation; reads only (frozen). Raises DiscoveryError. See plan §3."""
        # 1. security_type membership.
        if self.security_type not in constants.SECURITY_TYPES:
            raise DiscoveryError(
                f"security_type {self.security_type!r} not in "
                f"{sorted(constants.SECURITY_TYPES)}"
            )
        # 2. cusip shape (mirrors PositionRecord/CusipMapEntry).
        if (
            len(self.cusip) != constants.CUSIP_LENGTH
            or self.cusip != self.cusip.upper()
            or constants.CUSIP_PATTERN.fullmatch(self.cusip) is None
        ):
            raise DiscoveryError(f"invalid cusip {self.cusip!r}")
        # 3. change_type is a real ChangeType member (reject a raw string slipping the str-Enum).
        if not isinstance(self.change_type, ChangeType):
            raise DiscoveryError(
                f"change_type must be a ChangeType, got {type(self.change_type).__name__}"
            )
        # 4. split_suspected is a real bool (not an int).
        if not isinstance(self.split_suspected, bool):
            raise DiscoveryError(
                f"split_suspected must be bool, got {type(self.split_suspected).__name__}"
            )
        # 5. corporate_action_note is a str.
        if not isinstance(self.corporate_action_note, str):
            raise DiscoveryError(
                f"corporate_action_note must be str, got "
                f"{type(self.corporate_action_note).__name__}"
            )
        # 6. Reject bool in any non-None numeric field (bool is a subclass of int and passes
        #    math.isfinite). from_dict already rejects bool; this covers DIRECT construction.
        _numeric_fields = (
            ("current_shares", self.current_shares),
            ("prior_shares", self.prior_shares),
            ("current_value_reported", self.current_value_reported),
            ("prior_value_reported", self.prior_value_reported),
            ("shares_delta", self.shares_delta),
            ("value_delta", self.value_delta),
            ("current_weight_pct", self.current_weight_pct),
            ("prior_weight_pct", self.prior_weight_pct),
            ("weight_delta_bps", self.weight_delta_bps),
            ("shares_delta_pct", self.shares_delta_pct),
            ("value_delta_pct", self.value_delta_pct),
        )
        for name, val in _numeric_fields:
            if val is not None and isinstance(val, bool):
                raise DiscoveryError(f"field {name!r} must not be a bool")
        # 7. Finite (+ sign) guard for non-None floats. Weights must be >= 0; deltas may be
        #    negative (only finiteness checked). The SD-2 boundary value_delta_pct (~+100,000%)
        #    is large but FINITE -> passes.
        for name, fval in (
            ("current_weight_pct", self.current_weight_pct),
            ("prior_weight_pct", self.prior_weight_pct),
            ("weight_delta_bps", self.weight_delta_bps),
            ("shares_delta_pct", self.shares_delta_pct),
            ("value_delta_pct", self.value_delta_pct),
        ):
            if fval is not None and not math.isfinite(fval):
                raise DiscoveryError(f"field {name!r} must be finite, got {fval!r}")
        for name, wval in (
            ("current_weight_pct", self.current_weight_pct),
            ("prior_weight_pct", self.prior_weight_pct),
        ):
            if wval is not None and wval < 0:
                raise DiscoveryError(f"field {name!r} must be >= 0, got {wval}")
        # 8. Period ordering: prior_period < period (filing-date ordering INTENTIONALLY not
        #    enforced — amendments/late filings can reorder filing_date).
        if not self.prior_period < self.period:
            raise DiscoveryError(
                f"prior_period {self.prior_period} must be < period {self.period}"
            )
        # 13. Numeric sign sanity for share/value quantities (mirrors PositionRecord).
        for name, qval in (
            ("current_shares", self.current_shares),
            ("prior_shares", self.prior_shares),
            ("current_value_reported", self.current_value_reported),
            ("prior_value_reported", self.prior_value_reported),
        ):
            if qval is not None and qval < 0:
                raise DiscoveryError(f"field {name!r} must be >= 0, got {qval}")

        _deltas_all_none = (
            self.shares_delta is None
            and self.shares_delta_pct is None
            and self.weight_delta_bps is None
            and self.value_delta is None
            and self.value_delta_pct is None
        )
        _current_all_set = (
            self.current_shares is not None
            and self.current_value_reported is not None
            and self.current_weight_pct is not None
        )
        _current_all_none = (
            self.current_shares is None
            and self.current_value_reported is None
            and self.current_weight_pct is None
        )
        _prior_qty_all_set = (
            self.prior_shares is not None
            and self.prior_value_reported is not None
            and self.prior_weight_pct is not None
        )
        _prior_qty_all_none = (
            self.prior_shares is None
            and self.prior_value_reported is None
            and self.prior_weight_pct is None
        )

        if self.change_type == ChangeType.NEW:
            # 9. NEW
            if not (_current_all_set and _prior_qty_all_none and _deltas_all_none):
                raise DiscoveryError(
                    "NEW requires current_* set, prior quantities None, all deltas None"
                )
        elif self.change_type == ChangeType.EXIT:
            # 10. EXIT
            if not (_current_all_none and _prior_qty_all_set and _deltas_all_none):
                raise DiscoveryError(
                    "EXIT requires current_* None, prior quantities set, all deltas None"
                )
        else:
            # 11. Matched (ACTIVE_ADD/ACTIVE_TRIM/DRIFT_UP/DRIFT_DOWN/HOLD).
            #     shares_delta_pct / value_delta_pct MAY be None (prior denominator 0).
            if not (
                _current_all_set
                and _prior_qty_all_set
                and self.shares_delta is not None
                and self.weight_delta_bps is not None
                and self.value_delta is not None
            ):
                raise DiscoveryError(
                    f"{self.change_type.value} (matched) requires current_*, prior quantities, "
                    "and shares_delta/weight_delta_bps/value_delta all non-None"
                )
        # 12. STRICT split invariant: split_suspected=True ⇒ change_type == HOLD.
        if self.split_suspected and self.change_type != ChangeType.HOLD:
            raise DiscoveryError(
                f"split_suspected=True requires change_type == HOLD, got "
                f"{self.change_type.value}"
            )

    def to_dict(self) -> dict[str, _Scalar]:
        """Serialize to a JSON-ready dict. Dates -> ISO strings; change_type -> bare .value."""
        return {
            "cik": self.cik,
            "period": self.period.isoformat(),
            "filing_date": self.filing_date.isoformat(),
            "prior_period": self.prior_period.isoformat(),
            "prior_filing_date": self.prior_filing_date.isoformat(),
            "cusip": self.cusip,
            "security_type": self.security_type,
            "ticker": self.ticker,
            "current_shares": self.current_shares,
            "current_value_reported": self.current_value_reported,
            "current_weight_pct": self.current_weight_pct,
            "prior_shares": self.prior_shares,
            "prior_value_reported": self.prior_value_reported,
            "prior_weight_pct": self.prior_weight_pct,
            "shares_delta": self.shares_delta,
            "shares_delta_pct": self.shares_delta_pct,
            "weight_delta_bps": self.weight_delta_bps,
            "value_delta": self.value_delta,
            "value_delta_pct": self.value_delta_pct,
            "change_type": self.change_type.value,
            "split_suspected": self.split_suspected,
            "corporate_action_note": self.corporate_action_note,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PositionChange:
        """Parse/coerce raw values THEN construct -> __post_init__ validates.

        All four date fields are REQUIRED (_require_date). change_type via ChangeType(...) (an
        unknown value raises ValueError -> DiscoveryError). split_suspected via _require_bool
        (JSON 0/1 rejected). corporate_action_note: missing/null -> ""; present non-null non-str
        -> DiscoveryError.
        """
        try:
            cik = _require_str(raw, "cik")
            period = _require_date(raw, "period")
            filing_date = _require_date(raw, "filing_date")
            prior_period = _require_date(raw, "prior_period")
            prior_filing_date = _require_date(raw, "prior_filing_date")
            cusip = _require_str(raw, "cusip")
            security_type = _require_str(raw, "security_type")
            ticker = _optional_str(raw, "ticker")
            current_shares = _optional_int(raw, "current_shares")
            current_value_reported = _optional_int(raw, "current_value_reported")
            current_weight_pct = _optional_float(raw, "current_weight_pct")
            prior_shares = _optional_int(raw, "prior_shares")
            prior_value_reported = _optional_int(raw, "prior_value_reported")
            prior_weight_pct = _optional_float(raw, "prior_weight_pct")
            shares_delta = _optional_int(raw, "shares_delta")
            shares_delta_pct = _optional_float(raw, "shares_delta_pct")
            weight_delta_bps = _optional_float(raw, "weight_delta_bps")
            value_delta = _optional_int(raw, "value_delta")
            value_delta_pct = _optional_float(raw, "value_delta_pct")
            change_type = ChangeType(_require_str(raw, "change_type"))
            split_suspected = _require_bool(raw, "split_suspected")
            note = raw.get("corporate_action_note")
            if note is None:
                corporate_action_note = ""
            elif isinstance(note, str):
                corporate_action_note = note
            else:
                raise TypeError(
                    f"field 'corporate_action_note' must be str or null, "
                    f"got {type(note).__name__}"
                )
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"cannot parse PositionChange from dict: {exc}") from exc

        return cls(
            cik=cik,
            period=period,
            filing_date=filing_date,
            prior_period=prior_period,
            prior_filing_date=prior_filing_date,
            cusip=cusip,
            security_type=security_type,
            ticker=ticker,
            current_shares=current_shares,
            current_value_reported=current_value_reported,
            current_weight_pct=current_weight_pct,
            prior_shares=prior_shares,
            prior_value_reported=prior_value_reported,
            prior_weight_pct=prior_weight_pct,
            shares_delta=shares_delta,
            shares_delta_pct=shares_delta_pct,
            weight_delta_bps=weight_delta_bps,
            value_delta=value_delta,
            value_delta_pct=value_delta_pct,
            change_type=change_type,
            split_suspected=split_suspected,
            corporate_action_note=corporate_action_note,
        )


@dataclass(frozen=True, kw_only=True)
class ReturnRecord:
    """Filing-date-anchored forward returns for one PositionChange (Prompt 5).

    All prices/returns reflect daily ADJUSTED CLOSES (or raw close for a symbol whose adjusted
    coverage is < ADJ_CLOSE_MIN_COVERAGE). The extrema fields (next_period_high/low,
    entry_quarter_high/low) are extrema of daily CHOSEN-FIELD CLOSES (consistent with the return
    baseline), NOT raw intraday high/low. Options are priced on the UNDERLYING (is_underlying_price
    True) as a DIRECTIONAL signal — never option contract P&L. Returns come from EODHD prices ONLY
    (never value_reported). Equity and options are tracked separately.

    `priced=False` => every price/return/entry/cumulative/SPY field below is None (only the
    identity/audit fields are set). See __post_init__ for the authoritative invariants.
    """

    # --- anchor / identity (carried from the PositionChange) ---
    cik: str
    cusip: str
    ticker: str | None  # display only
    eodhd_symbol: str | None  # normalized symbol actually priced (None if unmappable)
    security_type: str  # COMMON/PUT/CALL (equity/options separation preserved)
    change_type: ChangeType
    period: date  # the holding's reporting period (quarter-end); used for the entry window
    filing_date: date  # ANCHOR for forward returns
    next_filing_date: date  # next quarter's filing date, or `today` if most recent

    # --- priced flag (decides nullability of everything below) ---
    priced: bool
    is_underlying_price: bool  # True IFF PUT/CALL: returns are the UNDERLYING's

    # --- filing-date prices (None unless priced) ---
    price_on_filing_date: float | None  # DENOMINATOR -> > 0 when non-None (engine guard)
    price_on_next_filing_date: float | None  # NUMERATOR -> may be 0.0

    # --- next-period range over [filing_date, next_filing_date] (None unless priced) ---
    next_period_high: float | None  # may be 0.0; may be endpoint-derived (no in-range bars)
    next_period_low: float | None
    next_period_high_date: date | None
    next_period_low_date: date | None

    # --- forward returns from the filing-date price (None unless priced) ---
    filing_to_filing_return_pct: float | None
    filing_to_next_period_high_pct: float | None
    filing_to_next_period_low_pct: float | None

    # --- entry estimate (NEW positions ONLY; None otherwise / unpriced / empty entry window) ---
    entry_quarter_high: float | None
    entry_quarter_low: float | None  # DENOMINATOR for entry returns -> > 0 when set
    best_case_entry_price: float | None  # == entry_quarter_low (bought at quarter low)
    worst_case_entry_price: float | None  # == entry_quarter_high
    best_case_entry_return_pct: float | None  # quarter low -> price_on_next_filing_date
    worst_case_entry_return_pct: float | None  # quarter high -> price_on_next_filing_date

    # --- multi-quarter cumulative (first-held filing -> chain end; None if N/A / unpriced) ---
    cumulative_return_pct: float | None
    cumulative_from_filing_date: date | None
    cumulative_to_filing_date: date | None

    # --- SPY benchmark over the SAME [filing_date, next_filing_date] window ---
    spy_filing_to_filing_return_pct: float | None
    spy_next_period_high_pct: float | None
    spy_next_period_low_pct: float | None

    # --- SMH benchmark (VanEck Semiconductor ETF) over the SAME window; secondary benchmark ---
    smh_filing_to_filing_return_pct: float | None
    smh_next_period_high_pct: float | None
    smh_next_period_low_pct: float | None

    def __post_init__(self) -> None:
        """Authoritative invariants. Reads only (frozen). Raises DiscoveryError on violation."""
        # 1. cik non-empty + numeric (mirror PositionRecord shape via cik_to_padded).
        try:
            constants.cik_to_padded(self.cik)
        except ValueError as exc:
            raise DiscoveryError(f"invalid cik {self.cik!r}: {exc}") from exc
        # cusip shape (mirror PositionChange).
        if (
            len(self.cusip) != constants.CUSIP_LENGTH
            or self.cusip != self.cusip.upper()
            or constants.CUSIP_PATTERN.fullmatch(self.cusip) is None
        ):
            raise DiscoveryError(f"invalid cusip {self.cusip!r}")
        # 2. security_type membership; change_type is a real member; bools are real bools.
        if self.security_type not in constants.SECURITY_TYPES:
            raise DiscoveryError(
                f"security_type {self.security_type!r} not in "
                f"{sorted(constants.SECURITY_TYPES)}"
            )
        if not isinstance(self.change_type, ChangeType):
            raise DiscoveryError(
                f"change_type must be a ChangeType, got {type(self.change_type).__name__}"
            )
        if not isinstance(self.priced, bool):
            raise DiscoveryError(f"priced must be bool, got {type(self.priced).__name__}")
        if not isinstance(self.is_underlying_price, bool):
            raise DiscoveryError(
                f"is_underlying_price must be bool, got "
                f"{type(self.is_underlying_price).__name__}"
            )
        # 3. is_underlying_price <=> security_type in {PUT, CALL}.
        is_option = self.security_type in {
            constants.SECURITY_TYPE_PUT,
            constants.SECURITY_TYPE_CALL,
        }
        if self.is_underlying_price != is_option:
            raise DiscoveryError(
                f"is_underlying_price {self.is_underlying_price} must be {is_option} for "
                f"security_type {self.security_type!r}"
            )

        _price_fields = (
            ("price_on_filing_date", self.price_on_filing_date),
            ("price_on_next_filing_date", self.price_on_next_filing_date),
            ("next_period_high", self.next_period_high),
            ("next_period_low", self.next_period_low),
            ("entry_quarter_high", self.entry_quarter_high),
            ("entry_quarter_low", self.entry_quarter_low),
            ("best_case_entry_price", self.best_case_entry_price),
            ("worst_case_entry_price", self.worst_case_entry_price),
        )
        _return_fields = (
            ("filing_to_filing_return_pct", self.filing_to_filing_return_pct),
            ("filing_to_next_period_high_pct", self.filing_to_next_period_high_pct),
            ("filing_to_next_period_low_pct", self.filing_to_next_period_low_pct),
            ("best_case_entry_return_pct", self.best_case_entry_return_pct),
            ("worst_case_entry_return_pct", self.worst_case_entry_return_pct),
            ("cumulative_return_pct", self.cumulative_return_pct),
            ("spy_filing_to_filing_return_pct", self.spy_filing_to_filing_return_pct),
            ("spy_next_period_high_pct", self.spy_next_period_high_pct),
            ("spy_next_period_low_pct", self.spy_next_period_low_pct),
            ("smh_filing_to_filing_return_pct", self.smh_filing_to_filing_return_pct),
            ("smh_next_period_high_pct", self.smh_next_period_high_pct),
            ("smh_next_period_low_pct", self.smh_next_period_low_pct),
        )
        _date_derived_fields = (
            ("next_period_high_date", self.next_period_high_date),
            ("next_period_low_date", self.next_period_low_date),
            ("cumulative_from_filing_date", self.cumulative_from_filing_date),
            ("cumulative_to_filing_date", self.cumulative_to_filing_date),
        )

        # 8. Bool-rejection + finiteness + sign (>= 0 for prices) on every non-None number.
        for name, pval in _price_fields:
            if pval is None:
                continue
            if isinstance(pval, bool):
                raise DiscoveryError(f"field {name!r} must not be a bool")
            if not math.isfinite(pval):
                raise DiscoveryError(f"field {name!r} must be finite, got {pval!r}")
            if pval < 0:
                raise DiscoveryError(f"field {name!r} must be >= 0, got {pval}")
        for name, rval in _return_fields:
            if rval is None:
                continue
            if isinstance(rval, bool):
                raise DiscoveryError(f"field {name!r} must not be a bool")
            if not math.isfinite(rval):
                raise DiscoveryError(f"field {name!r} must be finite, got {rval!r}")

        # 4. not priced => ALL price/return/entry/cumulative/SPY/date-derived fields None.
        if not self.priced:
            for name, val in (*_price_fields, *_return_fields, *_date_derived_fields):
                if val is not None:
                    raise DiscoveryError(
                        f"unpriced record must have {name!r} None, got {val!r}"
                    )
            return  # identity/audit fields remain set; nothing else to check.

        # 5. priced => core position fields set (next-period set even if endpoint-derived).
        _core = (
            ("price_on_filing_date", self.price_on_filing_date),
            ("price_on_next_filing_date", self.price_on_next_filing_date),
            ("filing_to_filing_return_pct", self.filing_to_filing_return_pct),
            ("filing_to_next_period_high_pct", self.filing_to_next_period_high_pct),
            ("filing_to_next_period_low_pct", self.filing_to_next_period_low_pct),
            ("next_period_high", self.next_period_high),
            ("next_period_low", self.next_period_low),
            ("next_period_high_date", self.next_period_high_date),
            ("next_period_low_date", self.next_period_low_date),
        )
        for name, val in _core:
            if val is None:
                raise DiscoveryError(f"priced record must have {name!r} non-None")

        # 6. SPY trio set-together-or-all-None.
        spy = (
            self.spy_filing_to_filing_return_pct,
            self.spy_next_period_high_pct,
            self.spy_next_period_low_pct,
        )
        if any(v is not None for v in spy) and any(v is None for v in spy):
            raise DiscoveryError("SPY trio must be set together or all None")

        # 6b. SMH trio set-together-or-all-None (mirrors SPY; SMH is a secondary benchmark so it
        #     may be all-None even when SPY is set — the two trios are independent).
        smh = (
            self.smh_filing_to_filing_return_pct,
            self.smh_next_period_high_pct,
            self.smh_next_period_low_pct,
        )
        if any(v is not None for v in smh) and any(v is None for v in smh):
            raise DiscoveryError("SMH trio must be set together or all None")

        # 7. Entry one-directional: any entry field non-None => change_type == NEW; a NEW's entry
        #    fields are EITHER all-set OR all-None (never partial).
        entry_vals = (
            self.entry_quarter_high,
            self.entry_quarter_low,
            self.best_case_entry_price,
            self.worst_case_entry_price,
            self.best_case_entry_return_pct,
            self.worst_case_entry_return_pct,
        )
        entry_any = any(v is not None for v in entry_vals)
        entry_all = all(v is not None for v in entry_vals)
        if entry_any and self.change_type != ChangeType.NEW:
            raise DiscoveryError(
                f"entry fields set but change_type is {self.change_type.value}, not NEW"
            )
        if entry_any and not entry_all:
            raise DiscoveryError("entry fields must be all-set or all-None (no partial set)")

        # 9. Ordering: next_period_high >= next_period_low; entry_high >= entry_low.
        if (
            self.next_period_high is not None
            and self.next_period_low is not None
            and self.next_period_high < self.next_period_low
        ):
            raise DiscoveryError(
                f"next_period_high {self.next_period_high} < "
                f"next_period_low {self.next_period_low}"
            )
        if (
            self.entry_quarter_high is not None
            and self.entry_quarter_low is not None
            and self.entry_quarter_high < self.entry_quarter_low
        ):
            raise DiscoveryError(
                f"entry_quarter_high {self.entry_quarter_high} < "
                f"entry_quarter_low {self.entry_quarter_low}"
            )

        # 10. Alias equality when present.
        if (
            self.best_case_entry_price is not None
            and self.entry_quarter_low is not None
            and self.best_case_entry_price != self.entry_quarter_low
        ):
            raise DiscoveryError("best_case_entry_price must equal entry_quarter_low")
        if (
            self.worst_case_entry_price is not None
            and self.entry_quarter_high is not None
            and self.worst_case_entry_price != self.entry_quarter_high
        ):
            raise DiscoveryError("worst_case_entry_price must equal entry_quarter_high")

        # 11. Date consistency.
        if self.filing_date > self.next_filing_date:
            raise DiscoveryError(
                f"filing_date {self.filing_date} must be <= "
                f"next_filing_date {self.next_filing_date}"
            )
        if (
            self.cumulative_from_filing_date is not None
            and self.cumulative_to_filing_date is not None
            and self.cumulative_from_filing_date > self.cumulative_to_filing_date
        ):
            raise DiscoveryError(
                f"cumulative_from {self.cumulative_from_filing_date} must be <= "
                f"cumulative_to {self.cumulative_to_filing_date}"
            )

    def to_dict(self) -> dict[str, _Scalar]:
        """Serialize to a JSON-ready dict. Dates -> ISO strings (or None); change_type -> .value."""

        def _d(value: date | None) -> str | None:
            return value.isoformat() if value is not None else None

        return {
            "cik": self.cik,
            "cusip": self.cusip,
            "ticker": self.ticker,
            "eodhd_symbol": self.eodhd_symbol,
            "security_type": self.security_type,
            "change_type": self.change_type.value,
            "period": self.period.isoformat(),
            "filing_date": self.filing_date.isoformat(),
            "next_filing_date": self.next_filing_date.isoformat(),
            "priced": self.priced,
            "is_underlying_price": self.is_underlying_price,
            "price_on_filing_date": self.price_on_filing_date,
            "price_on_next_filing_date": self.price_on_next_filing_date,
            "next_period_high": self.next_period_high,
            "next_period_low": self.next_period_low,
            "next_period_high_date": _d(self.next_period_high_date),
            "next_period_low_date": _d(self.next_period_low_date),
            "filing_to_filing_return_pct": self.filing_to_filing_return_pct,
            "filing_to_next_period_high_pct": self.filing_to_next_period_high_pct,
            "filing_to_next_period_low_pct": self.filing_to_next_period_low_pct,
            "entry_quarter_high": self.entry_quarter_high,
            "entry_quarter_low": self.entry_quarter_low,
            "best_case_entry_price": self.best_case_entry_price,
            "worst_case_entry_price": self.worst_case_entry_price,
            "best_case_entry_return_pct": self.best_case_entry_return_pct,
            "worst_case_entry_return_pct": self.worst_case_entry_return_pct,
            "cumulative_return_pct": self.cumulative_return_pct,
            "cumulative_from_filing_date": _d(self.cumulative_from_filing_date),
            "cumulative_to_filing_date": _d(self.cumulative_to_filing_date),
            "spy_filing_to_filing_return_pct": self.spy_filing_to_filing_return_pct,
            "spy_next_period_high_pct": self.spy_next_period_high_pct,
            "spy_next_period_low_pct": self.spy_next_period_low_pct,
            "smh_filing_to_filing_return_pct": self.smh_filing_to_filing_return_pct,
            "smh_next_period_high_pct": self.smh_next_period_high_pct,
            "smh_next_period_low_pct": self.smh_next_period_low_pct,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> ReturnRecord:
        """Parse/coerce raw values THEN construct -> __post_init__ validates."""
        try:
            record = cls(
                cik=_require_str(raw, "cik"),
                cusip=_require_str(raw, "cusip"),
                ticker=_optional_str(raw, "ticker"),
                eodhd_symbol=_optional_str(raw, "eodhd_symbol"),
                security_type=_require_str(raw, "security_type"),
                change_type=ChangeType(_require_str(raw, "change_type")),
                period=_require_date(raw, "period"),
                filing_date=_require_date(raw, "filing_date"),
                next_filing_date=_require_date(raw, "next_filing_date"),
                priced=_require_bool(raw, "priced"),
                is_underlying_price=_require_bool(raw, "is_underlying_price"),
                price_on_filing_date=_optional_float(raw, "price_on_filing_date"),
                price_on_next_filing_date=_optional_float(raw, "price_on_next_filing_date"),
                next_period_high=_optional_float(raw, "next_period_high"),
                next_period_low=_optional_float(raw, "next_period_low"),
                next_period_high_date=_optional_date(raw, "next_period_high_date"),
                next_period_low_date=_optional_date(raw, "next_period_low_date"),
                filing_to_filing_return_pct=_optional_float(
                    raw, "filing_to_filing_return_pct"
                ),
                filing_to_next_period_high_pct=_optional_float(
                    raw, "filing_to_next_period_high_pct"
                ),
                filing_to_next_period_low_pct=_optional_float(
                    raw, "filing_to_next_period_low_pct"
                ),
                entry_quarter_high=_optional_float(raw, "entry_quarter_high"),
                entry_quarter_low=_optional_float(raw, "entry_quarter_low"),
                best_case_entry_price=_optional_float(raw, "best_case_entry_price"),
                worst_case_entry_price=_optional_float(raw, "worst_case_entry_price"),
                best_case_entry_return_pct=_optional_float(
                    raw, "best_case_entry_return_pct"
                ),
                worst_case_entry_return_pct=_optional_float(
                    raw, "worst_case_entry_return_pct"
                ),
                cumulative_return_pct=_optional_float(raw, "cumulative_return_pct"),
                cumulative_from_filing_date=_optional_date(
                    raw, "cumulative_from_filing_date"
                ),
                cumulative_to_filing_date=_optional_date(raw, "cumulative_to_filing_date"),
                spy_filing_to_filing_return_pct=_optional_float(
                    raw, "spy_filing_to_filing_return_pct"
                ),
                spy_next_period_high_pct=_optional_float(raw, "spy_next_period_high_pct"),
                spy_next_period_low_pct=_optional_float(raw, "spy_next_period_low_pct"),
                smh_filing_to_filing_return_pct=_optional_float(
                    raw, "smh_filing_to_filing_return_pct"
                ),
                smh_next_period_high_pct=_optional_float(raw, "smh_next_period_high_pct"),
                smh_next_period_low_pct=_optional_float(raw, "smh_next_period_low_pct"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DiscoveryError(f"cannot parse ReturnRecord from dict: {exc}") from exc
        return record
