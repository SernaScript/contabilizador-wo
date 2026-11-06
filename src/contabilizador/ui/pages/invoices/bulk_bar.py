"""Contextual bulk bar: shown only with two or more invoices selected (presentational).

Its parts flow onto a second row when the page is narrow, so a selection never forces the
window wider than the screen. A refresh of the page hands the catalog again; the choices
already made stay while their codes still exist.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from contabilizador.shared import strings
from contabilizador.ui.widgets.code_combo import CodeCombo, CodeItem
from contabilizador.ui.widgets.common import make_label
from contabilizador.ui.widgets.flow_layout import FlowLayout

PRODUCT_WIDTH = 210
COST_CENTER_WIDTH = 190


def _field(label: str, combo: CodeCombo) -> QWidget:
    """Label and combo travel together when the bar wraps."""
    field = QWidget()
    row = QHBoxLayout(field)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.addWidget(make_label(label, role="label"))
    row.addWidget(combo)
    return field


class BulkBar(QFrame):
    apply_requested = Signal(object, object)  # producto | None, centro de costo | None
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "bulk-bar")
        layout = FlowLayout(self, spacing=12, row_spacing=8)
        layout.setContentsMargins(16, 8, 16, 8)
        self.count_label = make_label("", role="value")
        layout.addWidget(self.count_label)
        self.product_combo = CodeCombo(allow_empty=True, empty_label=strings.PLACEHOLDER_NO_CHANGE)
        self.product_combo.setFixedWidth(PRODUCT_WIDTH)
        layout.addWidget(_field(strings.LABEL_BULK_PRODUCT, self.product_combo))
        self.cost_center_combo = CodeCombo(
            allow_empty=True, empty_label=strings.PLACEHOLDER_NO_CHANGE
        )
        self.cost_center_combo.setFixedWidth(COST_CENTER_WIDTH)
        layout.addWidget(_field(strings.LABEL_BULK_COST_CENTER, self.cost_center_combo))
        self.apply_button = QPushButton(strings.ACTION_APPLY)
        self.apply_button.setProperty("variant", "primary")
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.setEnabled(False)
        layout.addWidget(self.apply_button)
        self.clear_button = QPushButton(strings.ACTION_CLEAR_SELECTION)
        self.clear_button.setProperty("variant", "ghost")
        self.clear_button.setToolTip(strings.SHORTCUT_CLEAR_SELECTION)
        layout.addWidget(self.clear_button)
        self._catalog: tuple[tuple[CodeItem, ...], tuple[CodeItem, ...]] | None = None

        self.product_combo.committed.connect(self._sync_apply)
        self.cost_center_combo.committed.connect(self._sync_apply)
        self.apply_button.clicked.connect(self._on_apply)
        self.clear_button.clicked.connect(self.clear_requested)

    def set_catalog(self, products: Sequence[CodeItem], cost_centers: Sequence[CodeItem]) -> None:
        catalog = (tuple(products), tuple(cost_centers))
        if catalog == self._catalog:
            return  # el mismo catalogo: nada cambia, ni lo que se esta escribiendo
        self._catalog = catalog
        # Un refresco no deshace lo elegido: se conserva si el codigo sigue existiendo
        product, cost_center = self.choices()
        self.product_combo.set_items([], list(products))
        self.cost_center_combo.set_items([], list(cost_centers))
        self.product_combo.set_current_code(product)
        self.cost_center_combo.set_current_code(cost_center)
        self._sync_apply()

    def set_count(self, count: int) -> None:
        self.count_label.setText(strings.selected_invoices(count))

    def choices(self) -> tuple[str | None, str | None]:
        return self.product_combo.current_code(), self.cost_center_combo.current_code()

    def reset(self) -> None:
        self.product_combo.set_current_code(None)
        self.cost_center_combo.set_current_code(None)
        self._sync_apply()

    def _sync_apply(self, *_args: object) -> None:
        product, cost_center = self.choices()
        self.apply_button.setEnabled(product is not None or cost_center is not None)

    def _on_apply(self) -> None:
        product, cost_center = self.choices()
        if product is None and cost_center is None:
            return
        self.apply_requested.emit(product, cost_center)
