"""Tests for symbol_map.to_eodhd_symbol + load_symbol_overrides."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from celebpm import constants
from celebpm.symbol_map import load_symbol_overrides, to_eodhd_symbol


class TestToEodhdSymbol:
    def test_plain_us_suffix(self) -> None:
        assert to_eodhd_symbol("AAPL") == "AAPL.US"

    def test_lowercase_upcased(self) -> None:
        assert to_eodhd_symbol("aapl") == "AAPL.US"

    def test_class_share_slash(self) -> None:
        assert to_eodhd_symbol("BRK/B") == "BRK-B.US"

    def test_class_share_dot(self) -> None:
        assert to_eodhd_symbol("BRK.B") == "BRK-B.US"

    def test_one_letter_class_not_passthrough(self) -> None:
        # BF.B: '.B' is one letter, NOT a 2-letter exchange suffix -> class-share handling.
        assert to_eodhd_symbol("BF.B") == "BF-B.US"

    def test_space_separator(self) -> None:
        assert to_eodhd_symbol("BRK B") == "BRK-B.US"

    def test_multi_separator(self) -> None:
        assert to_eodhd_symbol("A.B.C") == "A-B-C.US"

    def test_consecutive_separators_not_collapsed(self) -> None:
        # "BRK. B" (dot+space) -> two dashes, unpriceable downstream but a SAFE result.
        assert to_eodhd_symbol("BRK. B") == "BRK--B.US"

    def test_us_passthrough(self) -> None:
        assert to_eodhd_symbol("AAPL.US") == "AAPL.US"
        assert to_eodhd_symbol("SPY.US") == "SPY.US"

    def test_us_passthrough_does_not_warn(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)
        assert to_eodhd_symbol("AAPL.US") == "AAPL.US"
        assert caplog.records == []

    def test_non_us_passthrough_warns(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)
        assert to_eodhd_symbol("SHOP.TO") == "SHOP.TO"
        assert any("non-.US" in r.message or ".US" in r.message for r in caplog.records)

    def test_none_and_blank(self) -> None:
        assert to_eodhd_symbol(None) is None
        assert to_eodhd_symbol("") is None
        assert to_eodhd_symbol("   ") is None

    def test_invalid_chars_none(self) -> None:
        # leading non-alnum after normalization -> None.
        assert to_eodhd_symbol("$$$") is None

    def test_override_consulted_first_as_is(self) -> None:
        # override returns the FULL EODHD symbol AS-IS (not re-suffixed).
        assert to_eodhd_symbol("FOO", {"FOO": "BRK-B.US"}) == "BRK-B.US"

    def test_override_keyed_uppercase(self) -> None:
        assert to_eodhd_symbol("foo", {"FOO": "BAR.US"}) == "BAR.US"


class TestDegenerateRejected:
    def test_dot_rejected(self) -> None:
        assert to_eodhd_symbol(".") is None

    def test_double_dot(self) -> None:
        # ".." -> translate maps both dots to dashes -> "--" -> append .US -> "--.US" fails pattern.
        assert to_eodhd_symbol("..") is None


class TestLoadSymbolOverrides:
    def test_missing_file_empty(self, tmp_path: Path) -> None:
        assert load_symbol_overrides(tmp_path) == {}

    def _write(self, tmp_path: Path, payload: object) -> None:
        d = constants.price_cache_dir(tmp_path)
        d.mkdir(parents=True, exist_ok=True)
        (d / constants.SYMBOL_OVERRIDES_FILE).write_text(
            json.dumps(payload), encoding="utf-8"
        )

    def test_not_json_object(self, tmp_path: Path, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)
        self._write(tmp_path, [1, 2, 3])
        assert load_symbol_overrides(tmp_path) == {}
        assert caplog.records

    def test_keys_values_stripped_upcased(self, tmp_path: Path) -> None:
        self._write(tmp_path, {"  foo ": " brk-b.us "})
        assert load_symbol_overrides(tmp_path) == {"FOO": "BRK-B.US"}

    def test_bad_value_entry_ignored(self, tmp_path: Path, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)
        self._write(tmp_path, {"GOOD": "AAA.US", "BAD": 123, "DEGEN": "..."})
        out = load_symbol_overrides(tmp_path)
        assert out == {"GOOD": "AAA.US"}
        assert caplog.records

    def test_key_collision_warns_last_wins(self, tmp_path: Path, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)
        # JSON dicts can't have duplicate keys; simulate collision via differing case.
        self._write(tmp_path, {"brk.b": "AAA.US", "BRK.B": "BBB.US"})
        out = load_symbol_overrides(tmp_path)
        assert out == {"BRK.B": "BBB.US"}
        assert any("collision" in r.message for r in caplog.records)
