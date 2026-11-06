"""Empresa page: grouped settings form, read-only consecutives and Guardar.

Presentational: the container loads values with ``show_company`` and reacts to
``save_requested``. Nothing here touches a use case.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui.pages.company.form import SECTION_GAP, CompanyForm, CompanyValues
from contabilizador.ui.theme import (
    FORM_PAGE_GAP,
    PAGE_MARGIN,
    PAGE_MARGIN_BOTTOM,
    PAGE_MARGIN_TOP,
)
from contabilizador.ui.widgets.common import make_label
from contabilizador.ui.widgets.empty_state import EmptyState

COLUMN_WIDTH = 600
LABEL_COLUMN_WIDTH = 280
# Posiciones del QStackedWidget
_BLANK, _FORM, _EMPTY = 0, 1, 2


def _consecutive_text(last_used: int) -> str:
    return str(last_used) if last_used > 0 else strings.COMPANY_CONSECUTIVE_NONE


class CompanyView(QWidget):
    save_requested = Signal(object)  # CompanyValues
    create_company_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self.title_label = make_label(strings.COMPANY_PAGE_TITLE, role="page-title")
        self.purpose_label = make_label(strings.COMPANY_PAGE_PURPOSE, role="purpose")
        self.form = CompanyForm()
        self.fc_value: QLabel = make_label("", role="value")
        self.nc_value: QLabel = make_label("", role="value")
        self.unsaved_label: QLabel = make_label(strings.COMPANY_UNSAVED_CHANGES, role="hint")
        self.unsaved_label.hide()
        self.save_button = QPushButton(strings.ACTION_SAVE)
        self.save_button.setProperty("variant", "primary")
        self.save_button.setAutoDefault(True)
        self.save_button.setEnabled(False)
        self.empty_state = EmptyState(
            "company",
            strings.COMPANY_EMPTY_TITLE,
            strings.COMPANY_EMPTY_TEXT,
            strings.ACTION_NEW_COMPANY,
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN_TOP, PAGE_MARGIN, PAGE_MARGIN_BOTTOM)
        root.setSpacing(FORM_PAGE_GAP)
        root.addWidget(self._build_header())
        self.stack = QStackedWidget()
        # Vacia hasta que llegan los datos: nunca muestra la empresa anterior ni un vacio falso
        self.stack.insertWidget(_BLANK, QWidget())
        self.stack.insertWidget(_FORM, self._build_form_page())
        self.stack.insertWidget(_EMPTY, self._build_empty_page())
        root.addWidget(self.stack, 1)

        self.form.edited.connect(self._sync_save)
        self.form.submitted.connect(self._on_submitted)
        self.save_button.clicked.connect(self._request_save)
        self.empty_state.action_triggered.connect(self.create_company_requested)

    # --- construccion -------------------------------------------------------
    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setProperty("role", "page-header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.title_label)
        layout.addWidget(self.purpose_label)
        return header

    @staticmethod
    def _in_column(widget: QWidget) -> QHBoxLayout:
        """Left-aligned column of readable width inside a wide page."""
        widget.setMaximumWidth(COLUMN_WIDTH)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(widget, 100, Qt.AlignmentFlag.AlignTop)
        row.addStretch(1)
        return row

    def _build_form_page(self) -> QWidget:
        column = QWidget()
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        column_layout.addWidget(self.form)
        column_layout.addSpacing(SECTION_GAP)
        column_layout.addWidget(self._build_consecutives())
        column_layout.addSpacing(SECTION_GAP)
        column_layout.addWidget(self._build_save_bar())
        column_layout.addStretch(1)
        content = QWidget()
        content.setLayout(self._in_column(column))
        # Con ventanas pequenas la pagina se desplaza en vez de recortar campos
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)
        return scroll

    def _build_save_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self.unsaved_label)
        layout.addStretch(1)
        layout.addWidget(self.save_button)
        return bar

    def _build_consecutives(self) -> QWidget:
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(make_label(strings.SECTION_CONSECUTIVES, role="section"))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        grid.setColumnMinimumWidth(0, LABEL_COLUMN_WIDTH)
        grid.setColumnStretch(1, 1)
        grid.addWidget(make_label(strings.LABEL_LAST_FC, role="label"), 0, 0)
        grid.addWidget(self.fc_value, 0, 1)
        grid.addWidget(make_label(strings.LABEL_LAST_NC, role="label"), 1, 0)
        grid.addWidget(self.nc_value, 1, 1)
        layout.addLayout(grid)
        hint = make_label(strings.COMPANY_CONSECUTIVES_HINT, role="hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return section

    def _build_empty_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        # Ancho natural: con mas ancho el texto envuelto del EmptyState se recorta
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.empty_state, 0, Qt.AlignmentFlag.AlignTop)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)
        return page

    # --- estados ------------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        return self.stack.currentIndex() == _EMPTY

    def show_loading(self) -> None:
        self.stack.setCurrentIndex(_BLANK)

    def show_empty(self) -> None:
        self.stack.setCurrentIndex(_EMPTY)

    def show_company(self, values: CompanyValues, last_fc: int, last_nc: int) -> None:
        self.form.set_values(values)
        self.set_consecutives(last_fc, last_nc)
        self.stack.setCurrentIndex(_FORM)
        self._sync_save()

    def set_consecutives(self, last_fc: int, last_nc: int) -> None:
        self.fc_value.setText(_consecutive_text(last_fc))
        self.nc_value.setText(_consecutive_text(last_nc))

    def is_dirty(self) -> bool:
        """Unsaved edits that are on screen (a hidden form's edits no longer count)."""
        return self.stack.currentIndex() == _FORM and self.form.is_dirty()

    def show_saved(self, values: CompanyValues, last_fc: int, last_nc: int) -> None:
        """After a save: what was saved is the new baseline; edits made meanwhile stay."""
        self.form.mark_saved(values)
        self.set_consecutives(last_fc, last_nc)
        self._sync_save()

    def set_busy(self, busy: bool) -> None:
        """Locks Guardar while a save runs. The fields stay enabled: greying them out for a
        few milliseconds only flickers."""
        self._busy = busy
        self._sync_save()

    def show_name_error(self, text: str) -> None:
        self.form.set_name_error(text)
        self.form.focus_name()

    # --- guardar ------------------------------------------------------------
    def _sync_save(self) -> None:
        dirty = self.form.is_dirty()
        self.save_button.setEnabled(dirty and not self._busy)
        self.unsaved_label.setVisible(dirty)

    def _on_submitted(self) -> None:
        # Enter en un campo equivale a pulsar Guardar, pero solo si hay algo que guardar
        if self.save_button.isEnabled():
            self._request_save()

    def _request_save(self) -> None:
        if self.form.validate():
            self.save_requested.emit(self.form.values())
