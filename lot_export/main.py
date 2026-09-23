"""
Point d'entrée de l'application.
Assemble les dépendances (config, services) et lance l'interface graphique PySide6.

Lancer avec :  python -m lot_export.main
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .config import config_file_path, load_config
from .gui.main_window import LotExportWindow
from .services.export_service import ExportService
from .services.file_locator import AuditFileLocator


def build_window() -> LotExportWindow:
    """Câble les dépendances entre elles (composition root)."""
    config_path = config_file_path()
    config = load_config(config_path)
    locator = AuditFileLocator(config.root_path)
    export_service = ExportService(locator)
    return LotExportWindow(config, export_service, config_path)


def main() -> None:
    app = QApplication(sys.argv)
    window = build_window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
