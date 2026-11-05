"""
Interface graphique (Tkinter) — couche de présentation uniquement.
Toute la logique métier est déléguée à ExportService / AuditFileLocator.

Le travail long (copie de fichiers) tourne dans un thread dédié
(ExportWorker) qui ne touche jamais aux widgets : Tkinter n'est pas
thread-safe. Le worker dépose ses événements (log, progression, fin) dans
une file (queue.Queue) que la fenêtre dépile périodiquement via `after()`,
dans le thread de l'UI.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from PIL import Image, ImageTk

from ..config import AppConfig, config_file_path, save_config
from ..models import ExportSummary
from ..services.address_parser import extract_addresses, find_invalid_addresses
from ..services.commune_parser import extract_commune_codes
from ..services.error_id_parser import extract_error_ids, find_duplicate_error_ids, find_invalid_error_ids
from ..services.export_report import write_not_exported_report
from ..services.export_service import ExportService
from ..services.file_locator import AuditFileLocator
from ..services.lot_naming import build_lot_dir
from ..services.pending_ids import (
    PENDING_FILE_NAME,
    clear_pending,
    load_pending,
    update_pending,
    update_pending_from_summary,
)
from .theme import FONTS, LABEL_ROLES, PALETTE, apply_theme
from ..utils.resources import resource_path

STATUS_ICONS = {"success": "✅", "not_found": "⚠️ ", "error": "❌"}
POLL_INTERVAL_MS = 50
PENDING_DETAIL_LIMIT = 15  # nombre d'ID détaillés dans la boîte de dialogue de chargement
WINDOW_HEIGHT = 880
SCREEN_MARGIN = 80  # place laissée à la barre de titre et à la barre des tâches


@dataclass(frozen=True)
class FilterMode:
    """Mode d'export filtré : quelles valeurs saisir, comment les lire et quel export lancer."""
    radio_label: str
    unit: str
    prompt: str
    placeholder: str
    invalid_message: str
    parse: Callable[[str], Dict[str, List[str]]]
    find_invalid: Callable[[str], List[str]]
    find_duplicates: Callable[[str], Dict[str, int]]
    export: Callable[[ExportService], Callable[..., ExportSummary]]


# Modes filtrés (le mode "communes" copie les fichiers complets).
FILTER_MODES: Dict[str, FilterMode] = {
    "error_ids": FilterMode(
        radio_label="ID erreur (lignes filtrées)",
        unit="ID erreur",
        prompt="Collez vos ID erreur (ex : 74143_1, 74143_2) :",
        placeholder="74143_1\n74143_2\n38068_207",
        invalid_message="Aucun ID erreur valide détecté (format attendu : 74143_1).",
        parse=extract_error_ids,
        find_invalid=find_invalid_error_ids,
        find_duplicates=find_duplicate_error_ids,
        export=lambda service: service.export_by_error_ids,
    ),
    "addresses": FilterMode(
        radio_label="Adresse (lignes filtrées)",
        unit="adresse(s)",
        prompt="Collez vos adresses, une par ligne (format : <code INSEE>_<adresse>) :",
        placeholder="05094_495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT\n"
                    "74143_12 RUE DES ALPES 74000 ANNECY",
        invalid_message="Aucune adresse valide détectée "
                        "(format attendu : 05094_495 CHEMIN DE PIGE BOUIN 05700 NOSSAGE ET BENEVENT).",
        parse=extract_addresses,
        find_invalid=find_invalid_addresses,
        find_duplicates=lambda _text: {},
        export=lambda service: service.export_by_addresses,
    ),
}


