"""Base of the two sheets that end in a product picker (wizard and edit sheet).

It owns what both share: the picker, the inline error and the lock while a save is running.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QPushButton, QWidget

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.parts import InlineError
from contabilizador.ui.pages.suppliers.product_picker import ProductPicker
from contabilizador.ui.widgets import CodeItem, Sheet


def validation_error(picker: ProductPicker) -> str | None:
    """Why the product choice cannot be saved yet, in Spanish; ``None`` when it can."""
    if picker.missing_codes():
        return strings.SUPPLIER_PRODUCTS_MISSING
    if not picker.selected_codes() or picker.default_code() is None:
        return strings.SUPPLIER_PRODUCTS_NONE
    return None


class PickerSheet(Sheet):
    save_requested = Signal(object)  # SupplierValues
    catalog_requested = Signal()

    def __init__(
        self,
        title: str,
        products: Sequence[CodeItem],
        *,
        subtitle: str | None = None,
        primary_label: str = strings.ACTION_SAVE,
        cancel_label: str = strings.ACTION_CANCEL,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            title,
            subtitle=subtitle,
            primary_label=primary_label,
            cancel_label=cancel_label,
            parent=parent,
        )
        self._locked = False
        self.picker = ProductPicker()
        self.picker.set_products(products)
        self.picker.catalog_requested.connect(self.catalog_requested)
        self.picker.selection_changed.connect(self._clear_error)
        self.picker.selection_changed.connect(self._sync_primary)
        self.error_note = InlineError()
        self._sync_primary()

    def set_selection(self, codes: Sequence[str], default_code: str | None = None) -> None:
        """Loads a supplier's products (the picker does not announce this as an edit)."""
        self.picker.set_selection(codes, default_code)
        self._sync_primary()

    def _sync_primary(self) -> None:
        """Guardar waits for the first product; the tooltip says what is missing."""
        empty = not self.picker.selected_codes()
        self.set_primary_enabled(not empty)
        self.primary_button.setToolTip(strings.SUPPLIER_PRODUCTS_NONE if empty else "")

    def _add_picker_to_body(self) -> None:
        """Subclasses call this after the widgets that go above the picker."""
        self.body_layout.addWidget(self.picker, 1)
        self.body_layout.addWidget(self.error_note)

    def _set_footer_tab_order(self, *buttons: QPushButton) -> None:
        """Tab goes from the list through the footer buttons in the order they are drawn
        (the extra buttons are created last, so their default order would be wrong)."""
        previous: QWidget = self.picker.list
        for button in buttons:
            QWidget.setTabOrder(previous, button)
            previous = button

    # --- errores bajo el selector, no en el pie ---------------------------------------
    def set_error(self, text: str | None) -> None:
        self.error_note.set_text(text)

    def _clear_error(self) -> None:
        if self.error_note.isVisibleTo(self):
            self.set_error(None)

    def mark_failed(self, message: str) -> None:
        """The container could not save: stay on this supplier and say why."""
        self.set_busy(False)
        self.set_error(message)

    def _begin_save(self) -> bool:
        """Validates the picker; on success locks the sheet and returns True."""
        error = validation_error(self.picker)
        if error is not None:
            self.set_error(error)
            return False
        self.set_error(None)
        self.set_busy(True)
        return True

    # --- bloqueo mientras se guarda ------------------------------------------------------
    def reject(self) -> None:
        if self._locked:
            return  # guardando: la ventana no se puede cerrar a medias
        super().reject()

    def set_busy(self, busy: bool) -> None:
        self._locked = busy
        super().set_busy(busy)
        self.picker.setEnabled(not busy)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self.picker.focus_search()
