from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from lot_export.services.excel_filter import ExcelFilterError, filter_audit_rows, find_values


def _make_audit(path: Path, ids: list) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["INSEE", "Valeur", "ID erreur", "Formule"])
    for row, error_id in enumerate(ids, start=2):
        ws.append(["74143", row * 10, error_id, f"=B{row}*2"])
    wb.create_sheet("IPE").append(["Id immeuble"])
    wb.save(path)
    return path


def test_keeps_only_requested_rows_and_shifts_formulas(tmp_path: Path):
    source = _make_audit(tmp_path / "audit_74143.xlsx", ["74143_1", "74143_2", None, "74143_3"])
    destination = tmp_path / "out.xlsx"

    result = filter_audit_rows(source, destination, ["74143_3", "74143_1"])

    assert result.kept_ids == ["74143_3", "74143_1"]
    assert result.missing_ids == []
    ws = load_workbook(destination)["Audit"]
    rows = list(ws.iter_rows(values_only=True))
    assert rows == [
        ("INSEE", "Valeur", "ID erreur", "Formule"),
        ("74143", 20, "74143_1", "=B2*2"),
        ("74143", 50, "74143_3", "=B3*2"),
    ]


def test_other_sheets_are_preserved(tmp_path: Path):
    source = _make_audit(tmp_path / "audit.xlsx", ["74143_1"])
    destination = tmp_path / "out.xlsx"

    filter_audit_rows(source, destination, ["74143_1"])

    assert load_workbook(destination).sheetnames == ["Audit", "IPE"]


def test_reports_missing_ids_and_writes_nothing_when_no_match(tmp_path: Path):
    source = _make_audit(tmp_path / "audit.xlsx", ["74143_1"])
    destination = tmp_path / "out.xlsx"

    result = filter_audit_rows(source, destination, ["74143_9"])

    assert result.kept_ids == []
    assert result.missing_ids == ["74143_9"]
    assert not destination.exists()


def test_raises_when_column_missing(tmp_path: Path):
    wb = Workbook()
    wb.active.title = "Audit"
    wb.active.append(["INSEE"])
    wb.save(tmp_path / "audit.xlsx")

    with pytest.raises(ExcelFilterError):
        filter_audit_rows(tmp_path / "audit.xlsx", tmp_path / "out.xlsx", ["74143_1"])


def test_filters_on_address_column_ignoring_case_accents_and_spaces(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["INSEE", "Adresse", "ID erreur"])
    ws.append(["05094", "495 Chemin de Pige Bouin 05700 Nossage et Bénévent", "05094_1"])
    ws.append(["05094", "3 ROUTE DU COL 05700 NOSSAGE ET BENEVENT", "05094_2"])
    ws.append(["05094", "495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT", "05094_3"])
    wb.save(tmp_path / "audit.xlsx")
    wanted = ["495 CHEMIN DE PIGE  BOUIN 05700 NOSSAGE ET BENEVENT", "1 RUE ABSENTE"]

    result = filter_audit_rows(tmp_path / "audit.xlsx", tmp_path / "out.xlsx", wanted, "adresse")

    assert result.kept_ids == [wanted[0]]
    assert result.missing_ids == ["1 RUE ABSENTE"]
    ids = [row[2] for row in load_workbook(tmp_path / "out.xlsx")["Audit"].iter_rows(min_row=2, values_only=True)]
    assert ids == ["05094_1", "05094_3"]


