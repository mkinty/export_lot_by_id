"""
Localisation des fichiers audit sur le disque (arborescence OneDrive).
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional


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

    def find_all(self, commune: str) -> List[Path]:
        """
        Fichiers audit de la commune : audit_<commune>.xlsx d'abord, puis les autres copies.
        Sans cette priorité, une copie de conflit OneDrive (audit_38200-NB-PC.xlsx) passerait
        avant le vrai fichier, « - » étant trié avant « . ».
        """
        commune_dir = self._commune_dir(commune)
        if not commune_dir.is_dir():
            return []
        expected = f"{self.FILE_PREFIX}{commune.strip()}{self.FILE_SUFFIX}".lower()
        files = [
            entry for entry in commune_dir.iterdir()
            if entry.is_file() and entry.name.lower().startswith(self.FILE_PREFIX)
            and entry.name.lower().endswith(self.FILE_SUFFIX)
        ]
        return sorted(files, key=lambda entry: (entry.name.lower() != expected, entry.name.lower()))

    def find(self, commune: str) -> Optional[Path]:
        """Renvoie le fichier audit à utiliser pour cette commune, ou None."""
        files = self.find_all(commune)
        return files[0] if files else None

    def explain_missing(self, commune: str) -> str:
        """Dit précisément pourquoi aucun fichier audit n'est trouvé pour cette commune."""
        commune_dir = self._commune_dir(commune)
        if not self.root_path.is_dir():
            detail = f"dossier source {self.root_path} absent"
        elif not commune_dir.parent.is_dir():
            detail = f"dossier {commune_dir.parent.name} absent de {self.root_path}"
        elif not commune_dir.is_dir():
            detail = f"dossier {commune_dir.name} absent de {commune_dir.parent}"
        else:
            detail = f"aucun fichier {self.FILE_PREFIX}*{self.FILE_SUFFIX} dans {commune_dir}"
        return f"fichier audit introuvable : {detail}"
