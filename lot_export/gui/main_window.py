"""
Interface graphique (PySide6) — couche de présentation uniquement.
Toute la logique métier est déléguée à ExportService / AuditFileLocator.

Le travail long (copie de fichiers) tourne dans un QThread dédié
(ExportWorker) qui communique avec l'UI uniquement via des signaux Qt.
C'est le mécanisme thread-safe natif de Qt : contrairement à la version
Tkinter, il n'y a besoin ni de file d'attente manuelle, ni de polling —
Qt garantit que les slots connectés s'exécutent dans le thread de l'UI.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QRadioButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)
from PySide6.QtGui import QPixmap

from ..config import AppConfig, save_config
from ..models import ExportSummary
from ..services.commune_parser import extract_commune_codes
from ..services.error_id_parser import extract_error_ids
from ..services.export_service import ExportService
from ..services.file_locator import AuditFileLocator
from ..services.lot_naming import build_lot_dir
from .theme import PALETTE, build_stylesheet
from ..utils.resources import resource_path

STATUS_ICONS = {"success": "✅", "not_found": "⚠️ ", "error": "❌"}


class ExportWorker(QThread):
    """Exécute l'export dans un thread séparé et notifie l'UI via des signaux Qt."""

    log = Signal(str)
    progress = Signal(int, int, str)
    finished_export = Signal(str, Path, object)  # lot_number, lot_dir, ExportSummary

    def __init__(
            self,
            export_service: ExportService,
            lot_number: str,
            communes: List[str],
            lot_dir: Path,
            parent: Optional[QWidget] = None,
            error_ids: Optional[Dict[str, List[str]]] = None,
    ):
        super().__init__(parent)
        self.export_service = export_service
        self.lot_number = lot_number
        self.communes = communes
        self.lot_dir = lot_dir
        # Si renseigné : {code INSEE: [ID erreur]} -> export filtré sur ces lignes uniquement
        self.error_ids = error_ids

    def run(self) -> None:  # noqa: D102 - override Qt
        on_progress = lambda done, total, label: self.progress.emit(done, total, label)
        if self.error_ids is None:
            self.log.emit(f"🚀 LOT{self.lot_number} — Export de {len(self.communes)} commune(s)...")
            self.log.emit("─" * 45)
            summary: ExportSummary = self.export_service.export(self.communes, self.lot_dir, on_progress)
        else:
            nb_ids = sum(len(ids) for ids in self.error_ids.values())
            self.log.emit(f"🚀 LOT{self.lot_number} — Export de {nb_ids} ID erreur "
                          f"sur {len(self.error_ids)} commune(s)...")
            self.log.emit("─" * 45)
            summary = self.export_service.export_by_error_ids(self.error_ids, self.lot_dir, on_progress)

        for item in summary.items:
            icon = STATUS_ICONS[item.status.value]
            self.log.emit(f"  {icon} {item.commune} — {item.message}")

        self.log.emit("─" * 45)
        if summary.has_success:
            self.log.emit(f"🎉 {summary.success_count}/{summary.total} fichier(s) copié(s)")
            self.log.emit(f"📂 {self.lot_dir}")
        else:
            self.log.emit("❌ Aucun fichier copié")

        self.finished_export.emit(self.lot_number, self.lot_dir, summary)


class LotExportWindow(QWidget):
    """Fenêtre principale de l'application d'export par LOT."""

    def __init__(
            self,
            config: AppConfig,
            export_service: ExportService,
            config_path: Optional[Path] = None,
    ):
        super().__init__()
        self.config = config
        self.config_path = config_path
        self.export_service = export_service
        self._worker: Optional[ExportWorker] = None

        self.setWindowTitle("Export LOT — Projet SNA")
        self.resize(760, 820)
        self.setStyleSheet(build_stylesheet(PALETTE))

        self._build_ui()
        self._update_preview()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(4)
        root_layout.addWidget(body, stretch=1)

        intro = QLabel(
            "Copie les fichiers audit depuis le dossier source dans un nouveau\n"
            "dossier LOT créé dans le dossier de destination."
        )
        intro.setProperty("role", "muted")
        body_layout.addWidget(intro)
        body_layout.addSpacing(8)

        body_layout.addWidget(self._build_folders())
        body_layout.addSpacing(8)

        body_layout.addWidget(self._build_lot_input())
        body_layout.addSpacing(8)
        body_layout.addWidget(self._build_commune_input())
        body_layout.addSpacing(8)
        body_layout.addWidget(self._build_action_button())
        body_layout.addSpacing(6)
        body_layout.addWidget(self._build_progress())
        body_layout.addSpacing(6)
        body_layout.addWidget(self._build_log(), stretch=1)

    def _build_header(self) -> QWidget:
        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(56)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        # Logo
        logo = QLabel()
        pix = QPixmap(resource_path("resources/logo.png"))

        logo.setPixmap(
            pix.scaledToHeight(
                60,
                Qt.SmoothTransformation
            )
        )

        layout.addWidget(logo)
        title = QLabel("Export des fichiers Excel par LOT")
        title.setObjectName("HeaderTitle")
        layout.addWidget(title)
        layout.addStretch()
        return header

    def _build_folders(self) -> QWidget:
        container = QFrame()
        container.setObjectName("FoldersPanel")
        layout = QGridLayout(container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)
        layout.setColumnStretch(1, 1)

        self.entry_root, self.button_root = self._add_folder_row(
            layout, 0, "Dossier source :", self.config.root_path_be,
            "Dossier racine contenant les sous-dossiers DepXX/COMMUNE/audit_*.xlsx",
            self._on_choose_root,
        )
        self.entry_downloads, self.button_downloads = self._add_folder_row(
            layout, 1, "Destination :", self.config.downloads_dir,
            "Dossier dans lequel le dossier LOTxx sera créé",
            self._on_choose_downloads,
        )
        return container

    @staticmethod
    def _add_folder_row(layout: QGridLayout, row: int, label_text: str, value: str,
                        tooltip: str, on_browse) -> tuple[QLineEdit, QPushButton]:
        label = QLabel(label_text)
        label.setProperty("role", "muted")
        layout.addWidget(label, row, 0)

        entry = QLineEdit(value)
        entry.setReadOnly(True)
        entry.setToolTip(tooltip)
        entry.setCursorPosition(0)
        layout.addWidget(entry, row, 1)

        button = QPushButton("Parcourir…")
        button.setObjectName("BrowseButton")
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(on_browse)
        layout.addWidget(button, row, 2)
        return entry, button

    def _build_lot_input(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label = QLabel("Numéro de LOT :")
        label.setProperty("role", "muted")
        layout.addWidget(label)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        prefix = QLabel("LOT")
        prefix.setObjectName("LotPrefix")
        row_layout.addWidget(prefix)

        self.entry_lot = QLineEdit()
        self.entry_lot.setObjectName("LotEntry")
        self.entry_lot.setFixedWidth(140)
        self.entry_lot.textChanged.connect(self._update_preview)
        row_layout.addWidget(self.entry_lot)
        row_layout.addStretch()
        layout.addWidget(row)

        self.label_preview = QLabel("")
        self.label_preview.setProperty("role", "dim")
        layout.addWidget(self.label_preview)

        return container

    def _build_commune_input(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_label = QLabel("Exporter par :")
        mode_label.setProperty("role", "muted")
        mode_layout.addWidget(mode_label)
        self.radio_communes = QRadioButton("Codes commune (fichiers complets)")
        self.radio_error_ids = QRadioButton("ID erreur (lignes filtrées)")
        self.radio_communes.setChecked(True)
        self.mode_group = QButtonGroup(self)
        for radio in (self.radio_communes, self.radio_error_ids):
            self.mode_group.addButton(radio)
            mode_layout.addWidget(radio)
        mode_layout.addStretch()
        self.mode_group.buttonToggled.connect(self._on_mode_changed)
        layout.addWidget(mode_row)

        self.label_input = QLabel()
        self.label_input.setProperty("role", "muted")
        layout.addWidget(self.label_input)

        self.textbox_communes = QTextEdit()
        self.textbox_communes.setFixedHeight(140)
        self.textbox_communes.textChanged.connect(self._update_input_count)
        layout.addWidget(self.textbox_communes)

        self.label_input_count = QLabel()
        self.label_input_count.setProperty("role", "dim")
        layout.addWidget(self.label_input_count)

        self._on_mode_changed()

        return container

    def _build_action_button(self) -> QWidget:
        self.button_run = QPushButton("📦  Créer le LOT & Exporter")
        self.button_run.setObjectName("RunButton")
        self.button_run.setFixedHeight(44)
        self.button_run.setCursor(Qt.PointingHandCursor)
        self.button_run.clicked.connect(self._on_run_clicked)
        return self.button_run

    def _build_progress(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.label_progress = QLabel("")
        self.label_progress.setProperty("role", "muted")
        layout.addWidget(self.label_progress)

        return container

    def _build_log(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        label = QLabel("Journal :")
        label.setProperty("role", "muted")
        layout.addWidget(label)

        self.textbox_log = QTextEdit()
        self.textbox_log.setObjectName("LogConsole")
        self.textbox_log.setReadOnly(True)
        self.textbox_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.textbox_log)

        return container

    # ------------------------------------------------------------- helpers

    def _lot_dir(self) -> Optional[Path]:
        return build_lot_dir(self.config.downloads_path, self.entry_lot.text())

    def _update_preview(self) -> None:
        lot_dir = self._lot_dir()
        if lot_dir is None:
            self.label_preview.setProperty("role", "dim")
            self.label_preview.setText("Saisissez un numéro (ex: 13 → LOT13)")
        else:
            exists = lot_dir.is_dir()
            self.label_preview.setProperty("role", "preview-warning" if exists else "dim")
            suffix = " (⚠️ existe déjà)" if exists else ""
            self.label_preview.setText(f"📂 Sera créé : {lot_dir}{suffix}")
        self._refresh_style(self.label_preview)

    def _ask_directory(self, title: str, current: Path) -> Optional[Path]:
        start = str(current) if current.is_dir() else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, title, start)
        return Path(chosen) if chosen else None

    def _apply_config(self, new_config: AppConfig) -> None:
        """Applique et persiste une nouvelle configuration."""
        self.config = new_config
        self.export_service.locator = AuditFileLocator(new_config.root_path)
        self.entry_root.setText(new_config.root_path_be)
        self.entry_root.setCursorPosition(0)
        self.entry_downloads.setText(new_config.downloads_dir)
        self.entry_downloads.setCursorPosition(0)
        self._update_preview()
        try:
            save_config(new_config, self.config_path)
        except OSError as exc:
            QMessageBox.warning(
                self, "Configuration",
                f"Le dossier a été appliqué mais la configuration n'a pas pu être sauvegardée :\n{exc}",
            )

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.button_run, self.button_root, self.button_downloads,
                       self.radio_communes, self.radio_error_ids):
            widget.setEnabled(not busy)

    def _by_error_ids(self) -> bool:
        return self.radio_error_ids.isChecked()

    def _update_input_count(self) -> None:
        text = self.textbox_communes.toPlainText()
        if self._by_error_ids():
            grouped = extract_error_ids(text)
            nb_ids = sum(len(ids) for ids in grouped.values())
            self.label_input_count.setText(f"{nb_ids} ID erreur détecté(s) sur {len(grouped)} commune(s)")
        else:
            self.label_input_count.setText(f"{len(extract_commune_codes(text))} code(s) commune détecté(s)")

    @staticmethod
    def _refresh_style(widget: QWidget) -> None:
        """Force Qt à réappliquer le QSS après un changement dynamique de propriété."""
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _append_log(self, message: str) -> None:
        self.textbox_log.append(message)

    def _set_progress(self, done: int, total: int, label: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)
        self.label_progress.setText(f"{done}/{total} — {label}")

    # -------------------------------------------------------------- events

    def _on_mode_changed(self, *_args) -> None:
        if self._by_error_ids():
            self.label_input.setText("Collez vos ID erreur (ex : 74143_1, 74143_2) :")
            self.textbox_communes.setPlaceholderText("74143_1\n74143_2\n38068_207")
        else:
            self.label_input.setText("Collez vos codes commune :")
            self.textbox_communes.setPlaceholderText("74143\n38068")
        self._update_input_count()

    def _on_choose_root(self) -> None:
        path = self._ask_directory("Choisir le dossier source des fichiers audit", self.config.root_path)
        if path is not None:
            self._apply_config(self.config.with_root_path(path))

    def _on_choose_downloads(self) -> None:
        path = self._ask_directory("Choisir le dossier de destination", self.config.downloads_path)
        if path is not None:
            self._apply_config(self.config.with_downloads_dir(path))

    def _on_run_clicked(self) -> None:
        text = self.textbox_communes.toPlainText()
        error_ids: Optional[Dict[str, List[str]]] = None
        if self._by_error_ids():
            error_ids = extract_error_ids(text)
            codes = list(error_ids)
        else:
            codes = extract_commune_codes(text)
        lot_number = self.entry_lot.text().strip()
        lot_dir = self._lot_dir()

        if not lot_number:
            QMessageBox.warning(self, "Numéro de LOT", "Saisissez un numéro de LOT (ex: 13).")
            return
        if not codes:
            message = ("Aucun ID erreur valide détecté (format attendu : 74143_1)."
                       if error_ids is not None else "Aucun code commune valide détecté.")
            QMessageBox.warning(self, "Erreur", message)
            return
        if not self.config.root_path.is_dir():
            QMessageBox.warning(
                self, "Dossier source",
                f"Le dossier source est introuvable :\n{self.config.root_path}\n\n"
                "Choisissez-le avec le bouton « Parcourir… ».",
            )
            return
        if not self._confirm_run(lot_number, lot_dir, codes):
            return

        self.textbox_log.clear()
        self._set_busy(True)

        self._worker = ExportWorker(self.export_service, lot_number, codes, lot_dir, self, error_ids)
        self._worker.log.connect(self._append_log)
        self._worker.progress.connect(self._set_progress)
        self._worker.finished_export.connect(self._on_export_finished)
        self._worker.start()

    def _confirm_run(self, lot_number: str, lot_dir: Path, codes: List[str]) -> bool:
        if lot_dir.is_dir():
            answer = QMessageBox.question(
                self, "Dossier existant",
                f"Le dossier LOT{lot_number} existe déjà :\n{lot_dir}\n\n"
                "Les fichiers seront ajoutés/écrasés dedans. Continuer ?",
            )
        else:
            answer = QMessageBox.question(
                self, "Confirmation",
                f"Créer le dossier LOT{lot_number} et exporter {len(codes)} commune(s) ?\n\n📂 {lot_dir}",
            )
        return answer == QMessageBox.Yes

    def _on_export_finished(self, lot_number: str, lot_dir: Path, summary: ExportSummary) -> None:
        self._set_busy(False)
        if not summary.has_success:
            QMessageBox.warning(self, "Terminé", "Aucun fichier copié. Voir le journal.")
            return
        try:
            os.startfile(lot_dir)  # Windows uniquement
        except (AttributeError, OSError):
            pass
        QMessageBox.information(
            self, "Terminé",
            f"✅ LOT{lot_number} créé avec {summary.success_count} fichier(s) !\n\n📂 {lot_dir}",
        )
