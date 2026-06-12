"""Investor-agnostic config loader. Degrades gracefully for unknown CIKs.

Any CIK in -> usable config out, but still requires the config file to exist. See plan §7.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from celebpm import constants
from celebpm.errors import ConfigError

logger = logging.getLogger(__name__)

_REQUIRED_KEYS = ("cik", "name", "fund", "slug", "notes")
_SLUG_RE = re.compile(constants.SLUG_PATTERN)


@dataclass(frozen=True)
class InvestorConfig:
    cik: str  # zero-padded 10-digit
    name: str  # operator label; "" / fallback if unknown
    fund: str
    slug: str  # data-dir name; auto-derived for unknown CIKs
    notes: str
    is_known: bool  # True if found in investors.json, False if synthesized


def load_all_investors(path: Path | str | None = None) -> dict[str, InvestorConfig]:
    """Read config/investors.json -> {padded_cik: InvestorConfig}.

    Validates required keys; raises ConfigError on malformed/unreadable file
    (root-cause, not silent skip). Defaults to constants.INVESTORS_CONFIG_PATH.

    v3 validations (all -> ConfigError):
      - each object's `slug` must match SLUG_PATTERN (^[a-z0-9_]+$).
      - slugs must be UNIQUE across all CIKs (no two investors share a data dir).
      - the JSON key must EQUAL the object's `cik` field (no key/object CIK mismatch).
    """
    cfg_path = Path(path) if path is not None else constants.INVESTORS_CONFIG_PATH

    try:
        text = cfg_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read investors config at {cfg_path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"investors config is not valid JSON ({cfg_path}): {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"investors config must be a JSON object, got {type(data).__name__}")

    result: dict[str, InvestorConfig] = {}
    seen_slugs: dict[str, str] = {}  # slug -> first cik that used it

    for key, obj in data.items():
        if not isinstance(obj, dict):
            raise ConfigError(f"investor entry {key!r} must be an object")

        for req in _REQUIRED_KEYS:
            if req not in obj:
                raise ConfigError(f"investor entry {key!r} missing required key {req!r}")

        cik_field = obj["cik"]
        slug = obj["slug"]
        name = obj["name"]
        fund = obj["fund"]
        notes = obj["notes"]

        for field_name, field_value in (
            ("cik", cik_field),
            ("slug", slug),
            ("name", name),
            ("fund", fund),
            ("notes", notes),
        ):
            if not isinstance(field_value, str):
                raise ConfigError(
                    f"investor entry {key!r} field {field_name!r} must be a string"
                )

        try:
            padded = constants.cik_to_padded(cik_field)
        except ValueError as exc:
            raise ConfigError(f"investor entry {key!r} has invalid cik {cik_field!r}: {exc}") from exc

        if key != cik_field:
            raise ConfigError(
                f"investor JSON key {key!r} does not equal object cik field {cik_field!r}"
            )

        if not _SLUG_RE.match(slug):
            raise ConfigError(
                f"investor entry {key!r} slug {slug!r} does not match {constants.SLUG_PATTERN!r}"
            )

        if slug in seen_slugs:
            raise ConfigError(
                f"duplicate slug {slug!r} used by both {seen_slugs[slug]!r} and {key!r}"
            )
        seen_slugs[slug] = key

        result[padded] = InvestorConfig(
            cik=padded,
            name=name,
            fund=fund,
            slug=slug,
            notes=notes,
            is_known=True,
        )

    return result


def load_investor(cik: str | int, path: Path | str | None = None) -> InvestorConfig:
    """Look up by CIK (padded internally). Synthesizes config for unknown CIKs.

    If not present, return InvestorConfig(is_known=False, slug=f"cik_{padded}",
    name="", fund="", notes=""). NEVER raises on an unknown CIK per se.
    Logs a WARNING when is_known is False.

    v3: a MISSING / malformed / unreadable config file raises ConfigError EVEN when
    looking up an unknown CIK (the loader needs the file to exist to know the CIK is unknown).
    """
    try:
        padded = constants.cik_to_padded(cik)
    except ValueError as exc:
        raise ConfigError(f"invalid CIK {cik!r}: {exc}") from exc

    investors = load_all_investors(path)
    known = investors.get(padded)
    if known is not None:
        return known

    logger.warning("CIK %s not found in investors config; synthesizing default config", padded)
    return InvestorConfig(
        cik=padded,
        name="",
        fund="",
        slug=f"cik_{padded}",
        notes="",
        is_known=False,
    )
