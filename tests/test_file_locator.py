from pathlib import Path

from lot_export.services.file_locator import AuditFileLocator


def test_finds_existing_audit_file(tmp_path: Path):
    commune_dir = tmp_path / "Dep75" / "75001"
    commune_dir.mkdir(parents=True)
    audit_file = commune_dir / "audit_75001.xlsx"
    audit_file.write_text("dummy")

    locator = AuditFileLocator(tmp_path)
    assert locator.find("75001") == audit_file


def test_returns_none_when_directory_missing(tmp_path: Path):
    locator = AuditFileLocator(tmp_path)
    assert locator.find("99999") is None


def test_returns_none_when_no_audit_file(tmp_path: Path):
    commune_dir = tmp_path / "Dep75" / "75001"
    commune_dir.mkdir(parents=True)
    (commune_dir / "notes.txt").write_text("dummy")

    locator = AuditFileLocator(tmp_path)
    assert locator.find("75001") is None


def test_commune_lookup_is_case_and_space_insensitive(tmp_path: Path):
    commune_dir = tmp_path / "Dep75" / "75001"
    commune_dir.mkdir(parents=True)
    audit_file = commune_dir / "audit_75001.xlsx"
    audit_file.write_text("dummy")

    locator = AuditFileLocator(tmp_path)
    assert locator.find(" 75001 ") == audit_file
