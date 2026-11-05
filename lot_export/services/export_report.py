"""
Rapport texte de contrôle d'un export filtré : combien de valeurs demandées, combien
réellement présentes dans les fichiers produits, et pourquoi les autres sont absentes.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

from ..models import ExportSummary, NotExportedCause

CAUSE_ADVICE = {
    NotExportedCause.NO_FILE: "vérifiez le dossier source choisi et la présence de DepXX/<commune>/audit_<commune>.xlsx.",
    NotExportedCause.VALUE_ABSENT: "vérifiez l'ID saisi et que le fichier source est bien la dernière version.",
    NotExportedCause.IN_OTHER_FILE: "résolvez le conflit entre les copies (OneDrive), puis rejouez ces ID.",
    NotExportedCause.FILE_INACCESSIBLE: "fermez le fichier, attendez la synchronisation OneDrive, puis rejouez ces ID.",
    NotExportedCause.FILE_INVALID: "ouvrez le fichier source : feuille Audit et colonne attendues présentes ?",
    NotExportedCause.MERGE_FAILED: "fermez le fichier final s'il est ouvert dans Excel, puis rejouez ces ID.",
    NotExportedCause.NOT_IN_OUTPUT: "anomalie de l'application : conservez ce rapport et signalez-la.",
}


def report_path(lot_dir: Path, lot_number: str) -> Path:
    return Path(lot_dir) / f"non_exportes_LOT{lot_number}.txt"


def write_not_exported_report(
    summary: ExportSummary,
    invalid_values: Sequence[str],
    duplicates: Mapping[str, int],
    lot_dir: Path,
    lot_number: str,
    unit: str,
    source_root: Path,
) -> Optional[Path]:
    """
    Écrit le rapport dans le dossier du LOT et renvoie son chemin.
    Sans anomalie, ne crée rien et supprime le rapport d'un export précédent, devenu périmé.
    """
    path = report_path(lot_dir, lot_number)
    if not summary.not_exported_count and not invalid_values and not duplicates:
        path.unlink(missing_ok=True)
        return None

    distinct = summary.exported_count + summary.not_exported_count
    extra_occurrences = sum(count - 1 for count in duplicates.values())
    lines: List[str] = [
        f"Contrôle de l'export — LOT{lot_number} — {unit}",
        f"Généré le {datetime.now():%d/%m/%Y à %H:%M}",
        f"Dossier source : {source_root}",
        "",
        "BILAN",
        f"  Valeurs reconnues dans la saisie        : {distinct + extra_occurrences}",
        f"  dont doublons, exportés une seule fois  : {extra_occurrences}",
        f"  Valeurs distinctes demandées            : {distinct}",
        f"  Exportées, vérifiées dans le fichier final : {summary.exported_count} "
        f"({summary.exported_rows} ligne(s) Audit)",
        f"  NON exportées                           : {summary.not_exported_count}",
        f"  Saisies non reconnues, jamais recherchées : {len(invalid_values)}",
        f"  Formules décalées de la source, recalées sur leur ligne : {summary.realigned_formulas}",
    ]
    causes = summary.not_exported_by_cause()
    if causes:
        lines += ["", "CAUSES ET QUE FAIRE"]
        for cause, count in causes:
            lines += [f"  {count} : {cause.value}", f"      → {CAUSE_ADVICE[cause]}"]
    if summary.not_exported_count:
        lines += ["", "DÉTAIL DES VALEURS NON EXPORTÉES"]
    for item in summary.items:
        if not item.not_exported:
            continue
        lines += ["", f"Commune {item.commune}" + (f" — {item.source}" if item.source else "")]
        lines += [f"  {entry.value} : {entry.reason}" for entry in item.not_exported]
    if invalid_values:
        lines += ["", "SAISIES NON RECONNUES (format invalide, jamais recherchées)"]
        lines += [f"  {value}" for value in invalid_values]
    if duplicates:
        lines += ["", "DOUBLONS DANS LA SAISIE (exportés une seule fois)"]
        lines += [f"  {value} : saisi {count} fois" for value, count in duplicates.items()]

    # utf-8-sig : accents correctement affichés par le Bloc-notes et Excel
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return path
