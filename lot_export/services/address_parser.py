"""
Extraction des adresses saisies par l'utilisateur et regroupement par code commune.
Une entrée a la forme <code INSEE>_<adresse>,
ex : 05094_495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT.
"""
from __future__ import annotations

import re
from typing import Dict, List

# Début d'une entrée : code INSEE suivi de « _ ». L'adresse court jusqu'à l'entrée suivante.
ENTRY_START_PATTERN = re.compile(r'\b((?:2[AB]|\d{2})\d{3})_')
# Séparateurs/délimiteurs de liste tolérés autour d'une adresse : , ; [ ] " '
TRIM_CHARS = " \t\r\n,;[]\"'"


def extract_addresses(text: str) -> Dict[str, List[str]]:
    """
    Extrait les adresses d'un texte libre et les regroupe par code INSEE :
    {"05094": ["495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT"], ...}.
    Les adresses sont mises en majuscules, les espaces multiples réduits.
    Conserve l'ordre d'apparition et supprime les doublons.
    """
    text = text.upper()
    matches = list(ENTRY_START_PATTERN.finditer(text))
    grouped: Dict[str, List[str]] = {}
    for match, following in zip(matches, matches[1:] + [None]):
        end = following.start() if following else len(text)
        # une adresse ne s'étend jamais au-delà de sa ligne
        line = text[match.end():end].splitlines()[0] if end > match.end() else ""
        address = " ".join(line.strip(TRIM_CHARS).split())
        if not address:
            continue
        addresses = grouped.setdefault(match.group(1), [])
        if address not in addresses:
            addresses.append(address)
    return grouped
