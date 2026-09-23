"""
Configuration de l'application.
Centralise le chargement/sauvegarde des paramètres persistants (config.json).
Aucune dépendance UI ici : facilement testable.
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, asdict, replace
from pathlib import Path

APP_NAME = "LOT Export"

# DEFAULT_ROOT_PATH = r"C:\Users\u269775\Altice Campus SFR\Swap Adresse - Etude Cible\audit_SNA"
DEFAULT_ROOT_PATH = str(Path.home() / "mkinty")
DEFAULT_DOWNLOADS_DIR = str(Path.home() / "Downloads")


@dataclass(frozen=True)
class AppConfig:
    """Paramètres de configuration de l'application."""
    root_path_be: str = DEFAULT_ROOT_PATH
    downloads_dir: str = DEFAULT_DOWNLOADS_DIR

    @property
    def root_path(self) -> Path:
        return Path(self.root_path_be)

    @property
    def downloads_path(self) -> Path:
        return Path(self.downloads_dir)

    def with_root_path(self, path: str | Path) -> "AppConfig":
        """Renvoie une copie de la config avec un nouveau dossier source."""
        return replace(self, root_path_be=str(path))

    def with_downloads_dir(self, path: str | Path) -> "AppConfig":
        """Renvoie une copie de la config avec un nouveau dossier de destination."""
        return replace(self, downloads_dir=str(path))


def _user_config_dir() -> Path:
    """Dossier de configuration utilisateur, persistant même pour l'exécutable PyInstaller."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME


def config_file_path() -> Path:
    """Emplacement par défaut du fichier config.json (dossier de configuration utilisateur)."""
    return _user_config_dir() / "config.json"


def load_config(path: Path | None = None) -> AppConfig:
    """Charge la configuration depuis config.json, ou renvoie les valeurs par défaut si absent/invalide."""
    path = path or config_file_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return AppConfig()
    if not isinstance(data, dict):
        return AppConfig()

    return AppConfig(
        root_path_be=data.get("root_path_be") or DEFAULT_ROOT_PATH,
        downloads_dir=data.get("downloads_dir") or DEFAULT_DOWNLOADS_DIR,
    )


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Sauvegarde la configuration dans config.json."""
    path = path or config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
