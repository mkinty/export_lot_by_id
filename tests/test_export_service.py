from pathlib import Path

import pytest

from openpyxl import Workbook, load_workbook

from lot_export.models import ExportStatus, NotExported, NotExportedCause
from lot_export.services.excel_filter import FilterResult
from lot_export.services.export_service import ExportService
from lot_export.services.file_locator import AuditFileLocator


def _all_present(path, values, column):
    return list(values)


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

    service = ExportService(AuditFileLocator(audit_tree), filter_fn=fake_filter, find_fn=_all_present)
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

    service = ExportService(AuditFileLocator(audit_tree), filter_fn=fake_filter, find_fn=_all_present)
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


def test_not_exported_values_carry_their_reason(audit_tree: Path, tmp_path: Path):
    service = ExportService(
        AuditFileLocator(audit_tree),
        filter_fn=lambda src, dst, ids, column: FilterResult(
            kept_ids=["75001_1"], missing_ids=["75001_2"], reasons={"75001_2": "absent de Audit"}),
        find_fn=_all_present,
    )

    summary = service.export_by_error_ids({"75001": ["75001_1", "75001_2"], "00000": ["00000_1"]}, tmp_path / "LOT1")

    assert summary.exported_count == 1
    assert summary.not_exported_count == 2
    assert summary.items[0].not_exported == (NotExported("75001_2", "absent de Audit"),)
    assert "fichier audit introuvable" in summary.items[1].not_exported[0].reason
    assert "Dep00" in summary.items[1].not_exported[0].reason


def test_unreadable_file_marks_all_its_values_not_exported(audit_tree: Path, tmp_path: Path):
    service = ExportService(AuditFileLocator(audit_tree))

    summary = service.export_by_error_ids({"75001": ["75001_1", "75001_2"]}, tmp_path / "LOT1")

    assert [entry.value for entry in summary.items[0].not_exported] == ["75001_1", "75001_2"]
    assert "lecture Excel impossible" in summary.items[0].not_exported[0].reason


def test_merge_failure_marks_exported_values_not_exported(audit_tree: Path, tmp_path: Path):
    def fake_filter(src, dst, ids, column):
        dst.write_text("filtré", encoding="utf-8")
        return FilterResult(kept_ids=list(ids))

    def failing_merge(sources, target):
        raise ValueError("boom")

    service = ExportService(AuditFileLocator(audit_tree), filter_fn=fake_filter, merge_fn=failing_merge)

    summary = service.export_by_error_ids({"75001": ["75001_1"]}, tmp_path / "LOT1", single_file_name="a.xlsx")

    assert summary.exported_count == 0
    assert summary.items[0].not_exported == (
        NotExported("75001_1", "fusion impossible (boom)", NotExportedCause.MERGE_FAILED),)


def test_end_to_end_filtered_source_single_file_keeps_every_id_visible(tmp_path: Path):
    root = tmp_path / "root"
    for insee, hidden_row in (("74143", 2), ("38068", 3)):
        folder = root / f"Dep{insee[:2]}" / insee
        folder.mkdir(parents=True)
        wb = Workbook()
        ws = wb.active
        ws.title = "Audit"
        ws.append(["INSEE", "ID erreur"])
        ws.append([insee, f"{insee}_1"])
        ws.append([insee, f"{insee}_2"])
        ws.auto_filter.ref = "A1:B3"
        ws.auto_filter.add_filter_column(1, [f"{insee}_9"])
        ws.row_dimensions[hidden_row].hidden = True
        wb.save(folder / f"audit_{insee}.xlsx")
    wanted = {"74143": ["74143_1", "74143_2"], "38068": ["38068_1", "38068_2", "38068_9"]}

    summary = ExportService(AuditFileLocator(root)).export_by_error_ids(
        wanted, tmp_path / "LOT1", single_file_name="audit_LOT1.xlsx")

    ws = load_workbook(tmp_path / "LOT1" / "audit_LOT1.xlsx")["Audit"]
    assert [ws.cell(row, 2).value for row in range(2, ws.max_row + 1)] == ["74143_1", "74143_2", "38068_1", "38068_2"]
    assert not any(dimension.hidden for dimension in ws.row_dimensions.values())
    assert summary.exported_count == 4
    assert [entry.value for entry in summary.items[1].not_exported] == ["38068_9"]


