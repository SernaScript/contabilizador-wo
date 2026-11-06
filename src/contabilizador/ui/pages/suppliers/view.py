"""Proveedores page (presentational): header, search and the list of suppliers.

It receives rows and emits requests (``edit_requested``, ``delete_requested``...); it never
calls a use case. Unconfigured suppliers come first and show a "Sin configurar" pill where
their products would be, so the list itself tells what needs attention.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QStackedLayout,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.model import (
    COL_ACTION,
    COL_DEFAULT,
    COL_PENDING,
    COL_PRODUCTS,
    COL_SUPPLIER,
    NIT_ROLE,
    STATUS_ROLE,
    SuppliersFilterProxy,
    SuppliersModel,
)
from contabilizador.ui.pages.suppliers.rows import SupplierRow
from contabilizador.ui.theme import (
    FONT_SIZES,
    PAGE_GAP,
    PAGE_MARGIN,
    PAGE_MARGIN_BOTTOM,
    PAGE_MARGIN_TOP,
    TOKENS,
)
from contabilizador.ui.widgets import (
    EmptyState,
    SearchField,
    make_label,
    paint_row_action,
    paint_status_pill,
)

STATE_LOADING = "loading"
STATE_NO_COMPANY = "no_company"
STATE_EMPTY = "empty"
STATE_LIST = "list"
STATE_NO_MATCH = "no_match"
STATE_ERROR = "error"
_PAGES = (STATE_LOADING, STATE_NO_COMPANY, STATE_EMPTY, STATE_LIST, STATE_NO_MATCH, STATE_ERROR)

ROW_HEIGHT = 52
FOCUS_BAR = 3
CELL_PAD = 8
# Proveedor se estira; el resto tiene un ancho minimo para que todo quepa en 1024 px.
# Con ventanas mas anchas, la mitad de lo que sobra va al producto por defecto (hasta un tope)
COLUMN_WIDTHS = {
    COL_PRODUCTS: 180,
    COL_DEFAULT: 146,
    COL_PENDING: 134,
    COL_ACTION: 92,
}
SUPPLIER_MIN_WIDTH = 190
DEFAULT_EXTRA_CAP = 130


class _SupplierDelegate(QStyledItemDelegate):
    """Draws the "Sin configurar" pill and the row action; every other cell is plain text."""

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        column = index.column()
        status = index.data(STATUS_ROLE)
        if status is None and column not in (COL_SUPPLIER, COL_ACTION):
            super().paint(painter, option, index)
            return
        self._paint_background(painter, option, index)
        area = option.rect.adjusted(CELL_PAD, 0, -CELL_PAD, 0)
        if column == COL_SUPPLIER:
            self._paint_supplier(painter, option, area, index)
            self._paint_focus_bar(painter, option, index)
        elif status is not None:
            text = str(index.data(Qt.ItemDataRole.DisplayRole))
            paint_status_pill(painter, area, str(status), text, option.font)
        else:
            self._paint_action(painter, option, area, index)

    @staticmethod
    def _paint_focus_bar(
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Keyboard focus on a row: the same blue bar the sidebar uses for the active page
        (the selection tint alone is too light to see where the focus is)."""
        view = option.widget
        focused_row = (
            isinstance(view, QTableView)
            and view.hasFocus()
            and view.currentIndex().row() == index.row()
        )
        if focused_row:
            bar = QRect(option.rect.left(), option.rect.top(), FOCUS_BAR, option.rect.height())
            painter.fillRect(bar, QColor(TOKENS.blue))

    @staticmethod
    def _paint_supplier(
        painter: QPainter,
        option: QStyleOptionViewItem,
        area: QRect,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Name over NIT: the name leads, the NIT is the secondary line."""
        strong = QFont(option.font)
        strong.setWeight(QFont.Weight.Medium)
        small = QFont(option.font)
        small.setPixelSize(FONT_SIZES.caption)
        top_metrics, bottom_metrics = QFontMetrics(strong), QFontMetrics(small)
        block = top_metrics.height() + 2 + bottom_metrics.height()
        top = area.top() + (area.height() - block) // 2
        name = top_metrics.elidedText(
            str(index.data(Qt.ItemDataRole.DisplayRole)), Qt.TextElideMode.ElideRight, area.width()
        )
        painter.save()
        painter.setFont(strong)
        painter.setPen(QColor(TOKENS.ink))
        painter.drawText(
            QRect(area.left(), top, area.width(), top_metrics.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            name,
        )
        painter.setFont(small)
        painter.setPen(QColor(TOKENS.slate))
        painter.drawText(
            QRect(
                area.left(), top + top_metrics.height() + 2, area.width(), bottom_metrics.height()
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            str(index.data(NIT_ROLE)),
        )
        painter.restore()

    @staticmethod
    def _paint_action(
        painter: QPainter,
        option: QStyleOptionViewItem,
        area: QRect,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        paint_row_action(painter, area, str(index.data(Qt.ItemDataRole.DisplayRole)), option.font)

    def _paint_background(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Selection and hover background only (the text is painted by hand)."""
        blank = QStyleOptionViewItem(option)
        self.initStyleOption(blank, index)
        blank.text = ""
        style = option.widget.style() if option.widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, blank, painter, option.widget)


