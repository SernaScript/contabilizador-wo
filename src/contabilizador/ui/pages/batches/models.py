"""Read-only table models of the Lotes exportados page: batches and the invoices of a batch."""

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
from PySide6.QtGui import QColor

from contabilizador.shared import strings
from contabilizador.ui.pages.batches.rows import BatchDocumentRow, BatchRow
from contabilizador.ui.theme import TOKENS

type ModelIndex = QModelIndex | QPersistentModelIndex

# (estado del tema, texto) de la pastilla; None cuando la celda no lleva pastilla
STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 1

LEFT = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
RIGHT = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
MUTED = QColor(TOKENS.slate)


class _ReadOnlyModel(QAbstractTableModel):
    HEADERS: tuple[str, ...] = ()
    RIGHT_ALIGNED: frozenset[int] = frozenset()

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return RIGHT if section in self.RIGHT_ALIGNED else LEFT  # igual que las celdas
        return None

    def _alignment(self, column: int) -> int:
        return RIGHT if column in self.RIGHT_ALIGNED else LEFT


class BatchesTableModel(_ReadOnlyModel):
    HEADERS = (
        strings.COLUMN_BATCH_ID,
        strings.COLUMN_BATCH_DATE,
        strings.COLUMN_BATCH_RANGES,
        strings.COLUMN_BATCH_DOCUMENTS,
        strings.COLUMN_BATCH_STATUS,
    )
    RIGHT_ALIGNED = frozenset({3})
    STATUS_COLUMN = 4

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[BatchRow] = []

    def set_rows(self, rows: Sequence[BatchRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, row: int) -> BatchRow | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of(self, batch_id: int) -> int:
        for position, row in enumerate(self._rows):
            if row.batch_id == batch_id:
                return position
        return -1

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._rows)

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                str(row.batch_id),
                row.date_text,
                row.ranges,
                str(row.document_count),
                row.status.label,
            )[column]
        if role == STATUS_ROLE:
            return (row.status.status, row.status.label) if column == self.STATUS_COLUMN else None
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == self.STATUS_COLUMN:
                return row.status.tooltip
            return row.ranges if column == 2 else None
        if role == Qt.ItemDataRole.ForegroundRole:
            return MUTED if row.voided else None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(column)
        return None


class BatchDocumentsModel(_ReadOnlyModel):
    HEADERS = (
        strings.COLUMN_BATCH_CONSECUTIVE,
        strings.COLUMN_BATCH_DOCUMENT,
        strings.COLUMN_NIT,
        strings.COLUMN_SUPPLIER,
        strings.COLUMN_ISSUE_DATE,
        strings.COLUMN_BATCH_STATUS,
    )
    STATUS_COLUMN = 5

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[BatchDocumentRow] = []

    def set_rows(self, rows: Sequence[BatchDocumentRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def row_at(self, row: int) -> BatchDocumentRow | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def row_of(self, cufe: str) -> int:
        for position, row in enumerate(self._rows):
            if row.cufe == cufe:
                return position
        return -1

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._rows)

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled
        # una factura ya liberada no se puede volver a liberar: no se selecciona
        if not self._rows[index.row()].released:
            flags |= Qt.ItemFlag.ItemIsSelectable
        return flags

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                row.consecutive,
                row.document,
                row.supplier_nit,
                row.supplier_name,
                row.issue_date,
                "",  # la pastilla la dibuja el delegado
            )[column]
        if role == STATUS_ROLE:
            if column == self.STATUS_COLUMN and row.released:
                return ("archived", strings.BATCH_DOCUMENT_RELEASED)
            return None
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 3:
                return f"{row.supplier_name} ({row.supplier_nit})"
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            return MUTED if row.released else None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return self._alignment(column)
        return None
