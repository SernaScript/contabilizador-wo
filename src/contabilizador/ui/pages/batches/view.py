"""Lotes exportados page (presentational): the company's batches on top, the invoices of the
selected batch below, and the actions that depend on that selection.

It receives rows and emits requests; it never calls a use case.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QByteArray, QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QKeyEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.pages.batches.delegates import StatusPillDelegate
from contabilizador.ui.pages.batches.models import BatchDocumentsModel, BatchesTableModel
from contabilizador.ui.pages.batches.rows import BatchRow
from contabilizador.ui.theme import (
    PAGE_GAP,
    PAGE_MARGIN,
    PAGE_MARGIN_BOTTOM,
    PAGE_MARGIN_TOP,
    TOKENS,
)
from contabilizador.ui.widgets import EmptyState, StatusPill, make_label

BATCH_ROW_HEIGHT = 38
# La lista de lotes mide lo que sus filas (hasta este tope); el resto de la pagina es del
# detalle. Un par de lotes no reservan media pantalla en blanco.
MAX_BATCH_ROWS = 6
MAX_LIST_SHARE = 0.55
DOCUMENT_ROW_HEIGHT = 34
MIN_SECTION_WIDTH = 64
EMPTY_MAX_WIDTH = 560
INITIAL_SPLIT = (230, 400)
# El tema dibuja las manijas como una linea de 1 px, imposible de agarrar con el raton
SPLITTER_QSS = f"""
    QSplitter::handle:vertical {{ height: 9px; background: transparent; }}
    QSplitter::handle:vertical:hover {{ background: {TOKENS.hairline}; }}
"""


class _PathLabel(QLabel):
    """One-line label that elides the middle of a long path instead of widening the page;
    the full path stays in the tooltip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def set_path(self, text: str, tooltip: str | None = None) -> None:
        """``text`` is what is read (the file name); ``tooltip`` the full path."""
        self._full = text
        self.setToolTip(tooltip if tooltip is not None else text)
        self._elide()

    def full_text(self) -> str:
        return self._full

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        metrics = self.fontMetrics()
        self.setText(metrics.elidedText(self._full, Qt.TextElideMode.ElideMiddle, self.width()))


class _InvoicesTable(QTableView):
    """Invoices of the selected batch: Esc clears the selection ("Quitar selección")."""

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape and not event.modifiers():
            self.clearSelection()
            event.accept()
            return
        super().keyPressEvent(event)


def _centered(widget: QWidget) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 24, 0, 24)
    widget.setMaximumWidth(EMPTY_MAX_WIDTH)
    layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
    return page


def _configure_table(table: QTableView, row_height: int, mode: QAbstractItemView.SelectionMode):
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(mode)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setShowGrid(False)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideRight)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionsClickable(False)
    header.setHighlightSections(False)
    header.setMinimumSectionSize(MIN_SECTION_WIDTH)


