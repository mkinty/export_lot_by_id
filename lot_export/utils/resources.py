from pathlib import Path
import sys


def resource_path(relative_path: str) -> str:
    """
    Retourne le chemin absolu d'une ressource,
    en mode développement ou avec PyInstaller.
    """
    if hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)

    return str(Path(__file__).resolve().parents[1] / relative_path)