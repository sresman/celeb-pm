"""Tests for config_loader."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from celebpm import config_loader
from celebpm.errors import ConfigError

_VALID = {
    "0001777813": {
        "cik": "0001777813",
        "name": "Gavin Baker",
        "fund": "Atreides Management, LP",
        "slug": "atreides_management",
        "notes": "x",
    },
    "0002045724": {
        "cik": "0002045724",
        "name": "Leopold Aschenbrenner",
        "fund": "Situational Awareness LP",
        "slug": "situational_awareness",
        "notes": "y",
    },
}


def _write(tmp_path: Path, data: object) -> Path:
    p = tmp_path / "investors.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestLoadAllInvestors:
    def test_returns_both_keyed_by_padded_cik(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _VALID)
        result = config_loader.load_all_investors(path)
        assert set(result) == {"0001777813", "0002045724"}
        assert result["0001777813"].slug == "atreides_management"
        assert result["0001777813"].is_known is True

    def test_malformed_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "investors.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigError):
            config_loader.load_all_investors(p)

    def test_missing_required_key_raises(self, tmp_path: Path) -> None:
        bad = {"0001777813": {"cik": "0001777813", "name": "x"}}
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigError):
            config_loader.load_all_investors(path)

    def test_bad_slug_raises(self, tmp_path: Path) -> None:
        bad = {
            "0001777813": {
                "cik": "0001777813",
                "name": "x",
                "fund": "y",
                "slug": "Bad-Slug!",
                "notes": "z",
            }
        }
        path = _write(tmp_path, bad)
        with pytest.raises(ConfigError):
            config_loader.load_all_investors(path)

    def test_duplicate_slug_raises(self, tmp_path: Path) -> None:
        dup = {
            "0001777813": {
                "cik": "0001777813",
                "name": "a",
                "fund": "b",
                "slug": "shared",
                "notes": "c",
            },
            "0002045724": {
                "cik": "0002045724",
                "name": "d",
                "fund": "e",
                "slug": "shared",
                "notes": "f",
            },
        }
        path = _write(tmp_path, dup)
        with pytest.raises(ConfigError):
            config_loader.load_all_investors(path)

    def test_key_not_equal_cik_raises(self, tmp_path: Path) -> None:
        mismatch = {
            "0001777813": {
                "cik": "0002045724",
                "name": "a",
                "fund": "b",
                "slug": "atreides_management",
                "notes": "c",
            }
        }
        path = _write(tmp_path, mismatch)
        with pytest.raises(ConfigError):
            config_loader.load_all_investors(path)


class TestLoadInvestor:
    def test_known_cik_padded(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _VALID)
        cfg = config_loader.load_investor("0001777813", path)
        assert cfg.is_known is True
        assert cfg.name == "Gavin Baker"

    def test_known_cik_int(self, tmp_path: Path) -> None:
        path = _write(tmp_path, _VALID)
        cfg = config_loader.load_investor(1777813, path)
        assert cfg.is_known is True
        assert cfg.cik == "0001777813"

    def test_unknown_cik_synthesized(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write(tmp_path, _VALID)
        with caplog.at_level(logging.WARNING):
            cfg = config_loader.load_investor("9999999999", path)
        assert cfg.is_known is False
        assert cfg.slug == "cik_9999999999"
        assert cfg.name == ""
        assert any("not found" in rec.message for rec in caplog.records)

    def test_missing_file_raises_even_for_unknown_cik(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.json"
        with pytest.raises(ConfigError):
            config_loader.load_investor("9999999999", missing)
