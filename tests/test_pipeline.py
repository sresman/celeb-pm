"""End-to-end orchestrator integration tests (FAKE clients, tmp data_root)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from celebpm import constants
from celebpm.constants import JSONObject
from celebpm.discovery import discover_filings, latest_filing_per_period
from celebpm.models import FilingRecord
from celebpm.openfigi_client import MapMatch, MapResult
from celebpm.pipeline import run_pipeline
from tests.conftest import (
    FakeClient,
    FakeFundamentalsClient,
    FakeMappingClient,
    FakePriceClient,
    build_series,
    general_fundamentals,
)

CIK = "0001777813"
SLUG = "atreides_management"
TODAY = date(2026, 6, 1)

CUSIP_ALPHA = "00846U101"
CUSIP_BETA = "09247X101"

_FIXTURES = Path(__file__).parent / "fixtures"


def _xml(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _json_fixture(name: str) -> JSONObject:
    data = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _submissions() -> tuple[JSONObject, JSONObject]:
    return _json_fixture("submissions_sample.json"), _json_fixture("submissions_overflow.json")


def _selected() -> list[FilingRecord]:
    subs, ov = _submissions()
    routes = {
        constants.submissions_url(CIK): subs,
        constants.submissions_overflow_url("CIK0001777813-submissions-001.json"): ov,
    }
    fl = discover_filings(CIK, FakeClient(routes))
    return sorted(latest_filing_per_period(fl), key=lambda f: f.period_of_report)


def _index_for(filing: FilingRecord) -> JSONObject:
    # Reusable directory listing with the infoTable hint (filename matched by parser).
    return {
        "directory": {
            "name": filing.filing_index_url,
            "item": [
                {"name": "primary_doc.xml", "type": "text"},
                {"name": "form13fInfoTable.xml", "type": "text"},
            ],
        }
    }


def _map_result(cusip: str, ticker: str, name: str) -> MapResult:
    return MapResult(
        cusip=cusip,
        matches=(
            MapMatch(
                ticker=ticker,
                name=name,
                exch_code="US",
                security_type="Common Stock",
                security_type2="Common Stock",
                market_sector="Equity",
                composite_figi="BBG000000001",
                figi="BBG000000002",
            ),
        ),
    )


def _build_routes(
    selected: list[FilingRecord],
    *,
    xml_by_period: dict[date, str],
    raise_period: date | None = None,
) -> FakeClient:
    subs, ov = _submissions()
    json_routes: dict[str, JSONObject] = {
        constants.submissions_url(CIK): subs,
        constants.submissions_overflow_url("CIK0001777813-submissions-001.json"): ov,
    }
    text_routes: dict[str, str] = {}
    for filing in selected:
        if raise_period is not None and filing.period_of_report == raise_period:
            continue  # omit routes -> locate_and_fetch raises EdgarError (no route)
        index_url = constants.filing_index_json_url(filing.filing_index_url)
        json_routes[index_url] = _index_for(filing)
        xml_url = filing.filing_index_url + "form13fInfoTable.xml"
        text_routes[xml_url] = xml_by_period[filing.period_of_report]
        if filing.amendment and filing.primary_doc:
            # refine_amendment_type fetches the cover page (primary_doc.xml). Route a benign
            # cover page so refine leaves amendment_type UNKNOWN + WARN (no abort).
            cover_url = filing.filing_index_url + filing.primary_doc
            text_routes[cover_url] = "<edgarSubmission></edgarSubmission>"
    return FakeClient(json_routes, text_routes)


def _price_client() -> FakePriceClient:
    closes = {date(2023, 1, 1) + __import__("datetime").timedelta(days=7 * i): 100.0 + i for i in range(220)}
    series = {
        constants.SPY_BENCHMARK_SYMBOL: build_series(constants.SPY_BENCHMARK_SYMBOL, closes),
        constants.SMH_BENCHMARK_SYMBOL: build_series(constants.SMH_BENCHMARK_SYMBOL, closes),
        "ALPHA.US": build_series("ALPHA.US", closes),
        "BETA.US": build_series("BETA.US", closes),
    }
    return FakePriceClient(series)


def _figi() -> FakeMappingClient:
    return FakeMappingClient(
        {
            CUSIP_ALPHA: _map_result(CUSIP_ALPHA, "ALPHA", "ALPHA CORP"),
            CUSIP_BETA: _map_result(CUSIP_BETA, "BETA", "BETA INC"),
        }
    )


def _fundamentals() -> FakeFundamentalsClient:
    """ALPHA.US -> a sector/industry; BETA.US -> an ETF (sector resolves to the ETF label)."""
    return FakeFundamentalsClient(
        {
            "ALPHA.US": general_fundamentals(
                sector="Technology", industry="Software", instrument_type="Common Stock"
            ),
            "BETA.US": general_fundamentals(instrument_type="ETF"),
        }
    )


def test_full_pipeline_produces_all_artifacts(tmp_path: Path) -> None:
    selected = _selected()
    periods = [f.period_of_report for f in selected]
    # earliest quarter alpha-only; all later quarters alpha+beta -> BETA is a NEW.
    xml_by_period = {periods[0]: _xml("infotable_alpha_only.xml")}
    for p in periods[1:]:
        xml_by_period[p] = _xml("infotable_common.xml")

    # Seed a manual classification for ALPHA -> it must WIN over the EODHD fundamentals sector.
    (tmp_path / constants.TICKER_CLASSIFICATIONS_FILE).write_text(
        json.dumps(
            {"ALPHA": {"sector": "Semiconductors", "industry": "Chip Design", "theme": "AI Chips"}}
        ),
        encoding="utf-8",
    )

    edgar = _build_routes(selected, xml_by_period=xml_by_period)
    result = run_pipeline(
        CIK, today=TODAY, data_root=tmp_path, edgar=edgar, figi=_figi(),
        price_client=_price_client(), fundamentals_client=_fundamentals(),
    )

    for fname in (
        constants.FILINGS_FILE,
        constants.POSITIONS_FILE,
        constants.CHANGES_FILE,
        constants.RETURNS_FILE,
    ):
        assert (tmp_path / SLUG / fname).exists()
    assert (tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_FILE).exists()
    assert (tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_SUMMARY_FILE).exists()

    # internally-consistent counts
    assert result.n_filings_parsed + result.n_filings_skipped == result.n_filings_selected
    assert result.timeline_degraded == (result.n_filings_skipped > 0)
    assert result.n_filings_skipped == 0
    assert result.n_new_ideas >= 1  # BETA NEW

    # result.summary matches on-disk summary JSON
    disk = json.loads(
        (tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_SUMMARY_FILE).read_text()
    )
    assert disk[constants.SUMMARY_KEY_TOTAL_NEW] == result.summary.total_new
    assert result.summary.total_new == result.n_new_ideas

    # CSV columns
    import pandas as pd

    df = pd.read_csv(
        tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_FILE,
        keep_default_na=False, dtype=str,
    )
    assert list(df.columns) == list(constants.NEW_IDEAS_COLUMNS)

    # View 2 (Conviction Tracker) artifacts exist
    assert (tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_FILE).exists()
    assert (
        tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_SUMMARY_FILE
    ).exists()

    # result path fields point at the canonical on-disk locations
    assert (
        result.conviction_csv_path
        == tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_FILE
    )
    assert (
        result.conviction_summary_path
        == tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_SUMMARY_FILE
    )

    # n_conviction_adds is a non-negative int tied to the summary's total_adds (wiring guard).
    # NOTE: do NOT assert >= 1 — the fixture guarantees a BETA NEW (View 1) but not an
    # ACTIVE_ADD (View 2), which needs a same-CUSIP weight increase above threshold across
    # consecutive quarters that this fixture does not clearly create.
    assert isinstance(result.n_conviction_adds, int)
    assert result.n_conviction_adds >= 0
    assert result.n_conviction_adds == result.conviction_summary.total_adds

    # on-disk conviction summary matches the result object
    conv_disk = json.loads(
        (
            tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_SUMMARY_FILE
        ).read_text()
    )
    assert conv_disk[constants.CONVICTION_KEY_TOTAL_ADDS] == result.conviction_summary.total_adds

    # conviction CSV columns
    conv_df = pd.read_csv(
        tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_FILE,
        keep_default_na=False, dtype=str,
    )
    assert list(conv_df.columns) == list(constants.CONVICTION_ADDS_COLUMNS)

    # ascending period order in filings.json
    filings_disk = json.loads((tmp_path / SLUG / constants.FILINGS_FILE).read_text())
    written_periods = [f["period_of_report"] for f in filings_disk]
    # storage sorts positions but writes filings in input (ascending) order
    assert written_periods == sorted(written_periods)

    # View 3 (Position Lifecycle) artifact + fundamentals cache
    lifecycle_csv = tmp_path / SLUG / constants.VIEWS_DIR / constants.LIFECYCLE_FILE
    assert lifecycle_csv.exists()
    assert result.lifecycle_csv_path == lifecycle_csv
    assert (tmp_path / constants.FUNDAMENTALS_CACHE_FILE).exists()

    lc_df = pd.read_csv(lifecycle_csv, keep_default_na=False, dtype=str)
    assert list(lc_df.columns) == list(constants.LIFECYCLE_COLUMNS)
    # one row per change record (every quarter held is a lifecycle row)
    assert result.n_lifecycle_rows == result.n_changes == len(lc_df)
    # every entry-quarter row reads quarters_since_entry == 0 and cum_return_from_entry == 0.0
    entries = lc_df[lc_df["quarters_since_entry"] == "0"]
    assert len(entries) >= 1
    assert set(entries["cum_return_from_entry_pct"]) == {"0.0"}
    # BETA is unclassified -> falls back to the EODHD fundamentals ETF sector; theme blank.
    beta_rows = lc_df[lc_df["ticker"] == "BETA"]
    assert len(beta_rows) >= 1
    assert set(beta_rows["sector"]) == {constants.SECTOR_ETF_LABEL}
    assert set(beta_rows["theme"]) == {""}
    # ALPHA is classified -> the manual classification WINS over the fundamentals "Technology".
    alpha_rows = lc_df[lc_df["ticker"] == "ALPHA"]
    assert set(alpha_rows["sector"]) == {"Semiconductors"}
    assert set(alpha_rows["industry"]) == {"Chip Design"}
    assert set(alpha_rows["theme"]) == {"AI Chips"}
    # rows are sorted by (cycle_id, quarters_since_entry)
    keys = list(zip(lc_df["cycle_id"], lc_df["quarters_since_entry"].astype(int)))
    assert keys == sorted(keys)
    # SMH benchmark columns are present and populated for priced rows.
    assert "smh_period_return_pct" in lc_df.columns
    assert "excess_vs_smh_pct" in lc_df.columns
    priced_lc = lc_df[lc_df["priced"] == "True"]
    assert (priced_lc["smh_period_return_pct"] != "").any()
    assert (priced_lc["excess_vs_smh_pct"] != "").any()


def test_single_quarter_empty_feed(tmp_path: Path) -> None:
    selected = _selected()
    # Keep ONLY the earliest filing -> 1 quarter -> 0 changes -> 0 NEW.
    one = selected[:1]
    xml_by_period = {one[0].period_of_report: _xml("infotable_alpha_only.xml")}
    edgar = _build_routes(one, xml_by_period=xml_by_period)
    result = run_pipeline(
        CIK, today=TODAY, data_root=tmp_path, edgar=edgar, figi=_figi(),
        price_client=_price_client(), fundamentals_client=_fundamentals(),
    )
    assert result.n_changes == 0
    assert result.n_returns == 0
    assert result.n_new_ideas == 0
    csv_path = tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_FILE
    import pandas as pd

    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    assert list(df.columns) == list(constants.NEW_IDEAS_COLUMNS)
    assert len(df) == 0
    disk = json.loads(
        (tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_SUMMARY_FILE).read_text()
    )
    assert disk[constants.SUMMARY_KEY_TOTAL_NEW] == 0
    assert disk[constants.SUMMARY_KEY_WIN_RATE_PCT] is None

    # View 2 empty-state: one quarter -> 0 changes -> 0 adds (header-only CSV).
    assert result.n_conviction_adds == 0
    conv_csv = tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_FILE
    conv_df = pd.read_csv(conv_csv, keep_default_na=False, dtype=str)
    assert list(conv_df.columns) == list(constants.CONVICTION_ADDS_COLUMNS)
    assert len(conv_df) == 0
    conv_disk = json.loads(
        (
            tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_SUMMARY_FILE
        ).read_text()
    )
    assert conv_disk[constants.CONVICTION_KEY_TOTAL_ADDS] == 0

    # View 3 empty-state: one quarter -> 0 changes -> 0 lifecycle rows (header-only CSV).
    assert result.n_lifecycle_rows == 0
    lc_csv = tmp_path / SLUG / constants.VIEWS_DIR / constants.LIFECYCLE_FILE
    lc_df = pd.read_csv(lc_csv, keep_default_na=False, dtype=str)
    assert list(lc_df.columns) == list(constants.LIFECYCLE_COLUMNS)
    assert len(lc_df) == 0


def test_bad_filing_skipped(tmp_path: Path) -> None:
    selected = _selected()
    periods = [f.period_of_report for f in selected]
    xml_by_period = {periods[0]: _xml("infotable_alpha_only.xml")}
    for p in periods[1:]:
        xml_by_period[p] = _xml("infotable_common.xml")
    # omit routes for the SECOND filing -> EdgarError on fetch -> skip
    bad_period = periods[1]
    edgar = _build_routes(selected, xml_by_period=xml_by_period, raise_period=bad_period)
    result = run_pipeline(
        CIK, today=TODAY, data_root=tmp_path, edgar=edgar, figi=_figi(),
        price_client=_price_client(), fundamentals_client=_fundamentals(),
    )
    assert result.n_filings_skipped == 1
    assert bad_period in result.skipped_periods
    assert result.timeline_degraded is True
    # pipeline still produces a CSV
    assert (tmp_path / SLUG / constants.VIEWS_DIR / constants.NEW_IDEAS_FILE).exists()
    # View 2 artifacts are produced even when a filing is skipped
    assert (tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_FILE).exists()
    assert (
        tmp_path / SLUG / constants.VIEWS_DIR / constants.CONVICTION_ADDS_SUMMARY_FILE
    ).exists()
    # View 3 artifact is produced even when a filing is skipped
    assert (tmp_path / SLUG / constants.VIEWS_DIR / constants.LIFECYCLE_FILE).exists()
