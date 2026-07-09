"""Standalone runner: rebuild View 1 + View 2 + View 3 artifacts from already-persisted JSON.

COMPOSE-ONLY — no business logic, no DIRECT pandas import (pandas stays a single import site in
view_io.py). Reads positions/changes/returns via storage.read_*, builds all three views, writes
them. View 3 (Position Lifecycle) draws sector/industry/theme from the hand-maintained
`ticker_classifications.json` (PRIMARY), falling back to the EODHD fundamentals cache. To populate
that fallback this runner performs ONE network step — the EODHD fundamentals fetch — over the
symbols in returns.json, caching results (and misses) so re-runs are offline. It degrades
GRACEFULLY without an API key or classifications file: sector/industry/theme render blank and the
rebuild still completes. Also exposes `python -m celebpm.build_views <cik>` (a runner, NOT a UI).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from celebpm import storage
from celebpm.config_loader import load_investor
from celebpm.eodhd_client import EodhdClient
from celebpm.errors import DiscoveryError
from celebpm.fundamentals import resolve_fundamentals
from celebpm.price_types import FundamentalsClient
from celebpm.view_io import (
    write_conviction_adds_view,
    write_new_ideas_view,
    write_position_lifecycle_view,
)
from celebpm.views import (
    build_conviction_adds_view,
    build_new_ideas_view,
    build_position_lifecycle_view,
)


@dataclass(frozen=True, kw_only=True)
class RebuildResult:
    slug: str
    cik: str
    n_new_ideas: int
    n_conviction_adds: int
    n_lifecycle_rows: int
    new_ideas_csv_path: Path
    new_ideas_summary_path: Path
    conviction_csv_path: Path
    conviction_summary_path: Path
    lifecycle_csv_path: Path


def rebuild_views(
    cik: str | int,
    *,
    data_root: Path | str | None = None,
    config_path: Path | str | None = None,
    fundamentals_client: FundamentalsClient | None = None,
) -> RebuildResult:
    """Rebuild ALL THREE views for one investor (CIK) from persisted JSON.

    Reads positions/changes/returns from <data_root>/<slug>/, builds View 1 + View 2 + View 3,
    writes all five artifacts. The ONLY network is the EODHD fundamentals fetch for View 3
    (fundamentals_client defaults to EodhdClient.from_env(); injectable for tests); its results
    + misses are cached, so subsequent runs are offline. A missing input file raises
    DiscoveryError (propagated, not re-wrapped). A missing/malformed config FILE raises
    ConfigError (uncaught — hard setup error).
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

    # View 3 — fundamentals fetch (the one network step; cached + graceful without a key).
    fundamentals_client = (
        fundamentals_client if fundamentals_client is not None else EodhdClient.from_env()
    )
    fund_symbols = {r.eodhd_symbol for r in returns if r.eodhd_symbol is not None}
    fund_cache = storage.read_fundamentals_cache(data_root)
    resolve_fundamentals(fund_symbols, fundamentals_client, fund_cache)
    storage.write_fundamentals_cache(fund_cache, data_root)
    classifications = storage.read_ticker_classifications(data_root)
    lifecycle_view = build_position_lifecycle_view(
        config=config,
        positions=positions,
        changes=changes,
        returns=returns,
        fundamentals=fund_cache,
        classifications=classifications,
    )

    ni_csv, ni_sum = write_new_ideas_view(new_view, data_root)
    cv_csv, cv_sum = write_conviction_adds_view(conv_view, data_root)
    lc_csv = write_position_lifecycle_view(lifecycle_view, data_root)

    return RebuildResult(
        slug=slug,
        cik=config.cik,
        n_new_ideas=len(new_view.rows),
        n_conviction_adds=len(conv_view.rows),
        n_lifecycle_rows=len(lifecycle_view.rows),
        new_ideas_csv_path=ni_csv,
        new_ideas_summary_path=ni_sum,
        conviction_csv_path=cv_csv,
        conviction_summary_path=cv_sum,
        lifecycle_csv_path=lc_csv,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="celebpm.build_views",
        description=(
            "Rebuild View 1 + View 2 + View 3 artifacts from persisted JSON "
            "(one network step: EODHD fundamentals for View 3; cached + graceful without a key)."
        ),
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
    print(
        f"position_lifecycles: rows={result.n_lifecycle_rows} csv={result.lifecycle_csv_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
