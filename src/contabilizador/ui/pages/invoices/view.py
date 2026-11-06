"""Facturas view (presentational): header with stepper and Importar, search and filter
chips, the document tree with its detail panel, the contextual bulk bar and the
readiness footer. It receives data and emits signals; the container runs use cases.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from PySide6.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QContextMenuEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QMouseEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QSplitter,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from contabilizador.exports.domain.readiness import Readiness
from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.pages.invoices.bulk_bar import BulkBar
from contabilizador.ui.pages.invoices.delegates import (
    CodeDelegate,
    DocumentDelegate,
    StatusDelegate,
    SupplierDelegate,
    status_column_width,
)
from contabilizador.ui.pages.invoices.detail_panel import DetailPanel
from contabilizador.ui.pages.invoices.model import (
    LAST_COLUMN,
    Column,
    DocumentFilterProxy,
    DocumentTreeModel,
    Role,
)
from contabilizador.ui.pages.invoices.rows import (
    FIELD_PRODUCT,
    FILTER_INCOMPLETE,
    FILTER_KEYS,
    FILTER_UNCONFIGURED,
    InvoiceRow,
    PageSummary,
)
from contabilizador.ui.theme import PAGE_GAP, PAGE_MARGIN, PAGE_MARGIN_TOP
from contabilizador.ui.widgets.banner import Banner
from contabilizador.ui.widgets.busy_overlay import BusyOverlay
from contabilizador.ui.widgets.code_combo import CodeItem
from contabilizador.ui.widgets.common import IconButton, make_label
from contabilizador.ui.widgets.drop_overlay import DropOverlay, paths_from_mime
from contabilizador.ui.widgets.empty_state import EmptyState
from contabilizador.ui.widgets.filter_chips import FilterChips
from contabilizador.ui.widgets.readiness_bar import ReadinessBar
from contabilizador.ui.widgets.search_field import SearchField
from contabilizador.ui.widgets.split_button import SplitButton
from contabilizador.ui.widgets.stepper import Stepper

FILTER_LABELS: dict[str, str] = {
    "all": strings.FILTER_ALL,
    "ready": strings.FILTER_READY,
    "incomplete": strings.FILTER_INCOMPLETE,
    "unconfigured": strings.FILTER_UNCONFIGURED,
    "mismatch": strings.FILTER_MISMATCH,
    "suggested": strings.FILTER_SUGGESTED,
}
# Anchos preferidos de las columnas fijas; el resto es del proveedor. Estado es solo el piso: se
# mide con la pastilla mas larga (``column_widths``) para que ninguna se corte. Los demas anchos
# son lo que el texto necesita con el relleno del tema (una fecha pide 91 px, no menos).
COLUMN_WIDTHS: dict[Column, int] = {
    Column.DOCUMENT: 138,  # incluye los 18 px del chevron: cabe "FEV-001001" con su insignia
    Column.ISSUE_DATE: 92,
    Column.DUE_DATE: 92,
    Column.QUANTITY: 72,
    Column.TOTAL: 100,
    Column.PRODUCT: 128,
    Column.COST_CENTER: 118,
    Column.STATUS: 190,
}
SUPPLIER_MIN_WIDTH = 140
# Columnas que se pliegan, en este orden, cuando no caben: sus datos siguen en el detalle y
# los tooltips. El importe, los textos editables y el estado nunca se pliegan: se estrechan.
FOLDABLE_COLUMNS = (Column.QUANTITY, Column.DUE_DATE, Column.ISSUE_DATE)
# Hasta donde se estrecha cada columna cuando plegar no basta. El texto largo se elide (su
# tooltip lo dice entero); un numero no se parte, asi que el importe cede casi nada.
COLUMN_FLOORS: dict[Column, int] = {
    Column.PRODUCT: 88,
    Column.COST_CENTER: 104,  # el encabezado "Centro de costo" y los nombres cortos caben enteros
    Column.STATUS: 144,  # las pastillas cortas caben enteras; solo se elide la mas larga
    Column.TOTAL: 92,  # "$ 12.345.678"
}
# Se estrecha por tandas: primero los nombres editables (se leen elididos y el tooltip los
# completa), despues la pastilla de estado (icono + texto elidido) y al final el importe.
SQUEEZE_TIERS = (
    (Column.PRODUCT, Column.COST_CENTER),
    (Column.STATUS,),
    (Column.TOTAL,),
)
STEP_IMPORT, STEP_COMPLETE, STEP_EXPORT = 0, 1, 2
SEARCH_WIDTH = 320
SEARCH_MIN_WIDTH = 200
TREE_BUTTONS_GAP = 4
PANEL_TOGGLE_GAP = 8  # se suma al espaciado de la fila: separa el panel del grupo de arbol


@dataclass(frozen=True, slots=True)
class ColumnPlan:
    """Which foldable columns hide and how wide the rest are; Proveedor takes what is left."""

    hidden: tuple[Column, ...]
    widths: dict[Column, int]


def _squeeze(widths: dict[Column, int], tier: Sequence[Column], deficit: int) -> int:
    """Takes up to ``deficit`` px from the columns of ``tier``, in proportion to how far each
    is above its floor; returns what is still missing."""
    room = {
        column: widths[column] - COLUMN_FLOORS[column]
        for column in tier
        if widths[column] > COLUMN_FLOORS[column]
    }
    total = sum(room.values())
    if not total:
        return deficit
    taken = min(deficit, total)
    shares = {column: taken * spare // total for column, spare in room.items()}
    leftover = taken - sum(shares.values())  # pixeles que dejo la division entera
    for column in room:
        if not leftover:
            break
        shares[column] += 1
        leftover -= 1
    for column, share in shares.items():
        widths[column] -= share
    return deficit - taken


def plan_columns(available: int, preferred: Mapping[Column, int]) -> ColumnPlan:
    """Fits the columns in ``available`` px: fold the least useful ones first and, when that
    is not enough, squeeze the rest toward their floors. Proveedor needs its minimum."""
    widths = dict(preferred)
    hidden: list[Column] = []

    def needed() -> int:
        shown = sum(width for column, width in widths.items() if column not in hidden)
        return shown + SUPPLIER_MIN_WIDTH

    for column in FOLDABLE_COLUMNS:
        if needed() > available:
            hidden.append(column)
    deficit = needed() - available
    for tier in SQUEEZE_TIERS:
        if deficit <= 0:
            break
        deficit = _squeeze(widths, tier, deficit)
    return ColumnPlan(tuple(hidden), widths)


def _row_key(index: QModelIndex | QPersistentModelIndex) -> tuple[int, int] | None:
    """Position of the row of ``index`` (parent row or -1, row), whatever its column."""
    if not index.isValid():
        return None
    parent = index.parent()
    return (parent.row() if parent.isValid() else -1, index.row())


class DocumentTree(QTreeView):
    """Tree with the page's keyboard conventions: Space expands, Esc clears the selection.

    The cells you can change say so: the pointer is a hand over them, a click opens their
    editor (Ctrl/Shift+click still selects rows) and ``is_row_active`` tells the delegates
    which row is hovered or current so they show their chevron there.
    """

    escape_pressed = Signal()
    resized = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.menu_factory: Callable[[QModelIndex], QMenu | None] | None = None
        self._hover = QPersistentModelIndex()
        self._press: tuple[tuple[int, int] | None, int] | None = None
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.setExpandsOnDoubleClick(False)
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(False)
        self.setAllColumnsShowFocus(True)
        self.setUniformRowHeights(True)
        self.setIndentation(18)
        self.setToolTip(strings.SHORTCUT_EXPAND)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        key = event.key()
        if key == Qt.Key.Key_Space:
            current = self.currentIndex()
            if current.isValid() and current.data(Role.IS_INVOICE):
                self.setExpanded(current, not self.isExpanded(current))
                event.accept()
                return
        if key == Qt.Key.Key_Escape:
            self.clearSelection()
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.resized.emit()

    # --- celdas editables ----------------------------------------------------
    def is_row_active(self, index: QModelIndex | QPersistentModelIndex) -> bool:
        """Whether the row of ``index`` is the hovered one or the current one."""
        key = _row_key(index)
        return key is not None and key in (_row_key(self._hover), _row_key(self.currentIndex()))

    def _is_editable(self, index: QModelIndex) -> bool:
        return index.isValid() and bool(index.flags() & Qt.ItemFlag.ItemIsEditable)

    def _set_hover(self, index: QModelIndex) -> None:
        if _row_key(index) == _row_key(self._hover):
            return
        # Sin fila bajo el puntero el indice persistente queda invalido
        self._hover = QPersistentModelIndex(index.siblingAtColumn(0))
        self.viewport().update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        index = self.indexAt(event.position().toPoint())
        self._set_hover(index)
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor
            if self._is_editable(index)
            else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def viewportEvent(self, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if event.type() in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._set_hover(QModelIndex())
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        return super().viewportEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        index = self.indexAt(event.position().toPoint())
        plain = not (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
        left = event.button() == Qt.MouseButton.LeftButton
        # Solo un clic simple sobre una celda editable puede abrir su editor al soltar
        clickable = left and plain and self._is_editable(index)
        self._press = (_row_key(index), index.column()) if clickable else None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        pressed, self._press = self._press, None
        super().mouseReleaseEvent(event)
        if pressed is None:
            return
        index = self.indexAt(event.position().toPoint())
        # Un clic (no un arrastre) sobre una celda editable abre su editor. La sobrecarga con
        # disparador no avisa por consola cuando no hay editor (catalogo vacio): el delegado
        # ya le dijo a la persona por que.
        if self._is_editable(index) and (_row_key(index), index.column()) == pressed:
            self.edit(index, QAbstractItemView.EditTrigger.AllEditTriggers, event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802 - Qt API
        if self.menu_factory is None:
            return
        menu = self.menu_factory(self.indexAt(event.pos()))
        if menu is not None:
            menu.exec(event.globalPos())


class InvoicesView(QWidget):
    import_files_requested = Signal()
    import_folder_requested = Signal()
    paths_dropped = Signal(list)  # list[Path]
    configure_suppliers_requested = Signal()
    configure_supplier_requested = Signal(str, str)  # nit, nombre
    export_requested = Signal()
    bulk_apply_requested = Signal(list, object, object)  # ids de factura, producto, centro
    restore_suggestion_requested = Signal(list)  # ids de linea
    copy_cufe_requested = Signal(str)
    show_in_folder_requested = Signal(object)  # Path
    edit_line_requested = Signal(int, str)  # line_id, campo (lo pide el detalle)
    refresh_requested = Signal()
    detail_visibility_changed = Signal(bool)
    cancel_requested = Signal()
    catalog_missing = Signal(str)  # campo sin catalogo para elegir

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model: DocumentTreeModel | None = None
        self._total = 0
        self._saved_state: tuple[set[int], list[int], int | None] | None = None
        self.proxy = DocumentFilterProxy(self)
        self.setAcceptDrops(True)
        self._build()
        self._connect()
        self.update_summary(_EMPTY_SUMMARY)

    # --- construccion --------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        page = QWidget()
        page_layout = QVBoxLayout(page)
        # Mismos margenes que el resto de paginas; abajo queda el pie de preparacion
        page_layout.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN_TOP, PAGE_MARGIN, 12)
        page_layout.setSpacing(PAGE_GAP)

        # Sin subtitulo: el stepper ya cuenta para que sirve la pagina (importar, completar,
        # exportar) y la linea de texto se partia en dos al estrechar la ventana
        header = QHBoxLayout()
        header.setSpacing(16)
        self.title_label = make_label(strings.INVOICES_PAGE_TITLE, role="page-title")
        header.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addStretch(1)
        self.stepper = Stepper()
        header.addWidget(self.stepper, 0, Qt.AlignmentFlag.AlignVCenter)
        self.import_button = SplitButton(
            strings.ACTION_IMPORT, icon_name="import", shortcut_id="import_files"
        )
        self.files_action = self.import_button.add_option(
            strings.ACTION_IMPORT_FILES_MENU, icon_name="file", shortcut_id="import_files"
        )
        self.folder_action = self.import_button.add_option(
            strings.ACTION_IMPORT_FOLDER_MENU, icon_name="folder", shortcut_id="import_folder"
        )
        header.addWidget(self.import_button, 0, Qt.AlignmentFlag.AlignVCenter)
        page_layout.addLayout(header)

        self.banner = Banner("", status="blocked", action_label=strings.configure_pending_action(1))
        self.banner.hide()
        page_layout.addWidget(self.banner)

        # Dos filas: busqueda y acciones de la vista arriba, chips de filtro debajo.
        # Asi la busqueda nunca queda aplastada por los chips en ventanas estrechas.
        self.toolbar = QFrame()
        self.toolbar.setProperty("role", "toolbar")
        toolbar = QVBoxLayout(self.toolbar)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self.search = SearchField()
        self.search.setMinimumWidth(SEARCH_MIN_WIDTH)
        self.search.setMaximumWidth(SEARCH_WIDTH)
        top_row.addWidget(self.search)
        top_row.addStretch(1)
        # Desplegar y plegar filas son un grupo; el panel de detalle es otro aparte, en el
        # borde derecho, sobre el panel que controla
        tree_buttons = QHBoxLayout()
        tree_buttons.setSpacing(TREE_BUTTONS_GAP)
        self.expand_button = IconButton("expand_all", strings.ACTION_EXPAND_ALL)
        tree_buttons.addWidget(self.expand_button)
        self.collapse_button = IconButton("collapse_all", strings.ACTION_COLLAPSE_ALL)
        tree_buttons.addWidget(self.collapse_button)
        top_row.addLayout(tree_buttons)
        top_row.addSpacing(PANEL_TOGGLE_GAP)
        self.detail_button = IconButton("panel_close", strings.ACTION_TOGGLE_DETAIL)
        top_row.addWidget(self.detail_button)
        toolbar.addLayout(top_row)
        self.chips = FilterChips()
        self.chips.set_chips([(key, FILTER_LABELS[key]) for key in FILTER_KEYS])
        toolbar.addWidget(self.chips)
        page_layout.addWidget(self.toolbar)

        self.bulk_bar = BulkBar()
        self.bulk_bar.hide()
        page_layout.addWidget(self.bulk_bar)

        self.stack = QStackedWidget()
        self.content = QWidget()
        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)
        self.tree = DocumentTree()
        self.tree.setModel(self.proxy)
        self.tree.menu_factory = self.context_menu_for
        self._install_delegates()
        left_layout.addWidget(self.tree, 1)
        self.no_results_label = make_label(strings.NO_RESULTS, role="muted")
        self.no_results_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results_label.hide()
        left_layout.addWidget(self.no_results_label)
        self.splitter.addWidget(left)
        self.detail = DetailPanel()
        self.splitter.addWidget(self.detail)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        content_layout.addWidget(self.splitter, 1)
        self.stack.addWidget(self.content)
        self.empty_state = EmptyState(
            "import",
            strings.EMPTY_INVOICES_TITLE,
            strings.EMPTY_INVOICES_TEXT,
            action_label=strings.ACTION_CHOOSE_FILES,
        )
        self.stack.addWidget(self.empty_state)
        page_layout.addWidget(self.stack, 1)
        root.addWidget(page, 1)

        self.readiness = ReadinessBar()
        root.addWidget(self.readiness)

        self.drop_overlay = DropOverlay(self)
        self.busy_overlay = BusyOverlay(self)

    def _install_delegates(self) -> None:
        self.tree.setItemDelegateForColumn(Column.DOCUMENT, DocumentDelegate(self.tree))
        self.tree.setItemDelegateForColumn(Column.SUPPLIER, SupplierDelegate(self.tree))
        self.tree.setItemDelegateForColumn(Column.STATUS, StatusDelegate(self.tree))
        for column in (Column.PRODUCT, Column.COST_CENTER):
            delegate = CodeDelegate(self.tree)
            delegate.catalog_missing.connect(self.catalog_missing)
            self.tree.setItemDelegateForColumn(column, delegate)

    def _apply_column_widths(self) -> None:
        # Solo tiene efecto con un modelo puesto: antes no existen las secciones
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(Column.SUPPLIER, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(60)
        for column, width in self.column_widths().items():
            self.tree.setColumnWidth(column, width)

    def column_widths(self) -> dict[Column, int]:
        """Fixed columns; Estado grows to the widest pill of the current font."""
        self.tree.ensurePolished()
        widths = dict(COLUMN_WIDTHS)
        widths[Column.STATUS] = max(widths[Column.STATUS], status_column_width(self.tree.font()))
        return widths

    def fit_columns(self) -> None:
        """Folds the least useful columns, then squeezes the rest, while the tree is too
        narrow for all of them."""
        plan = plan_columns(self.tree.viewport().width(), self.column_widths())
        for column in FOLDABLE_COLUMNS:
            self.tree.setColumnHidden(column, column in plan.hidden)
        for column, width in plan.widths.items():
            self.tree.setColumnWidth(column, width)

    def _connect(self) -> None:
        self.import_button.clicked.connect(self.import_files_requested)
        self.files_action.triggered.connect(self.import_files_requested)
        self.folder_action.triggered.connect(self.import_folder_requested)
        self.empty_state.action_triggered.connect(self.import_files_requested)
        self.banner.action_triggered.connect(self.configure_suppliers_requested)
        self.readiness.export_requested.connect(self.export_requested)
        self.stepper.step_clicked.connect(self._on_step_clicked)
        self.search.search_changed.connect(self._on_search_changed)
        self.chips.filter_changed.connect(self._on_filter_changed)
        self.expand_button.clicked.connect(self.tree.expandAll)
        self.collapse_button.clicked.connect(self.tree.collapseAll)
        self.detail_button.clicked.connect(self._toggle_detail)
        self.bulk_bar.apply_requested.connect(self._on_bulk_apply)
        self.bulk_bar.clear_requested.connect(self.clear_selection)
        self.busy_overlay.cancel_requested.connect(self.cancel_requested)
        self.tree.escape_pressed.connect(self._sync_selection)
        self.tree.resized.connect(self.fit_columns)
        self.detail.configure_supplier_requested.connect(self.configure_supplier_requested)
        self.detail.copy_cufe_requested.connect(self.copy_cufe_requested)
        self.detail.show_in_folder_requested.connect(self.show_in_folder_requested)
        self.detail.edit_line_requested.connect(self.edit_line_requested)
        self.detail.restore_suggestion_requested.connect(self.restore_suggestion_requested)
        self.detail.refresh_requested.connect(self.refresh_requested)
        selection = self.tree.selectionModel()
        selection.selectionChanged.connect(self._sync_selection)
        selection.currentChanged.connect(self._on_current_changed)
        self.proxy.modelAboutToBeReset.connect(self._remember_state)
        self.proxy.modelReset.connect(self._restore_state)
        self.proxy.dataChanged.connect(self._refresh_detail)

    # --- datos ---------------------------------------------------------------
    def set_model(self, model: DocumentTreeModel) -> None:
        self._model = model
        self.proxy.setSourceModel(model)
        self._apply_column_widths()
        self.fit_columns()

    def model(self) -> DocumentTreeModel | None:
        return self._model

    def set_catalog(self, products: Sequence[CodeItem], cost_centers: Sequence[CodeItem]) -> None:
        self.bulk_bar.set_catalog(products, cost_centers)

    def update_summary(self, summary: PageSummary) -> None:
        self._total = summary.total
        self.chips.set_counts(summary.filter_counts)
        counts: dict[object, int] = {k: v for k, v in summary.readiness_counts.items()}
        # La leyenda culpa a un proveedor solo si todas las bloqueadas lo esperan a el
        blocked = summary.readiness_counts.get(Readiness.BLOCKED, 0)
        held = summary.filter_counts.get(FILTER_UNCONFIGURED, 0)
        self.readiness.set_counts(counts, blocked_by_supplier=held >= blocked)
        count = len(summary.unconfigured)
        # Las facturas que esos proveedores retienen: el mismo numero del chip
        held = summary.filter_counts.get(FILTER_UNCONFIGURED, 0)
        self.banner.set_text(strings.unconfigured_suppliers_banner(count, held))
        self.banner.set_action(strings.configure_pending_action(count))
        self.banner.setVisible(count > 0)
        self.stepper.set_current(summary.flow_step)
        empty = summary.total == 0
        self.stack.setCurrentWidget(self.empty_state if empty else self.content)
        self.toolbar.setVisible(not empty)
        self.readiness.setVisible(not empty)
        self._sync_selection()
        self._sync_no_results()

    # --- filtros -------------------------------------------------------------
    def set_filter(self, key: str) -> None:
        self.chips.set_current(key)
        self.proxy.set_filter(key)
        self._sync_no_results()

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _on_filter_changed(self, key: str) -> None:
        self.proxy.set_filter(key)
        self._sync_no_results()

    def _on_search_changed(self, text: str) -> None:
        self.proxy.set_search(text)
        self._sync_no_results()

    def _sync_no_results(self) -> None:
        self.no_results_label.setVisible(self._total > 0 and self.proxy.rowCount() == 0)

    def _on_step_clicked(self, step: int) -> None:
        if step == STEP_IMPORT:
            self.import_files_requested.emit()
        elif step == STEP_COMPLETE:
            self.set_filter(FILTER_INCOMPLETE)
        else:
            self.export_requested.emit()

    # --- seleccion -----------------------------------------------------------
    def selected_invoice_ids(self) -> list[int]:
        model = self._model
        selection = self.tree.selectionModel()
        if model is None or selection is None:
            return []
        wanted = {index.data(Role.INVOICE_ID) for index in selection.selectedRows(0)}
        return [row.invoice_id for row in model.rows() if row.invoice_id in wanted]

    def selected_cufes(self) -> list[str]:
        model = self._model
        if model is None:
            return []
        wanted = set(self.selected_invoice_ids())
        return [row.cufe for row in model.rows() if row.invoice_id in wanted]

    def select_invoices(self, invoice_ids: Sequence[int]) -> None:
        model = self._model
        selection_model = self.tree.selectionModel()
        if model is None or selection_model is None:
            return
        selection = QItemSelection()
        first: QModelIndex | None = None
        for invoice_id in invoice_ids:
            index = self.proxy.mapFromSource(model.index_for_invoice(invoice_id))
            if not index.isValid():
                continue
            selection.select(index, index.siblingAtColumn(LAST_COLUMN))
            first = first if first is not None else index
        flags = (
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows
        )
        selection_model.select(selection, flags)
        if first is not None:
            selection_model.setCurrentIndex(first, QItemSelectionModel.SelectionFlag.NoUpdate)

    def clear_selection(self) -> None:
        self.tree.clearSelection()
        self._sync_selection()

    def current_invoice(self) -> InvoiceRow | None:
        return self._invoice_for(self.tree.currentIndex())

    def expanded_invoice_ids(self) -> set[int]:
        expanded: set[int] = set()
        for row in range(self.proxy.rowCount()):
            index = self.proxy.index(row, 0)
            if self.tree.isExpanded(index):
                expanded.add(index.data(Role.INVOICE_ID))
        return expanded

    def _invoice_for(self, index: QModelIndex) -> InvoiceRow | None:
        if self._model is None or not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        return self._model.invoice_at(source) if source.isValid() else None

    def _sync_selection(self, *_args: object) -> None:
        ids = self.selected_invoice_ids()
        count = len(ids)
        self.bulk_bar.setVisible(count >= 2 and self._total > 0)
        self.bulk_bar.set_count(count)
        if count == 0:
            self.readiness.set_selection(None)
            return
        model = self._model
        wanted = set(ids)
        chosen = (
            [row for row in model.rows() if row.invoice_id in wanted] if model is not None else []
        )
        # El pie describe la seleccion: su barra, su leyenda y su linea de descuadres
        counts = Counter(row.readiness for row in chosen)
        exportable = sum(1 for row in chosen if row.exportable)
        blocked_by_supplier = all(
            not row.supplier_configured for row in chosen if row.readiness is Readiness.BLOCKED
        )
        self.readiness.set_selection(
            exportable, count, counts=counts, blocked_by_supplier=blocked_by_supplier
        )

    def _on_current_changed(self, current: QModelIndex, _previous: QModelIndex) -> None:
        self.detail.show_invoice(self._invoice_for(current))

    def _refresh_detail(self, *_args: object) -> None:
        self.detail.show_invoice(self.current_invoice())

    def _on_bulk_apply(self, product: object, cost_center: object) -> None:
        ids = self.selected_invoice_ids()
        if not ids:
            return
        self.bulk_apply_requested.emit(ids, product, cost_center)
        self.bulk_bar.reset()

    # --- expansion y seleccion a traves de un reset --------------------------
    def _remember_state(self) -> None:
        current = self.tree.currentIndex()
        current_id = current.data(Role.INVOICE_ID) if current.isValid() else None
        self._saved_state = (self.expanded_invoice_ids(), self.selected_invoice_ids(), current_id)

    def _restore_state(self) -> None:
        saved, self._saved_state = self._saved_state, None
        model = self._model
        if saved is None or model is None:
            self._sync_selection()
            self._refresh_detail()
            return
        expanded, selected, current_id = saved
        for invoice_id in expanded:
            index = self.proxy.mapFromSource(model.index_for_invoice(invoice_id))
            if index.isValid():
                self.tree.expand(index)
        self.select_invoices(selected)
        if current_id is not None:
            index = self.proxy.mapFromSource(model.index_for_invoice(current_id))
            selection_model = self.tree.selectionModel()
            if index.isValid() and selection_model is not None:
                selection_model.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.NoUpdate)
        self._sync_selection()
        self._refresh_detail()
        self._sync_no_results()

    # --- edicion -------------------------------------------------------------
    def edit_line(self, line_id: int, field: str) -> None:
        """Expands the invoice, scrolls to the line and opens the editor of ``field``."""
        model = self._model
        if model is None:
            return
        source = model.index_for_line(line_id)
        if not source.isValid():
            return
        column = Column.PRODUCT if field == FIELD_PRODUCT else Column.COST_CENTER
        cell = self.proxy.mapFromSource(model.index(source.row(), column, source.parent()))
        if not cell.isValid():
            # la fila esta filtrada: se muestra todo ya mismo (sin debounce) para editarla
            self.search.clear_now()
            self.set_filter(FILTER_KEYS[0])
            cell = self.proxy.mapFromSource(model.index(source.row(), column, source.parent()))
            if not cell.isValid():
                return
        self.tree.expand(cell.parent())
        self.tree.scrollTo(cell)
        self.tree.setCurrentIndex(cell)
        self.tree.edit(cell)

    def context_menu_for(self, index: QModelIndex) -> QMenu | None:
        model = self._model
        if model is None or not index.isValid():
            return None
        source = self.proxy.mapToSource(index)
        invoice = model.invoice_at(source)
        line = model.line_at(source)
        menu = QMenu(self.tree)
        copy = menu.addAction(icons.icon("copy"), strings.ACTION_COPY_CUFE)
        copy.triggered.connect(lambda: self.copy_cufe_requested.emit(invoice.cufe))
        show = menu.addAction(icons.icon("folder_open"), strings.ACTION_SHOW_XML)
        show.triggered.connect(lambda: self.show_in_folder_requested.emit(invoice.source_file))
        menu.addSeparator()
        if line is not None:
            ids = [line.line_id] if line.is_manual else []
        else:
            ids = [item.line_id for item in invoice.lines if item.is_manual]
        restore = menu.addAction(icons.icon("restore"), strings.ACTION_RESTORE_SUGGESTION)
        restore.setEnabled(bool(ids))
        restore.setToolTip(strings.PROVENANCE_MANUAL)
        restore.triggered.connect(lambda: self.restore_suggestion_requested.emit(ids))
        return menu

    # --- detalle -------------------------------------------------------------
    def is_detail_visible(self) -> bool:
        return not self.detail.isHidden()

    def set_detail_visible(self, visible: bool) -> None:
        self.detail.setVisible(visible)
        self.detail_button.set_icon("panel_close" if visible else "panel_open")

    def _toggle_detail(self) -> None:
        visible = not self.is_detail_visible()
        self.set_detail_visible(visible)
        self.detail_visibility_changed.emit(visible)

    # --- tareas --------------------------------------------------------------
    def set_busy(self, message: str, *, cancellable: bool = False) -> None:
        self.busy_overlay.start(message, cancellable=cancellable)
        self.import_button.setEnabled(False)

    def set_progress(self, done: int, total: int) -> None:
        self.busy_overlay.set_progress(done, total)

    def set_idle(self) -> None:
        self.busy_overlay.finish()
        self.import_button.setEnabled(True)

    # --- arrastrar y soltar --------------------------------------------------
    def _set_dragging(self, active: bool) -> None:
        if active:
            self.drop_overlay.show_overlay()
        else:
            self.drop_overlay.hide_overlay()
        self.empty_state.set_active(active)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        if self.busy_overlay.is_running or not event.mimeData().hasUrls():
            event.ignore()
            return
        event.acceptProposedAction()
        self._set_dragging(True)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 - Qt API
        self._set_dragging(False)
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        self._set_dragging(False)
        paths = paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.paths_dropped.emit(paths)


_EMPTY_SUMMARY = PageSummary(
    total=0,
    readiness_counts={},
    filter_counts={},
    unconfigured=(),
    attention=0,
    exportable_cufes=(),
    flow_step=0,
)
