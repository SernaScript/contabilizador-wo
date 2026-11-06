"""Tree model of the Facturas page (invoice rows with their lines) and its filter proxy.

The model only shapes ``InvoiceRow`` / ``LineRow`` for the view; editing a product or a
cost center emits ``document_edited`` / ``line_edited`` and updates the row optimistically,
and the container runs the use case and refreshes. The proxy filters recursively (a line
that matches the search shows its invoice) and never re-filters while the user edits.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import IntEnum
from typing import Any

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor

from contabilizador.invoices.domain.suggestion import MappingSource
from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.formatting import (
    code_and_name,
    format_date,
    format_money,
    format_percent,
    format_quantity,
)
from contabilizador.ui.pages.invoices.rows import (
    FIELD_COST_CENTER,
    FIELD_PRODUCT,
    FILTER_ALL,
    InvoiceRow,
    LineRow,
    SummaryKind,
    difference_text,
    matches_filter,
)
from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets.code_combo import CodeItem

type ModelIndex = QModelIndex | QPersistentModelIndex


class Column(IntEnum):
    DOCUMENT = 0
    SUPPLIER = 1
    ISSUE_DATE = 2
    DUE_DATE = 3
    QUANTITY = 4
    TOTAL = 5
    PRODUCT = 6
    COST_CENTER = 7
    STATUS = 8


HEADERS: dict[Column, str] = {
    Column.DOCUMENT: strings.COLUMN_DOCUMENT,
    Column.SUPPLIER: strings.COLUMN_SUPPLIER,
    Column.ISSUE_DATE: strings.COLUMN_ISSUE_DATE,
    Column.DUE_DATE: strings.COLUMN_DUE_DATE,
    Column.QUANTITY: strings.COLUMN_QUANTITY,
    Column.TOTAL: strings.COLUMN_TOTAL,
    Column.PRODUCT: strings.COLUMN_PRODUCT,
    Column.COST_CENTER: strings.COLUMN_COST_CENTER,
    Column.STATUS: strings.COLUMN_STATUS,
}
COLUMN_FIELDS: dict[int, str] = {
    Column.PRODUCT: FIELD_PRODUCT,
    Column.COST_CENTER: FIELD_COST_CENTER,
}
RIGHT_ALIGNED_COLUMNS = (Column.QUANTITY, Column.TOTAL)
LAST_COLUMN = len(Column) - 1

_USER_ROLE = int(Qt.ItemDataRole.UserRole)


class Role(IntEnum):
    """Custom roles (delegates and the view read rows through them, never the model)."""

    INVOICE_ID = _USER_ROLE + 1
    LINE_ID = _USER_ROLE + 2
    IS_INVOICE = _USER_ROLE + 3
    STATUS = _USER_ROLE + 4
    PILL_TEXT = _USER_ROLE + 5
    SOURCE = _USER_ROLE + 6
    CUFE = _USER_ROLE + 7
    EXPORTABLE = _USER_ROLE + 8
    DOCUMENT_TYPE = _USER_ROLE + 9
    EDITOR_ITEMS = _USER_ROLE + 10
    FIELD = _USER_ROLE + 11
    IS_EMPTY = _USER_ROLE + 12  # celda editable sin valor: invita a elegir


PROVENANCE_ICONS = {
    MappingSource.MEMORY: "memory",
    MappingSource.SUPPLIER_DEFAULT: "supplier_default",
}
PROVENANCE_TEXT = {
    MappingSource.MEMORY: strings.PROVENANCE_MEMORY,
    MappingSource.SUPPLIER_DEFAULT: strings.PROVENANCE_SUPPLIER_DEFAULT,
    MappingSource.ASSIGNED: strings.PROVENANCE_MANUAL,
}
RIGHT = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


class DocumentTreeModel(QAbstractItemModel):
    # (invoice_id, field, code) / (line_id, field, code): el contenedor ejecuta el caso de uso
    document_edited = Signal(int, str, str)
    line_edited = Signal(int, str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[InvoiceRow] = []
        self._products: dict[str, str] = {}
        self._cost_centers: dict[str, str] = {}
        self._product_items: list[CodeItem] = []
        self._cost_center_items: list[CodeItem] = []
        self._supplier_products: dict[str, tuple[str, ...]] = {}

    # --- datos ---------------------------------------------------------------
    def set_documents(self, rows: Sequence[InvoiceRow]) -> bool:
        """Replaces the rows. Same invoices and lines (by id) → updated in place so the
        view keeps expansion and selection; otherwise a full reset. Returns True on reset."""
        new_rows = list(rows)
        if new_rows and _same_structure(self._rows, new_rows):
            self._rows = new_rows
            self._emit_all_changed()
            return False
        self.beginResetModel()
        self._rows = new_rows
        self.endResetModel()
        return True

    def set_catalog(
        self,
        products: Sequence[CodeItem],
        cost_centers: Sequence[CodeItem],
        supplier_products: Mapping[str, Sequence[str]],
    ) -> None:
        self._product_items = list(products)
        self._cost_center_items = list(cost_centers)
        self._products = {item.code: item.name for item in products}
        self._cost_centers = {item.code: item.name for item in cost_centers}
        self._supplier_products = {nit: tuple(codes) for nit, codes in supplier_products.items()}
        self._emit_all_changed()

    def rows(self) -> tuple[InvoiceRow, ...]:
        return tuple(self._rows)

    def row_at(self, row: int) -> InvoiceRow:
        return self._rows[row]

    def invoice_at(self, index: ModelIndex) -> InvoiceRow:
        parent = index.parent()
        return self._rows[parent.row() if parent.isValid() else index.row()]

    def line_at(self, index: ModelIndex) -> LineRow | None:
        parent = index.parent()
        if not parent.isValid():
            return None
        return self._rows[parent.row()].lines[index.row()]

    def is_invoice(self, index: ModelIndex) -> bool:
        return index.isValid() and not index.parent().isValid()

    def index_for_invoice(self, invoice_id: int) -> QModelIndex:
        for row, invoice in enumerate(self._rows):
            if invoice.invoice_id == invoice_id:
                return self.index(row, 0)
        return QModelIndex()

    def index_for_line(self, line_id: int) -> QModelIndex:
        for row, invoice in enumerate(self._rows):
            for position, line in enumerate(invoice.lines):
                if line.line_id == line_id:
                    return self.index(position, 0, self.index(row, 0))
        return QModelIndex()

    def product_name(self, code: str) -> str | None:
        return self._products.get(code)

    def cost_center_name(self, code: str) -> str | None:
        return self._cost_centers.get(code)

    def has_products(self) -> bool:
        return bool(self._product_items)

    def has_cost_centers(self) -> bool:
        return bool(self._cost_center_items)

    def editor_items(self, index: ModelIndex) -> tuple[list[CodeItem], list[CodeItem]] | None:
        """(preferred, rest) for the combo editor of a product / cost center cell."""
        field = COLUMN_FIELDS.get(index.column())
        if field is None or not index.isValid():
            return None
        if field == FIELD_COST_CENTER:
            return [], list(self._cost_center_items)
        wanted = self._supplier_products.get(self.invoice_at(index).supplier_nit, ())
        by_code = {item.code: item for item in self._product_items}
        preferred = [by_code[code] for code in wanted if code in by_code]
        rest = [item for item in self._product_items if item.code not in wanted]
        return preferred, rest

    # --- QAbstractItemModel --------------------------------------------------
    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        if not parent.isValid():
            return len(self._rows)
        if parent.parent().isValid():
            return 0
        return len(self._rows[parent.row()].lines)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return len(Column)

    def index(self, row: int, column: int, parent: ModelIndex = QModelIndex()) -> QModelIndex:  # noqa: B008
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        if not parent.isValid():
            return self.createIndex(row, column, 0)
        # las lineas guardan la fila de su factura + 1 (0 = fila de factura)
        return self.createIndex(row, column, parent.row() + 1)

    def parent(self, child: ModelIndex = QModelIndex()) -> QModelIndex:  # type: ignore[override]  # noqa: B008
        if not child.isValid():
            return QModelIndex()
        owner = int(child.internalId())
        if owner == 0:
            return QModelIndex()
        return self.createIndex(owner - 1, 0, 0)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[Column(section)]
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole:
            return RIGHT if section in RIGHT_ALIGNED_COLUMNS else None
        return None

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() in COLUMN_FIELDS:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        invoice = self.invoice_at(index)
        line = self.line_at(index)
        column = Column(index.column())
        if role == Role.IS_INVOICE:
            return line is None
        if role == Role.INVOICE_ID:
            return invoice.invoice_id
        if role == Role.CUFE:
            return invoice.cufe
        if role == Role.LINE_ID:
            return line.line_id if line is not None else None
        if role == Role.STATUS:
            return invoice.pill_status
        if role == Role.PILL_TEXT:
            return invoice.pill_text
        if role == Role.EXPORTABLE:
            return invoice.exportable
        if role == Role.DOCUMENT_TYPE:
            return invoice.document_type
        if role == Role.SOURCE:
            return line.source.value if line is not None else None
        if role == Role.FIELD:
            return COLUMN_FIELDS.get(column)
        if role == Role.IS_EMPTY:
            return self._is_empty(invoice, line, column)
        if role == Role.EDITOR_ITEMS:
            return self.editor_items(index)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return RIGHT if column in RIGHT_ALIGNED_COLUMNS else None
        if line is None:
            return self._invoice_data(invoice, column, role)
        return self._line_data(invoice, line, column, role)

    def setData(  # noqa: N802
        self, index: ModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        field = COLUMN_FIELDS.get(index.column())
        if not index.isValid() or role != Qt.ItemDataRole.EditRole or field is None:
            return False
        code = str(value).strip() if value is not None else ""
        if not code:
            return False
        line = self.line_at(index)
        invoice_row = index.parent().row() if line is not None else index.row()
        invoice = self._rows[invoice_row]
        if line is not None:
            if line.value(field) == code:
                return True
            self._rows[invoice_row] = invoice.with_line_value(line.line_id, field, code)
            self._emit_invoice_changed(invoice_row)
            self.line_edited.emit(line.line_id, field, code)
            return True
        summary = invoice.summary(field)
        if summary.kind is SummaryKind.VALUE and summary.value == code:
            return True
        self._rows[invoice_row] = invoice.with_all_lines(field, code)
        self._emit_invoice_changed(invoice_row)
        self.document_edited.emit(invoice.invoice_id, field, code)
        return True

    # --- valores por celda ---------------------------------------------------
    @staticmethod
    def _is_empty(invoice: InvoiceRow, line: LineRow | None, column: Column) -> bool:
        field = COLUMN_FIELDS.get(column)
        if field is None:
            return False
        if line is None:
            return invoice.summary(field).kind is SummaryKind.EMPTY
        return not line.value(field)

    def _names(self, field: str) -> dict[str, str]:
        return self._products if field == FIELD_PRODUCT else self._cost_centers

    def _display_code(self, field: str, code: str) -> str:
        """``codigo - nombre``: lo que lee un tooltip (la celda muestra solo el nombre)."""
        return code_and_name(code, self._names(field).get(code))

    def _cell_label(self, field: str, code: str) -> str:
        """The name leads in the cell (it reads in 130 px); a code the catalog no longer
        knows shows as is."""
        return self._names(field).get(code) or code

    def _invoice_data(self, invoice: InvoiceRow, column: Column, role: int) -> Any:
        display = role == Qt.ItemDataRole.DisplayRole
        tooltip = role == Qt.ItemDataRole.ToolTipRole
        field = COLUMN_FIELDS.get(column)
        if field is not None:
            return self._summary_data(invoice, field, role)
        match column:
            case Column.DOCUMENT:
                if display:
                    return invoice.label
                if tooltip:
                    if invoice.document_type == "NC":
                        return strings.FLAG_CREDIT_NOTE
                    return strings.document_tooltip(
                        strings.FLAG_INVOICE, format_date(invoice.due_date)
                    )
            case Column.SUPPLIER:
                if display:
                    return invoice.supplier_name
                if tooltip:
                    return strings.supplier_tooltip(invoice.supplier_name, invoice.supplier_nit)
            case Column.ISSUE_DATE:
                if display:
                    return format_date(invoice.issue_date)
            case Column.DUE_DATE:
                if display:
                    return format_date(invoice.due_date)
            case Column.QUANTITY:
                if display:
                    return strings.lines_count(invoice.line_count)
            case Column.TOTAL:
                if display:
                    return format_money(invoice.total)
                if tooltip and not invoice.totals.matches:
                    return strings.totals_mismatch_tooltip(difference_text(invoice.totals))
            case Column.STATUS:
                if display:
                    return invoice.pill_text
                if tooltip:
                    return self._status_tooltip(invoice)
        return None

    def _summary_data(self, invoice: InvoiceRow, field: str, role: int) -> Any:
        summary = invoice.summary(field)
        if role == Qt.ItemDataRole.EditRole:
            return summary.value
        if role == Qt.ItemDataRole.DisplayRole:
            if summary.kind is SummaryKind.VALUE and summary.value is not None:
                return self._cell_label(field, summary.value)
            return strings.VARIOUS if summary.kind is SummaryKind.VARIOUS else strings.ACTION_CHOOSE
        if role == Qt.ItemDataRole.ToolTipRole:
            if summary.kind is SummaryKind.VARIOUS:
                return strings.editable_cell_tooltip(
                    strings.various_values_tooltip(
                        [self._display_code(field, code) for code in summary.values]
                    )
                )
            if summary.kind is SummaryKind.VALUE and summary.value is not None:
                return strings.editable_cell_tooltip(self._display_code(field, summary.value))
            return strings.editable_cell_tooltip(None, empty=True)
        if role == Qt.ItemDataRole.ForegroundRole:
            if summary.kind is SummaryKind.EMPTY:
                return QColor(TOKENS.incomplete)
            if summary.kind is SummaryKind.VARIOUS:
                return QColor(TOKENS.slate)
        return None

    def _status_tooltip(self, invoice: InvoiceRow) -> str:
        if invoice.problems:
            return "\n".join(
                strings.problem_message(p.kind.value, p.line_number, p.detail)
                for p in invoice.problems
            )
        if not invoice.totals.matches:
            return strings.totals_mismatch_tooltip(difference_text(invoice.totals))
        return strings.DETAIL_NO_PROBLEMS

    def _line_data(self, invoice: InvoiceRow, line: LineRow, column: Column, role: int) -> Any:
        display = role == Qt.ItemDataRole.DisplayRole
        tooltip = role == Qt.ItemDataRole.ToolTipRole
        field = COLUMN_FIELDS.get(column)
        if field is not None:
            return self._line_value_data(line, field, role)
        match column:
            case Column.DOCUMENT:
                # La descripcion necesita ancho: va en Proveedor; aqui solo "Línea n", apagado
                if display:
                    return strings.line_label(line.number)
                if role == Qt.ItemDataRole.ForegroundRole:
                    return QColor(TOKENS.slate)
                if tooltip:
                    return strings.line_values_sentence(
                        format_quantity(line.quantity),
                        format_money(line.unit_value),
                        format_percent(line.tax_percent),
                    )
            case Column.SUPPLIER:
                if display or tooltip:
                    return line.description
            case Column.QUANTITY:
                if display:
                    return format_quantity(line.quantity)
            case Column.TOTAL:
                if display:
                    return format_money(line.total)
            case Column.STATUS:
                problem = line.primary_problem
                if display:
                    return (
                        _sentence(strings.problem_kind_message(problem.kind.value))
                        if problem
                        else ""
                    )
                if tooltip and line.problems:
                    return "\n".join(
                        strings.problem_message(p.kind.value, p.line_number, p.detail)
                        for p in line.problems
                    )
                if role == Qt.ItemDataRole.ForegroundRole:
                    return QColor(TOKENS.slate)
            case _:
                if display:
                    return ""
        return None

    def _line_value_data(self, line: LineRow, field: str, role: int) -> Any:
        code = line.value(field)
        tooltip = role == Qt.ItemDataRole.ToolTipRole
        if role == Qt.ItemDataRole.EditRole:
            return code
        if role == Qt.ItemDataRole.DisplayRole:
            return self._cell_label(field, code) if code else strings.ACTION_CHOOSE
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(TOKENS.incomplete) if not code else None
        if not code:
            return strings.editable_cell_tooltip(None, empty=True) if tooltip else None
        if role == Qt.ItemDataRole.DecorationRole and line.source in PROVENANCE_ICONS:
            return icons.icon(PROVENANCE_ICONS[line.source], TOKENS.slate, 14)
        if tooltip:
            # texto completo (la celda puede elidir), de donde sale el valor y que se puede cambiar
            provenance = PROVENANCE_TEXT.get(line.source)
            display = self._display_code(field, code)
            held = f"{display}\n{provenance}" if provenance else display
            return strings.editable_cell_tooltip(held)
        return None

    # --- notificaciones ------------------------------------------------------
    def _emit_invoice_changed(self, row: int) -> None:
        top = self.index(row, 0)
        self.dataChanged.emit(top, self.index(row, LAST_COLUMN))
        count = len(self._rows[row].lines)
        if count:
            self.dataChanged.emit(self.index(0, 0, top), self.index(count - 1, LAST_COLUMN, top))

    def _emit_all_changed(self) -> None:
        for row in range(len(self._rows)):
            self._emit_invoice_changed(row)


def _same_structure(current: Sequence[InvoiceRow], new: Sequence[InvoiceRow]) -> bool:
    if len(current) != len(new):
        return False
    return all(
        a.invoice_id == b.invoice_id
        and [line.line_id for line in a.lines] == [line.line_id for line in b.lines]
        for a, b in zip(current, new, strict=True)
    )


class DocumentFilterProxy(QSortFilterProxyModel):
    """Chip + search filter. Recursive (a matching line shows its invoice; a matching
    invoice shows every line) and static: rows only move on ``refilter``."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filter = FILTER_ALL
        self._search = ""
        self.setRecursiveFilteringEnabled(True)
        self.setAutoAcceptChildRows(True)
        # No se vuelve a filtrar al editar: la fila no desaparece bajo el cursor
        self.setDynamicSortFilter(False)

    def filter_key(self) -> str:
        return self._filter

    def set_filter(self, key: str) -> None:
        self.beginFilterChange()
        self._filter = key
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def search_text(self) -> str:
        return self._search

    def set_search(self, text: str) -> None:
        self.beginFilterChange()
        self._search = text.strip().casefold()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def refilter(self) -> None:
        """Re-evaluates every row against the current chip and search."""
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(self, source_row: int, source_parent: ModelIndex) -> bool:  # noqa: N802
        model = self.sourceModel()
        if not isinstance(model, DocumentTreeModel):
            return True
        if not source_parent.isValid():
            invoice = model.row_at(source_row)
            return matches_filter(invoice, self._filter) and self._search in invoice.search_text
        invoice = model.row_at(source_parent.row())
        line = invoice.lines[source_row]
        return matches_filter(invoice, self._filter) and self._search in line.search_text
