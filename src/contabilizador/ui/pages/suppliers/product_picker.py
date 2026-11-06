"""Product picker: searchable checklist with a star for the default product.

Presentational: it receives the catalog and the current selection, and reports changes
through ``selection_changed``. The rules of the selection live in ``product_list``.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QModelIndex, QObject, QRect, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QStackedLayout, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui.formatting import code_and_name
from contabilizador.ui.pages.suppliers.product_list import (
    CHECKED_ROLE,
    CODE_ROLE,
    DEFAULT_SHORTCUT,
    MISSING_ROLE,
    Entry,
    FilterProxy,
    ProductListView,
    ProductsModel,
    star_rect,
    star_tooltip,
)
from contabilizador.ui.widgets import CodeItem, SearchField, make_label

PAGE_LIST, PAGE_NO_MATCH, PAGE_EMPTY = 0, 1, 2


class ProductPicker(QWidget):
    """Searchable checklist of the catalog; the star marks the default product."""

    selection_changed = Signal()
    catalog_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog: list[CodeItem] = []
        self._model = ProductsModel(self)
        self._proxy = FilterProxy(self)
        self._proxy.setSourceModel(self._model)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = make_label(strings.FIELD_SUPPLIER_PRODUCTS, role="value")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.count_label = make_label("", role="caption")
        header.addWidget(self.count_label)
        root.addLayout(header)

        self.search = SearchField(strings.PICKER_SEARCH_PLACEHOLDER)
        # El atajo global de buscar no aplica dentro de la hoja
        self.search.setToolTip(strings.PICKER_SEARCH_PLACEHOLDER)
        self.search.textChanged.connect(self._on_search)
        self.search.installEventFilter(self)
        root.addWidget(self.search)

        self._pages = QStackedLayout()
        self.list = ProductListView()
        self.list.setModel(self._proxy)
        self.list.setAccessibleName(strings.FIELD_SUPPLIER_PRODUCTS)
        self._pages.addWidget(self.list)
        self.no_match_label = make_label("", role="muted")
        self.no_match_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_match_label.setWordWrap(True)
        self._pages.addWidget(self.no_match_label)
        self._pages.addWidget(self._build_empty_page())
        root.addLayout(self._pages, 1)

        self.summary_label = make_label("", role="caption")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        self._shortcut = QShortcut(QKeySequence(DEFAULT_SHORTCUT), self.list)
        self._shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        self._shortcut.activated.connect(self.set_current_as_default)
        self._model.changed.connect(self._on_model_changed)
        self._sync()

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label = make_label(strings.NO_PRODUCTS_HINT, role="muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)
        self.catalog_button = QPushButton(strings.ACTION_PICKER_GO_TO_CATALOGS)
        self.catalog_button.setProperty("variant", "secondary")
        self.catalog_button.clicked.connect(self.catalog_requested)
        layout.addWidget(self.catalog_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    # --- datos -------------------------------------------------------------------
    def set_products(self, items: Sequence[CodeItem]) -> None:
        """Replaces the catalog; the current selection and default are kept."""
        self._catalog = list(items)
        self._rebuild(self._model.checked_codes(), self._model.default_code())

    def set_selection(self, codes: Sequence[str], default_code: str | None = None) -> None:
        """Checks ``codes`` (listed first, in this order). Does not emit ``selection_changed``."""
        self._rebuild(tuple(codes), default_code)

    def _rebuild(self, selection: Sequence[str], default_code: str | None) -> None:
        known = {item.code: item for item in self._catalog}
        chosen = list(dict.fromkeys(selection))
        entries = [
            Entry(code, known[code].name if code in known else "", True, code not in known)
            for code in chosen
        ]
        entries.extend(
            Entry(item.code, item.name) for item in self._catalog if item.code not in chosen
        )
        self._model.reset(entries, default_code)
        self._sync()

    def selected_codes(self) -> tuple[str, ...]:
        return self._model.checked_codes()

    def default_code(self) -> str | None:
        return self._model.default_code()

    def missing_codes(self) -> tuple[str, ...]:
        """Selected products that are no longer in the catalog."""
        return self._model.missing_codes()

    def visible_codes(self) -> list[str]:
        return [
            str(self._proxy.index(row, 0).data(CODE_ROLE)) for row in range(self._proxy.rowCount())
        ]

    def set_checked(self, code: str, checked: bool) -> None:
        self._model.set_checked(code, checked)

    def set_default_code(self, code: str) -> None:
        self._model.set_default(code)

    def set_current_as_default(self) -> None:
        code = self.current_code()
        if code is not None:
            self._model.set_default(code)

    def current_code(self) -> str | None:
        code = self.list.currentIndex().data(CODE_ROLE)
        return str(code) if code is not None else None

    def focus_search(self) -> None:
        if self.search.isVisibleTo(self):
            self.search.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- geometria (para pruebas y accesibilidad) -------------------------------
    def index_for(self, code: str) -> QModelIndex:
        for row in range(self._proxy.rowCount()):
            index = self._proxy.index(row, 0)
            if index.data(CODE_ROLE) == code:
                return index
        return QModelIndex()

    def row_rect(self, code: str) -> QRect:
        return self.list.visualRect(self.index_for(code))

    def star_rect(self, code: str) -> QRect:
        index = self.index_for(code)
        if not index.isValid() or not index.data(CHECKED_ROLE) or index.data(MISSING_ROLE):
            return QRect()
        return star_rect(self.list.visualRect(index))

    def star_tooltip(self, *, is_default: bool) -> str:
        return star_tooltip(is_default=is_default)

    # --- reaccion ------------------------------------------------------------------
    def _on_search(self, text: str) -> None:
        self._proxy.set_query(text)
        # Cada busqueda nueva empieza en su primera coincidencia al pasar a la lista
        self.list.setCurrentIndex(QModelIndex())
        self._sync()

    def _on_model_changed(self) -> None:
        self._sync()
        self.selection_changed.emit()

    def _sync(self) -> None:
        total = self._model.rowCount()
        if total == 0:
            page = PAGE_EMPTY
        elif self._proxy.rowCount() == 0:
            page = PAGE_NO_MATCH
            self.no_match_label.setText(strings.picker_no_match(self.search.text().strip()))
        else:
            page = PAGE_LIST
        self._pages.setCurrentIndex(page)
        self.search.setVisible(page != PAGE_EMPTY)
        self.summary_label.setVisible(page != PAGE_EMPTY)
        self.count_label.setText(strings.picker_selected_count(len(self._model.checked_codes())))
        default = self._model.default_code()
        if default is None:
            self.summary_label.setText(strings.PICKER_NO_DEFAULT_HINT)
        else:
            label = code_and_name(default, self._model.name_of(default))
            can_change = len(self._model.checked_codes()) > 1
            self.summary_label.setText(strings.picker_default_summary(label, can_change=can_change))

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # Intro o flecha abajo en la busqueda pasan a la lista; Intro nunca envia el formulario
        moves_to_list = (
            watched is self.search
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Down)
        )
        if moves_to_list:
            self._focus_list()
            return True
        return super().eventFilter(watched, event)

    def _focus_list(self) -> None:
        if self._proxy.rowCount() == 0:
            return
        if not self.list.currentIndex().isValid():
            self.list.setCurrentIndex(self._proxy.index(0, 0))
        self.list.setFocus(Qt.FocusReason.OtherFocusReason)
