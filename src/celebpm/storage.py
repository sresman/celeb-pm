"""Thin persistence layer. FETCH FILINGS produces data/<slug>/filings.json.

discover_filings stays PURE (no disk); the caller composes discovery + storage. See plan §11.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from celebpm import constants
from celebpm.errors import DiscoveryError
from celebpm.models import (
    CusipMapEntry,
    FilingRecord,
    PositionChange,
    PositionRecord,
    ReturnRecord,
)

logger = logging.getLogger(__name__)


def _resolved_root(data_root: Path | str | None) -> Path:
    if data_root is not None:
        return Path(data_root).resolve()
    return (constants.REPO_ROOT / constants.DATA_ROOT).resolve()


def _assert_under_root(root: Path, target: Path) -> None:
    """Raise DiscoveryError if `target` is not `root` itself nor under it.

    The containment invariant shared by per-slug paths and the shared cusip-map path.
    Resolves BOTH paths so a `..` traversal cannot slip past the comparison.
    """
    root = root.resolve()
    target = target.resolve()
    if root != target and root not in target.parents:
        raise DiscoveryError(f"path {target} resolves outside data_root {root}")


def _safe_path(
    slug: str, filename: str, data_root: Path | str | None
) -> tuple[Path, Path]:
    """Resolve <data_root>/<slug>/<filename> and assert it stays UNDER data_root.

    Returns (resolved_dir, resolved_file). Raises DiscoveryError on traversal escape.
    """
    root = _resolved_root(data_root)
    target_dir = (root / slug).resolve()
    target_file = (target_dir / filename).resolve()
    _assert_under_root(root, target_dir)
    return target_dir, target_file


def safe_data_path(
    slug: str, filename: str, data_root: Path | str | None = None
) -> Path:
    """PUBLIC path-safety helper: resolve <data_root>/<slug>/<filename> under data_root.

    A thin wrapper over the existing containment logic. `filename` MAY contain a subdir
    (e.g. f"{VIEWS_DIR}/{NEW_IDEAS_FILE}"); the resolved path is still asserted to live under
    <data_root>/<slug>/ and a traversal attempt (`..`) raises DiscoveryError. Returns the
    resolved file path. Provided so external writers (view_io) do not reach into private
    _safe_path / _assert_under_root.
    """
    root = _resolved_root(data_root)
    slug_dir = (root / slug).resolve()
    _assert_under_root(root, slug_dir)
    target_file = (slug_dir / filename).resolve()
    _assert_under_root(slug_dir, target_file)
    return target_file


def _safe_filings_path(slug: str, data_root: Path | str | None) -> tuple[Path, Path]:
    """Thin wrapper kept for the filings round-trip (behavioral no-op over _safe_path)."""
    return _safe_path(slug, constants.FILINGS_FILE, data_root)


def write_filings(
    slug: str,
    records: list[FilingRecord],
    data_root: Path | str | None = None,
) -> Path:
    """Serialize records as a BARE JSON LIST to <data_root>/<slug>/filings.json.

    Creates the dir on demand. data_root defaults to REPO_ROOT/DATA_ROOT. Returns the path.
    ATOMIC write: temp file in the SAME dir, flush+fsync, then os.replace. PATH-SAFETY:
    resolved path must stay under data_root.
    """
    target_dir, target_file = _safe_filings_path(slug, data_root)
    payload = [record.to_dict() for record in records]
    text = json.dumps(payload, indent=2)
    _atomic_write_json(target_dir, target_file, text, prefix=".filings-")
    logger.info("wrote %d filing record(s) to %s", len(records), target_file)
    return target_file


def read_filings(
    slug: str,
    data_root: Path | str | None = None,
) -> list[FilingRecord]:
    """Read <data_root>/<slug>/filings.json (a bare JSON list) -> [FilingRecord].

    PATH-SAFETY: same resolve+assert-under-data_root as write_filings.
    MISSING FILE -> raise DiscoveryError (clear error, NOT a silent []).
    """
    _, target_file = _safe_filings_path(slug, data_root)
    if not target_file.exists():
        raise DiscoveryError(f"filings file not found for slug {slug!r}: {target_file}")

    text = target_file.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(f"filings file is not valid JSON ({target_file}): {exc}") from exc

    if not isinstance(data, list):
        raise DiscoveryError(
            f"filings file must contain a JSON list, got {type(data).__name__} ({target_file})"
        )

    records: list[FilingRecord] = []
    for item in data:
        if not isinstance(item, dict):
            raise DiscoveryError(f"each filings entry must be an object ({target_file})")
        records.append(FilingRecord.from_dict(item))
    return records


def _atomic_write_json(target_dir: Path, target_file: Path, text: str, prefix: str) -> None:
    """Write text to target_file atomically (temp in same dir, flush+fsync, os.replace)."""
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(target_dir), prefix=prefix, suffix=".json.tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, target_file)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_positions(
    slug: str,
    records: list[PositionRecord],
    data_root: Path | str | None = None,
) -> Path:
    """Serialize PositionRecords as a BARE JSON LIST to <data_root>/<slug>/positions.json.

    OVERWRITES wholesale (no append/dedup — caller owns incremental merge per the §7
    contract). SORTS by (period, cusip, security_type) BEFORE writing for stable, idempotent,
    deterministic output regardless of caller order. ATOMIC + PATH-SAFE (mirrors filings).
    """
    target_dir, target_file = _safe_path(slug, constants.POSITIONS_FILE, data_root)
    ordered = sorted(records, key=lambda r: (r.period, r.cusip, r.security_type))
    payload = [record.to_dict() for record in ordered]
    text = json.dumps(payload, indent=2)
    _atomic_write_json(target_dir, target_file, text, prefix=".positions-")
    logger.info("wrote %d position record(s) to %s", len(ordered), target_file)
    return target_file


def read_positions(
    slug: str,
    data_root: Path | str | None = None,
) -> list[PositionRecord]:
    """Read <data_root>/<slug>/positions.json (a bare JSON list) -> [PositionRecord].

    PATH-SAFE. MISSING FILE -> DiscoveryError (contract UNCHANGED; the incremental caller
    catches it and treats a missing file as empty first-run history).
    """
    _, target_file = _safe_path(slug, constants.POSITIONS_FILE, data_root)
    if not target_file.exists():
        raise DiscoveryError(f"positions file not found for slug {slug!r}: {target_file}")

    text = target_file.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(
            f"positions file is not valid JSON ({target_file}): {exc}"
        ) from exc

    if not isinstance(data, list):
        raise DiscoveryError(
            f"positions file must contain a JSON list, got {type(data).__name__} "
            f"({target_file})"
        )

    records: list[PositionRecord] = []
    for item in data:
        if not isinstance(item, dict):
            raise DiscoveryError(f"each positions entry must be an object ({target_file})")
        records.append(PositionRecord.from_dict(item))
    return records


def write_changes(
    slug: str,
    records: list[PositionChange],
    data_root: Path | str | None = None,
) -> Path:
    """Serialize PositionChanges as a BARE JSON LIST to <data_root>/<slug>/changes.json.

    SORTS by (period, cusip, security_type) before writing (period is the CURRENT quarter-end,
    non-null for every change_type incl EXIT, so the key is total). REJECTS a record set spanning
    >1 distinct cik (per-slug public storage boundary) and any duplicate (period, cusip,
    security_type). ATOMIC + PATH-SAFE (mirrors positions).
    """
    target_dir, target_file = _safe_path(slug, constants.CHANGES_FILE, data_root)
    ciks = {r.cik for r in records}
    if len(ciks) > 1:
        raise DiscoveryError(
            f"write_changes record set spans multiple ciks: {sorted(ciks)}"
        )
    seen: set[tuple[object, str, str]] = set()
    for r in records:
        key = (r.period, r.cusip, r.security_type)
        if key in seen:
            raise DiscoveryError(
                f"duplicate (period, cusip, security_type) {key} in changes record set"
            )
        seen.add(key)
    ordered = sorted(records, key=lambda r: (r.period, r.cusip, r.security_type))
    payload = [record.to_dict() for record in ordered]
    text = json.dumps(payload, indent=2)
    _atomic_write_json(target_dir, target_file, text, prefix=".changes-")
    logger.info("wrote %d change record(s) to %s", len(ordered), target_file)
    return target_file


def read_changes(
    slug: str,
    data_root: Path | str | None = None,
) -> list[PositionChange]:
    """Read <data_root>/<slug>/changes.json (a bare JSON list) -> [PositionChange].

    PATH-SAFE. MISSING FILE -> DiscoveryError. Root not a list / item not an object / invalid
    enum or date / failed coercion / missing required field -> DiscoveryError (from from_dict).
    """
    _, target_file = _safe_path(slug, constants.CHANGES_FILE, data_root)
    if not target_file.exists():
        raise DiscoveryError(f"changes file not found for slug {slug!r}: {target_file}")

    text = target_file.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(
            f"changes file is not valid JSON ({target_file}): {exc}"
        ) from exc

    if not isinstance(data, list):
        raise DiscoveryError(
            f"changes file must contain a JSON list, got {type(data).__name__} "
            f"({target_file})"
        )

    records: list[PositionChange] = []
    for item in data:
        if not isinstance(item, dict):
            raise DiscoveryError(f"each changes entry must be an object ({target_file})")
        records.append(PositionChange.from_dict(item))
    return records


def write_returns(
    slug: str,
    records: list[ReturnRecord],
    data_root: Path | str | None = None,
) -> Path:
    """Serialize ReturnRecords as a BARE JSON LIST to <data_root>/<slug>/returns.json.

    returns.json stays a bare list (NO schema_version — regenerable; the cache FILE is versioned
    via its wrapper, not this). An empty list -> writes `[]` and returns the Path (NOT an error).
    REJECTS a record set spanning >1 distinct cik (per-slug boundary, mirrors write_changes).
    DETERMINISTIC SORT by (filing_date, cusip, security_type, change_type.value). The duplicate
    guard uses the FULL 4-tuple (filing_date, cusip, security_type, change_type) — matching the
    sort key. ATOMIC + PATH-SAFE.
    """
    target_dir, target_file = _safe_path(slug, constants.RETURNS_FILE, data_root)
    ciks = {r.cik for r in records}
    if len(ciks) > 1:
        raise DiscoveryError(f"write_returns record set spans multiple ciks: {sorted(ciks)}")
    seen: set[tuple[object, str, str, str]] = set()
    for r in records:
        key = (r.filing_date, r.cusip, r.security_type, r.change_type.value)
        if key in seen:
            raise DiscoveryError(
                f"duplicate (filing_date, cusip, security_type, change_type) {key} in "
                "returns record set"
            )
        seen.add(key)
    ordered = sorted(
        records,
        key=lambda r: (r.filing_date, r.cusip, r.security_type, r.change_type.value),
    )
    payload = [record.to_dict() for record in ordered]
    text = json.dumps(payload, indent=2)
    _atomic_write_json(
        target_dir, target_file, text, prefix=constants.RETURNS_TMP_PREFIX
    )
    logger.info("wrote %d return record(s) to %s", len(ordered), target_file)
    return target_file


def read_returns(
    slug: str,
    data_root: Path | str | None = None,
) -> list[ReturnRecord]:
    """Read <data_root>/<slug>/returns.json (a bare JSON list) -> [ReturnRecord].

    PATH-SAFE. A file containing `[]` -> []. MISSING FILE -> DiscoveryError (mirrors
    read_changes). Non-list top-level / non-dict item / invalid enum/date/coercion / failed
    invariant -> DiscoveryError (from from_dict / __post_init__).
    """
    _, target_file = _safe_path(slug, constants.RETURNS_FILE, data_root)
    if not target_file.exists():
        raise DiscoveryError(f"returns file not found for slug {slug!r}: {target_file}")

    text = target_file.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(
            f"returns file is not valid JSON ({target_file}): {exc}"
        ) from exc

    if not isinstance(data, list):
        raise DiscoveryError(
            f"returns file must contain a JSON list, got {type(data).__name__} "
            f"({target_file})"
        )

    records: list[ReturnRecord] = []
    for item in data:
        if not isinstance(item, dict):
            raise DiscoveryError(f"each returns entry must be an object ({target_file})")
        records.append(ReturnRecord.from_dict(item))
    return records


def read_cusip_map(
    data_root: Path | str | None = None,
) -> dict[str, CusipMapEntry]:
    """Read the SHARED <data_root>/cusip_ticker_map.json (a bare JSON list) -> dict keyed by cusip.

    MISSING FILE -> {} (NOT DiscoveryError): the shared cache is legitimately empty on first
    run for every investor (deliberate divergence from read_positions/read_filings, where a
    missing file implies a skipped pipeline step). A DUPLICATE cusip in the file -> DiscoveryError
    (corruption). Non-list top-level / non-dict element -> DiscoveryError. Forward-compat optional
    provenance fields are absorbed by CusipMapEntry.from_dict.
    """
    root = _resolved_root(data_root)
    target_file = constants.cusip_map_path(data_root).resolve()
    _assert_under_root(root, target_file)
    if not target_file.exists():
        return {}

    text = target_file.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(
            f"cusip map file is not valid JSON ({target_file}): {exc}"
        ) from exc

    if not isinstance(data, list):
        raise DiscoveryError(
            f"cusip map file must contain a JSON list, got {type(data).__name__} "
            f"({target_file})"
        )

    entries: dict[str, CusipMapEntry] = {}
    for item in data:
        if not isinstance(item, dict):
            raise DiscoveryError(f"each cusip map entry must be an object ({target_file})")
        entry = CusipMapEntry.from_dict(item)
        if entry.cusip in entries:
            raise DiscoveryError(
                f"duplicate cusip {entry.cusip!r} in cusip map file ({target_file})"
            )
        entries[entry.cusip] = entry
    return entries


def write_cusip_map(
    entries: dict[str, CusipMapEntry] | list[CusipMapEntry],
    data_root: Path | str | None = None,
) -> Path:
    """Serialize the SHARED cusip map as a BARE JSON LIST, SORTED by cusip. ATOMIC + PATH-SAFE.

    Accepts a dict (keyed by cusip) OR a list (both validated):
      - dict input: each key MUST equal entry.cusip (else DiscoveryError — catches a mis-keyed
        cache before it hits disk).
      - list input: reject DUPLICATE cusips (else DiscoveryError).
    OVERWRITES wholesale (the resolver owns the merge; see plan §5b/§6).
    """
    if isinstance(entries, dict):
        records: list[CusipMapEntry] = []
        for key, entry in entries.items():
            if key != entry.cusip:
                raise DiscoveryError(
                    f"cusip map dict key {key!r} != entry.cusip {entry.cusip!r}"
                )
            records.append(entry)
    else:
        seen: set[str] = set()
        records = []
        for entry in entries:
            if entry.cusip in seen:
                raise DiscoveryError(
                    f"duplicate cusip {entry.cusip!r} in cusip map list input"
                )
            seen.add(entry.cusip)
            records.append(entry)

    root = _resolved_root(data_root)
    target_file = constants.cusip_map_path(data_root).resolve()
    _assert_under_root(root, target_file)
    target_dir = target_file.parent

    ordered = sorted(records, key=lambda e: e.cusip)
    payload = [entry.to_dict() for entry in ordered]
    text = json.dumps(payload, indent=2)
    _atomic_write_json(target_dir, target_file, text, prefix=".cusipmap-")
    logger.info("wrote %d cusip map entr(ies) to %s", len(ordered), target_file)
    return target_file
