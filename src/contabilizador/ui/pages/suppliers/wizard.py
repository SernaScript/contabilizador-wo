"""Supplier wizard: configures a list of suppliers one at a time.

Presentational: it never saves. "Guardar y siguiente" asks the container (``save_requested``)
and waits for ``mark_saved`` (next supplier) or ``mark_failed`` (stay and show why).
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QPushButton, QWidget

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.parts import ContextList, SupplierIdentity
from contabilizador.ui.pages.suppliers.picker_sheet import PickerSheet
from contabilizador.ui.pages.suppliers.rows import SupplierStep, SupplierValues
from contabilizador.ui.widgets import CodeItem


def _progress_text(index: int, total: int) -> str | None:
    return strings.supplier_dialog_subtitle(index + 1, total) if total > 1 else None


def _primary_text(index: int, total: int) -> str:
    return strings.ACTION_SAVE_AND_NEXT if index < total - 1 else strings.ACTION_SAVE


class SupplierWizard(PickerSheet):
    skipped = Signal(str)  # nit

    def __init__(
        self,
        steps: Sequence[SupplierStep],
        products: Sequence[CodeItem],
        parent: QWidget | None = None,
    ) -> None:
        wanted = tuple(steps)
        if not wanted:
            raise ValueError("the wizard needs at least one supplier")
        super().__init__(
            strings.SUPPLIER_DIALOG_TITLE,
            products,
            subtitle=_progress_text(0, len(wanted)),
            primary_label=_primary_text(0, len(wanted)),
            cancel_label=strings.ACTION_CLOSE,
            parent=parent,
        )
        self._steps = wanted
        self._index = 0
        self._context_rows = max(
            min(len(step.lines), ContextList.MAX_VISIBLE_ROWS) for step in wanted
        )

        self.skip_button: QPushButton | None = None
        if len(wanted) > 1:
            self.skip_button = self.add_button(strings.ACTION_SKIP)
            self.skip_button.clicked.connect(self._skip)

        self.identity = SupplierIdentity()
        self.context = ContextList()
        self.body_layout.addWidget(self.identity)
        self.body_layout.addWidget(self.context)
        self._add_picker_to_body()
        footer = [self.cancel_button, self.primary_button]
        self._set_footer_tab_order(*([self.skip_button] if self.skip_button else []), *footer)
        self._show_step()

    # --- estado ---------------------------------------------------------------------
    def current_index(self) -> int:
        return self._index

    def step_count(self) -> int:
        return len(self._steps)

    def current_step(self) -> SupplierStep:
        return self._steps[self._index]

    def _show_step(self) -> None:
        step = self._steps[self._index]
        total = len(self._steps)
        progress = _progress_text(self._index, total)
        self.subtitle_label.setText(progress or "")
        self.subtitle_label.setVisible(progress is not None)
        self.set_primary_label(_primary_text(self._index, total))
        self.identity.set_supplier(step.nit, step.name)
        self.context.set_lines(step.lines, self._context_rows)
        self.picker.search.clear()
        self.set_selection(step.product_codes, step.default_product_code or None)
        self.set_error(None)
        self.set_busy(False)
        self.picker.focus_search()

    # --- respuesta del contenedor ----------------------------------------------------
    def mark_saved(self) -> None:
        """The container saved the current supplier: show the next one or finish."""
        self.set_busy(False)
        self._advance()

    def _advance(self) -> None:
        if self._index + 1 < len(self._steps):
            self._index += 1
            self._show_step()
        else:
            QDialog.accept(self)

    # --- acciones del usuario ----------------------------------------------------------
    def accept(self) -> None:
        """Primary button / Enter: validate, then ask the container to save."""
        if not self._begin_save():
            return
        step = self._steps[self._index]
        self.save_requested.emit(
            SupplierValues(
                step.nit,
                step.name,
                self.picker.selected_codes(),
                self.picker.default_code() or "",
            )
        )

    def _skip(self) -> None:
        self.skipped.emit(self._steps[self._index].nit)
        self._advance()
