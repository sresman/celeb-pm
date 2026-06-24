"""Thin end-to-end orchestrator: load_investor -> EDGAR -> parse -> OpenFIGI -> diff ->
returns -> View 1 + View 2 CSVs. COMPOSE-ONLY — no business logic lives here (plan §4).

Also exposes a minimal `python -m celebpm.pipeline <cik>` runner (a runner, NOT a UI).
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from celebpm import storage
from celebpm.config_loader import load_investor
from celebpm.cusip_map import resolve_tickers
from celebpm.diff import compute_changes
from celebpm.discovery import discover_filings, latest_filing_per_period
from celebpm.edgar_client import EdgarClient, HttpClient
from celebpm.eodhd_client import EodhdClient
from celebpm.errors import DiscoveryError, EdgarError
from celebpm.models import FilingRecord, PositionRecord
from celebpm.openfigi_client import MappingClient, OpenFigiClient
from celebpm.parser import (
    locate_and_fetch_infotable,
    parse_positions_from_xml,
    refine_amendment_type,
)
from celebpm.price_cache import CachingPriceProvider
from celebpm.price_types import PriceClient
from celebpm.returns import compute_returns
from celebpm.views import (
    ConvictionAddsSummary,
    NewIdeasSummary,
    build_conviction_adds_view,
    build_new_ideas_view,
)
from celebpm.view_io import write_conviction_adds_view, write_new_ideas_view

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class PipelineResult:
    slug: str
    cik: str
    n_filings_discovered: int
    n_filings_selected: int
    n_filings_parsed: int
    n_filings_skipped: int
    skipped_periods: tuple[date, ...]
    n_positions: int
    n_changes: int
    n_returns: int
    n_new_ideas: int
    timeline_degraded: bool
    csv_path: Path
    summary_path: Path
    summary: NewIdeasSummary
    n_conviction_adds: int
    conviction_csv_path: Path
    conviction_summary_path: Path
    conviction_summary: ConvictionAddsSummary


def run_pipeline(
    cik: str | int,
    *,
    today: date,
    data_root: Path | str | None = None,
    edgar: HttpClient | None = None,
    figi: MappingClient | None = None,
    price_client: PriceClient | None = None,
    config_path: Path | str | None = None,
) -> PipelineResult:
    """Run the full Phase-1 pipeline for one investor (CIK), writing all 6 artifacts.

    Clients are injected for testing; defaults construct one real client each. The price
    provider (CachingPriceProvider) is built ONCE internally from the raw price_client. A
    single bad filing is skipped-and-warned (timeline_degraded). The SPY preflight (non-empty
    changes) is fatal; resolve_tickers partial is non-fatal.
    """
    edgar = edgar if edgar is not None else EdgarClient()
    figi = figi if figi is not None else OpenFigiClient.from_env()
    price_client = price_client if price_client is not None else EodhdClient.from_env()
    provider = CachingPriceProvider(price_client, data_root=data_root, today=today)

    config = load_investor(cik, config_path)
    slug = config.slug

    all_filings = discover_filings(config.cik, edgar)
    selected = latest_filing_per_period(all_filings)
    # Process ascending by period (do not rely on upstream ordering).
    selected = sorted(selected, key=lambda f: f.period_of_report)

    filings_out: list[FilingRecord] = []
    positions_out: list[PositionRecord] = []
    skipped_periods: list[date] = []

    for filing in selected:
        try:
            xml_text, index_payload = locate_and_fetch_infotable(filing, edgar)
            filing = refine_amendment_type(filing, edgar, index_payload)
            updated_filing, positions = parse_positions_from_xml(filing, xml_text)
        except (EdgarError, DiscoveryError) as exc:
            logger.warning(
                "SKIPPING filing %s (period %s): %s",
                filing.accession_number,
                filing.period_of_report,
                exc,
            )
            skipped_periods.append(filing.period_of_report)
            continue
        filings_out.append(updated_filing)
        positions_out.extend(positions)

    storage.write_filings(slug, filings_out, data_root)
    storage.write_positions(slug, positions_out, data_root)  # pre-ticker; overwritten below

    cache = storage.read_cusip_map(data_root)
    resolve = resolve_tickers(positions_out, figi, cache)
    storage.write_cusip_map(resolve.cache, data_root)
    storage.write_positions(slug, resolve.positions, data_root)  # re-persist WITH tickers
    if resolve.partial:
        logger.info("ticker resolution PARTIAL; misses retry next run")

    changes = compute_changes(resolve.positions)
    storage.write_changes(slug, changes, data_root)

    # Empty short-circuit: skip the SPY preflight entirely for an empty investor.
    returns = compute_returns(changes, provider) if changes else []
    storage.write_returns(slug, returns, data_root)

    view = build_new_ideas_view(
        config=config, positions=resolve.positions, changes=changes, returns=returns
    )
    csv_path, summary_path = write_new_ideas_view(view, data_root)

    conv_view = build_conviction_adds_view(
        config=config, positions=resolve.positions, changes=changes, returns=returns
    )
    conviction_csv_path, conviction_summary_path = write_conviction_adds_view(
        conv_view, data_root
    )

    n_skipped = len(skipped_periods)
    return PipelineResult(
        slug=slug,
        cik=config.cik,
        n_filings_discovered=len(all_filings),
        n_filings_selected=len(selected),
        n_filings_parsed=len(filings_out),
        n_filings_skipped=n_skipped,
        skipped_periods=tuple(skipped_periods),
        n_positions=len(resolve.positions),
        n_changes=len(changes),
        n_returns=len(returns),
        n_new_ideas=len(view.rows),
        timeline_degraded=n_skipped > 0,
        csv_path=csv_path,
        summary_path=summary_path,
        summary=view.summary,
        n_conviction_adds=len(conv_view.rows),
        conviction_csv_path=conviction_csv_path,
        conviction_summary_path=conviction_summary_path,
        conviction_summary=conv_view.summary,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="celebpm.pipeline", description="Run the 13F pipeline.")
    parser.add_argument("cik", help="investor CIK (any form; padded internally)")
    parser.add_argument("--data-root", default=None, help="output root (default: repo data/)")
    parser.add_argument(
        "--today", default=None, help="anchor date YYYY-MM-DD (default: today)"
    )
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today else date.today()
    result = run_pipeline(args.cik, today=today, data_root=args.data_root)
    print(f"slug={result.slug} cik={result.cik}")
    print(
        f"filings: discovered={result.n_filings_discovered} "
        f"selected={result.n_filings_selected} parsed={result.n_filings_parsed} "
        f"skipped={result.n_filings_skipped} timeline_degraded={result.timeline_degraded}"
    )
    print(
        f"positions={result.n_positions} changes={result.n_changes} "
        f"returns={result.n_returns} new_ideas={result.n_new_ideas} "
        f"conviction_adds={result.n_conviction_adds}"
    )
    print(f"csv={result.csv_path}")
    print(f"summary={result.summary_path}")
    print(f"conviction_csv={result.conviction_csv_path}")
    print(f"conviction_summary={result.conviction_summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
