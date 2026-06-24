"""Standalone runner: rebuild View 1 + View 2 artifacts from already-persisted JSON.

COMPOSE-ONLY — no business logic, no network clients, no DIRECT pandas import (pandas stays a
single import site in view_io.py). Reads positions/changes/returns via storage.read_*, builds
both views, writes both. Also exposes `python -m celebpm.build_views <cik>` (a runner, NOT a UI).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from celebpm import storage
from celebpm.config_loader import load_investor
from celebpm.errors import DiscoveryError
from celebpm.view_io import write_conviction_adds_view, write_new_ideas_view
from celebpm.views import build_conviction_adds_view, build_new_ideas_view


@dataclass(frozen=True, kw_only=True)
class RebuildResult:
    slug: str
    cik: str
    n_new_ideas: int
    n_conviction_adds: int
    new_ideas_csv_path: Path
    new_ideas_summary_path: Path
    conviction_csv_path: Path
    conviction_summary_path: Path


def rebuild_views(
    cik: str | int,
    *,
    data_root: Path | str | None = None,
    config_path: Path | str | None = None,
) -> RebuildResult:
    """Rebuild BOTH views for one investor (CIK) from persisted JSON. No network.

    Reads positions/changes/returns from <data_root>/<slug>/, builds View 1 + View 2, writes
    all four artifacts. A missing input file raises DiscoveryError (propagated, not re-wrapped:
    storage.read_* already carries a clear path-bearing message). A missing/malformed config
    FILE raises ConfigError (uncaught — hard setup error).
    """
    config = load_investor(cik, config_path)
    slug = config.slug

    positions = storage.read_positions(slug, data_root)
    changes = storage.read_changes(slug, data_root)
    returns = storage.read_returns(slug, data_root)

    new_view = build_new_ideas_view(
        config=config, positions=positions, changes=changes, returns=returns
    )
    conv_view = build_conviction_adds_view(
        config=config, positions=positions, changes=changes, returns=returns
    )

    ni_csv, ni_sum = write_new_ideas_view(new_view, data_root)
    cv_csv, cv_sum = write_conviction_adds_view(conv_view, data_root)

    return RebuildResult(
        slug=slug,
        cik=config.cik,
        n_new_ideas=len(new_view.rows),
        n_conviction_adds=len(conv_view.rows),
        new_ideas_csv_path=ni_csv,
        new_ideas_summary_path=ni_sum,
        conviction_csv_path=cv_csv,
        conviction_summary_path=cv_sum,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="celebpm.build_views",
        description="Rebuild View 1 + View 2 CSV/summary artifacts from persisted JSON (no network).",
    )
    parser.add_argument("cik", help="investor CIK (any form; padded internally)")
    parser.add_argument("--data-root", default=None, help="data root (default: repo data/)")
    parser.add_argument("--config", default=None, help="investors.json path (default: repo config/)")
    args = parser.parse_args(argv)
    try:
        result = rebuild_views(args.cik, data_root=args.data_root, config_path=args.config)
    except DiscoveryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "hint: run `python -m celebpm.pipeline <CIK>` first to populate the JSON.",
            file=sys.stderr,
        )
        return 1
    print(f"slug={result.slug} cik={result.cik}")
    print(
        f"new_ideas: rows={result.n_new_ideas} csv={result.new_ideas_csv_path} "
        f"summary={result.new_ideas_summary_path}"
    )
    print(
        f"conviction_adds: rows={result.n_conviction_adds} csv={result.conviction_csv_path} "
        f"summary={result.conviction_summary_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
