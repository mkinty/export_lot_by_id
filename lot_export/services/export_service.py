"""
Service métier : copie les fichiers audit des communes vers le dossier LOT.
Ne dépend d'aucune bibliothèque graphique -> testable unitairement sans mock complexe.
"""
from __future__ import annotations

import shutil
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from ..models import ExportItem, ExportStatus, ExportSummary, NotExported, NotExportedCause
from .excel_filter import (
    ADDRESS_HEADER,
    ERROR_ID_HEADER,
    ExcelFilterError,
    FilterResult,
    filter_audit_rows,
    find_values,
)
from .excel_merger import merge_audit_files
from .file_locator import AuditFileLocator

ProgressCallback = Callable[[int, int, str], None]
CopyFunction = Callable[[Path, Path], None]
FilterFunction = Callable[[Path, Path, Sequence[str], str], FilterResult]  # (src, dst, valeurs, colonne)
MergeFunction = Callable[[Sequence[Path], Path], int]  # (fichiers, destination) -> nb lignes Audit
FindFunction = Callable[[Path, Sequence[str], str], List[str]]  # (fichier, valeurs, colonne) -> valeurs présentes


class ExportService:
    """Orchestration de l'export d'une liste de communes vers un dossier LOT."""

    def __init__(
        self,
        locator: AuditFileLocator,
        copy_fn: Optional[CopyFunction] = None,
        filter_fn: Optional[FilterFunction] = None,
        merge_fn: Optional[MergeFunction] = None,
        find_fn: Optional[FindFunction] = None,
    ):
        self.locator = locator
        # Les fonctions de copie, de filtrage et de fusion sont injectables : permet de les remplacer par un mock
        # dans les tests, sans toucher au disque ni dépendre de shutil/openpyxl.
        self._copy_fn: CopyFunction = copy_fn or (lambda src, dst: shutil.copy2(src, dst))
        self._filter_fn: FilterFunction = filter_fn or filter_audit_rows
        self._merge_fn: MergeFunction = merge_fn or merge_audit_files
        self._find_fn: FindFunction = find_fn or find_values

    def export(
        self,
        communes: Iterable[str],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback] = None,
        single_file_name: Optional[str] = None,
    ) -> ExportSummary:
        """
        Copie les fichiers audit complets des communes données vers destination_dir.
        Si single_file_name est renseigné, les fichiers sont fusionnés dans ce fichier unique.
        """
        return self._run(list(communes), destination_dir, on_progress, single_file_name, "Copie",
                         lambda commune, dest: self._export_one(commune, dest))

    def export_by_error_ids(
        self,
        error_ids_by_commune: Mapping[str, Sequence[str]],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback] = None,
        single_file_name: Optional[str] = None,
    ) -> ExportSummary:
        """Pour chaque commune, écrit dans destination_dir un fichier audit réduit aux ID erreur donnés."""
        return self._run(list(error_ids_by_commune), destination_dir, on_progress, single_file_name, "Filtrage",
                         lambda commune, dest: self._export_filtered(
                             commune, error_ids_by_commune[commune], dest, ERROR_ID_HEADER, "ID erreur"),
                         ERROR_ID_HEADER)

    def export_by_addresses(
        self,
        addresses_by_commune: Mapping[str, Sequence[str]],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback] = None,
        single_file_name: Optional[str] = None,
    ) -> ExportSummary:
        """Pour chaque commune, écrit dans destination_dir un fichier audit réduit aux adresses données."""
        return self._run(list(addresses_by_commune), destination_dir, on_progress, single_file_name, "Filtrage",
                         lambda commune, dest: self._export_filtered(
                             commune, addresses_by_commune[commune], dest, ADDRESS_HEADER, "adresse"),
                         ADDRESS_HEADER)

    def _run(
        self,
        communes: List[str],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback],
        single_file_name: Optional[str],
        verb: str,
        export_one: Callable[[str, Path], ExportItem],
        column: Optional[str] = None,
    ) -> ExportSummary:
        destination_dir = Path(destination_dir)
        destination_dir.mkdir(parents=True, exist_ok=True)
        if single_file_name is None:
            summary = self._export_all(communes, destination_dir, on_progress, verb, export_one)
        else:
            # Fichier unique : un fichier par commune dans un dossier temporaire, puis fusion.
            with tempfile.TemporaryDirectory(prefix="lot_export_") as tmp:
                summary = self._export_all(communes, Path(tmp), on_progress, verb, export_one)
                self._merge(summary, destination_dir / single_file_name, on_progress)
        if column is not None:
            self._verify_outputs(summary, column, on_progress)
        return summary

    def _verify_outputs(self, summary: ExportSummary, column: str, on_progress: Optional[ProgressCallback]) -> None:
        """Relit les fichiers produits : une valeur n'est comptée exportée que si elle y figure réellement."""
        by_output: Dict[Path, List[str]] = {}
        for item in summary.items:
            if item.ok:
                by_output.setdefault(item.destination, []).extend(item.exported)
        if on_progress and by_output:
            on_progress(summary.total, summary.total, "Contrôle des fichiers produits...")
        present: Dict[Path, set] = {}
        failures: Dict[Path, str] = {}
        for output, values in by_output.items():
            try:
                present[output] = set(self._find_fn(output, values, column))
            except Exception as exc:  # le fichier final ne se relit pas : l'export n'est pas garanti
                failures[output] = f"contrôle du fichier {output.name} impossible ({exc})"

        checked = []
        for item in summary.items:
            if not item.ok:
                checked.append(item)
                continue
            found = present.get(item.destination, set())
            kept = tuple(value for value in item.exported if value in found)
            lost = tuple(value for value in item.exported if value not in found)
            if lost:
                reason = failures.get(item.destination, f"absent du fichier final {item.destination.name}")
                item = replace(
                    item, exported=kept, status=item.status if kept else ExportStatus.ERROR,
                    message=f"{item.message} — {len(lost)} absent(s) du fichier final",
                    not_exported=item.not_exported + _not_exported(lost, reason, NotExportedCause.NOT_IN_OUTPUT),
                )
            checked.append(item)
        summary.items = checked

    @staticmethod
    def _export_all(
        communes: List[str],
        destination_dir: Path,
        on_progress: Optional[ProgressCallback],
        verb: str,
        export_one: Callable[[str, Path], ExportItem],
    ) -> ExportSummary:
        summary = ExportSummary()
        for index, commune in enumerate(communes, start=1):
            if on_progress:
                on_progress(index, len(communes), f"{verb} {commune}...")
            summary.items.append(export_one(commune, destination_dir))
        return summary

    def _merge(self, summary: ExportSummary, target: Path, on_progress: Optional[ProgressCallback]) -> None:
        """Fusionne les fichiers exportés avec succès dans target et met à jour le bilan."""
        sources = [item.destination for item in summary.items if item.ok]
        if not sources:
            return
        if on_progress:
            on_progress(len(summary.items), len(summary.items), f"Fusion dans {target.name}...")
        try:
            rows = self._merge_fn(sources, target)
        except Exception as exc:  # fusion impossible : aucune commune n'est réellement exportée
            summary.items = [
                replace(item, destination=None, status=ExportStatus.ERROR,
                        message=f"{item.message} — fusion impossible ({exc})", exported=(), rows=0,
                        not_exported=item.not_exported + _not_exported(
                            item.exported, f"fusion impossible ({exc})", NotExportedCause.MERGE_FAILED))
                if item.ok else item
                for item in summary.items
            ]
            return
        summary.items = [replace(item, destination=target) if item.ok else item for item in summary.items]
        summary.merged_file = target
        summary.merged_rows = rows

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

    def _export_filtered(
        self, commune: str, values: Sequence[str], destination_dir: Path, column: str, label: str,
    ) -> ExportItem:
        source = self.locator.find(commune)
        if source is None:
            reason = self.locator.explain_missing(commune)
            return ExportItem(commune=commune, status=ExportStatus.NOT_FOUND, message=reason,
                               not_exported=_not_exported(values, reason, NotExportedCause.NO_FILE))

        destination = destination_dir / source.name
        try:
            result = self._filter_fn(source, destination, values, column)
        except OSError as exc:
            message = f"fichier inaccessible, verrouillé ou non synchronisé ({exc})"
            return ExportItem(commune=commune, source=source, destination=destination,
                               status=ExportStatus.ERROR, message=message,
                               not_exported=_not_exported(values, message, NotExportedCause.FILE_INACCESSIBLE))
        except ExcelFilterError as exc:
            return ExportItem(commune=commune, source=source, destination=destination,
                               status=ExportStatus.ERROR, message=str(exc),
                               not_exported=_not_exported(values, str(exc), NotExportedCause.FILE_INVALID))
        except Exception as exc:  # fichier Excel corrompu/illisible : ne pas interrompre le lot
            message = f"lecture Excel impossible ({exc})"
            return ExportItem(commune=commune, source=source, destination=destination,
                               status=ExportStatus.ERROR, message=message,
                               not_exported=_not_exported(values, message, NotExportedCause.FILE_INVALID))

        not_exported = self._explain_missing(commune, source, result, column)
        missing = f" — introuvable(s) : {', '.join(result.missing_ids)}" if result.missing_ids else ""
        if not result.kept_ids:
            return ExportItem(commune=commune, source=source, status=ExportStatus.NOT_FOUND,
                               message=f"aucun(e) {label} trouvé(e) dans {source.name}{missing}",
                               not_exported=not_exported)

        return ExportItem(commune=commune, source=source, destination=destination,
                           status=ExportStatus.SUCCESS,
                           message=f"{source.name} — {len(result.kept_ids)}/{len(values)} {label}(s){missing}",
                           exported=tuple(result.kept_ids), not_exported=not_exported, rows=result.kept_rows)

    def _explain_missing(
        self, commune: str, source: Path, result: FilterResult, column: str,
    ) -> Tuple[NotExported, ...]:
        """Cherche les valeurs absentes dans les autres copies : on signale, sans choisir à la place de l'utilisateur."""
        located: Dict[str, Path] = {}
        if result.missing_ids:
            for other in self.locator.find_all(commune):
                if other == source:
                    continue
                try:
                    found = self._find_fn(other, result.missing_ids, column)
                except Exception:  # copie illisible : la raison par défaut reste valable
                    continue
                for value in found:
                    located.setdefault(value, other)

        entries = []
        for value in result.missing_ids:
            if value in located:
                entries.append(NotExported(
                    value,
                    f"absent de {source.name}, mais présent dans {located[value].name}, autre copie non exportée "
                    "du même dossier : vérifiez quelle copie est à jour",
                    NotExportedCause.IN_OTHER_FILE,
                ))
            else:
                entries.append(NotExported(
                    value, result.reasons.get(value, f"absent(e) de la colonne « {column} »")))
        return tuple(entries)


def _not_exported(values: Iterable[str], reason: str, cause: NotExportedCause) -> Tuple[NotExported, ...]:
    return tuple(NotExported(value, reason, cause) for value in values)
