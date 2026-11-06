"""New company dialog: the company form inside a Sheet.

Presentational. Primary validates the name inline and emits ``submitted``; the owner
(``NewCompanyFlow``) creates the company and calls ``accept`` or ``show_name_error``.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QWidget

from contabilizador.shared import strings
from contabilizador.ui.pages.company.form import CompanyForm, CompanyValues
from contabilizador.ui.widgets.sheet import Sheet


class NewCompanyDialog(Sheet):
    submitted = Signal(object)  # CompanyValues

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            strings.ACTION_NEW_COMPANY,
            subtitle=strings.NEW_COMPANY_PURPOSE,
            primary_label=strings.NEW_COMPANY_SUBMIT,
            parent=parent,
        )
        self.form = CompanyForm()
        self.set_body(self.form)
        # El dialogo no se cierra al pulsar: primero hay que crear la empresa
        self.primary_button.clicked.disconnect(self.accept)
        self.primary_button.clicked.connect(self._submit)

    def values(self) -> CompanyValues:
        return self.form.values()

    def show_name_error(self, text: str) -> None:
        self.form.set_name_error(text)
        self.form.focus_name()

    def _submit(self) -> None:
        if self.form.validate():
            self.submitted.emit(self.form.values())

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        # Se escribe de inmediato: el foco va al nombre y no al boton principal
        self.form.focus_name()