def _audit_file(path: Path, ids: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["INSEE", "ID erreur"])
    for error_id in ids:
        ws.append([error_id[:5], error_id])
    wb.save(path)
    return path


def test_a_value_missing_from_the_final_file_is_not_counted_as_exported(audit_tree: Path, tmp_path: Path):
    def fake_filter(src, dst, ids, column):
        return FilterResult(kept_ids=list(ids), kept_rows=len(ids))

    service = ExportService(AuditFileLocator(audit_tree), filter_fn=fake_filter,
                            find_fn=lambda path, values, column: ["75001_1"])

    summary = service.export_by_error_ids({"75001": ["75001_1", "75001_2"]}, tmp_path / "LOT1")

    assert summary.exported_count == 1
    assert [(entry.value, entry.cause) for entry in summary.items[0].not_exported] == [
        ("75001_2", NotExportedCause.NOT_IN_OUTPUT)]


def test_unreadable_final_file_means_nothing_is_confirmed_exported(audit_tree: Path, tmp_path: Path):
    def failing_find(path, values, column):
        raise OSError("illisible")

    service = ExportService(AuditFileLocator(audit_tree), find_fn=failing_find,
                            filter_fn=lambda src, dst, ids, column: FilterResult(kept_ids=list(ids)))

    summary = service.export_by_error_ids({"75001": ["75001_1"]}, tmp_path / "LOT1")

    assert summary.exported_count == 0
    assert not summary.has_success
    assert "contrôle du fichier" in summary.items[0].not_exported[0].reason


def test_missing_commune_folder_cause_names_the_source_folder(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()

    summary = ExportService(AuditFileLocator(root)).export_by_error_ids({"38068": ["38068_1"]}, tmp_path / "LOT1")

    entry = summary.items[0].not_exported[0]
    assert entry.cause == NotExportedCause.NO_FILE
    assert "Dep38" in entry.reason and str(root) in entry.reason


def test_value_only_in_another_copy_is_reported_not_exported(tmp_path: Path):
    root = tmp_path / "root"
    folder = root / "Dep38" / "38200"
    _audit_file(folder / "audit_38200.xlsx", ["38200_1"])
    _audit_file(folder / "audit_38200-NB-G1029762.xlsx", ["38200_2"])

    summary = ExportService(AuditFileLocator(root)).export_by_error_ids(
        {"38200": ["38200_1", "38200_2", "38200_3"]}, tmp_path / "LOT1")

    item = summary.items[0]
    assert item.source.name == "audit_38200.xlsx"
    assert item.exported == ("38200_1",)
    causes = {entry.value: entry.cause for entry in item.not_exported}
    assert causes == {"38200_2": NotExportedCause.IN_OTHER_FILE, "38200_3": NotExportedCause.VALUE_ABSENT}
    assert "audit_38200-NB-G1029762.xlsx" in item.not_exported[0].reason


def test_full_reconciliation_every_requested_id_is_accounted_for(tmp_path: Path):
    """Scénario 980 -> 500 réduit : chaque ID demandé est soit dans le fichier final, soit expliqué."""
    root = tmp_path / "root"
    _audit_file(root / "Dep74" / "74143" / "audit_74143.xlsx", [f"74143_{n}" for n in range(1, 41)])
    _audit_file(root / "Dep38" / "38068" / "audit_38068.xlsx", [f"38068_{n}" for n in range(1, 11)])
    wanted = {
        "74143": [f"74143_{n}" for n in range(1, 51)],   # 40 présents, 10 absents
        "38068": [f"38068_{n}" for n in range(1, 11)],   # 10 présents
        "45001": [f"45001_{n}" for n in range(1, 31)],   # commune sans fichier
    }

    summary = ExportService(AuditFileLocator(root)).export_by_error_ids(
        wanted, tmp_path / "LOT1", single_file_name="audit_LOT1.xlsx")

    ws = load_workbook(tmp_path / "LOT1" / "audit_LOT1.xlsx")["Audit"]
    in_file = {ws.cell(row, 2).value for row in range(2, ws.max_row + 1)}
    assert summary.exported_count == len(in_file) == 50
    assert summary.exported_count + summary.not_exported_count == 90
    assert dict(summary.not_exported_by_cause()) == {
        NotExportedCause.NO_FILE: 30, NotExportedCause.VALUE_ABSENT: 10}
