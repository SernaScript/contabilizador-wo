"""Native file dialogs of the Catálogos page behind a small port, so tests never open one."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QFileDialog, QWidget

from contabilizador.shared import strings


class FileDialogs(Protocol):
    def choose_workbook(self, parent: QWidget) -> Path | None:
        """The Excel file to import, or ``None`` when the person cancels."""
        ...

    def choose_template_destination(self, parent: QWidget, suggested: Path) -> Path | None:
        """Where to save the template (``suggested`` is the proposed full path)."""
        ...


def downloads_folder() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
    return Path(location) if location else Path.home()


class QtFileDialogs:
    def choose_workbook(self, parent: QWidget) -> Path | None:
        chosen, _filter = QFileDialog.getOpenFileName(
            parent,
            strings.FILE_DIALOG_EXCEL_TITLE,
            str(downloads_folder()),
            strings.FILE_DIALOG_EXCEL_FILTER,
        )
        return Path(chosen) if chosen else None

    def choose_template_destination(self, parent: QWidget, suggested: Path) -> Path | None:
        chosen, _filter = QFileDialog.getSaveFileName(
            parent,
            strings.CATALOG_TEMPLATE_DIALOG_TITLE,
            str(suggested),
            strings.FILE_DIALOG_EXCEL_FILTER,
        )
        return Path(chosen) if chosen else None
