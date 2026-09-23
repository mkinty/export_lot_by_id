"""
Construction et validation du nom/chemin du dossier LOT.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_FORBIDDEN_CHARS_PATTERN = re.compile(r'[^\w-]')


def sanitize_lot_number(raw_number: str) -> str:
    """Ne conserve que les caractères alphanumériques, tirets et underscores."""
    return _FORBIDDEN_CHARS_PATTERN.sub("", raw_number.strip())


def build_lot_dir(downloads_dir: Path, lot_number: str) -> Optional[Path]:
    """Construit le chemin complet du dossier LOT<numero>. Renvoie None si le numéro est vide."""
    clean_number = sanitize_lot_number(lot_number)
    if not clean_number:
        return None
    return Path(downloads_dir) / f"LOT{clean_number}"
