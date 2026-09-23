"""
Extraction et normalisation des codes commune saisis par l'utilisateur.
"""
from __future__ import annotations

import re
from typing import List

# Codes Corse (2A/2B + 3 chiffres) ou codes INSEE/postaux à 5 chiffres.
COMMUNE_CODE_PATTERN = re.compile(r'\b(?:2[ABab]\d{3}|\d{5})\b')


def extract_commune_codes(text: str) -> List[str]:
    """
    Extrait les codes commune uniques d'un texte libre.
    Conserve l'ordre d'apparition et supprime les doublons.
    """
    matches = COMMUNE_CODE_PATTERN.findall(text.upper())
    return list(dict.fromkeys(matches))
