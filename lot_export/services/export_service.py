"""
Service métier : copie les fichiers audit des communes vers le dossier LOT.
Ne dépend d'aucune bibliothèque graphique -> testable unitairement sans mock complexe.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Iterable, List, Mapping, Optional, Sequence

from ..models import ExportItem, ExportStatus, ExportSummary
from .excel_filter import ExcelFilterError, FilterResult, filter_audit_rows
from .file_locator import AuditFileLocator

ProgressCallback = Callable[[int, int, str], None]
CopyFunction = Callable[[Path, Path], None]
FilterFunction = Callable[[Path, Path, Sequence[str]], FilterResult]


class ExportService:
    """Orchestration de l'export d'une liste de communes vers un dossier LOT."""

    def __init__(
        self,
        locator: AuditFileLocator,
        copy_fn: Optional[CopyFunction] = None,
        filter_fn: Optional[FilterFunction] = None,
    ):
        self.locator = locator
        # Les fonctions de copie et de filtrage sont injectables : permet de les remplacer par un mock
        # dans les tests, sans toucher au disque ni dépendre de shutil/openpyxl.
        self._copy_fn: CopyFunction = copy_fn or (lambda src, dst: shutil.copy2(src, dst))
        self._filter_fn: FilterFunction = filter_fn or filter_audit_rows

    def export(
        self,
        communes: Iterable[str],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExportSummary:
        """Copie les fichiers audit complets des communes données vers destination_dir."""
        return self._run(list(communes), destination_dir, on_progress, "Copie",
                         lambda commune, dest: self._export_one(commune, dest))

    def export_by_error_ids(
        self,
        error_ids_by_commune: Mapping[str, Sequence[str]],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExportSummary:
        """Pour chaque commune, écrit dans destination_dir un fichier audit réduit aux ID erreur donnés."""
        return self._run(list(error_ids_by_commune), destination_dir, on_progress, "Filtrage",
                         lambda commune, dest: self._export_filtered(commune, error_ids_by_commune[commune], dest))

    def _run(
        self,
        communes: List[str],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback],
        verb: str,
        export_one: Callable[[str, Path], ExportItem],
    ) -> ExportSummary:
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)

        summary = ExportSummary()
        for index, commune in enumerate(communes, start=1):
            if on_progress:
                on_progress(index, len(communes), f"{verb} {commune}...")
            summary.items.append(export_one(commune, destination_dir))

        return summary

    def _export_one(self, commune: str, destination_dir: Path) -> ExportItem:
        source = self.locator.find(commune)
        if source is None:
            return ExportItem(commune=commune, status=ExportStatus.NOT_FOUND,
                               message="fichier introuvable")

        destination = destination_dir / source.name
        try:
            self._copy_fn(source, destination)
        except OSError as exc:
            return ExportItem(commune=commune, source=source, destination=destination,
                               status=ExportStatus.ERROR, message=str(exc))

        return ExportItem(commune=commune, source=source, destination=destination,
                           status=ExportStatus.SUCCESS, message=f"{source.name} copié")

    def _export_filtered(self, commune: str, error_ids: Sequence[str], destination_dir: Path) -> ExportItem:
        source = self.locator.find(commune)
        if source is None:
            return ExportItem(commune=commune, status=ExportStatus.NOT_FOUND,
                               message="fichier introuvable")

        destination = destination_dir / source.name
        try:
            result = self._filter_fn(source, destination, error_ids)
        except (OSError, ExcelFilterError) as exc:
            return ExportItem(commune=commune, source=source, destination=destination,
                               status=ExportStatus.ERROR, message=str(exc))
        except Exception as exc:  # fichier Excel corrompu/illisible : ne pas interrompre le lot
            return ExportItem(commune=commune, source=source, destination=destination,
                               status=ExportStatus.ERROR, message=f"lecture Excel impossible ({exc})")

        missing = f" — introuvable(s) : {', '.join(result.missing_ids)}" if result.missing_ids else ""
        if not result.kept_ids:
            return ExportItem(commune=commune, source=source, status=ExportStatus.NOT_FOUND,
                               message=f"aucun ID erreur trouvé dans {source.name}{missing}")

        return ExportItem(commune=commune, source=source, destination=destination,
                           status=ExportStatus.SUCCESS,
                           message=f"{source.name} — {len(result.kept_ids)}/{len(error_ids)} ligne(s){missing}")
