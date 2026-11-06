"""Catálogos page (presentational): one segmented control instead of nested tabs, search,
a read-only table and the actions that depend on the selected row.

It receives rows and emits requests; it never calls a use case.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt, Signal
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.pages.catalogs.model import ACTION_COLUMN, CatalogTableModel
from contabilizador.ui.pages.catalogs.rows import CatalogRow
from contabilizador.ui.theme import (
    PAGE_GAP,
    PAGE_MARGIN,
    PAGE_MARGIN_BOTTOM,
    PAGE_MARGIN_TOP,
    TOKENS,
)
from contabilizador.ui.widgets import (
    EmptyState,
    SearchField,
    Segmented,
    icon_label,
    make_label,
    paint_row_action,
)

ROW_HEIGHT = 38
CODE_COLUMN_WIDTH = 160
ACTION_COLUMN_WIDTH = 96
CELL_PAD = 8
SEARCH_MIN_WIDTH = 200
SEARCH_MAX_WIDTH = 360
EMPTY_MAX_WIDTH = 560

KIND_LABELS = {
    CatalogKind.PRODUCT: strings.CATALOG_PRODUCTS,
    CatalogKind.COST_CENTER: strings.CATALOG_COST_CENTERS,
}


def _button(text: str, variant: str, icon_name: str, icon_color: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("variant", variant)
    button.setIcon(icons.icon(icon_name, icon_color))
    return button


def _centered(widget: QWidget) -> QWidget:
    """Page that floats ``widget`` in the middle instead of stretching it to the edges."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 24, 0, 24)
    widget.setMaximumWidth(EMPTY_MAX_WIDTH)
    layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
    return page


class _QuietMessage(QWidget):
    """Search outcome without matches: icon, sentence and one way out, no dashed frame (the
    dashed ``EmptyState`` is for states the page can fix by creating or importing data)."""

    action_triggered = Signal()

    def __init__(self, icon_name: str, title: str, action_label: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 48, 0, 48)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(icon_label(icon_name, TOKENS.slate, 32), 0, Qt.AlignmentFlag.AlignHCenter)
        self.title_label = make_label(title, role="section")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        self.text_label = make_label("", role="muted")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label)
        self.action_button = QPushButton(action_label)
        self.action_button.setProperty("variant", "ghost")
        self.action_button.clicked.connect(self.action_triggered)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_text(self, text: str) -> None:
        self.text_label.setText(text)


