"""
Modèles de données métier.
Simples dataclasses, sans dépendance externe : faciles à instancier dans les tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ExportStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass(frozen=True)
class ExportItem:
    """Résultat de l'export d'une commune."""
    commune: str
    source: Optional[Path] = None
    destination: Optional[Path] = None
    status: ExportStatus = ExportStatus.NOT_FOUND
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == ExportStatus.SUCCESS


@dataclass
class ExportSummary:
    """Bilan complet d'un export par lot (agrège les ExportItem)."""
    items: list[ExportItem] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def success_count(self) -> int:
        return sum(1 for item in self.items if item.ok)

    @property
    def has_success(self) -> bool:
        return self.success_count > 0
