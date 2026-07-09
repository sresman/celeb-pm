"""View 1 + View 2 CSV + summary-JSON writers. The SINGLE pandas import in the codebase.

pandas is the one justified `Any`-narrowing boundary (see plan §0/§3.2). Every public helper
returns a Path / tuple[Path, Path] — no pandas type escapes this module. Writes are atomic
(stage both temp files, then os.replace both) and path-safe via storage.safe_data_path.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd  # pandas boundary: untyped (the single justified Any edge — plan §3.2)

from celebpm import constants, storage
from celebpm.views import (
    ConvictionAddRow,
    ConvictionAddsView,
    NewIdeaRow,
    NewIdeasView,
    PositionLifecycleRow,
    PositionLifecycleView,
)


def _fmt_date(value: date) -> str:
    return value.isoformat()


def _fmt_exit(value: date | None) -> str:
    return value.isoformat() if value is not None else constants.EXIT_CURRENT_LABEL


def _fmt_optional_date(value: date | None) -> str | None:
    """ISO string, or None (rendered as the CSV NA rep). NOT the View-1 'CURRENT' label."""
    return value.isoformat() if value is not None else None


def row_to_dict(row: NewIdeaRow) -> dict[str, object]:
    """One CSV row as a dict keyed by NEW_IDEAS_COLUMNS.

    Dates -> ISO strings; exit_quarter None -> "CURRENT"; bools -> "True"/"False" strings;
    None numerics pass through (rendered as the NA rep by to_csv).
    """
    return {
        "quarter": _fmt_date(row.quarter),
        "ticker": row.ticker_display,
        "company": row.company,
        "security_type": row.security_type,
        "is_option": str(row.is_option),
        "is_underlying_price": str(row.is_underlying_price),
        "initial_weight_pct": row.initial_weight_pct,
        "best_case_entry_return_pct": row.best_case_entry_return_pct,
        "worst_case_entry_return_pct": row.worst_case_entry_return_pct,
        "filing_to_filing_return_pct": row.filing_to_filing_return_pct,
        "filing_to_next_period_high_pct": row.filing_to_next_period_high_pct,
        "filing_to_next_period_low_pct": row.filing_to_next_period_low_pct,
        "excess_filing_to_filing_pct": row.excess_filing_to_filing_pct,
        "excess_next_period_high_pct": row.excess_next_period_high_pct,
        "excess_next_period_low_pct": row.excess_next_period_low_pct,
        "smh_excess_filing_to_filing_pct": row.smh_excess_filing_to_filing_pct,
        "smh_excess_next_period_high_pct": row.smh_excess_next_period_high_pct,
        "smh_excess_next_period_low_pct": row.smh_excess_next_period_low_pct,
        "cumulative_return_pct": row.cumulative_return_pct,
        "quarters_held": row.quarters_held,
        "max_weight_pct": row.max_weight_pct,
        "exit_quarter": _fmt_exit(row.exit_quarter),
        "became_active_add": str(row.became_active_add),
        "priced": str(row.priced),
        "cusip": row.cusip,
        "filing_date": _fmt_date(row.filing_date),
    }


def _build_dataframe(view: NewIdeasView) -> "pd.DataFrame":
    records = [row_to_dict(r) for r in view.rows]
    if not records:
        # Empty feed: explicit columns so the header-only CSV is still well-formed.
        return pd.DataFrame(data=[], columns=list(constants.NEW_IDEAS_COLUMNS))
    return pd.DataFrame.from_records(records, columns=list(constants.NEW_IDEAS_COLUMNS))


def _write_csv_atomic(
    df: "pd.DataFrame", csv_path: Path, *, prefix: str = constants.VIEW_TMP_PREFIX
) -> None:
    """Stage the CSV to a temp file in the same dir, then os.replace into place.

    The temp fd is created/closed by pandas' path-based to_csv; we add a SECOND explicit
    replace step so a crash leaves the prior CSV intact. Cleans up the temp on failure.
    `prefix` names the transient temp file only (replaced away immediately); it defaults to
    the View-1 prefix so existing callers are unchanged, and lets View 2 use a distinct one.
    """
    target_dir = csv_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(target_dir), prefix=prefix, suffix=".csv.tmp"
    )
    os.close(tmp_fd)  # pandas opens the path itself; we just need a unique name
    try:
        df.to_csv(tmp_name, index=False, na_rep=constants.CSV_NA_REP)
        os.replace(tmp_name, csv_path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_new_ideas_view(
    view: NewIdeasView,
    data_root: Path | str | None = None,
) -> tuple[Path, Path]:
    """Write <data_root>/<slug>/views/new_ideas.csv and new_ideas_summary.json.

    Returns (csv_path, summary_path). Both artifacts are staged to temp files then atomically
    replaced (best-effort consistency — a crash mid-write leaves the prior pair intact). The
    summary JSON is a sibling file (SD-4: NOT footer rows) carrying the SD-5 caveat in `notes`.
    Path-safety via storage.safe_data_path (a traversal slug/filename raises DiscoveryError).
    """
    csv_path = storage.safe_data_path(
        view.slug, f"{constants.VIEWS_DIR}/{constants.NEW_IDEAS_FILE}", data_root
    )
    summary_path = storage.safe_data_path(
        view.slug, f"{constants.VIEWS_DIR}/{constants.NEW_IDEAS_SUMMARY_FILE}", data_root
    )

    df = _build_dataframe(view)
    summary_text = json.dumps(view.summary.to_dict(), indent=2)

    target_dir = csv_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    # Stage the CSV temp first (do not replace yet), then write the summary atomically, then
    # swap the CSV in. The summary writer already does tmp-then-replace internally.
    _write_csv_atomic(df, csv_path)
    storage._atomic_write_json(
        summary_path.parent, summary_path, summary_text, prefix=constants.VIEW_TMP_PREFIX
    )
    return csv_path, summary_path


def conviction_add_row_to_dict(row: ConvictionAddRow) -> dict[str, object]:
    """One CSV row as a dict keyed by CONVICTION_ADDS_COLUMNS.

    Dates -> ISO strings; original_entry_quarter None -> None (NA rep "", NOT "CURRENT");
    bools -> "True"/"False" strings; add_type + None numerics pass through (NA rep by to_csv).
    """
    return {
        "quarter": _fmt_date(row.quarter),
        "ticker": row.ticker_display,
        "company": row.company,
        "security_type": row.security_type,
        "is_option": str(row.is_option),
        "weight_before_pct": row.weight_before_pct,
        "weight_after_pct": row.weight_after_pct,
        "weight_delta_pct": row.weight_delta_pct,
        "shares_delta_pct": row.shares_delta_pct,
        "prior_quarter_return_pct": row.prior_quarter_return_pct,
        "add_type": row.add_type,
        "quarters_held_before_add": row.quarters_held_before_add,
        "nth_add": row.nth_add,
        "original_entry_quarter": _fmt_optional_date(row.original_entry_quarter),
        "cumulative_return_since_entry_pct": row.cumulative_return_since_entry_pct,
        "filing_to_filing_return_pct": row.filing_to_filing_return_pct,
        "filing_to_next_period_high_pct": row.filing_to_next_period_high_pct,
        "filing_to_next_period_low_pct": row.filing_to_next_period_low_pct,
        "excess_filing_to_filing_pct": row.excess_filing_to_filing_pct,
        "excess_next_period_high_pct": row.excess_next_period_high_pct,
        "excess_next_period_low_pct": row.excess_next_period_low_pct,
        "smh_excess_filing_to_filing_pct": row.smh_excess_filing_to_filing_pct,
        "smh_excess_next_period_high_pct": row.smh_excess_next_period_high_pct,
        "smh_excess_next_period_low_pct": row.smh_excess_next_period_low_pct,
        "followed_by_exit": str(row.followed_by_exit),
        "followed_by_another_add": str(row.followed_by_another_add),
        "still_held": str(row.still_held),
        "priced": str(row.priced),
        "cusip": row.cusip,
        "filing_date": _fmt_date(row.filing_date),
    }


def _build_conviction_dataframe(view: ConvictionAddsView) -> "pd.DataFrame":
    records = [conviction_add_row_to_dict(r) for r in view.rows]
    if not records:
        # Empty feed: explicit columns so the header-only CSV is still well-formed.
        return pd.DataFrame(data=[], columns=list(constants.CONVICTION_ADDS_COLUMNS))
    return pd.DataFrame.from_records(records, columns=list(constants.CONVICTION_ADDS_COLUMNS))


def write_conviction_adds_view(
    view: ConvictionAddsView,
    data_root: Path | str | None = None,
) -> tuple[Path, Path]:
    """Write <data_root>/<slug>/views/conviction_adds.csv and conviction_adds_summary.json.

    Returns (csv_path, summary_path). Both artifacts are staged to temp files (prefixed with
    CONVICTION_TMP_PREFIX so a concurrent View-1 rebuild never collides on temp names) then
    atomically replaced. The summary JSON is a sibling file; its to_dict emits the nested
    adding_to_winners / averaging_down objects. Path-safety via storage.safe_data_path.
    """
    csv_path = storage.safe_data_path(
        view.slug, f"{constants.VIEWS_DIR}/{constants.CONVICTION_ADDS_FILE}", data_root
    )
    summary_path = storage.safe_data_path(
        view.slug, f"{constants.VIEWS_DIR}/{constants.CONVICTION_ADDS_SUMMARY_FILE}", data_root
    )

    df = _build_conviction_dataframe(view)
    summary_text = json.dumps(view.summary.to_dict(), indent=2)

    target_dir = csv_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    _write_csv_atomic(df, csv_path, prefix=constants.CONVICTION_TMP_PREFIX)
    storage._atomic_write_json(
        summary_path.parent, summary_path, summary_text, prefix=constants.CONVICTION_TMP_PREFIX
    )
    return csv_path, summary_path


def lifecycle_row_to_dict(row: PositionLifecycleRow) -> dict[str, object]:
    """One CSV row as a dict keyed by LIFECYCLE_COLUMNS.

    Dates -> ISO strings; change_type is already a string; priced bool -> "True"/"False";
    sector/industry and None numerics pass through (rendered as the NA rep by to_csv).
    """
    return {
        "cycle_id": row.cycle_id,
        "ticker": row.ticker_display,
        "company": row.company,
        "cusip": row.cusip,
        "security_type": row.security_type,
        "sector": row.sector,
        "industry": row.industry,
        "theme": row.theme,
        "period": _fmt_date(row.period),
        "filing_date": _fmt_date(row.filing_date),
        "change_type": row.change_type,
        "quarters_since_entry": row.quarters_since_entry,
        "weight_pct": row.weight_pct,
        "weight_delta_bps": row.weight_delta_bps,
        "shares_delta_pct": row.shares_delta_pct,
        "period_return_pct": row.period_return_pct,
        "period_high_pct": row.period_high_pct,
        "period_low_pct": row.period_low_pct,
        "cum_return_from_entry_pct": row.cum_return_from_entry_pct,
        "spy_period_return_pct": row.spy_period_return_pct,
        "excess_period_return_pct": row.excess_period_return_pct,
        "smh_period_return_pct": row.smh_period_return_pct,
        "excess_vs_smh_pct": row.excess_vs_smh_pct,
        "price_on_filing_date": row.price_on_filing_date,
        "entry_price": row.entry_price,
        "priced": str(row.priced),
    }


def _build_lifecycle_dataframe(view: PositionLifecycleView) -> "pd.DataFrame":
    records = [lifecycle_row_to_dict(r) for r in view.rows]
    if not records:
        # Empty feed: explicit columns so the header-only CSV is still well-formed.
        return pd.DataFrame(data=[], columns=list(constants.LIFECYCLE_COLUMNS))
    return pd.DataFrame.from_records(records, columns=list(constants.LIFECYCLE_COLUMNS))


def write_position_lifecycle_view(
    view: PositionLifecycleView,
    data_root: Path | str | None = None,
) -> Path:
    """Write <data_root>/<slug>/views/position_lifecycles.csv (CSV ONLY — no summary).

    Returns the csv_path. Staged to a temp file (LIFECYCLE_TMP_PREFIX) then atomically replaced
    (a crash mid-write leaves the prior CSV intact). Path-safety via storage.safe_data_path.
    """
    csv_path = storage.safe_data_path(
        view.slug, f"{constants.VIEWS_DIR}/{constants.LIFECYCLE_FILE}", data_root
    )
    df = _build_lifecycle_dataframe(view)
    _write_csv_atomic(df, csv_path, prefix=constants.LIFECYCLE_TMP_PREFIX)
    return csv_path
