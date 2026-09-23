"""
Palette de couleurs et feuille de style (QSS) centralisées pour l'interface PySide6.
Un seul endroit à modifier pour changer tout le thème visuel de l'application.
"""
import platform

from dataclasses import dataclass


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
    FONT_FAMILY = "Sans Serif"
    FONT_MONO = "Monospace"


def build_stylesheet(p: Palette = PALETTE) -> str:
    """Génère la feuille de style QSS appliquée à toute la fenêtre.

    Les rôles (role="muted", role="dim", ...) permettent de cibler des
    QLabel sans dupliquer de styles inline dans le code Python de l'UI.
    """
    return f"""
        QWidget {{
            background-color: {p.bg};
            color: {p.text};
            font-family: "{FONT_FAMILY}";
            font-size: 11pt;
        }}

        #Header {{
            background-color: {p.surface};
        }}
        #HeaderTitle {{
            font-size: 14pt;
            font-weight: 600;
            color: {p.text};
        }}

        QLabel[role="muted"] {{
            color: {p.text_muted};
            font-size: 10pt;
        }}
        QLabel[role="dim"] {{
            color: {p.text_dim};
            font-size: 9pt;
        }}
        QLabel[role="preview-warning"] {{
            color: {p.warning};
            font-size: 9pt;
        }}
        QLabel#LotPrefix {{
            color: {p.info};
            font-size: 14pt;
            font-weight: 600;
        }}

        QLineEdit, QTextEdit {{
            background-color: {p.input_bg};
            border: 1px solid {p.border};
            border-radius: 6px;
            padding: 6px 8px;
            selection-background-color: {p.accent};
        }}
        QLineEdit#LotEntry {{
            font-size: 14pt;
            font-weight: 600;
        }}

        QTextEdit#LogConsole {{
            background-color: {p.console_bg};
            color: {p.success};
            font-family: "{FONT_MONO}";
            font-size: 10pt;
            border: 1px solid {p.border};
        }}

        QPushButton#RunButton {{
            background-color: {p.accent};
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px;
            font-size: 12pt;
            font-weight: 600;
        }}
        QPushButton#RunButton:hover {{
            background-color: {p.accent_hover};
        }}
        QPushButton#RunButton:pressed {{
            background-color: {p.accent_pressed};
        }}
        QPushButton#RunButton:disabled {{
            background-color: {p.accent_disabled};
            color: {p.text_dim};
        }}

        #FoldersPanel {{
            background-color: {p.surface};
            border: 1px solid {p.border};
            border-radius: 8px;
        }}
        #FoldersPanel QLabel {{
            background-color: transparent;
        }}
        #FoldersPanel QLineEdit {{
            font-size: 10pt;
        }}
        QPushButton#BrowseButton {{
            background-color: {p.input_bg};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 6px;
            padding: 5px 12px;
            font-size: 10pt;
        }}
        QPushButton#BrowseButton:hover {{
            border-color: {p.accent};
        }}
        QPushButton#BrowseButton:disabled {{
            color: {p.text_dim};
        }}

        QProgressBar {{
            background-color: {p.input_bg};
            border: none;
            border-radius: 4px;
            height: 10px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {p.accent};
            border-radius: 4px;
        }}
    """
