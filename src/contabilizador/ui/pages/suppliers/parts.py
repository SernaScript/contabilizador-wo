"""Small presentational pieces shared by the wizard and the edit sheet."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui.formatting import format_money
from contabilizador.ui.pages.suppliers.rows import ContextLine
from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets import icon_label, make_label


class SupplierIdentity(QWidget):
    """NIT and name read from the XML: labels, not inputs (they are the supplier's key)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(4)
        grid.addWidget(make_label(strings.COLUMN_SUPPLIER_NIT, role="label"), 0, 0)
        self.nit_label: QLabel = make_label("", role="value")
        self.nit_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(self.nit_label, 0, 1)
        grid.addWidget(make_label(strings.COLUMN_SUPPLIER_NAME, role="label"), 1, 0)
        self.name_label: QLabel = make_label("", role="value")
        self.name_label.setWordWrap(True)
        self.name_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(self.name_label, 1, 1)
        grid.setColumnStretch(1, 1)

    def set_supplier(self, nit: str, name: str) -> None:
        self.nit_label.setText(nit)
        self.name_label.setText(name)


class ContextList(QWidget):
    """Read-only list of the supplier's pending lines: description left, amount right."""

    ROW_HEIGHT = 28
    MAX_VISIBLE_ROWS = 3

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        self.title_label = make_label(strings.WIZARD_CONTEXT_TITLE, role="value")
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.count_label = make_label("", role="caption")
        header.addWidget(self.count_label)
        layout.addLayout(header)
        self.table = QTableWidget(0, 2)
        self.table.setAccessibleName(strings.WIZARD_CONTEXT_TITLE)
        self.table.horizontalHeader().hide()
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(self.ROW_HEIGHT)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        self.setVisible(False)

    def set_lines(self, lines: Sequence[ContextLine], visible_rows: int | None = None) -> None:
        """Fills the list. ``visible_rows`` fixes its height (the wizard passes the tallest of
        its steps so the window keeps one size from supplier to supplier)."""
        self.table.setRowCount(len(lines))
        for row, line in enumerate(lines):
            description = QTableWidgetItem(line.description)
            description.setToolTip(f"{line.document}\n{line.description}")
            amount = QTableWidgetItem(format_money(line.amount))
            amount.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 0, description)
            self.table.setItem(row, 1, amount)
        self.count_label.setText(strings.wizard_context_lines(len(lines)))
        rows = visible_rows if visible_rows is not None else min(len(lines), self.MAX_VISIBLE_ROWS)
        self.table.setFixedHeight(rows * self.ROW_HEIGHT + 2)
        self.setVisible(bool(lines))

    def row_count(self) -> int:
        return self.table.rowCount()

    def description(self, row: int) -> str:
        item = self.table.item(row, 0)
        return item.text() if item is not None else ""

    def amount_text(self, row: int) -> str:
        item = self.table.item(row, 1)
        return item.text() if item is not None else ""


class InlineError(QFrame):
    """Validation or failure message placed under the field it is about, with the full
    width of the sheet (the footer has room for a couple of words only)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.icon_label = icon_label("blocked", TOKENS.blocked, 16)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)
        self.text_label = make_label("", role="error")
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, 1)
        self.setVisible(False)

    def text(self) -> str:
        return self.text_label.text()

    def set_text(self, text: str | None) -> None:
        self.text_label.setText(text or "")
        self.setVisible(bool(text))
