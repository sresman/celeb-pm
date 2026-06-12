"""LIVE end-to-end smoke test — hits real EDGAR + OpenFIGI + EODHD. MANUAL only; NOT in CI.

Run with: .venv/bin/pytest tests_live/test_pipeline_live.py
Requires EODHD_API_KEY in the environment (.env) and network access to EDGAR/OpenFIGI.
ONE real client of each kind; the pipeline wraps the raw EodhdClient in CachingPriceProvider
internally. LOOSE structural assertions only (live data drifts — no exact counts). Runs against
Situational Awareness (CIK 0002045724, fewer quarters -> fewer OpenFIGI/EODHD calls).
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from celebpm import constants
from celebpm.edgar_client import EdgarClient
from celebpm.eodhd_client import EodhdClient
from celebpm.openfigi_client import OpenFigiClient
from celebpm.pipeline import run_pipeline

pytestmark = pytest.mark.skipif(
    not (os.environ.get(constants.EODHD_API_KEY_ENV) or "").strip(),
    reason="EODHD_API_KEY not set",
)

SITUATIONAL_AWARENESS_CIK = "0002045724"


def test_pipeline_end_to_end_structural(tmp_path: Path) -> None:
    result = run_pipeline(
        SITUATIONAL_AWARENESS_CIK,
        today=date.today(),
        data_root=tmp_path,
        edgar=EdgarClient(),
        figi=OpenFigiClient.from_env(),
        price_client=EodhdClient.from_env(),
    )

    csv_path = tmp_path / result.slug / constants.VIEWS_DIR / constants.NEW_IDEAS_FILE
    summary_path = (
        tmp_path / result.slug / constants.VIEWS_DIR / constants.NEW_IDEAS_SUMMARY_FILE
    )
    assert csv_path.exists()
    assert summary_path.exists()

    df = pd.read_csv(csv_path, keep_default_na=False, dtype=str)
    assert list(df.columns) == list(constants.NEW_IDEAS_COLUMNS)

    summary = json.loads(summary_path.read_text())
    assert constants.SUMMARY_KEY_NOTES in summary
    assert summary[constants.SUMMARY_KEY_NOTES] == constants.SUMMARY_NOTES
    # PipelineResult returned with internally-consistent counts.
    assert result.n_filings_parsed + result.n_filings_skipped == result.n_filings_selected
    assert result.n_new_ideas == result.summary.total_new
