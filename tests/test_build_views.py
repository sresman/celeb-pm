"""Runner tests for build_views: rebuild all three views from persisted JSON.

View 3 needs an EODHD fundamentals fetch; tests stay offline by pre-seeding the fundamentals
cache (cache hit) or injecting a FakeFundamentalsClient. No real HTTP."""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from celebpm import build_views, constants, storage
from celebpm.build_views import RebuildResult, main, rebuild_views
from celebpm.errors import ConfigError, DiscoveryError
from celebpm.models import (
    ChangeType,
    FundamentalsEntry,
    PositionChange,
    PositionRecord,
    ReturnRecord,
)
from tests.conftest import FakeFundamentalsClient, general_fundamentals

CIK = "0001777813"
SLUG = "test_inv"
CUSIP = "00846U101"

Q1 = date(2024, 3, 31)
Q1F = date(2024, 5, 15)
Q2 = date(2024, 6, 30)
Q2F = date(2024, 8, 14)
Q3F = date(2024, 11, 14)


# --------------------------------------------------------------------------------------
# seed factories (records constructed directly — the runner does NOT run the diff engine)
# --------------------------------------------------------------------------------------
def _position(*, period: date, filing_date: date, weight: float) -> PositionRecord:
    return PositionRecord(
        cik=CIK,
        accession_number="0001777813-24-000001",
        period=period,
        filing_date=filing_date,
        cusip=CUSIP,
        company_name="ALPHA CORP",
        title_of_class="COM",
        security_type="COMMON",
        put_call="",
        ticker="ALPHA",
        shares=1000,
        ssh_prnamt_type="SH",
        value_reported=100000,
        investment_discretion="SOLE",
        weight_pct_reported=weight,
        weight_pct_equity_only=weight,
    )


def _new_change() -> PositionChange:
    return PositionChange(
        cik=CIK,
        period=Q1,
        filing_date=Q1F,
        prior_period=date(2023, 12, 31),
        prior_filing_date=date(2024, 2, 14),
        cusip=CUSIP,
        security_type="COMMON",
        ticker="ALPHA",
        current_shares=1000,
        current_value_reported=100000,
        current_weight_pct=4.0,
        prior_shares=None,
        prior_value_reported=None,
        prior_weight_pct=None,
        shares_delta=None,
        shares_delta_pct=None,
        weight_delta_bps=None,
        value_delta=None,
        value_delta_pct=None,
        change_type=ChangeType.NEW,
        split_suspected=False,
    )


def _active_add_change() -> PositionChange:
    return PositionChange(
        cik=CIK,
        period=Q2,
        filing_date=Q2F,
        prior_period=Q1,
        prior_filing_date=Q1F,
        cusip=CUSIP,
        security_type="COMMON",
        ticker="ALPHA",
        current_shares=1300,
        current_value_reported=130000,
        current_weight_pct=6.0,
        prior_shares=1000,
        prior_value_reported=100000,
        prior_weight_pct=4.0,
        shares_delta=300,
        shares_delta_pct=30.0,
        weight_delta_bps=200.0,
        value_delta=30000,
        value_delta_pct=30.0,
        change_type=ChangeType.ACTIVE_ADD,
        split_suspected=False,
    )


