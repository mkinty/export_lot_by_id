"""
Déplacement d'une formule vers une autre ligne, sans jamais bloquer l'export.

Certains fichiers audit contiennent des formules décalées : BG11 lit la ligne 2 au lieu de la
ligne 11. Conserver ce décalage en déplaçant la ligne fait lire la ligne d'un autre ID, ou une
ligne inexistante (« Formula out of range » d'openpyxl). Une formule qui ne lit qu'une seule
ligne de sa feuille est donc recalée sur sa nouvelle ligne.
"""
from __future__ import annotations

import re
from typing import Optional, Set, Tuple

from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import Token
from openpyxl.formula.translate import Translator, TranslatorError
from openpyxl.utils.cell import coordinate_from_string

BROKEN_REFERENCE = "=#REF!"  # ce qu'Excel écrit lui-même quand une référence sort de la feuille
_LOCAL_REFERENCE = re.compile(r"^\$?[A-Z]{1,3}(\$?)(\d+)(?::\$?[A-Z]{1,3}(\$?)(\d+))?$")


def _single_relative_row(formula: str) -> Optional[int]:
    """Ligne lue par la formule si ses références relatives en désignent une seule, sinon None."""
    rows: Set[int] = set()
    for token in Tokenizer(formula).items:
        if token.type != Token.OPERAND or token.subtype != Token.RANGE:
            continue
        match = _LOCAL_REFERENCE.match(token.value)
        if match is None:  # autre feuille, colonne entière, nom défini : pas de recalage possible
            return None
        for dollar, row in ((match.group(1), match.group(2)), (match.group(3), match.group(4))):
            if row and not dollar:
                rows.add(int(row))
    return rows.pop() if len(rows) == 1 else None


def relocate_formula(formula: str, origin: str, target: str) -> Tuple[str, bool]:
    """
    Renvoie la formule pour la cellule `target` et indique si elle a été recalée sur sa ligne.
    Une référence impossible à déplacer devient #REF! : visible dans Excel, sans bloquer la commune.
    """
    origin_row = coordinate_from_string(origin)[1]
    target_row = coordinate_from_string(target)[1]
    read_row = _single_relative_row(formula)
    row_delta = target_row - (origin_row if read_row is None else read_row)
    try:
        translated = Translator(formula, origin).translate_formula(row_delta=row_delta)
    except TranslatorError:
        return BROKEN_REFERENCE, False
    return translated, read_row is not None and read_row != origin_row
