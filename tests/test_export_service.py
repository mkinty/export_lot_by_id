from pathlib import Path

import pytest

from lot_export.models import ExportStatus
from lot_export.services.excel_filter import FilterResult
from lot_export.services.export_service import ExportService
from lot_export.services.file_locator import AuditFileLocator


@pytest.fixture
def audit_tree(tmp_path: Path) -> Path:
    """Arborescence source avec deux communes valides (75001 et 69002)."""
    root = tmp_path / "audit_root"
    for commune in ("75001", "69002"):
        commune_dir = root / f"Dep{commune[:2]}" / commune
        commune_dir.mkdir(parents=True)
        (commune_dir / f"audit_{commune}.xlsx").write_text("dummy")
    return root


def test_export_copies_found_files(audit_tree: Path, tmp_path: Path):
    service = ExportService(AuditFileLocator(audit_tree))
    destination = tmp_path / "LOT1"

    summary = service.export(["75001", "69002"], destination)

    assert summary.total == 2
    assert summary.success_count == 2
    assert (destination / "audit_75001.xlsx").exists()
    assert (destination / "audit_69002.xlsx").exists()


def test_export_reports_missing_commune(audit_tree: Path, tmp_path: Path):
    service = ExportService(AuditFileLocator(audit_tree))

    summary = service.export(["00000"], tmp_path / "LOT1")

    assert summary.total == 1
    assert summary.success_count == 0
    assert summary.items[0].status == ExportStatus.NOT_FOUND


def test_export_reports_copy_error_without_touching_disk(audit_tree: Path, tmp_path: Path):
    def failing_copy(src, dst):
        raise OSError("disque plein")

    service = ExportService(AuditFileLocator(audit_tree), copy_fn=failing_copy)
    summary = service.export(["75001"], tmp_path / "LOT1")

    assert summary.items[0].status == ExportStatus.ERROR
    assert "disque plein" in summary.items[0].message


def test_progress_callback_called_for_each_commune(audit_tree: Path, tmp_path: Path):
    service = ExportService(AuditFileLocator(audit_tree))
    calls = []

    service.export(
        ["75001", "69002"], tmp_path / "LOT1",
        on_progress=lambda done, total, label: calls.append((done, total)),
    )

    assert calls == [(1, 2), (2, 2)]


def test_export_creates_destination_directory_if_missing(audit_tree: Path, tmp_path: Path):
    service = ExportService(AuditFileLocator(audit_tree))
    destination = tmp_path / "does" / "not" / "exist_yet"

    service.export(["75001"], destination)

    assert destination.is_dir()


def test_export_by_error_ids_passes_ids_to_filter(audit_tree: Path, tmp_path: Path):
    calls = []

    def fake_filter(src, dst, ids, column):
        calls.append((src.name, dst.name, list(ids), column))
        return FilterResult(kept_ids=["75001_1"], missing_ids=["75001_2"])

    service = ExportService(AuditFileLocator(audit_tree), filter_fn=fake_filter)
    summary = service.export_by_error_ids(
        {"75001": ["75001_1", "75001_2"], "00000": ["00000_1"]}, tmp_path / "LOT1",
    )

    assert calls == [("audit_75001.xlsx", "audit_75001.xlsx", ["75001_1", "75001_2"], "ID erreur")]
    assert summary.items[0].status == ExportStatus.SUCCESS
    assert "1/2" in summary.items[0].message and "75001_2" in summary.items[0].message
    assert summary.items[1].status == ExportStatus.NOT_FOUND


def test_export_by_error_ids_reports_no_matching_rows(audit_tree: Path, tmp_path: Path):
    service = ExportService(
        AuditFileLocator(audit_tree),
        filter_fn=lambda src, dst, ids, column: FilterResult(missing_ids=list(ids)),
    )

    summary = service.export_by_error_ids({"75001": ["75001_9"]}, tmp_path / "LOT1")

    assert summary.items[0].status == ExportStatus.NOT_FOUND
    assert not summary.has_success


def test_export_by_error_ids_reports_unreadable_excel(audit_tree: Path, tmp_path: Path):
    # Les fichiers de la fixture ne sont pas de vrais .xlsx : openpyxl doit échouer proprement
    service = ExportService(AuditFileLocator(audit_tree))

    summary = service.export_by_error_ids({"75001": ["75001_1"]}, tmp_path / "LOT1")

    assert summary.items[0].status == ExportStatus.ERROR


def test_export_by_addresses_filters_on_address_column(audit_tree: Path, tmp_path: Path):
    calls = []

    def fake_filter(src, dst, values, column):
        calls.append((src.name, list(values), column))
        return FilterResult(kept_ids=list(values))

    service = ExportService(AuditFileLocator(audit_tree), filter_fn=fake_filter)
    summary = service.export_by_addresses({"75001": ["1 RUE DE RIVOLI 75001 PARIS"]}, tmp_path / "LOT1")

    assert calls == [("audit_75001.xlsx", ["1 RUE DE RIVOLI 75001 PARIS"], "adresse")]
    assert summary.items[0].status == ExportStatus.SUCCESS
    assert "1/1 adresse(s)" in summary.items[0].message


def test_single_file_merges_exported_files_into_one(audit_tree: Path, tmp_path: Path):
    calls = []

    def fake_merge(sources, target):
        calls.append(([s.name for s in sources], target.name))
        target.write_text("merged")
        return 7

    service = ExportService(AuditFileLocator(audit_tree), merge_fn=fake_merge)
    destination = tmp_path / "LOT1"

    summary = service.export(["75001", "00000", "69002"], destination, single_file_name="audit_LOT1.xlsx")

    assert calls == [(["audit_75001.xlsx", "audit_69002.xlsx"], "audit_LOT1.xlsx")]
    assert sorted(p.name for p in destination.iterdir()) == ["audit_LOT1.xlsx"]
    assert summary.merged_file == destination / "audit_LOT1.xlsx"
    assert summary.merged_rows == 7
    assert summary.success_count == 2
    assert all(item.destination == summary.merged_file for item in summary.items if item.ok)


def test_single_file_merge_failure_marks_communes_in_error(audit_tree: Path, tmp_path: Path):
    def failing_merge(sources, target):
        raise ValueError("boom")

    service = ExportService(AuditFileLocator(audit_tree), merge_fn=failing_merge)

    summary = service.export(["75001"], tmp_path / "LOT1", single_file_name="audit_LOT1.xlsx")

    assert not summary.has_success
    assert summary.items[0].status == ExportStatus.ERROR
    assert "fusion impossible" in summary.items[0].message
    assert summary.merged_file is None


def test_single_file_without_success_does_not_merge(audit_tree: Path, tmp_path: Path):
    service = ExportService(AuditFileLocator(audit_tree), merge_fn=lambda s, t: pytest.fail("ne doit pas fusionner"))

    summary = service.export(["00000"], tmp_path / "LOT1", single_file_name="audit_LOT1.xlsx")

    assert summary.merged_file is None
