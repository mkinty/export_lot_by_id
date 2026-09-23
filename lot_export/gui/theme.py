"""
Palette de couleurs, polices et styles ttk centralisés pour l'interface Tkinter.
Un seul endroit à modifier pour changer tout le thème visuel de l'application.
"""
import platform
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class Palette:
    bg: str = "#0f1117"
    surface: str = "#161b2e"
    input_bg: str = "#1a1f35"
    console_bg: str = "#0a0d14"
    text: str = "#e8eaf6"
    text_muted: str = "#78909c"
    text_dim: str = "#546e7a"
    accent: str = "#1565c0"
    accent_hover: str = "#0d47a1"
    accent_pressed: str = "#0a3d8f"
    accent_disabled: str = "#37474f"
    success: str = "#69f0ae"
    warning: str = "#ffb74d"
    error: str = "#ef5350"
    info: str = "#90caf9"
    border: str = "#263043"


PALETTE = Palette()

if platform.system() == "Windows":
    FONT_FAMILY = "Segoe UI"
    FONT_MONO = "Consolas"

elif platform.system() == "Darwin":  # macOS
    FONT_FAMILY = "Helvetica Neue"
    FONT_MONO = "Menlo"

else:  # Linux
    FONT_FAMILY = "DejaVu Sans"
    FONT_MONO = "DejaVu Sans Mono"


@dataclass(frozen=True)
class Fonts:
    base: tuple = (FONT_FAMILY, 11)
    muted: tuple = (FONT_FAMILY, 10)
    dim: tuple = (FONT_FAMILY, 9)
    title: tuple = (FONT_FAMILY, 14, "bold")
    large: tuple = (FONT_FAMILY, 14, "bold")
    button: tuple = (FONT_FAMILY, 12, "bold")
    mono: tuple = (FONT_MONO, 10)


FONTS = Fonts()

# Couleur de texte associée à chaque "rôle" de label (équivalent des sélecteurs QLabel[role=...]).
LABEL_ROLES = {
    "muted": (PALETTE.text_muted, FONTS.muted),
    "dim": (PALETTE.text_dim, FONTS.dim),
    "preview-warning": (PALETTE.warning, FONTS.dim),
}


def apply_theme(root: tk.Misc, p: Palette = PALETTE) -> None:
    """Configure les options par défaut des widgets tk et les styles ttk utilisés."""
    root.configure(background=p.bg)
    root.option_add("*Font", FONTS.base)
    root.option_add("*Background", p.bg)
    root.option_add("*Foreground", p.text)

    style = ttk.Style(root)
    style.theme_use("clam")  # seul thème natif dont les couleurs sont entièrement personnalisables
    style.configure(
        "Accent.Horizontal.TProgressbar",
        troughcolor=p.input_bg, background=p.accent,
        bordercolor=p.input_bg, lightcolor=p.accent, darkcolor=p.accent,
        thickness=10,
    )
    style.configure(
        "Vertical.TScrollbar",
        background=p.surface, troughcolor=p.console_bg, bordercolor=p.console_bg,
        lightcolor=p.surface, darkcolor=p.surface, arrowcolor=p.text_muted,
    )
    style.map("Vertical.TScrollbar", background=[("active", p.border)])
