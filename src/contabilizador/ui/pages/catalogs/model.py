"""Read-only table model of one catalog: code and name, naturally ordered, searchable."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
)

from contabilizador.shared import strings
from contabilizador.ui.pages.catalogs.rows import CatalogRow, matches, sorted_rows

type ModelIndex = QModelIndex | QPersistentModelIndex

CODE_COLUMN = 0
NAME_COLUMN = 1
ACTION_COLUMN = 2  # "Editar" en cada fila, como en Proveedores
HEADERS = (strings.COLUMN_CODE, strings.COLUMN_NAME, "")
LEFT_ALIGNMENT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
RIGHT_ALIGNMENT = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


def _alignment(column: int) -> int:
    return RIGHT_ALIGNMENT if column == ACTION_COLUMN else LEFT_ALIGNMENT


class CatalogTableModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._all: list[CatalogRow] = []
        self._visible: list[CatalogRow] = []
        self._filter = ""

    # --- carga -------------------------------------------------------------
    def set_rows(self, rows: Sequence[CatalogRow]) -> None:
        self.beginResetModel()
        self._all = sorted_rows(rows)
        self._visible = self._apply_filter()
        self.endResetModel()

    def set_filter(self, query: str) -> None:
        if query == self._filter:
            return
        self.beginResetModel()
        self._filter = query
        self._visible = self._apply_filter()
        self.endResetModel()

    def _apply_filter(self) -> list[CatalogRow]:
        return [row for row in self._all if matches(row, self._filter)]

    # --- consultas ---------------------------------------------------------
    def filter_text(self) -> str:
        return self._filter

    def total_count(self) -> int:
        return len(self._all)

    def visible_count(self) -> int:
        return len(self._visible)

    def row_at(self, row: int) -> CatalogRow | None:
        return self._visible[row] if 0 <= row < len(self._visible) else None

    def row_of(self, code: str) -> int:
        """Position of ``code`` among the visible rows, ``-1`` when absent or filtered out."""
        for position, row in enumerate(self._visible):
            if row.code == code:
                return position
        return -1

    # --- QAbstractTableModel ----------------------------------------------
    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(section)  # igual que las celdas (por defecto Qt centra las cabeceras)
        return None

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._visible[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == ACTION_COLUMN:
                return strings.ACTION_EDIT
            return row.code if column == CODE_COLUMN else row.name
        if role == Qt.ItemDataRole.ToolTipRole and column != ACTION_COLUMN:
            return row.display
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return _alignment(column)
        return None
