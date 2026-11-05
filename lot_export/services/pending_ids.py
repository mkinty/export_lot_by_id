"""
ID erreur non exportés, conservés d'un lancement à l'autre pour pouvoir être rejoués.

Fichier JSON : {"74143_1": {"reason": "...", "date": "2026-11-05 10:56"}, ...}
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Mapping

from ..models import ExportSummary

PENDING_FILE_NAME = "ids_en_attente.json"


def load_pending(path: Path) -> Dict[str, dict]:
    """Renvoie la liste en attente ; un fichier absent ou illisible équivaut à une liste vide."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update_pending(path: Path, failures: Mapping[str, str], successes: Iterable[str]) -> Dict[str, dict]:
    """Retire les ID réussis, ajoute ou remplace les échecs (avec leur raison) et renvoie la liste à jour."""
    pending = load_pending(path)
    for error_id in successes:
        pending.pop(error_id, None)
    date = f"{datetime.now():%Y-%m-%d %H:%M}"
    for error_id, reason in failures.items():
        pending[error_id] = {"reason": reason, "date": date}
    _write(Path(path), pending)
    return pending


def update_pending_from_summary(path: Path, summary: ExportSummary) -> Dict[str, dict]:
    """Met à jour la liste en attente à partir du bilan d'un export par ID erreur."""
    failures = {entry.value: entry.reason for item in summary.items for entry in item.not_exported}
    successes = [error_id for item in summary.items for error_id in item.exported]
    return update_pending(path, failures, successes)


def clear_pending(path: Path) -> None:
    _write(Path(path), {})


def _write(path: Path, pending: Mapping[str, dict]) -> None:
    # écriture atomique : une interruption ne peut pas laisser un fichier à moitié écrit
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
