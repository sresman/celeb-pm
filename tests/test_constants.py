"""Tests for pure path/URL helpers in constants.py."""

from __future__ import annotations

import pytest

from celebpm import constants
from celebpm.errors import DiscoveryError


class TestCikToPadded:
    def test_int_input(self) -> None:
        assert constants.cik_to_padded(1777813) == "0001777813"

    def test_str_input(self) -> None:
        assert constants.cik_to_padded("1777813") == "0001777813"

    def test_already_padded(self) -> None:
        assert constants.cik_to_padded("0001777813") == "0001777813"

    def test_whitespace_stripped(self) -> None:
        assert constants.cik_to_padded("  1777813  ") == "0001777813"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            constants.cik_to_padded("")

    def test_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError):
            constants.cik_to_padded("ABC123")

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValueError):
            constants.cik_to_padded("12345678901")  # 11 digits


class TestSubmissionsUrl:
    def test_zero_padded(self) -> None:
        assert (
            constants.submissions_url(1777813)
            == "https://data.sec.gov/submissions/CIK0001777813.json"
        )


class TestFilingIndexUrl:
    def test_unpadded_cik_dash_stripped_accession(self) -> None:
        url = constants.filing_index_url("0001777813", "0001777813-26-000012")
        assert url == "https://www.sec.gov/Archives/edgar/data/1777813/000177781326000012/"

    def test_trailing_slash_present(self) -> None:
        url = constants.filing_index_url(1777813, "0001777813-26-000012")
        assert url.endswith("/")


class TestSubmissionsOverflowUrl:
    def test_valid_name(self) -> None:
        url = constants.submissions_overflow_url("CIK0001777813-submissions-001.json")
        assert url == "https://data.sec.gov/submissions/CIK0001777813-submissions-001.json"

    def test_bad_name_raises_discovery_error(self) -> None:
        with pytest.raises(DiscoveryError):
            constants.submissions_overflow_url("../etc/passwd")

    def test_wrong_pattern_raises(self) -> None:
        with pytest.raises(DiscoveryError):
            constants.submissions_overflow_url("CIK123.json")
