"""
Filtrage d'un fichier audit : ne conserve, dans la feuille Audit, que les lignes
dont l'ID erreur fait partie d'une liste donnée. Les autres feuilles sont copiées telles quelles.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

AUDIT_SHEET = "Audit"
ERROR_ID_HEADER = "ID erreur"


class ExcelFilterError(Exception):
    """Structure du fichier audit inattendue (feuille ou colonne absente)."""


@dataclass
class FilterResult:
    kept_ids: List[str] = field(default_factory=list)
    missing_ids: List[str] = field(default_factory=list)


def _normalize(value: object) -> str:
    return str(value).strip().upper() if value is not None else ""


def _find_error_id_column(ws: Worksheet) -> int:
    for cell in ws[1]:
        if _normalize(cell.value) == ERROR_ID_HEADER.upper():
            return cell.column
    raise ExcelFilterError(f"colonne « {ERROR_ID_HEADER} » introuvable")


def filter_audit_rows(source: Path, destination: Path, error_ids: Iterable[str]) -> FilterResult:
    """
    Écrit dans destination une copie de source où la feuille Audit ne contient plus
    que l'en-tête et les lignes dont l'ID erreur est dans error_ids.
    N'écrit rien si aucune ligne ne correspond.
    """
    wanted = list(dict.fromkeys(_normalize(i) for i in error_ids))
    wanted_set = set(wanted)

    wb = load_workbook(source)
    if AUDIT_SHEET not in wb.sheetnames:
        raise ExcelFilterError(f"feuille « {AUDIT_SHEET} » introuvable")
    ws = wb[AUDIT_SHEET]
    id_col = _find_error_id_column(ws)
    last_col = get_column_letter(ws.max_column)
    max_row = ws.max_row

    found: set[str] = set()
    target = 2
    for row in range(2, max_row + 1):
        error_id = _normalize(ws.cell(row, id_col).value)
        if error_id not in wanted_set:
            continue
        found.add(error_id)
        if row != target:
            # translate=True réécrit les formules relatives (ex: J57 -> J3) pour la nouvelle ligne
            ws.move_range(f"A{row}:{last_col}{row}", rows=target - row, translate=True)
        target += 1

    result = FilterResult(
        kept_ids=[i for i in wanted if i in found],
        missing_ids=[i for i in wanted if i not in found],
    )
    if not found:
        return result

    if target <= max_row:
        ws.delete_rows(target, max_row - target + 1)

    wb.save(destination)
    return result