class _SuppliersTable(QTableView):
    """Table with the keyboard and pointer affordances of the page."""

    delete_pressed = Signal(str)  # nit
    action_clicked = Signal(str)  # nit

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setItemDelegate(_SupplierDelegate(self))
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.horizontalHeader().setHighlightSections(False)
        self.horizontalHeader().setSectionsClickable(False)
        self.clicked.connect(self._on_clicked)

    def configure_columns(self) -> None:
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        for column in range(self.model().columnCount()):
            mode = (
                QHeaderView.ResizeMode.Stretch
                if column == COL_SUPPLIER
                else QHeaderView.ResizeMode.Fixed
            )
            header.setSectionResizeMode(column, mode)
        header.setMinimumSectionSize(72)
        self._fit_columns()

    def _fit_columns(self) -> None:
        widths = dict(COLUMN_WIDTHS)
        spare = self.viewport().width() - SUPPLIER_MIN_WIDTH - sum(widths.values())
        widths[COL_DEFAULT] += max(0, min(spare // 2, DEFAULT_EXTRA_CAP))
        for column, width in widths.items():
            self.setColumnWidth(column, width)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._fit_columns()
        self.fit_to_rows()  # la altura de la cabecera solo es definitiva con el estilo aplicado

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self.fit_to_rows()

    def fit_to_rows(self) -> None:
        """Caps the height at the rows' (a short list leaves the page background below it,
        not an empty white box); a long list is bounded by the page and scrolls."""
        frame = 2 * self.frameWidth()
        header = self.horizontalHeader().height()
        self.setMaximumHeight(header + self.model().rowCount() * ROW_HEIGHT + frame)

    def current_nit(self) -> str | None:
        nit = self.currentIndex().data(NIT_ROLE)
        return str(nit) if nit is not None else None

    def _on_clicked(self, index: QModelIndex) -> None:
        if index.column() == COL_ACTION:
            self.action_clicked.emit(str(index.data(NIT_ROLE)))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API
        index = self.indexAt(event.position().toPoint())
        on_action = index.isValid() and index.column() == COL_ACTION
        self.viewport().setCursor(
            Qt.CursorShape.PointingHandCursor if on_action else Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            nit = self.current_nit()
            if nit is not None:
                self.delete_pressed.emit(nit)
            event.accept()
            return
        super().keyPressEvent(event)


class SuppliersView(QWidget):
    edit_requested = Signal(str)  # nit: configure (wizard) or edit (sheet)
    delete_requested = Signal(str)  # nit
    configure_all_requested = Signal()
    navigate_requested = Signal(str)  # page key
    retry_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = STATE_LOADING
        self._has_rows = False
        self._model = SuppliersModel(self)
        self._proxy = SuppliersFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        root = QVBoxLayout(self)
        root.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN_TOP, PAGE_MARGIN, PAGE_MARGIN_BOTTOM)
        root.setSpacing(PAGE_GAP)

        header = QHBoxLayout()
        header.setSpacing(16)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        self.title_label = make_label(strings.SUPPLIERS_PAGE_TITLE, role="page-title")
        self.purpose_label = make_label(strings.SUPPLIERS_PAGE_PURPOSE, role="purpose")
        titles.addWidget(self.title_label)
        titles.addWidget(self.purpose_label)
        header.addLayout(titles, 1)
        self.configure_button = QPushButton()
        self.configure_button.setProperty("variant", "primary")
        self.configure_button.clicked.connect(self.configure_all_requested)
        self.configure_button.hide()
        header.addWidget(self.configure_button, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(header)

        toolbar = QHBoxLayout()
        self.search = SearchField(strings.SUPPLIERS_SEARCH_PLACEHOLDER)
        self.search.setMaximumWidth(340)
        self.search.search_changed.connect(self._apply_query)
        toolbar.addWidget(self.search, 1)
        toolbar.addStretch(2)
        root.addLayout(toolbar)

        self._stack = QStackedLayout()
        self.loading_label = make_label(strings.LOADING, role="muted")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self.loading_label)
        self.no_company_state = EmptyState(
            "company", strings.SUPPLIERS_NO_COMPANY_TITLE, strings.SUPPLIERS_NO_COMPANY_TEXT
        )
        self._stack.addWidget(self.no_company_state)
        self.empty_state = EmptyState(
            "suppliers",
            strings.EMPTY_SUPPLIERS_TITLE,
            strings.EMPTY_SUPPLIERS_TEXT,
            strings.ACTION_SUPPLIERS_GO_TO_INVOICES,
        )
        self.empty_state.action_triggered.connect(lambda: self.navigate_requested.emit("invoices"))
        self._stack.addWidget(self.empty_state)
        self.table = _SuppliersTable()
        self.table.setModel(self._proxy)
        self.table.configure_columns()
        self.table.setAccessibleName(strings.SUPPLIERS_PAGE_TITLE)
        self.table.activated.connect(self._on_activated)
        self.table.action_clicked.connect(self.edit_requested)
        self.table.delete_pressed.connect(self._on_delete_pressed)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self._stack.addWidget(self.table)
        self._stack.addWidget(self._build_no_match_page())
        self.error_state = EmptyState(
            "warning",
            strings.ERROR_GENERIC_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ACTION_RETRY,
        )
        self.retry_button = self.error_state.action_button
        self.error_state.action_triggered.connect(self.retry_requested)
        self._stack.addWidget(self.error_state)
        root.addLayout(self._stack, 1)
        self._apply_state()

    def _build_no_match_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        self.no_match_label = make_label("", role="muted")
        self.no_match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.no_match_label)
        self.clear_search_button = QPushButton(strings.ACTION_CLEAR_SEARCH)
        self.clear_search_button.setProperty("variant", "secondary")
        self.clear_search_button.clicked.connect(self._clear_search)
        layout.addWidget(self.clear_search_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    # --- estados ---------------------------------------------------------------------
    def state(self) -> str:
        return self._state

    def show_loading(self) -> None:
        self._has_rows = False
        self._set_state(STATE_LOADING)

    def show_no_company(self) -> None:
        self._has_rows = False
        self._set_state(STATE_NO_COMPANY)

    def show_failure(self) -> None:
        """The first load failed: say so and offer to try again."""
        self._has_rows = False
        self._set_state(STATE_ERROR)

    def _set_state(self, state: str) -> None:
        self._state = state
        self._stack.setCurrentIndex(_PAGES.index(state))
        searchable = state in (STATE_LIST, STATE_NO_MATCH)
        self.search.setVisible(searchable)

    def _apply_state(self) -> None:
        if not self._has_rows and self._state in (STATE_LOADING, STATE_NO_COMPANY, STATE_ERROR):
            self._set_state(self._state)
        elif self._model.rowCount() == 0:
            self._set_state(STATE_EMPTY)
        elif self._proxy.rowCount() == 0:
            self.no_match_label.setText(strings.suppliers_no_match(self.search.text().strip()))
            self._set_state(STATE_NO_MATCH)
        else:
            self._set_state(STATE_LIST)

    # --- datos ------------------------------------------------------------------------
    def set_suppliers(self, rows: Sequence[SupplierRow], product_names: Mapping[str, str]) -> None:
        selected = self.selected_nit()
        scroll = self.table.verticalScrollBar().value()
        self._has_rows = True
        self._model.set_suppliers(rows, product_names)
        waiting = sum(1 for row in rows if not row.configured)
        self.configure_button.setText(strings.configure_pending_action(waiting))
        self.configure_button.setVisible(waiting > 0)
        self._apply_state()
        self.table.fit_to_rows()
        if selected is not None:
            self.select_nit(selected)
        self.table.verticalScrollBar().setValue(scroll)

    def visible_nits(self) -> list[str]:
        return [
            str(self._proxy.index(row, COL_SUPPLIER).data(NIT_ROLE))
            for row in range(self._proxy.rowCount())
        ]

    def selected_nit(self) -> str | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        return str(rows[0].data(NIT_ROLE)) if rows else None

    def select_nit(self, nit: str) -> None:
        for row in range(self._proxy.rowCount()):
            if self._proxy.index(row, COL_SUPPLIER).data(NIT_ROLE) == nit:
                self.table.selectRow(row)
                return

    def _row_for(self, nit: str) -> SupplierRow | None:
        position = self._model.row_for_nit(nit)
        return self._model.supplier_at(position) if position >= 0 else None

    # --- busqueda -----------------------------------------------------------------------
    def set_search_text(self, text: str) -> None:
        self.search.setText(text)
        self._apply_query(text)

    def focus_search(self) -> None:
        if self.search.isVisibleTo(self):
            self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
            self.search.selectAll()

    def _apply_query(self, text: str) -> None:
        self._proxy.set_query(text)
        self.table.fit_to_rows()
        if self._has_rows:
            self._apply_state()

    def _clear_search(self) -> None:
        self.set_search_text("")
        self.search.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- acciones sobre una fila ---------------------------------------------------------
    def _on_activated(self, index: QModelIndex) -> None:
        nit = index.data(NIT_ROLE)
        if nit is not None:
            self.edit_requested.emit(str(nit))

    def _on_delete_pressed(self, nit: str) -> None:
        row = self._row_for(nit)
        if row is not None and row.configured:
            self.delete_requested.emit(nit)

    def context_menu(self, nit: str) -> QMenu:
        """Right-click menu of a supplier: configure/edit and, once configured, delete."""
        row = self._row_for(nit)
        menu = QMenu(self.table)
        label = (
            strings.ACTION_EDIT if row is not None and row.configured else strings.ACTION_CONFIGURE
        )
        menu.addAction(label, lambda: self.edit_requested.emit(nit))
        if row is not None and row.configured:
            menu.addAction(strings.ACTION_DELETE, lambda: self.delete_requested.emit(nit))
        return menu

    def _on_context_menu(self, position: QPoint) -> None:
        index = self.table.indexAt(position)
        if not index.isValid():
            return
        self.table.selectRow(index.row())
        menu = self.context_menu(str(index.data(NIT_ROLE)))
        menu.aboutToHide.connect(menu.deleteLater)
        menu.popup(self.table.viewport().mapToGlobal(position))
