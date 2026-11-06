"""System integration of the export sheet: open files/folders and ask where to save.

The container receives these as plain callables so tests never open real apps or
native dialogs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QWidget

from contabilizador.shared import strings
from contabilizador.ui.desktop import open_with_system

# opener(path) -> True si el sistema pudo abrirlo
type Opener = Callable[[Path], bool]
# chooser(parent, sugerido) -> ruta elegida o None si el usuario cancelo
type DestinationChooser = Callable[[QWidget | None, Path], Path | None]

__all__ = ["DestinationChooser", "Opener", "ask_save_path", "documents_folder", "open_with_system"]


def ask_save_path(parent: QWidget | None, suggested: Path) -> Path | None:
    chosen, _filter = QFileDialog.getSaveFileName(
        parent, strings.EXPORT_FILE_DIALOG_TITLE, str(suggested), strings.EXPORT_FILE_FILTER
    )
    return Path(chosen) if chosen else None


def documents_folder() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(location) if location else Path.home()
