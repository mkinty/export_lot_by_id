"""
Localisation des fichiers audit sur le disque (arborescence OneDrive).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional


class AuditFileLocator:
    """
    Recherche le fichier audit_*.xlsx d'une commune, dans une arborescence
    du type : root_path / DepXX / COMMUNE / audit_*.xlsx
    """

    FILE_PREFIX = "audit_"
    FILE_SUFFIX = ".xlsx"

    def __init__(self, root_path: Path):
        self.root_path = Path(root_path)

    def _commune_dir(self, commune: str) -> Path:
        commune = commune.strip().upper()
        departement = f"Dep{commune[:2]}"
        return self.root_path / departement / commune

    def find(self, commune: str) -> Optional[Path]:
        """Renvoie le chemin du premier fichier audit trouvé pour cette commune, ou None."""
        commune_dir = self._commune_dir(commune)
        if not commune_dir.is_dir():
            return None

        for entry in sorted(commune_dir.iterdir()):
            if entry.is_file() and entry.name.startswith(self.FILE_PREFIX) and entry.name.endswith(self.FILE_SUFFIX):
                return entry
        return None
