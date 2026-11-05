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


def _commune_folder(root: Path, *names: str) -> Path:
    folder = root / "Dep38" / "38200"
    folder.mkdir(parents=True)
    for name in names:
        (folder / name).write_text("x", encoding="utf-8")
    return folder


def test_commune_file_has_priority_over_a_onedrive_conflict_copy(tmp_path: Path):
    _commune_folder(tmp_path, "audit_38200-NB-G1029762.xlsx", "audit_38200.xlsx")

    locator = AuditFileLocator(tmp_path)

    assert locator.find("38200").name == "audit_38200.xlsx"
    assert [p.name for p in locator.find_all("38200")] == ["audit_38200.xlsx", "audit_38200-NB-G1029762.xlsx"]


def test_conflict_copy_is_used_when_it_is_the_only_file(tmp_path: Path):
    _commune_folder(tmp_path, "audit_38200-NB-G1029762.xlsx")

    assert AuditFileLocator(tmp_path).find("38200").name == "audit_38200-NB-G1029762.xlsx"


def test_excel_lock_file_is_ignored(tmp_path: Path):
    _commune_folder(tmp_path, "~$audit_38200.xlsx", "audit_38200.xlsx")

    assert [p.name for p in AuditFileLocator(tmp_path).find_all("38200")] == ["audit_38200.xlsx"]


def test_explain_missing_names_the_exact_level(tmp_path: Path):
    locator = AuditFileLocator(tmp_path)
    assert "dossier Dep38 absent" in locator.explain_missing("38200")

    (tmp_path / "Dep38").mkdir()
    assert "dossier 38200 absent" in locator.explain_missing("38200")

    (tmp_path / "Dep38" / "38200").mkdir()
    assert "aucun fichier audit_*.xlsx" in locator.explain_missing("38200")