class _ActionDelegate(QStyledItemDelegate):
    """Paints the "Editar" link of a row; the click itself is handled by the view."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        blank = QStyleOptionViewItem(option)
        self.initStyleOption(blank, index)
        blank.text = ""  # fondo, seleccion y foco los pinta el estilo; el texto es el enlace
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, blank, painter, widget)
        area = option.rect.adjusted(CELL_PAD, 0, -CELL_PAD, 0)
        paint_row_action(painter, area, str(index.data(Qt.ItemDataRole.DisplayRole)), option.font)


class _RowTable(QTableView):
    """Table with the row shortcuts of a list: Enter asks to edit the current row on every
    platform (macOS does not emit ``activated`` for Return, Windows does), Delete asks to
    remove it (the confirmation sheet still has the last word) and Esc clears the selection.
    The pointer turns into a hand over the edit link."""

    enter_pressed = Signal()
    delete_pressed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        index = self.indexAt(event.position().toPoint())
        on_link = index.isValid() and index.column() == ACTION_COLUMN
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor if on_link else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        plain = not (event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier)
        if plain and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.enter_pressed.emit()
            event.accept()
            return
        if plain and event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_pressed.emit()
            event.accept()
            return
        if plain and event.key() == Qt.Key.Key_Escape:
            self.clearSelection()  # "Quitar seleccion", como en el resto de la app
            event.accept()
            return
        super().keyPressEvent(event)


class CatalogsView(QWidget):
    kind_changed = Signal(object)  # CatalogKind, solo cuando la persona cambia de segmento
    new_requested = Signal()
    edit_requested = Signal(str)  # codigo
    delete_requested = Signal(str)  # codigo
    import_requested = Signal()
    template_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = CatalogKind.PRODUCT
        self._rows: dict[CatalogKind, list[CatalogRow]] = {}  # solo los tipos ya cargados
        self._has_company = True
        self._busy = False
        self.model = CatalogTableModel(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN_TOP, PAGE_MARGIN, PAGE_MARGIN_BOTTOM)
        root.setSpacing(PAGE_GAP)
        root.addWidget(self._build_header())
        root.addWidget(self._build_toolbar())
        root.addWidget(self._build_body(), 1)
        self.count_label = make_label("", role="caption")
        self.count_label.hide()
        root.addWidget(self.count_label)

        self.segmented.changed.connect(self._on_segment_changed)
        self.search.search_changed.connect(self.model.set_filter)
        self.search.search_changed.connect(lambda _text: self._refresh_state())
        self.table.activated.connect(self._emit_edit)  # doble clic
        self.table.clicked.connect(self._on_clicked)  # el enlace "Editar" de la fila
        self.table.enter_pressed.connect(self._emit_edit)
        self.table.delete_pressed.connect(self._emit_delete)
        selection = self.table.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(lambda *_args: self._sync_buttons())
        self.model.modelReset.connect(self._sync_buttons)
        self.new_button.clicked.connect(self.new_requested)
        self.import_button.clicked.connect(self.import_requested)
        self.template_button.clicked.connect(self.template_requested)
        self.delete_button.clicked.connect(self._emit_delete)
        self.empty.action_triggered.connect(self.import_requested)
        self.no_results.action_triggered.connect(self.search.clear)
        self._refresh_state()
        self._sync_buttons()

    # --- construccion --------------------------------------------------------
    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setProperty("role", "page-header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = make_label(strings.CATALOGS_PAGE_TITLE, role="page-title")
        self.purpose_label = make_label(strings.CATALOGS_PAGE_PURPOSE, role="purpose")
        self.purpose_label.setWordWrap(True)  # en ventanas estrechas cede ancho a los botones
        titles.addWidget(self.title_label)
        titles.addWidget(self.purpose_label)
        layout.addLayout(titles, 1)
        self.template_button = _button(
            strings.ACTION_DOWNLOAD_TEMPLATE, "ghost", "download", TOKENS.blue_hover
        )
        self.template_button.setToolTip(strings.CATALOG_TEMPLATE_HINT)
        self.import_button = _button(
            strings.ACTION_IMPORT_EXCEL, "secondary", "excel", TOKENS.blue_hover
        )
        self.import_button.setToolTip(strings.CATALOG_IMPORT_HINT)
        self.new_button = _button(strings.ACTION_NEW, "primary", "plus", TOKENS.on_blue)
        for button in (self.template_button, self.import_button, self.new_button):
            layout.addWidget(button, 0, Qt.AlignmentFlag.AlignBottom)
        return header

    def _build_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setProperty("role", "toolbar")
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.segmented = Segmented()
        self.segmented.set_options([(kind.value, label) for kind, label in KIND_LABELS.items()])
        layout.addWidget(self.segmented)
        self.search = SearchField(strings.CATALOG_SEARCH_PLACEHOLDER)
        self.search.setMinimumWidth(SEARCH_MIN_WIDTH)
        self.search.setMaximumWidth(SEARCH_MAX_WIDTH)
        layout.addWidget(self.search, 100)  # reclama el ancho antes que el espacio sobrante
        layout.addStretch(1)
        # Editar es el enlace de cada fila (como en Proveedores); aqui solo lo destructivo
        self.delete_button = _button(strings.ACTION_DELETE, "danger", "trash", TOKENS.blocked)
        layout.addWidget(self.delete_button)
        return toolbar

    def _build_body(self) -> QStackedWidget:
        self.stack = QStackedWidget()
        self.table = _RowTable()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionsClickable(False)
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(ACTION_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, CODE_COLUMN_WIDTH)
        self.table.setColumnWidth(ACTION_COLUMN, ACTION_COLUMN_WIDTH)
        self.table.setItemDelegateForColumn(ACTION_COLUMN, _ActionDelegate(self.table))
        self.table.setAccessibleName(strings.CATALOGS_PAGE_TITLE)
        self.stack.addWidget(self.table)

        self.empty = EmptyState(
            "catalogs",
            strings.catalog_empty_title(self._kind),
            strings.EMPTY_CATALOG_TEXT,
            strings.ACTION_IMPORT_EXCEL,
        )
        self.no_results = _QuietMessage(
            "search", strings.CATALOG_NO_RESULTS_TITLE, strings.ACTION_CLEAR_SEARCH
        )
        self.no_company = EmptyState(
            "company", strings.CATALOG_NO_COMPANY_TITLE, strings.CATALOG_NO_COMPANY_TEXT
        )
        self._pages = {
            "table": self.table,
            "empty": _centered(self.empty),
            "no_results": self.no_results,
            "no_company": _centered(self.no_company),
        }
        for page in self._pages.values():
            if page is not self.table:
                self.stack.addWidget(page)
        return self.stack

    # --- datos ---------------------------------------------------------------
    def set_rows(self, kind: CatalogKind, rows: Sequence[CatalogRow]) -> None:
        """Replaces the rows of ``kind``; the selection stays on the same code if it survives."""
        self._rows[kind] = list(rows)
        if kind is not self._kind:
            return
        keep = self.selected_code()
        self.model.set_rows(self._rows[kind])
        if keep is not None:
            self.select_code(keep)
        self._refresh_state()

    def reset(self) -> None:
        """Forgets every row (company change) so no stale data is shown while loading."""
        self._rows.clear()
        self.model.set_rows([])
        self._refresh_state()

    def current_kind(self) -> CatalogKind:
        return self._kind

    def set_kind(self, kind: CatalogKind) -> None:
        if kind is self._kind:
            return
        self._kind = kind
        self.segmented.set_current(kind.value)
        self.search.clear()
        self.model.set_filter("")  # sin esperar al debounce del buscador
        self.model.set_rows(self._rows.get(kind, []))
        self.table.setAccessibleName(KIND_LABELS[kind])
        self._refresh_state()

    def set_has_company(self, has_company: bool) -> None:
        self._has_company = has_company
        self._refresh_state()
        self._sync_buttons()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_buttons()

    # --- seleccion -----------------------------------------------------------
    def selected_code(self) -> str | None:
        selection = self.table.selectionModel()
        if selection is None:
            return None
        rows = selection.selectedRows()
        row = self.model.row_at(rows[0].row()) if rows else None
        return row.code if row is not None else None

    def select_code(self, code: str) -> bool:
        position = self.model.row_of(code)
        if position < 0:
            return False
        self.table.selectRow(position)
        self.table.scrollTo(self.model.index(position, 0))
        return True

    def reveal_code(self, code: str) -> None:
        """Selects ``code``, clearing a search that would hide it."""
        if self.model.row_of(code) < 0 and self.model.filter_text():
            self.search.clear()
            self.model.set_filter("")
            self._refresh_state()
        self.select_code(code)

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    # --- estado --------------------------------------------------------------
    def state(self) -> str:
        """Which body is showing: ``table``, ``empty``, ``no_results`` or ``no_company``."""
        for name, page in self._pages.items():
            if page is self.stack.currentWidget():
                return name
        return "table"

    def _compute_state(self) -> str:
        if not self._has_company:
            return "no_company"
        if self._kind not in self._rows:
            return "table"  # aun sin datos: no afirmar que el catalogo esta vacio
        if self.model.total_count() == 0:
            return "empty"
        if self.model.visible_count() == 0:
            return "no_results"
        return "table"

    def _refresh_state(self) -> None:
        name = self._compute_state()
        self.empty.set_title(strings.catalog_empty_title(self._kind))
        query = self.model.filter_text().strip()
        self.no_results.set_text(strings.catalog_no_results(self._kind, query))
        self.stack.setCurrentWidget(self._pages[name])
        loaded = self._kind in self._rows and self._has_company
        has_rows = name in ("table", "no_results")
        for control in (self.search, self.delete_button):
            control.setVisible(has_rows)
        show_count = loaded and has_rows
        if show_count:
            self.count_label.setText(
                strings.catalog_count(
                    self._kind, self.model.visible_count(), self.model.total_count()
                )
            )
        self.count_label.setVisible(show_count)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        active = self._has_company and not self._busy
        for button in (self.new_button, self.import_button, self.template_button):
            button.setEnabled(active)
            button.setVisible(self._has_company)
        selected = active and self.selected_code() is not None
        self.delete_button.setEnabled(selected)
        self.delete_button.setToolTip("" if selected else strings.CATALOG_DELETE_DISABLED_HINT)

    # --- senales -------------------------------------------------------------
    def _on_segment_changed(self, key: str) -> None:
        kind = CatalogKind(key)
        self.set_kind(kind)
        self.kind_changed.emit(kind)

    def _on_clicked(self, index: QModelIndex) -> None:
        # Un clic en el enlace selecciona la fila y pide editarla
        if index.column() == ACTION_COLUMN:
            self._emit_edit()

    def _emit_edit(self) -> None:
        code = self.selected_code()
        if code is not None and self._has_company and not self._busy:
            self.edit_requested.emit(code)

    def _emit_delete(self) -> None:
        code = self.selected_code()
        if code is not None and self._has_company and not self._busy:
            self.delete_requested.emit(code)
