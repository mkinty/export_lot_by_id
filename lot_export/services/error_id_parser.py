"""
Extraction des ID erreur saisis par l'utilisateur et regroupement par code commune.
Un ID erreur a la forme <code INSEE>_<numéro>, ex : 74143_1, 2A004_12.
"""
from __future__ import annotations

import re
from typing import Dict, List

ERROR_ID_PATTERN = re.compile(r'\b((?:2[AB]|\d{2})\d{3})_(\d+)\b')


def extract_error_ids(text: str) -> Dict[str, List[str]]:
    """
    Extrait les ID erreur d'un texte libre et les regroupe par code INSEE :
    {"74143": ["74143_1", "74143_2"], ...}.
    Conserve l'ordre d'apparition et supprime les doublons.
    """
    grouped: Dict[str, List[str]] = {}
    for insee, number in ERROR_ID_PATTERN.findall(text.upper()):
        ids = grouped.setdefault(insee, [])
        error_id = f"{insee}_{number}"
        if error_id not in ids:
            ids.append(error_id)
    return grouped