class ExportWorker(threading.Thread):
    """Exécute l'export dans un thread séparé et notifie l'UI via une file d'événements."""

    def __init__(
            self,
            export_service: ExportService,
            lot_number: str,
            communes: List[str],
            lot_dir: Path,
            events: "queue.Queue[tuple]",
            filter_mode: Optional[FilterMode] = None,
            filter_values: Optional[Dict[str, List[str]]] = None,
            single_file_name: Optional[str] = None,
            invalid_values: Optional[List[str]] = None,
            pending_file: Optional[Path] = None,
            duplicates: Optional[Dict[str, int]] = None,
    ):
        super().__init__(daemon=True)
        self.export_service = export_service
        self.lot_number = lot_number
        self.communes = communes
        self.lot_dir = lot_dir
        self.events = events
        # Si renseigné : {code INSEE: [valeurs]} -> export filtré sur ces lignes uniquement
        self.filter_mode = filter_mode
        self.filter_values = filter_values
        # Si renseigné : toutes les communes sont regroupées dans ce fichier Excel unique
        self.single_file_name = single_file_name
        # Saisies non reconnues, jamais recherchées mais signalées dans le rapport
        self.invalid_values = invalid_values or []
        self.duplicates = duplicates or {}
        self.report_path: Optional[Path] = None
        # Si renseigné (export par ID erreur) : liste des ID en attente à tenir à jour
        self.pending_file = pending_file

    def _log(self, message: str) -> None:
        self.events.put(("log", message))

    def run(self) -> None:  # noqa: D102 - override Thread
        try:
            summary = self._export()
        except Exception as exc:  # noqa: BLE001 - l'UI doit toujours être débloquée
            self._log(f"❌ Erreur inattendue : {exc}")
            summary = ExportSummary()
            self._keep_all_pending(f"erreur inattendue ({exc})")
        self.events.put(("finished", self.lot_number, self.lot_dir, summary))

    def _export(self) -> ExportSummary:
        on_progress = lambda done, total, label: self.events.put(("progress", done, total, label))
        if self.filter_mode is None:
            self._log(f"🚀 LOT{self.lot_number} — Export de {len(self.communes)} commune(s)...")
            self._log("─" * 45)
            summary: ExportSummary = self.export_service.export(
                self.communes, self.lot_dir, on_progress, self.single_file_name)
        else:
            nb_values = sum(len(values) for values in self.filter_values.values())
            self._log(f"🚀 LOT{self.lot_number} — Export de {nb_values} {self.filter_mode.unit} "
                      f"sur {len(self.filter_values)} commune(s)...")
            self._log("─" * 45)
            export = self.filter_mode.export(self.export_service)
            summary = export(self.filter_values, self.lot_dir, on_progress, self.single_file_name)

        for item in summary.items:
            icon = STATUS_ICONS[item.status.value]
            self._log(f"  {icon} {item.commune} — {item.message}")

        self._log("─" * 45)
        if summary.merged_file is not None:
            self._log(f"🎉 {summary.success_count}/{summary.total} commune(s) regroupée(s) dans "
                      f"{summary.merged_file.name} ({summary.merged_rows} ligne(s) Audit)")
            self._log(f"📂 {self.lot_dir}")
        elif summary.has_success:
            self._log(f"🎉 {summary.success_count}/{summary.total} fichier(s) copié(s)")
            self._log(f"📂 {self.lot_dir}")
        else:
            self._log("❌ Aucun fichier copié")
        if self.filter_mode is not None:
            self._report_not_exported(summary)
        self._update_pending(summary)
        return summary

    def _update_pending(self, summary: ExportSummary) -> None:
        if self.pending_file is None:
            return
        try:
            pending = update_pending_from_summary(self.pending_file, summary)
        except OSError as exc:
            self._log(f"❌ Liste des ID en attente impossible à mettre à jour : {exc}")
            return
        if pending:
            self._log(f"⏳ {len(pending)} ID en attente au total, à rejouer avec « Charger les ID en attente »")

    def _keep_all_pending(self, reason: str) -> None:
        """L'export s'est interrompu sans bilan : tous les ID demandés restent à rejouer."""
        if self.pending_file is None:
            return
        failures = {error_id: reason for values in self.filter_values.values() for error_id in values}
        try:
            update_pending(self.pending_file, failures, [])
        except OSError as exc:
            self._log(f"❌ Liste des ID en attente impossible à mettre à jour : {exc}")

    def _report_not_exported(self, summary: ExportSummary) -> None:
        unit = self.filter_mode.unit
        requested = summary.exported_count + summary.not_exported_count
        self._log(f"📊 {unit} : {summary.exported_count}/{requested} exporté(s) et vérifié(s) dans le fichier final "
                  f"({summary.exported_rows} ligne(s) Audit)")
        for cause, count in summary.not_exported_by_cause():
            self._log(f"   ⚠️ {count} : {cause.value}")
        if summary.realigned_formulas:
            self._log(f"   ℹ️ {summary.realigned_formulas} formule(s) décalée(s) de la source recalée(s) sur leur ligne")
        if self.duplicates:
            self._log(f"   ℹ️ {sum(n - 1 for n in self.duplicates.values())} doublon(s) dans la saisie, exporté(s) une fois")
        if self.invalid_values:
            self._log(f"   ⚠️ {len(self.invalid_values)} saisie(s) non reconnue(s), jamais recherchée(s)")
        try:
            self.report_path = write_not_exported_report(
                summary, self.invalid_values, self.duplicates, self.lot_dir, self.lot_number, unit,
                self.export_service.locator.root_path)
        except OSError as exc:
            self._log(f"❌ Rapport de contrôle impossible à écrire : {exc}")
            return
        if self.report_path is not None:
            self._log(f"📝 Détail et explications : {self.report_path}")


