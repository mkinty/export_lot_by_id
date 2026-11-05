"""
Filtrage d'un fichier audit : ne conserve, dans la feuille Audit, que les lignes
dont la valeur d'une colonne donnée (« ID erreur », « adresse »...) fait partie d'une liste.
Les autres feuilles sont copiées telles quelles.

Le fichier produit ne garde ni filtre actif ni ligne/colonne masquée (voir reveal_all) ;
le fichier source n'est jamais modifié.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

AUDIT_SHEET = "Audit"
ERROR_ID_HEADER = "ID erreur"
ADDRESS_HEADER = "adresse"
DEFAULT_COLUMN_WIDTH = 13  # une colonne masquée par une largeur nulle doit redevenir lisible


class ExcelFilterError(Exception):
    """Structure du fichier audit inattendue (feuille ou colonne absente)."""


@dataclass
class FilterResult:
    """Valeurs demandées trouvées (kept_ids) ou absentes (missing_ids) de la colonne filtrée."""
    kept_ids: List[str] = field(default_factory=list)
    missing_ids: List[str] = field(default_factory=list)
    # valeur absente -> explication pour le rapport des valeurs non exportées
    reasons: Dict[str, str] = field(default_factory=dict)
    kept_rows: int = 0


def _normalize(value: object) -> str:
    """Comparaison insensible à la casse, aux accents et aux espaces multiples."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().upper()


def _find_column(ws: Worksheet, header: str) -> int:
    for cell in ws[1]:
        if _normalize(cell.value) == _normalize(header):
            return cell.column
    raise ExcelFilterError(f"colonne « {header} » introuvable")


def reveal_all(wb: Workbook) -> None:
    """
    Retire les filtres actifs (les flèches de filtre restent) et réaffiche lignes et colonnes
    masquées, sur toutes les feuilles. Excel enregistre un filtre comme des lignes masquées :
    sans cela, les lignes exportées peuvent rester invisibles à l'ouverture du fichier.
    """
    for ws in wb.worksheets:
        ws.auto_filter.filterColumn = []
        ws.auto_filter.sortState = None
        ws.sheet_format.zeroHeight = None
        for row in ws.row_dimensions.values():
            row.hidden = False
            if row.height == 0:
                row.height = None
        for column in ws.column_dimensions.values():
            column.hidden = False
            if column.width == 0:
                column.width = DEFAULT_COLUMN_WIDTH


def _move_row_dimensions(ws: Worksheet, kept_rows: List[int]) -> None:
    """Fait suivre hauteur et style de ligne : move_range et delete_rows ne déplacent que les cellules."""
    dimensions = ws.row_dimensions
    moved = {new: dimensions[old] for new, old in enumerate(kept_rows, start=2) if old in dimensions}
    for row in [row for row in dimensions if row >= 2]:
        del dimensions[row]
    for new, dimension in moved.items():
        dimension.index = new
        dimensions[new] = dimension


def _explain_missing(ws: Worksheet, missing: Iterable[str], column: str, nb_values: int) -> Dict[str, str]:
    """Explique chaque valeur absente (clé normalisée), en cherchant si elle apparaît ailleurs dans la feuille."""
    reasons = {key: f"absent(e) de la colonne « {column} » de la feuille {AUDIT_SHEET} "
                    f"({nb_values} valeur(s) distincte(s) dans cette colonne)" for key in missing}
    if not reasons:
        return reasons
    pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, reasons)) + r")(?!\w)")
    located = set()
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if cell.value is None or (isinstance(cell.value, str) and cell.value.startswith("=")):
                continue
            text = _normalize(cell.value)
            for key in set(pattern.findall(text)) - located:
                located.add(key)
                reasons[key] = (f"pas de correspondance exacte dans la colonne « {column} », mais trouvé(e) "
                                f"en {cell.coordinate} de la feuille {AUDIT_SHEET} : « {text[:80]} »")
    return reasons


def find_values(path: Path, values: Iterable[str], column: str = ERROR_ID_HEADER) -> List[str]:
    """Renvoie les valeurs présentes dans la colonne `column` de la feuille Audit, sans modifier le fichier."""
    wanted = {_normalize(value): value for value in values}
    wb = load_workbook(path, read_only=True)
    try:
        if AUDIT_SHEET not in wb.sheetnames:
            raise ExcelFilterError(f"feuille « {AUDIT_SHEET} » introuvable")
        ws = wb[AUDIT_SHEET]
        ws.reset_dimensions()  # certains fichiers déclarent des dimensions fausses
        rows = ws.iter_rows(values_only=True)
        header = [_normalize(cell) for cell in next(rows, ())]
        if _normalize(column) not in header:
            raise ExcelFilterError(f"colonne « {column} » introuvable")
        index = header.index(_normalize(column))
        present = {_normalize(row[index]) for row in rows if index < len(row)}
    finally:
        wb.close()
    return [original for key, original in wanted.items() if key in present]


def filter_audit_rows(
        source: Path, destination: Path, values: Iterable[str], column: str = ERROR_ID_HEADER,
) -> FilterResult:
    """
    Écrit dans destination une copie de source où la feuille Audit ne contient plus
    que l'en-tête et les lignes dont la valeur de la colonne `column` est dans values,
    sans filtre actif ni ligne/colonne masquée.
    N'écrit rien si aucune ligne ne correspond.
    """
    # clé normalisée -> valeur telle que saisie (pour le compte rendu)
    wanted = {}
    for value in values:
        wanted.setdefault(_normalize(value), value)

    wb = load_workbook(source)
    if AUDIT_SHEET not in wb.sheetnames:
        raise ExcelFilterError(f"feuille « {AUDIT_SHEET} » introuvable")
    ws = wb[AUDIT_SHEET]
    id_col = _find_column(ws, column)
    last_col = get_column_letter(ws.max_column)
    max_row = ws.max_row

    # Toutes les lignes sont lues, y compris celles masquées par un filtre.
    column_values = {row: _normalize(ws.cell(row, id_col).value) for row in range(2, max_row + 1)}
    kept_rows = [row for row, value in column_values.items() if value in wanted]
    found = {column_values[row] for row in kept_rows}
    missing = [key for key in wanted if key not in found]
    nb_distinct = len(set(column_values.values()) - {""})
    reasons = _explain_missing(ws, missing, column, nb_distinct)

    result = FilterResult(
        kept_ids=[original for key, original in wanted.items() if key in found],
        missing_ids=[wanted[key] for key in missing],
        reasons={wanted[key]: reason for key, reason in reasons.items()},
        kept_rows=len(kept_rows),
    )
    if not found:
        return result

    for target, row in enumerate(kept_rows, start=2):
        if row != target:
            # translate=True réécrit les formules relatives (ex: J57 -> J3) pour la nouvelle ligne
            ws.move_range(f"A{row}:{last_col}{row}", rows=target - row, translate=True)
    first_unused = len(kept_rows) + 2
    if first_unused <= max_row:
        ws.delete_rows(first_unused, max_row - first_unused + 1)
    _move_row_dimensions(ws, kept_rows)
    reveal_all(wb)

    wb.save(destination)
    return result