def _return_rec(
    *, filing_date: date, period: date, next_filing_date: date, change_type: ChangeType
) -> ReturnRecord:
    is_new = change_type == ChangeType.NEW
    return ReturnRecord(
        cik=CIK,
        cusip=CUSIP,
        ticker="ALPHA",
        eodhd_symbol="ALPHA.US",
        security_type="COMMON",
        change_type=change_type,
        period=period,
        filing_date=filing_date,
        next_filing_date=next_filing_date,
        priced=True,
        is_underlying_price=False,
        price_on_filing_date=100.0,
        price_on_next_filing_date=110.0,
        next_period_high=115.0,
        next_period_low=95.0,
        next_period_high_date=filing_date,
        next_period_low_date=filing_date,
        filing_to_filing_return_pct=10.0,
        filing_to_next_period_high_pct=15.0,
        filing_to_next_period_low_pct=-5.0,
        entry_quarter_high=105.0 if is_new else None,
        entry_quarter_low=90.0 if is_new else None,
        best_case_entry_price=90.0 if is_new else None,
        worst_case_entry_price=105.0 if is_new else None,
        best_case_entry_return_pct=12.0 if is_new else None,
        worst_case_entry_return_pct=8.0 if is_new else None,
        cumulative_return_pct=20.0,
        cumulative_from_filing_date=filing_date,
        cumulative_to_filing_date=next_filing_date,
        spy_filing_to_filing_return_pct=4.0,
        spy_next_period_high_pct=6.0,
        spy_next_period_low_pct=-2.0,
        smh_filing_to_filing_return_pct=5.0,
        smh_next_period_high_pct=7.0,
        smh_next_period_low_pct=-3.0,
    )


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "investors.json"
    cfg.write_text(
        json.dumps(
            {
                CIK: {
                    "cik": CIK,
                    "name": "Test",
                    "fund": "Test LP",
                    "slug": SLUG,
                    "notes": "",
                }
            }
        ),
        encoding="utf-8",
    )
    return cfg


def _seed_fundamentals_cache(tmp_path: Path) -> None:
    """Pre-seed the shared fundamentals cache so the default-client runner is OFFLINE (cache hit)."""
    storage.write_fundamentals_cache(
        {
            "ALPHA.US": FundamentalsEntry(
                eodhd_symbol="ALPHA.US",
                sector="Technology",
                industry="Software",
                instrument_type="Common Stock",
                resolved=True,
                fetched_at="2024-01-01T00:00:00+00:00",
            )
        },
        data_root=tmp_path,
    )


def _seed_full(tmp_path: Path) -> None:
    _seed_fundamentals_cache(tmp_path)
    storage.write_positions(
        SLUG,
        [
            _position(period=Q1, filing_date=Q1F, weight=4.0),
            _position(period=Q2, filing_date=Q2F, weight=6.0),
        ],
        data_root=tmp_path,
    )
    storage.write_changes(SLUG, [_new_change(), _active_add_change()], data_root=tmp_path)
    storage.write_returns(
        SLUG,
        [
            _return_rec(
                filing_date=Q1F, period=Q1, next_filing_date=Q2F, change_type=ChangeType.NEW
            ),
            _return_rec(
                filing_date=Q2F,
                period=Q2,
                next_filing_date=Q3F,
                change_type=ChangeType.ACTIVE_ADD,
            ),
        ],
        data_root=tmp_path,
    )