class Tooltip:
    """Info-bulle minimale affichée au survol d'un widget."""

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self._tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self._tip is not None:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self.text, bg=PALETTE.surface, fg=PALETTE.text, font=FONTS.dim,
                 padx=6, pady=3, highlightthickness=1, highlightbackground=PALETTE.border).pack()

    def _hide(self, _event=None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class LotExportWindow(tk.Tk):
    """Fenêtre principale de l'application d'export par LOT."""

    def __init__(
            self,
            config: AppConfig,
            export_service: ExportService,
            config_path: Optional[Path] = None,
    ):
        super().__init__()
        self.app_config = config
        self.config_path = config_path
        self.export_service = export_service
        self._worker: Optional[ExportWorker] = None
        self._events: "queue.Queue[tuple]" = queue.Queue()
        # Dans le dossier de configuration : la liste survit aux redémarrages, même avec l'exécutable
        self.pending_file = (config_path or config_file_path()).with_name(PENDING_FILE_NAME)

        self.title("Export LOT — Projet SNA")
        self.geometry(f"760x{min(WINDOW_HEIGHT, self.winfo_screenheight() - SCREEN_MARGIN)}")
        self.minsize(640, 700)
        apply_theme(self)

        self._build_ui()
        self._update_preview()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        self._build_header().pack(fill="x")

        body = tk.Frame(self, bg=PALETTE.bg, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        self._label(
            body,
            "Copie les fichiers audit depuis le dossier source dans un nouveau\n"
            "dossier LOT créé dans le dossier de destination.",
            "muted", justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self._build_folders(body).pack(fill="x", pady=(0, 12))
        self._build_lot_input(body).pack(fill="x", pady=(0, 12))
        self._build_commune_input(body).pack(fill="x", pady=(0, 6))
        self._build_pending_row(body).pack(fill="x", pady=(0, 12))
        self._build_action_button(body).pack(fill="x", pady=(0, 10))
        self._build_progress(body).pack(fill="x", pady=(0, 10))
        self._build_log(body).pack(fill="both", expand=True)

    def _build_header(self) -> tk.Widget:
        header = tk.Frame(self, bg=PALETTE.surface, height=56, padx=16)
        header.pack_propagate(False)

        # Logo (Pillow pour un redimensionnement lissé)
        image = Image.open(resource_path("resources/logo.png"))
        height = 44
        width = round(image.width * height / image.height)
        self._logo = ImageTk.PhotoImage(image.resize((width, height), Image.LANCZOS))
        tk.Label(header, image=self._logo, bg=PALETTE.surface).pack(side="left", padx=(0, 10))

        tk.Label(header, text="Export des fichiers Excel par LOT", bg=PALETTE.surface,
                 fg=PALETTE.text, font=FONTS.title).pack(side="left")
        return header

    def _build_folders(self, parent: tk.Widget) -> tk.Widget:
        container = tk.Frame(parent, bg=PALETTE.surface, padx=12, pady=10,
                             highlightthickness=1, highlightbackground=PALETTE.border)
        container.columnconfigure(1, weight=1)

        self.var_root, self.button_root = self._add_folder_row(
            container, 0, "Dossier source :", self.app_config.root_path_be,
            "Dossier racine contenant les sous-dossiers DepXX/COMMUNE/audit_*.xlsx",
            self._on_choose_root,
        )
        self.var_downloads, self.button_downloads = self._add_folder_row(
            container, 1, "Destination :", self.app_config.downloads_dir,
            "Dossier dans lequel le dossier LOTxx sera créé",
            self._on_choose_downloads,
        )
        return container

    def _add_folder_row(self, container: tk.Frame, row: int, label_text: str, value: str,
                        tooltip: str, on_browse: Callable[[], None]) -> tuple[tk.StringVar, tk.Button]:
        pady = (0, 6) if row == 0 else 0
        self._label(container, label_text, "muted", bg=PALETTE.surface).grid(
            row=row, column=0, sticky="w", padx=(0, 8), pady=pady)

        var = tk.StringVar(value=value)
        entry = self._entry(container, textvariable=var, state="readonly", font=FONTS.muted)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=pady, ipady=4)
        Tooltip(entry, tooltip)

        button = self._button(
            container, "Parcourir…", on_browse,
            bg=PALETTE.input_bg, hover_bg=PALETTE.border, pressed_bg=PALETTE.accent_pressed,
            font=FONTS.muted, padx=12, pady=3,
        )
        button.grid(row=row, column=2, pady=pady)
        return var, button

    def _build_lot_input(self, parent: tk.Widget) -> tk.Widget:
        container = tk.Frame(parent, bg=PALETTE.bg)
        self._label(container, "Numéro de LOT :", "muted").pack(anchor="w", pady=(0, 4))

        row = tk.Frame(container, bg=PALETTE.bg)
        row.pack(anchor="w")
        tk.Label(row, text="LOT", bg=PALETTE.bg, fg=PALETTE.info, font=FONTS.large).pack(side="left", padx=(0, 6))

        self.var_lot = tk.StringVar()
        self.var_lot.trace_add("write", lambda *_: self._update_preview())
        self.entry_lot = self._entry(row, textvariable=self.var_lot, font=FONTS.large, width=10)
        self.entry_lot.pack(side="left", ipady=3)

        self.label_preview = self._label(container, "", "dim")
        self.label_preview.pack(anchor="w", pady=(4, 0))
        return container

    def _build_commune_input(self, parent: tk.Widget) -> tk.Widget:
        container = tk.Frame(parent, bg=PALETTE.bg)

        self._label(container, "Exporter par :", "muted").pack(anchor="w")
        mode_row = tk.Frame(container, bg=PALETTE.bg)
        mode_row.pack(anchor="w", pady=(0, 8))
        self.var_mode = tk.StringVar(value="communes")
        self.mode_radios = [self._radio(mode_row, "Codes commune (fichiers complets)", "communes")]
        self.mode_radios += [self._radio(mode_row, mode.radio_label, key) for key, mode in FILTER_MODES.items()]
        for radio in self.mode_radios:
            radio.pack(side="left", padx=(0, 10))

        self._label(container, "Fichier(s) Excel :", "muted").pack(anchor="w")
        output_row = tk.Frame(container, bg=PALETTE.bg)
        output_row.pack(anchor="w", pady=(0, 8))
        self.var_output = tk.StringVar(value="per_insee")
        self.output_radios = [
            self._radio(output_row, "Un fichier par code INSEE", "per_insee", self.var_output),
            self._radio(output_row, "Un seul fichier pour tout le LOT", "single", self.var_output),
        ]
        for radio in self.output_radios:
            radio.pack(side="left", padx=(0, 10))

        self.label_input = self._label(container, "", "muted")
        self.label_input.pack(anchor="w", pady=(0, 4))

        text_frame = tk.Frame(container, bg=PALETTE.input_bg, highlightthickness=1,
                              highlightbackground=PALETTE.border, highlightcolor=PALETTE.accent)
        text_frame.pack(fill="x")
        self.textbox_communes = tk.Text(
            text_frame, height=5, bg=PALETTE.input_bg, fg=PALETTE.text, insertbackground=PALETTE.text,
            selectbackground=PALETTE.accent, relief="flat", borderwidth=0, padx=8, pady=6, undo=True,
        )
        self.textbox_communes.pack(fill="both", expand=True)
        self.textbox_communes.bind("<<Modified>>", self._on_communes_modified)
        self.textbox_communes.bind("<FocusIn>", lambda _e: text_frame.config(highlightbackground=PALETTE.accent))
        self.textbox_communes.bind("<FocusOut>", lambda _e: text_frame.config(highlightbackground=PALETTE.border))

        # Tk n'a pas de placeholder natif : label superposé, masqué dès que du texte est saisi.
        self.label_placeholder = tk.Label(text_frame, bg=PALETTE.input_bg, fg=PALETTE.text_dim,
                                          justify="left", cursor="xterm")
        self.label_placeholder.bind("<Button-1>", lambda _e: self.textbox_communes.focus_set())

        self.label_input_count = self._label(container, "", "dim")
        self.label_input_count.pack(anchor="w", pady=(4, 0))

        self._on_mode_changed()
        return container

    def _build_pending_row(self, parent: tk.Widget) -> tk.Widget:
        container = tk.Frame(parent, bg=PALETTE.bg)
        self.label_pending = self._label(container, "", "dim")
        self.label_pending.pack(side="left")
        style = dict(bg=PALETTE.input_bg, hover_bg=PALETTE.border, pressed_bg=PALETTE.accent_pressed,
                     font=FONTS.dim, padx=10, pady=2)
        self.button_pending_clear = self._button(container, "🗑 Vider la liste", self._on_clear_pending, **style)
        self.button_pending_clear.pack(side="right", padx=(6, 0))
        self.button_pending_load = self._button(
            container, "📋 Charger les ID en attente", self._on_load_pending, **style)
        self.button_pending_load.pack(side="right")
        self._update_pending_ui()
        return container

    def _build_action_button(self, parent: tk.Widget) -> tk.Widget:
        self.button_run = self._button(
            parent, "📦  Créer le LOT & Exporter", self._on_run_clicked,
            bg=PALETTE.accent, hover_bg=PALETTE.accent_hover, pressed_bg=PALETTE.accent_pressed,
            fg="white", font=FONTS.button, pady=8,
        )
        return self.button_run

    def _build_progress(self, parent: tk.Widget) -> tk.Widget:
        container = tk.Frame(parent, bg=PALETTE.bg)
        self.progress_bar = ttk.Progressbar(container, style="Accent.Horizontal.TProgressbar",
                                            orient="horizontal", mode="determinate", maximum=1, value=0)
        self.progress_bar.pack(fill="x")
        self.label_progress = self._label(container, "", "muted")
        self.label_progress.pack(anchor="w", pady=(4, 0))
        return container

    def _build_log(self, parent: tk.Widget) -> tk.Widget:
        container = tk.Frame(parent, bg=PALETTE.bg)
        self._label(container, "Journal :", "muted").pack(anchor="w", pady=(0, 2))

        frame = tk.Frame(container, bg=PALETTE.console_bg, highlightthickness=1,
                         highlightbackground=PALETTE.border)
        frame.pack(fill="both", expand=True)
        self.textbox_log = tk.Text(
            frame, bg=PALETTE.console_bg, fg=PALETTE.success, font=FONTS.mono,
            selectbackground=PALETTE.accent, relief="flat", borderwidth=0, padx=8, pady=6,
            state="disabled", wrap="word",
        )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.textbox_log.yview)
        self.textbox_log.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.textbox_log.pack(side="left", fill="both", expand=True)
        return container

    # ----------------------------------------------------- widget factories

    @staticmethod
    def _label(parent: tk.Widget, text: str, role: str, bg: str = PALETTE.bg, **kwargs) -> tk.Label:
        fg, font = LABEL_ROLES[role]
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, **kwargs)

    @staticmethod
    def _entry(parent: tk.Widget, **kwargs) -> tk.Entry:
        return tk.Entry(
            parent, bg=PALETTE.input_bg, readonlybackground=PALETTE.input_bg, fg=PALETTE.text,
            insertbackground=PALETTE.text, selectbackground=PALETTE.accent, relief="flat",
            highlightthickness=1, highlightbackground=PALETTE.border, highlightcolor=PALETTE.accent,
            **kwargs,
        )

    def _radio(self, parent: tk.Widget, text: str, value: str,
               variable: Optional[tk.StringVar] = None) -> tk.Radiobutton:
        # sans variable explicite : choix du mode d'export (rafraîchit la zone de saisie)
        return tk.Radiobutton(
            parent, text=text, value=value, variable=variable or self.var_mode,
            command=None if variable else self._on_mode_changed,
            bg=PALETTE.bg, fg=PALETTE.text, selectcolor=PALETTE.input_bg,
            activebackground=PALETTE.bg, activeforeground=PALETTE.text,
            disabledforeground=PALETTE.text_dim, highlightthickness=0, cursor="hand2",
        )

    @staticmethod
    def _button(parent: tk.Widget, text: str, command: Callable[[], None], *, bg: str, hover_bg: str,
                pressed_bg: str, fg: str = PALETTE.text, **kwargs) -> tk.Button:
        button = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=pressed_bg, activeforeground=fg, disabledforeground=PALETTE.text_dim,
            relief="flat", borderwidth=0, highlightthickness=0, cursor="hand2", **kwargs,
        )
        button.normal_bg = bg  # couleur de repos, restaurée après survol / réactivation
        button.bind("<Enter>", lambda _e: button["state"] == "normal" and button.config(bg=hover_bg))
        button.bind("<Leave>", lambda _e: button["state"] == "normal" and button.config(bg=bg))
        return button

    # ------------------------------------------------------------- helpers

    def _lot_dir(self) -> Optional[Path]:
        return build_lot_dir(self.app_config.downloads_path, self.var_lot.get())

    def _update_preview(self) -> None:
        lot_dir = self._lot_dir()
        if lot_dir is None:
            role, text = "dim", "Saisissez un numéro (ex: 13 → LOT13)"
        else:
            exists = lot_dir.is_dir()
            role = "preview-warning" if exists else "dim"
            suffix = " (⚠️ existe déjà)" if exists else ""
            text = f"📂 Sera créé : {lot_dir}{suffix}"
        fg, font = LABEL_ROLES[role]
        self.label_preview.config(text=text, fg=fg, font=font)

    def _ask_directory(self, title: str, current: Path) -> Optional[Path]:
        start = str(current) if current.is_dir() else str(Path.home())
        chosen = filedialog.askdirectory(parent=self, title=title, initialdir=start, mustexist=True)
        return Path(chosen) if chosen else None

    def _apply_config(self, new_config: AppConfig) -> None:
        """Applique et persiste une nouvelle configuration."""
        self.app_config = new_config
        self.export_service.locator = AuditFileLocator(new_config.root_path)
        self.var_root.set(new_config.root_path_be)
        self.var_downloads.set(new_config.downloads_dir)
        self._update_preview()
        try:
            save_config(new_config, self.config_path)
        except OSError as exc:
            messagebox.showwarning(
                "Configuration",
                f"Le dossier a été appliqué mais la configuration n'a pas pu être sauvegardée :\n{exc}",
                parent=self,
            )

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (self.button_run, self.button_root, self.button_downloads,
                       self.button_pending_load, self.button_pending_clear,
                       *self.mode_radios, *self.output_radios):
            widget.config(state=state)
        for button in (self.button_run, self.button_root, self.button_downloads):
            button.config(bg=button.normal_bg)
        if busy:
            self.button_run.config(bg=PALETTE.accent_disabled)

    def _filter_mode(self) -> Optional[FilterMode]:
        """Mode filtré sélectionné, ou None pour l'export de fichiers complets par code commune."""
        return FILTER_MODES.get(self.var_mode.get())

    def _single_file_name(self, lot_dir: Path) -> Optional[str]:
        """Nom du fichier Excel unique (ex : audit_LOT13.xlsx), ou None pour un fichier par code INSEE."""
        return f"audit_{lot_dir.name}.xlsx" if self.var_output.get() == "single" else None

    def _communes_text(self) -> str:
        return self.textbox_communes.get("1.0", "end-1c")

    def _update_input_count(self) -> None:
        text = self._communes_text()
        if text:
            self.label_placeholder.place_forget()
        else:
            self.label_placeholder.place(x=9, y=7)
        mode = self._filter_mode()
        if mode is not None:
            grouped = mode.parse(text)
            nb_values = sum(len(values) for values in grouped.values())
            nb_invalid = len(mode.find_invalid(text))
            nb_duplicates = sum(count - 1 for count in mode.find_duplicates(text).values())
            invalid = f" — ⚠️ {nb_invalid} saisie(s) non reconnue(s)" if nb_invalid else ""
            duplicates = f" — {nb_duplicates} doublon(s) ignoré(s)" if nb_duplicates else ""
            self.label_input_count.config(
                text=f"{nb_values} {mode.unit} détecté(s) sur {len(grouped)} commune(s){duplicates}{invalid}")
        else:
            self.label_input_count.config(text=f"{len(extract_commune_codes(text))} code(s) commune détecté(s)")

    def _update_pending_ui(self) -> None:
        count = len(load_pending(self.pending_file))
        role, text = ("preview-warning", f"⏳ {count} ID en attente") \
            if count else ("dim", "✓ Aucun ID en attente")
        fg, font = LABEL_ROLES[role]
        self.label_pending.config(text=text, fg=fg, font=font)
        state = "normal" if count else "disabled"
        self.button_pending_load.config(state=state)
        self.button_pending_clear.config(state=state)

    def _append_log(self, message: str) -> None:
        self.textbox_log.config(state="normal")
        self.textbox_log.insert("end", message + "\n")
        self.textbox_log.see("end")
        self.textbox_log.config(state="disabled")

    def _clear_log(self) -> None:
        self.textbox_log.config(state="normal")
        self.textbox_log.delete("1.0", "end")
        self.textbox_log.config(state="disabled")

    def _set_progress(self, done: int, total: int, label: str) -> None:
        self.progress_bar.config(maximum=max(total, 1), value=done)
        self.label_progress.config(text=f"{done}/{total} — {label}")

    def _poll_events(self) -> None:
        """Dépile les événements du worker dans le thread de l'UI."""
        try:
            while True:
                kind, *args = self._events.get_nowait()
                if kind == "log":
                    self._append_log(*args)
                elif kind == "progress":
                    self._set_progress(*args)
                elif kind == "finished":
                    self._on_export_finished(*args)
                    return
        except queue.Empty:
            pass
        self.after(POLL_INTERVAL_MS, self._poll_events)

    # -------------------------------------------------------------- events

    def _on_communes_modified(self, _event=None) -> None:
        if self.textbox_communes.edit_modified():
            self.textbox_communes.edit_modified(False)
            self._update_input_count()

    def _on_mode_changed(self) -> None:
        mode = self._filter_mode()
        if mode is not None:
            self.label_input.config(text=mode.prompt)
            self.label_placeholder.config(text=mode.placeholder)
        else:
            self.label_input.config(text="Collez vos codes commune :")
            self.label_placeholder.config(text="74143\n38068")
        self._update_input_count()

    def _on_choose_root(self) -> None:
        path = self._ask_directory("Choisir le dossier source des fichiers audit", self.app_config.root_path)
        if path is not None:
            self._apply_config(self.app_config.with_root_path(path))

    def _on_choose_downloads(self) -> None:
        path = self._ask_directory("Choisir le dossier de destination", self.app_config.downloads_path)
        if path is not None:
            self._apply_config(self.app_config.with_downloads_dir(path))

    def _on_load_pending(self) -> None:
        pending = load_pending(self.pending_file)
        if not pending:
            self._update_pending_ui()
            return
        self.var_mode.set("error_ids")
        self._on_mode_changed()
        self.textbox_communes.delete("1.0", "end")
        self.textbox_communes.insert("1.0", "\n".join(pending))
        # Rejouer dans le même LOT remplacerait les fichiers déjà exportés pour ces communes
        self.var_lot.set("")
        self.entry_lot.focus_set()

        detail = "\n".join(f"• {error_id} : {info.get('reason', '')} ({info.get('date', '')})"
                           for error_id, info in list(pending.items())[:PENDING_DETAIL_LIMIT])
        more = f"\n… et {len(pending) - PENDING_DETAIL_LIMIT} autre(s)" if len(pending) > PENDING_DETAIL_LIMIT else ""
        messagebox.showinfo(
            "ID en attente",
            f"{len(pending)} ID chargé(s) dans la zone de saisie.\n\n{detail}{more}\n\n"
            "Saisissez un NOUVEAU numéro de LOT puis lancez l'export : ceux qui réussissent "
            "sont retirés de la liste.",
            parent=self,
        )

    def _on_clear_pending(self) -> None:
        if not messagebox.askyesno(
            "ID en attente",
            "Vider la liste des ID en attente ?\n(seule la liste est effacée, aucun fichier Excel n'est modifié)",
            parent=self,
        ):
            return
        try:
            clear_pending(self.pending_file)
        except OSError as exc:
            messagebox.showwarning("ID en attente", f"Impossible de vider la liste :\n{exc}", parent=self)
        self._update_pending_ui()

    def _on_run_clicked(self) -> None:
        text = self._communes_text()
        mode = self._filter_mode()
        filter_values: Optional[Dict[str, List[str]]] = None
        invalid_values: List[str] = []
        duplicates: Dict[str, int] = {}
        if mode is not None:
            filter_values = mode.parse(text)
            invalid_values = mode.find_invalid(text)
            duplicates = mode.find_duplicates(text)
            codes = list(filter_values)
        else:
            codes = extract_commune_codes(text)
        lot_number = self.var_lot.get().strip()
        lot_dir = self._lot_dir()

        if not lot_number:
            messagebox.showwarning("Numéro de LOT", "Saisissez un numéro de LOT (ex: 13).", parent=self)
            return
        if not codes:
            message = mode.invalid_message if mode is not None else "Aucun code commune valide détecté."
            messagebox.showwarning("Erreur", message, parent=self)
            return
        if not self.app_config.root_path.is_dir():
            messagebox.showwarning(
                "Dossier source",
                f"Le dossier source est introuvable :\n{self.app_config.root_path}\n\n"
                "Choisissez-le avec le bouton « Parcourir… ».",
                parent=self,
            )
            return
        single_file_name = self._single_file_name(lot_dir)
        if not self._confirm_run(lot_number, lot_dir, codes, single_file_name, filter_values):
            return

        self._clear_log()
        self._set_busy(True)

        self._worker = ExportWorker(self.export_service, lot_number, codes, lot_dir, self._events,
                                    mode, filter_values, single_file_name, invalid_values,
                                    self.pending_file if mode is FILTER_MODES["error_ids"] else None,
                                    duplicates)
        self._worker.start()
        self._poll_events()

    def _missing_files_warning(self, codes: List[str], filter_values: Optional[Dict[str, List[str]]]) -> str:
        """Annonce avant l'export les communes sans fichier : leurs valeurs ne pourront pas être exportées."""
        missing = [code for code in codes if self.export_service.locator.find(code) is None]
        if not missing:
            return ""
        lost = ""
        if filter_values is not None:
            nb_lost = sum(len(filter_values[code]) for code in missing)
            nb_total = sum(len(values) for values in filter_values.values())
            lost = f" : {nb_lost} valeur(s) sur {nb_total} ne seront PAS exportées"
        examples = ", ".join(missing[:8]) + (", …" if len(missing) > 8 else "")
        return (f"⚠️ {len(missing)} commune(s) sur {len(codes)} sans fichier audit dans le dossier source"
                f"{lost}.\nDossier source : {self.app_config.root_path}\nCommunes : {examples}\n\n")

    def _confirm_run(self, lot_number: str, lot_dir: Path, codes: List[str], single_file_name: Optional[str],
                     filter_values: Optional[Dict[str, List[str]]] = None) -> bool:
        warning = self._missing_files_warning(codes, filter_values)
        if lot_dir.is_dir():
            title = "Dossier existant"
            intro = f"Le dossier LOT{lot_number} existe déjà :\n{lot_dir}\n\n"
            if filter_values is not None:
                warning += ("⚠️ Un fichier déjà présent pour une même commune (ou le fichier unique du LOT) sera "
                            "REMPLACÉ et ne contiendra que la saisie actuelle : les lignes exportées auparavant "
                            "y seront perdues.\n\n")
                message = f"{intro}{warning}Continuer ?"
            else:
                message = f"{intro}{warning}Les fichiers seront ajoutés/écrasés dedans. Continuer ?"
        else:
            title = "Confirmation"
            target = f" dans un seul fichier ({single_file_name})" if single_file_name else ""
            message = (f"{warning}Créer le dossier LOT{lot_number} et exporter {len(codes)} commune(s)"
                       f"{target} ?\n\n📂 {lot_dir}")
        options = {"icon": "warning", "default": "no"} if warning else {}
        return messagebox.askyesno(title, message, parent=self, **options)

    @staticmethod
    def _export_control_note(summary: ExportSummary, report_path: Optional[Path]) -> str:
        """Bilan affiché en fin d'export : le journal peut être trop petit pour le voir."""
        requested = summary.exported_count + summary.not_exported_count
        if not requested:
            return f"\n\n📝 Voir le rapport :\n{report_path}" if report_path else ""
        lines = [f"\n\n📊 {summary.exported_count}/{requested} exporté(s), vérifié(s) dans le fichier final."]
        lines += [f"⚠️ {count} : {cause.value}" for cause, count in summary.not_exported_by_cause()]
        if report_path:
            lines.append(f"\n📝 Liste et explications :\n{report_path}")
        return "\n".join(lines)

    def _on_export_finished(self, lot_number: str, lot_dir: Path, summary: ExportSummary) -> None:
        report_path = self._worker.report_path if self._worker is not None else None
        report_note = self._export_control_note(summary, report_path)
        self._worker = None
        self._set_busy(False)
        self._update_preview()
        self._update_pending_ui()
        if not summary.has_success:
            messagebox.showwarning("Terminé", f"Aucun fichier copié. Voir le journal.{report_note}", parent=self)
            return
        try:
            os.startfile(lot_dir)  # Windows uniquement
        except (AttributeError, OSError):
            pass
        notify = messagebox.showwarning if summary.not_exported_count else messagebox.showinfo
        notify(
            "Terminé",
            (f"✅ LOT{lot_number} créé : {summary.success_count} commune(s) regroupée(s) dans "
             f"{summary.merged_file.name} !\n\n📂 {lot_dir}{report_note}")
            if summary.merged_file is not None else
            f"✅ LOT{lot_number} créé avec {summary.success_count} fichier(s) !\n\n📂 {lot_dir}{report_note}",
            parent=self,
        )
