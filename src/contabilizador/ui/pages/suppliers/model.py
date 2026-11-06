"""Table model of the Proveedores page and its search proxy.

Unconfigured suppliers come first (the container sorts them); the model only exposes rows.
The status of a cell (``STATUS_ROLE``) tells the delegate to paint a pill instead of text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)

from contabilizador.shared import strings
from contabilizador.ui.formatting import code_and_name
from contabilizador.ui.pages.suppliers.rows import SupplierRow

# El NIT va bajo el nombre en la misma columna (ahorra ancho y conserva la jerarquia)
COL_SUPPLIER, COL_PRODUCTS, COL_DEFAULT, COL_PENDING, COL_ACTION = range(5)
COLUMN_TITLES = (
    strings.COLUMN_SUPPLIER_NAME,
    strings.COLUMN_SUPPLIER_PRODUCTS,
    strings.COLUMN_SUPPLIER_DEFAULT,
    strings.COLUMN_SUPPLIER_PENDING,
    "",
)
ROW_ROLE = int(Qt.ItemDataRole.UserRole) + 1
STATUS_ROLE = int(Qt.ItemDataRole.UserRole) + 2
NIT_ROLE = int(Qt.ItemDataRole.UserRole) + 3

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


class SuppliersModel(QAbstractTableModel):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[SupplierRow] = []
        self._names: dict[str, str] = {}

    # --- datos ------------------------------------------------------------------
    def set_suppliers(self, rows: Sequence[SupplierRow], product_names: Mapping[str, str]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self._names = dict(product_names)
        self.endResetModel()

    def supplier_at(self, row: int) -> SupplierRow:
        return self._rows[row]

    def row_for_nit(self, nit: str) -> int:
        return next((position for position, item in enumerate(self._rows) if item.nit == nit), -1)

    # --- API de Qt ----------------------------------------------------------------
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(COLUMN_TITLES)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = 0
    ) -> object:
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return COLUMN_TITLES[section]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int((RIGHT if section == COL_PENDING else LEFT).value)
        return None

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> object:
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == ROW_ROLE:
            return row
        if role == NIT_ROLE:
            return row.nit
        if role == STATUS_ROLE:
            return "blocked" if column == COL_PRODUCTS and self._pill_text(row) else None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(row, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(row, column)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int((RIGHT if column == COL_PENDING else LEFT).value)
        return None

    # --- contenido de cada celda -----------------------------------------------------
    @staticmethod
    def _pill_text(row: SupplierRow) -> str:
        if not row.configured:
            return strings.SUPPLIERS_UNCONFIGURED_TITLE
        return strings.SUPPLIER_PRODUCT_MISSING_PILL if row.missing_codes else ""

    def _label(self, code: str) -> str:
        return code_and_name(code, self._names.get(code))

    def _display(self, row: SupplierRow, column: int) -> str:
        if column == COL_SUPPLIER:
            return row.name
        if column == COL_PRODUCTS:
            return self._pill_text(row) or strings.supplier_products_count(len(row.product_codes))
        if column == COL_DEFAULT:
            return self._label(row.default_product_code) if row.default_product_code else ""
        if column == COL_PENDING:
            return str(row.pending_invoices)
        return strings.ACTION_EDIT if row.configured else strings.ACTION_CONFIGURE

    def _tooltip(self, row: SupplierRow, column: int) -> str | None:
        if column == COL_PRODUCTS and row.missing_codes:
            return strings.supplier_missing_products_tooltip(list(row.missing_codes))
        if column == COL_PRODUCTS and row.configured:
            return "\n".join(self._label(code) for code in row.product_codes)
        if column == COL_SUPPLIER:
            return f"{row.name}\n{strings.COLUMN_SUPPLIER_NIT} {row.nit}"
        return None


class SuppliersFilterProxy(QSortFilterProxyModel):
    """Search by NIT or name; the source order (unconfigured first) is kept."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._query = ""

    def set_query(self, text: str) -> None:
        self.beginFilterChange()
        self._query = text
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(  # noqa: N802
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        model = self.sourceModel()
        row = model.index(source_row, 0, source_parent).data(ROW_ROLE)
        return isinstance(row, SupplierRow) and row.matches(self._query)