def _fit(table: QTableView, stretch_column: int) -> None:
    header = table.horizontalHeader()
    for column in range(table.model().columnCount()):
        mode = (
            QHeaderView.ResizeMode.Stretch
            if column == stretch_column
            else QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(column, mode)


def _button(text: str, variant: str, icon_name: str | None, color: str) -> QPushButton:
    button = QPushButton(text)
    button.setProperty("variant", variant)
    if icon_name:
        button.setIcon(icons.icon(icon_name, color))
    return button


class BatchesView(QWidget):
    batch_selected = Signal(object)  # id del lote | None
    void_requested = Signal(int)  # id del lote
    release_requested = Signal(int, list)  # (id del lote, cufes sin liberar)
    show_file_requested = Signal(int)  # id del lote
    empty_action_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loaded = False
        self._has_company = True
        self._busy = False
        self._split_customised = False  # la persona movio el divisor: se respeta
        self.batches_model = BatchesTableModel(self)
        self.documents_model = BatchDocumentsModel(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN_TOP, PAGE_MARGIN, PAGE_MARGIN_BOTTOM)
        root.setSpacing(PAGE_GAP)
        root.addWidget(self._build_header())
        root.addWidget(self._build_body(), 1)

        batch_selection = self.batches_table.selectionModel()
        if batch_selection is not None:
            batch_selection.selectionChanged.connect(lambda *_args: self._on_batch_changed())
        document_selection = self.documents_table.selectionModel()
        if document_selection is not None:
            document_selection.selectionChanged.connect(lambda *_args: self._sync_actions())
        self.splitter.splitterMoved.connect(self._on_split_moved)
        self.void_button.clicked.connect(self._emit_void)
        self.release_button.clicked.connect(self._emit_release)
        self.show_file_button.clicked.connect(self._emit_show_file)
        self.empty.action_triggered.connect(self.empty_action_requested)
        self._show_detail(None)
        self._refresh_state()

    # --- construccion --------------------------------------------------------
    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setProperty("role", "page-header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.title_label = make_label(strings.BATCHES_PAGE_TITLE, role="page-title")
        self.purpose_label = make_label(strings.BATCHES_PAGE_PURPOSE, role="purpose")
        layout.addWidget(self.title_label)
        layout.addWidget(self.purpose_label)
        return header

    def _build_body(self) -> QStackedWidget:
        self.stack = QStackedWidget()
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStyleSheet(SPLITTER_QSS)
        self.splitter.addWidget(self._build_batches_table())
        self.splitter.addWidget(self._build_detail())
        # Al ensanchar o alargar la ventana todo lo que sobra es del detalle: la lista de lotes
        # conserva la altura de sus filas (o la que la persona le dio)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes(list(INITIAL_SPLIT))

        self.empty = EmptyState(
            "batches",
            strings.EMPTY_BATCHES_TITLE,
            strings.EMPTY_BATCHES_TEXT,
            strings.BATCH_ACTION_GO_TO_INVOICES,
        )
        self.no_company = EmptyState(
            "company", strings.BATCH_NO_COMPANY_TITLE, strings.BATCH_NO_COMPANY_TEXT
        )
        self._pages = {
            "list": self.splitter,
            "empty": _centered(self.empty),
            "no_company": _centered(self.no_company),
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        return self.stack

    def _build_batches_table(self) -> QTableView:
        self.batches_table = QTableView()
        self.batches_table.setModel(self.batches_model)
        _configure_table(
            self.batches_table, BATCH_ROW_HEIGHT, QAbstractItemView.SelectionMode.SingleSelection
        )
        self.batches_table.setItemDelegateForColumn(
            self.batches_model.STATUS_COLUMN, StatusPillDelegate(self.batches_table)
        )
        _fit(self.batches_table, stretch_column=2)
        self.batches_table.setAccessibleName(strings.BATCHES_PAGE_TITLE)
        return self.batches_table

    def _build_detail(self) -> QWidget:
        detail = QWidget()
        layout = QVBoxLayout(detail)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        self.detail_placeholder = make_label(strings.BATCH_DETAIL_PLACEHOLDER, role="muted")
        self.detail_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.detail_placeholder, 1)

        self.detail_content = QWidget()
        content = QVBoxLayout(self.detail_content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.detail_title = make_label("", role="section")
        title_row.addWidget(self.detail_title)
        self.detail_pill = StatusPill("archived", strings.BATCH_STATUS_EXPORTED)
        title_row.addWidget(self.detail_pill)
        title_row.addStretch(1)
        titles.addLayout(title_row)
        self.detail_summary = make_label("", role="muted")
        self.detail_summary.setWordWrap(True)
        titles.addWidget(self.detail_summary)
        top.addLayout(titles, 1)
        self.show_file_button = _button(
            strings.ACTION_SHOW_BATCH_FILE, "secondary", "folder_open", TOKENS.blue_hover
        )
        self.void_button = _button(strings.ACTION_VOID_BATCH, "danger", None, TOKENS.blocked)
        top.addWidget(self.show_file_button, 0, Qt.AlignmentFlag.AlignTop)
        top.addWidget(self.void_button, 0, Qt.AlignmentFlag.AlignTop)
        content.addLayout(top)

        self.detail_file = _PathLabel()
        self.detail_file.setProperty("role", "caption")
        content.addWidget(self.detail_file)

        self.documents_table = _InvoicesTable()
        self.documents_table.setModel(self.documents_model)
        _configure_table(
            self.documents_table,
            DOCUMENT_ROW_HEIGHT,
            QAbstractItemView.SelectionMode.ExtendedSelection,
        )
        self.documents_table.setItemDelegateForColumn(
            self.documents_model.STATUS_COLUMN, StatusPillDelegate(self.documents_table)
        )
        _fit(self.documents_table, stretch_column=3)
        self.documents_table.setAccessibleName(strings.COLUMN_BATCH_DOCUMENTS)
        content.addWidget(self.documents_table, 1)

        # La frase explica el boton que tiene al lado: por que no se puede o cuantas se liberan
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bottom.addStretch(1)
        self.selection_label = make_label(strings.release_selection_caption(0), role="caption")
        bottom.addWidget(self.selection_label)
        self.release_button = _button(
            strings.ACTION_RELEASE_SELECTED_INVOICES, "secondary", "restore", TOKENS.blue_hover
        )
        bottom.addWidget(self.release_button)
        content.addLayout(bottom)

        layout.addWidget(self.detail_content, 1)
        return detail

    # --- altura de la lista --------------------------------------------------
    def list_height(self, rows: int | None = None) -> int:
        """Height that shows ``rows`` batches (default: all of them, up to the cap)."""
        table = self.batches_table
        header = table.horizontalHeader()
        table.ensurePolished()
        header.ensurePolished()
        count = min(self.batches_model.rowCount() if rows is None else rows, MAX_BATCH_ROWS)
        body = max(count, 1) * BATCH_ROW_HEIGHT
        return header.sizeHint().height() + body + 2 * table.frameWidth()

    def _apply_default_split(self) -> None:
        if self._split_customised:
            return
        total = self.splitter.height() or sum(INITIAL_SPLIT)
        wanted = min(self.list_height(), int(total * MAX_LIST_SHARE))
        # Los tamaños no incluyen la manija: si se cuenta, el divisor reparte de mas y la lista
        # queda unos pixeles corta (con barra de desplazamiento para una fila)
        rest = total - wanted - self.splitter.handleWidth()
        self.splitter.setSizes([wanted, max(rest, 1)])

    def restore_split_state(self, state: QByteArray) -> None:
        """The layout the person left last time; from then on it is not recomputed."""
        self.splitter.restoreState(state)
        self._split_customised = True

    def _on_split_moved(self, *_args: object) -> None:
        self._split_customised = True

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._apply_default_split()

    # --- datos ---------------------------------------------------------------
    def set_batches(self, rows: Sequence[BatchRow]) -> None:
        """Replaces the list; the selected batch and its selected invoices survive when they
        still exist, otherwise the newest batch is selected."""
        keep_id = self.selected_batch_id()
        keep_cufes = self.selected_cufes()
        self._loaded = True
        self.batches_model.set_rows(rows)
        self._apply_default_split()
        self._refresh_state()
        if not rows:
            self._show_detail(None)
            return
        known = keep_id is not None and self.batches_model.row_of(keep_id) >= 0
        target = keep_id if known and keep_id is not None else rows[0].batch_id
        self.select_batch(target)
        if known:
            self.select_cufes(keep_cufes)

    def reset(self) -> None:
        """Forgets every row (company change) so nothing stale shows while loading."""
        self._loaded = False
        self.batches_model.set_rows([])
        self._apply_default_split()
        self._show_detail(None)
        self._refresh_state()

    def set_has_company(self, has_company: bool) -> None:
        self._has_company = has_company
        self._refresh_state()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_actions()

    # --- seleccion -----------------------------------------------------------
    def _selected_row(self) -> BatchRow | None:
        selection = self.batches_table.selectionModel()
        if selection is None:
            return None
        rows = selection.selectedRows()
        return self.batches_model.row_at(rows[0].row()) if rows else None

    def selected_batch_id(self) -> int | None:
        row = self._selected_row()
        return row.batch_id if row is not None else None

    def select_batch(self, batch_id: int) -> bool:
        position = self.batches_model.row_of(batch_id)
        if position < 0:
            return False
        self.batches_table.selectRow(position)
        self.batches_table.scrollTo(self.batches_model.index(position, 0))
        return True

    def selected_cufes(self) -> list[str]:
        """Selected invoices that can still be released, in table order."""
        selection = self.documents_table.selectionModel()
        if selection is None:
            return []
        cufes = []
        for index in sorted(selection.selectedRows(), key=lambda i: i.row()):
            document = self.documents_model.row_at(index.row())
            if document is not None and not document.released:
                cufes.append(document.cufe)
        return cufes

    def select_cufes(self, cufes: Sequence[str]) -> None:
        selection = self.documents_table.selectionModel()
        if selection is None:
            return
        selection.clearSelection()
        for cufe in cufes:
            position = self.documents_model.row_of(cufe)
            if position >= 0:
                selection.select(
                    self.documents_model.index(position, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )

    # --- estado --------------------------------------------------------------
    def state(self) -> str:
        """Which body is showing: ``list``, ``empty`` or ``no_company``."""
        for name, page in self._pages.items():
            if page is self.stack.currentWidget():
                return name
        return "list"

    def _refresh_state(self) -> None:
        if not self._has_company:
            name = "no_company"
        elif self._loaded and self.batches_model.rowCount() == 0:
            name = "empty"  # solo tras cargar: antes de eso no se afirma que no haya lotes
        else:
            name = "list"
        self.stack.setCurrentWidget(self._pages[name])

    def _on_batch_changed(self) -> None:
        row = self._selected_row()
        self._show_detail(row)
        self.batch_selected.emit(row.batch_id if row is not None else None)

    def _show_detail(self, row: BatchRow | None) -> None:
        self.detail_content.setVisible(row is not None)
        self.detail_placeholder.setVisible(row is None)
        if row is None:
            self.documents_model.set_rows([])
            self._sync_actions()
            return
        self.detail_title.setText(strings.batch_title(row.batch_id))
        self.detail_pill.set_status(row.status.status, row.status.label)
        self.detail_pill.setToolTip(row.status.tooltip)
        self.detail_summary.setText(row.summary)
        self.detail_file.set_path(row.file_path.name, str(row.file_path))
        self.documents_model.set_rows(row.documents)
        # La columna Estado solo marca excepciones (las liberadas): sin ellas queda vacia
        self.documents_table.setColumnHidden(
            self.documents_model.STATUS_COLUMN, not any(item.released for item in row.documents)
        )
        self._sync_actions()

    def _sync_actions(self) -> None:
        row = self._selected_row()
        voided = row is not None and row.voided
        can_void = row is not None and not voided and not self._busy
        self.void_button.setEnabled(can_void)
        self.void_button.setToolTip(strings.BATCH_VOID_DISABLED_HINT if voided else "")
        cufes = self.selected_cufes()
        can_release = row is not None and not voided and bool(cufes) and not self._busy
        self.release_button.setEnabled(can_release)
        if can_release:
            hint = ""
        elif voided:
            hint = strings.BATCH_RELEASE_DISABLED_VOIDED
        else:
            hint = strings.BATCH_RELEASE_DISABLED_NOTHING
        self.release_button.setToolTip(hint)
        caption = strings.release_selection_caption(len(cufes)) if cufes else hint
        self.selection_label.setText(caption)
        self.show_file_button.setEnabled(row is not None)
        self.show_file_button.setToolTip(str(row.file_path) if row is not None else "")

    # --- senales -------------------------------------------------------------
    def _emit_void(self) -> None:
        batch_id = self.selected_batch_id()
        if batch_id is not None:
            self.void_requested.emit(batch_id)

    def _emit_release(self) -> None:
        batch_id = self.selected_batch_id()
        cufes = self.selected_cufes()
        if batch_id is not None and cufes:
            self.release_requested.emit(batch_id, cufes)

    def _emit_show_file(self) -> None:
        batch_id = self.selected_batch_id()
        if batch_id is not None:
            self.show_file_requested.emit(batch_id)