def _make_filtered_audit(path: Path) -> Path:
    """Fichier tel qu'enregistré par Excel avec un filtre actif : lignes 2 et 4 masquées, colonne B masquée."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["INSEE", "Valeur", "ID erreur"])
    for number in range(1, 5):
        ws.append(["74143", number, f"74143_{number}"])
    ws.auto_filter.ref = "A1:C5"
    ws.auto_filter.add_filter_column(2, ["74143_2", "74143_4"])
    ws.row_dimensions[2].hidden = True
    ws.row_dimensions[4].hidden = True
    ws.row_dimensions[5].height = 40
    ws.column_dimensions["B"].hidden = True
    other = wb.create_sheet("DGFIP")
    other.append(["Ref"])
    other.append(["A"])
    other.auto_filter.ref = "A1:A2"
    other.auto_filter.add_filter_column(0, ["B"])
    other.row_dimensions[2].hidden = True
    wb.save(path)
    return path


def test_rows_hidden_by_a_filter_are_exported_and_visible(tmp_path: Path):
    source = _make_filtered_audit(tmp_path / "audit.xlsx")
    destination = tmp_path / "out.xlsx"

    result = filter_audit_rows(source, destination, ["74143_1", "74143_2", "74143_3"])

    assert result.missing_ids == []
    wb = load_workbook(destination)
    ws = wb["Audit"]
    assert [row[2] for row in ws.iter_rows(min_row=2, values_only=True)] == ["74143_1", "74143_2", "74143_3"]
    assert not any(dimension.hidden for dimension in ws.row_dimensions.values())
    assert not ws.column_dimensions["B"].hidden
    assert ws.auto_filter.filterColumn == []
    assert ws.auto_filter.ref == "A1:C5"  # les flèches de filtre restent disponibles
    assert not wb["DGFIP"].auto_filter.filterColumn
    assert not wb["DGFIP"].row_dimensions[2].hidden


def test_row_height_follows_its_row(tmp_path: Path):
    source = _make_filtered_audit(tmp_path / "audit.xlsx")
    destination = tmp_path / "out.xlsx"

    filter_audit_rows(source, destination, ["74143_4"])  # ligne 5 de la source, hauteur 40

    assert load_workbook(destination)["Audit"].row_dimensions[2].height == 40


def test_source_file_is_not_modified(tmp_path: Path):
    source = _make_filtered_audit(tmp_path / "audit.xlsx")
    before = source.read_bytes()

    filter_audit_rows(source, tmp_path / "out.xlsx", ["74143_1"])

    assert source.read_bytes() == before


def test_missing_value_reason_points_to_cell_holding_it(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["INSEE", "ID erreur", "Remarque"])
    ws.append(["74143", "74143_1", None])
    ws.append(["74143", "74143_2, 74143_3", None])
    ws.append(["74143", "74143_12", None])
    wb.save(tmp_path / "audit.xlsx")

    result = filter_audit_rows(tmp_path / "audit.xlsx", tmp_path / "out.xlsx", ["74143_1", "74143_3", "74143_9"])

    assert result.missing_ids == ["74143_3", "74143_9"]
    assert "B3" in result.reasons["74143_3"]
    assert "absent(e) de la colonne" in result.reasons["74143_9"]


def test_find_values_reads_hidden_rows_and_ignores_case(tmp_path: Path):
    source = _make_filtered_audit(tmp_path / "audit.xlsx")

    assert find_values(source, ["74143_1", "74143_9", "74143_2"]) == ["74143_1", "74143_2"]


def test_find_values_raises_when_structure_is_unexpected(tmp_path: Path):
    wb = Workbook()
    wb.active.title = "Autre"
    wb.save(tmp_path / "audit.xlsx")

    with pytest.raises(ExcelFilterError):
        find_values(tmp_path / "audit.xlsx", ["74143_1"])


def _make_shifted_audit(path: Path) -> Path:
    """Comme les vrais fichiers : la colonne D lit une autre ligne que la sienne."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["INSEE", "Valeur", "ID erreur", "Formule"])
    formulas = {2: "=B5*2", 3: "=B3*2", 4: "=B2*2", 5: "=B4*2"}
    for row, formula in formulas.items():
        ws.append(["74143", row * 10, f"74143_{row}", formula])
    wb.save(path)
    return path


def test_formula_reading_a_row_above_no_longer_blocks_the_commune(tmp_path: Path):
    source = _make_shifted_audit(tmp_path / "audit.xlsx")

    result = filter_audit_rows(source, tmp_path / "out.xlsx", ["74143_4"])  # =B2*2 remonté en ligne 2

    assert result.kept_ids == ["74143_4"]
    assert result.realigned_formulas == 1
    ws = load_workbook(tmp_path / "out.xlsx")["Audit"]
    assert [cell.value for cell in ws[2]] == ["74143", 40, "74143_4", "=B2*2"]


def test_each_formula_reads_its_own_row_after_export(tmp_path: Path):
    source = _make_shifted_audit(tmp_path / "audit.xlsx")

    result = filter_audit_rows(source, tmp_path / "out.xlsx", ["74143_2", "74143_3", "74143_5"])

    assert result.realigned_formulas == 2  # 74143_3 lisait déjà sa propre ligne
    ws = load_workbook(tmp_path / "out.xlsx")["Audit"]
    assert [ws.cell(row, 4).value for row in range(2, 5)] == ["=B2*2", "=B3*2", "=B4*2"]


def test_hyperlink_stays_on_its_row(tmp_path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Audit"
    ws.append(["ID erreur", "Lien"])
    for number in range(1, 4):
        ws.append([f"74143_{number}", f"lien {number}"])
        ws.cell(number + 1, 2).hyperlink = f"https://example.org/{number}"
    wb.save(tmp_path / "audit.xlsx")

    filter_audit_rows(tmp_path / "audit.xlsx", tmp_path / "out.xlsx", ["74143_3"])

    out = load_workbook(tmp_path / "out.xlsx")["Audit"]
    assert out["B2"].value == "lien 3"
    assert out["B2"].hyperlink.target == "https://example.org/3"
    assert out["B2"].hyperlink.ref == "B2"
