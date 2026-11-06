"""Desktop integration shared by the pages: show a file in Finder / Explorer, open a file
or folder with the system. Pages receive these as plain callables so tests never launch
anything."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def show_in_file_manager(path: Path) -> None:
    """Opens the folder of ``path`` with the file selected where the platform allows it."""
    if sys.platform == "darwin":
        subprocess.run(["open", "-R", str(path)], check=False)
    elif sys.platform == "win32":
        # Explorer necesita las comillas dentro del mismo argumento: /select,"ruta con espacios"
        subprocess.run(f'explorer /select,"{path}"', check=False)
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))


def open_with_system(path: Path) -> bool:
    """Opens a file with its default app, or a folder in Finder / Explorer."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