def _data_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _header(csv_path: Path) -> list[str]:
    with csv_path.open(encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


# --------------------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------------------
def test_rebuild_views_writes_all_artifacts(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    _seed_full(tmp_path)  # pre-seeds the fundamentals cache -> default client is offline (hit)

    result = rebuild_views(CIK, data_root=tmp_path, config_path=cfg)
    assert isinstance(result, RebuildResult)
    assert result.slug == SLUG
    assert result.new_ideas_csv_path.exists()
    assert result.new_ideas_summary_path.exists()
    assert result.conviction_csv_path.exists()
    assert result.conviction_summary_path.exists()
    assert result.lifecycle_csv_path.exists()

    assert result.n_new_ideas >= 1
    assert result.n_conviction_adds >= 1
    assert result.n_lifecycle_rows == 2  # NEW + ACTIVE_ADD, one cycle
    assert len(_data_rows(result.new_ideas_csv_path)) >= 1
    assert len(_data_rows(result.conviction_csv_path)) >= 1
    assert len(_data_rows(result.lifecycle_csv_path)) == 2

    assert _header(result.new_ideas_csv_path) == list(constants.NEW_IDEAS_COLUMNS)
    assert _header(result.conviction_csv_path) == list(constants.CONVICTION_ADDS_COLUMNS)
    assert _header(result.lifecycle_csv_path) == list(constants.LIFECYCLE_COLUMNS)

    ni_sum = json.loads(result.new_ideas_summary_path.read_text())
    cv_sum = json.loads(result.conviction_summary_path.read_text())
    assert constants.SUMMARY_KEY_TOTAL_NEW in ni_sum
    assert constants.CONVICTION_KEY_TOTAL_ADDS in cv_sum

    # View 3: NO classifications file -> sector falls back to the fundamentals cache; theme blank.
    lc_rows = _data_rows(result.lifecycle_csv_path)
    assert {r["sector"] for r in lc_rows} == {"Technology"}
    assert {r["theme"] for r in lc_rows} == {""}
    assert {r["cycle_id"] for r in lc_rows} == {"ALPHA_COMMON_1"}
    assert sorted(r["quarters_since_entry"] for r in lc_rows) == ["0", "1"]


def test_rebuild_views_classifications_win_over_fundamentals(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    _seed_full(tmp_path)  # fundamentals cache has ALPHA.US -> "Technology"
    # A manual classification for ALPHA must override the fundamentals sector + supply a theme.
    (tmp_path / constants.TICKER_CLASSIFICATIONS_FILE).write_text(
        json.dumps(
            {"ALPHA": {"sector": "Semiconductors", "industry": "Chip Design", "theme": "AI Chips"}}
        ),
        encoding="utf-8",
    )
    result = rebuild_views(CIK, data_root=tmp_path, config_path=cfg)
    lc_rows = _data_rows(result.lifecycle_csv_path)
    assert {r["sector"] for r in lc_rows} == {"Semiconductors"}
    assert {r["industry"] for r in lc_rows} == {"Chip Design"}
    assert {r["theme"] for r in lc_rows} == {"AI Chips"}


def test_rebuild_views_fetches_fundamentals_when_uncached(tmp_path: Path) -> None:
    # No pre-seeded cache -> the runner FETCHES via the injected client, then writes the cache.
    cfg = _write_config(tmp_path)
    storage.write_positions(
        SLUG,
        [
            _position(period=Q1, filing_date=Q1F, weight=4.0),
            _position(period=Q2, filing_date=Q2F, weight=6.0),
        ],
        data_root=tmp_path,
    )
    storage.write_changes(SLUG, [_new_change(), _active_add_change()], data_root=tmp_path)
    storage.write_returns(
        SLUG,
        [
            _return_rec(
                filing_date=Q1F, period=Q1, next_filing_date=Q2F, change_type=ChangeType.NEW
            ),
            _return_rec(
                filing_date=Q2F, period=Q2, next_filing_date=Q3F,
                change_type=ChangeType.ACTIVE_ADD,
            ),
        ],
        data_root=tmp_path,
    )
    fund = FakeFundamentalsClient(
        {"ALPHA.US": general_fundamentals(sector="Energy", instrument_type="Common Stock")}
    )
    result = rebuild_views(
        CIK, data_root=tmp_path, config_path=cfg, fundamentals_client=fund
    )
    assert fund.fetched == ["ALPHA.US"]  # one network call
    assert (tmp_path / constants.FUNDAMENTALS_CACHE_FILE).exists()
    cache = storage.read_fundamentals_cache(tmp_path)
    assert cache["ALPHA.US"].sector == "Energy"
    lc_rows = _data_rows(result.lifecycle_csv_path)
    assert {r["sector"] for r in lc_rows} == {"Energy"}


def test_rebuild_views_no_pandas_import() -> None:
    # Guards DIRECT binding only: pandas is still imported transitively via view_io,
    # which is expected and acceptable. (Do NOT assert on sys.modules — fragile.)
    assert not hasattr(build_views, "pd")
    assert "pandas" not in vars(build_views)


def test_rebuild_views_missing_positions_raises(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    storage.write_changes(SLUG, [_new_change(), _active_add_change()], data_root=tmp_path)
    storage.write_returns(
        SLUG,
        [
            _return_rec(
                filing_date=Q1F, period=Q1, next_filing_date=Q2F, change_type=ChangeType.NEW
            )
        ],
        data_root=tmp_path,
    )
    with pytest.raises(DiscoveryError) as exc:
        rebuild_views(CIK, data_root=tmp_path, config_path=cfg)
    msg = str(exc.value)
    assert "positions" in msg
    assert SLUG in msg


def test_rebuild_views_empty_returns_ok(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    storage.write_positions(
        SLUG,
        [
            _position(period=Q1, filing_date=Q1F, weight=4.0),
            _position(period=Q2, filing_date=Q2F, weight=6.0),
        ],
        data_root=tmp_path,
    )
    storage.write_changes(SLUG, [_new_change(), _active_add_change()], data_root=tmp_path)
    storage.write_returns(SLUG, [], data_root=tmp_path)

    result = rebuild_views(CIK, data_root=tmp_path, config_path=cfg)
    assert result.new_ideas_csv_path.exists()
    assert result.new_ideas_summary_path.exists()
    assert result.conviction_csv_path.exists()
    assert result.conviction_summary_path.exists()


def test_rebuild_views_empty_state(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    storage.write_positions(SLUG, [], data_root=tmp_path)
    storage.write_changes(SLUG, [], data_root=tmp_path)
    storage.write_returns(SLUG, [], data_root=tmp_path)

    result = rebuild_views(CIK, data_root=tmp_path, config_path=cfg)
    assert _header(result.new_ideas_csv_path) == list(constants.NEW_IDEAS_COLUMNS)
    assert _header(result.conviction_csv_path) == list(constants.CONVICTION_ADDS_COLUMNS)
    assert _header(result.lifecycle_csv_path) == list(constants.LIFECYCLE_COLUMNS)
    assert len(_data_rows(result.new_ideas_csv_path)) == 0
    assert len(_data_rows(result.conviction_csv_path)) == 0
    assert result.n_lifecycle_rows == 0
    assert len(_data_rows(result.lifecycle_csv_path)) == 0

    assert main([CIK, "--data-root", str(tmp_path), "--config", str(cfg)]) == 0


def test_rebuild_views_configerror_propagates(tmp_path: Path) -> None:
    missing_cfg = tmp_path / "does_not_exist.json"
    with pytest.raises(ConfigError):
        rebuild_views(CIK, data_root=tmp_path, config_path=missing_cfg)
    # main does NOT swallow ConfigError as a DiscoveryError exit-1 path.
    with pytest.raises(ConfigError):
        main([CIK, "--data-root", str(tmp_path), "--config", str(missing_cfg)])


def test_main_smoke_exit_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _write_config(tmp_path)
    _seed_full(tmp_path)
    rc = main([CIK, "--data-root", str(tmp_path), "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "new_ideas" in out
    assert "conviction_adds" in out
    assert "position_lifecycles" in out
    assert SLUG in out
    views_dir = tmp_path / SLUG / constants.VIEWS_DIR
    assert (views_dir / constants.NEW_IDEAS_FILE).exists()
    assert (views_dir / constants.NEW_IDEAS_SUMMARY_FILE).exists()
    assert (views_dir / constants.CONVICTION_ADDS_FILE).exists()
    assert (views_dir / constants.CONVICTION_ADDS_SUMMARY_FILE).exists()
    assert (views_dir / constants.LIFECYCLE_FILE).exists()


def test_main_missing_file_exit_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = _write_config(tmp_path)
    rc = main([CIK, "--data-root", str(tmp_path), "--config", str(cfg)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "error:" in err
    assert "pipeline" in err
