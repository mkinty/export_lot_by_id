"""
Modèles de données métier.
Simples dataclasses, sans dépendance externe : faciles à instancier dans les tests.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ExportStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"


class NotExportedCause(str, Enum):
    """Catégorie de cause, pour compter les valeurs non exportées dans le bilan."""
    NO_FILE = "Fichier audit introuvable dans le dossier source"
    VALUE_ABSENT = "Absent du fichier audit de la commune"
    IN_OTHER_FILE = "Présent uniquement dans une autre copie du fichier audit"
    FILE_INACCESSIBLE = "Fichier audit inaccessible (verrouillé ou non synchronisé)"
    FILE_INVALID = "Fichier audit illisible ou de structure inattendue"
    MERGE_FAILED = "Fusion dans le fichier unique impossible"
    NOT_IN_OUTPUT = "Absent du fichier final lors du contrôle"


@dataclass(frozen=True)
class NotExported:
    """Valeur demandée (ID erreur, adresse) absente de l'export, avec la raison."""
    value: str
    reason: str
    cause: NotExportedCause = NotExportedCause.VALUE_ABSENT


@dataclass(frozen=True)
class ExportItem:
    """Résultat de l'export d'une commune."""
    commune: str
    source: Optional[Path] = None
    destination: Optional[Path] = None
    status: ExportStatus = ExportStatus.NOT_FOUND
    message: str = ""
    # Export filtré uniquement : valeurs demandées réparties entre exportées et non exportées
    exported: tuple[str, ...] = ()
    not_exported: tuple[NotExported, ...] = ()
    rows: int = 0  # lignes Audit exportées : un même ID peut figurer sur plusieurs lignes

    @property
    def ok(self) -> bool:
        return self.status == ExportStatus.SUCCESS


@dataclass
class ExportSummary:
    """Bilan complet d'un export par lot (agrège les ExportItem)."""
    items: list[ExportItem] = field(default_factory=list)
    # Renseignés uniquement pour un export en fichier unique
    merged_file: Optional[Path] = None
    merged_rows: int = 0

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.items if item.ok)

    @property
    def has_success(self) -> bool:
        return self.success_count > 0

    @property
    def exported_count(self) -> int:
        return sum(len(item.exported) for item in self.items)

    @property
    def exported_rows(self) -> int:
        return sum(item.rows for item in self.items)

    @property
    def not_exported_count(self) -> int:
        return sum(len(item.not_exported) for item in self.items)

    def not_exported_by_cause(self) -> list[tuple[NotExportedCause, int]]:
        """Nombre de valeurs non exportées par cause, de la plus fréquente à la moins fréquente."""
        counts = Counter(entry.cause for item in self.items for entry in item.not_exported)
        return counts.most_common()
