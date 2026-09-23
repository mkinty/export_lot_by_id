from pathlib import Path

from lot_export.services.lot_naming import build_lot_dir, sanitize_lot_number


def test_sanitize_removes_forbidden_characters():
    assert sanitize_lot_number("13 / test!") == "13test"


def test_sanitize_keeps_underscores_and_hyphens():
    assert sanitize_lot_number("13-A_2") == "13-A_2"


def test_build_lot_dir_returns_none_for_empty_number():
    assert build_lot_dir(Path("/tmp"), "  ") is None


def test_build_lot_dir_builds_expected_path():
    assert build_lot_dir(Path("/tmp"), "13") == Path("/tmp/LOT13")
