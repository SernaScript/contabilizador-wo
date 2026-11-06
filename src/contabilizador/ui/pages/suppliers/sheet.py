"""Edit sheet of a configured supplier: its allowed products and the default one.

Presentational like the wizard: saving and deleting are requests to the container.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QWidget

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.parts import SupplierIdentity
from contabilizador.ui.pages.suppliers.picker_sheet import PickerSheet
from contabilizador.ui.pages.suppliers.rows import SupplierRow, SupplierValues
from contabilizador.ui.widgets import CodeItem


class SupplierSheet(PickerSheet):
    delete_requested = Signal(str)  # nit

    def __init__(
        self,
        row: SupplierRow,
        products: Sequence[CodeItem],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(strings.SUPPLIER_EDIT_TITLE, products, parent=parent)
        self._row = row

        # "Eliminar" va a la izquierda del pie, lejos de Guardar
        self.delete_button = QPushButton(strings.ACTION_DELETE)
        self.delete_button.setProperty("variant", "danger")
        footer_layout = self.footer.layout()
        if isinstance(footer_layout, QHBoxLayout):
            footer_layout.insertWidget(0, self.delete_button)
        self.delete_button.clicked.connect(lambda: self.delete_requested.emit(self._row.nit))

        self.identity = SupplierIdentity()
        self.identity.set_supplier(row.nit, row.name)
        self.set_selection(row.product_codes, row.default_product_code or None)
        self.body_layout.addWidget(self.identity)
        self._add_picker_to_body()
        self._set_footer_tab_order(self.delete_button, self.cancel_button, self.primary_button)

    def finish(self) -> None:
        """The container did what was asked (saved or deleted): close the sheet."""
        self.set_busy(False)
        QDialog.accept(self)

    def accept(self) -> None:
        """Primary button / Enter: validate, then ask the container to save."""
        if not self._begin_save():
            return
        self.save_requested.emit(
            SupplierValues(
                self._row.nit,
                self._row.name,
                self.picker.selected_codes(),
                self.picker.default_code() or "",
            )
        )

    def set_busy(self, busy: bool) -> None:
        super().set_busy(busy)
        self.delete_button.setEnabled(not busy)
