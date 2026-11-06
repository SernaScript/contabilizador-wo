"""New company flow: opens the dialog and creates the company through the task runner.

Used for the switcher's "Nueva empresa" and the first-steps page. The main window listens
to ``company_created`` and selects the new company.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from contabilizador.companies.application.errors import DuplicateCompanyNameError
from contabilizador.companies.domain.company import Company
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.pages.company.form import CompanyValues
from contabilizador.ui.pages.company.new_company_dialog import NewCompanyDialog
from contabilizador.ui.tasks import TaskContext, TaskRunner
from contabilizador.ui.widgets.toast import ToastHost


class NewCompanyFlow(QObject):
    company_created = Signal(int)

    def __init__(
        self,
        services: Services,
        runner: TaskRunner,
        presenter: ErrorPresenter,
        toasts: ToastHost,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._presenter = presenter
        self._toasts = toasts
        self._window = parent
        self._dialog: NewCompanyDialog | None = None

    @property
    def dialog(self) -> NewCompanyDialog | None:
        return self._dialog

    def open(self) -> NewCompanyDialog:
        """Shows the dialog (non-blocking); a second call brings the open one forward."""
        if self._dialog is not None:
            self._dialog.raise_()
            self._dialog.activateWindow()
            return self._dialog
        dialog = NewCompanyDialog(self._window)
        dialog.submitted.connect(self._create)
        dialog.finished.connect(self._on_finished)
        self._dialog = dialog
        dialog.open()
        return dialog

    # --- creacion -----------------------------------------------------------
    def _create(self, values: CompanyValues) -> None:
        dialog = self._dialog
        if dialog is None:
            return
        dialog.set_busy(True)
        services = self._services

        def job(_context: TaskContext) -> Company:
            return services.create_company.execute(
                values.name,
                values.internal_third_party_id,
                values.warehouse,
                values.unit,
                values.payment_form,
            )

        # El flujo (no el dialogo) recibe el resultado: una empresa creada se anuncia aunque
        # el dialogo ya no exista
        self._runner.submit(job, on_done=self._on_created, on_error=self._on_failed, owner=self)

    def _on_created(self, company: Company) -> None:
        if self._dialog is not None:
            self._dialog.set_busy(False)
            self._dialog.accept()
        self._toasts.show_toast(strings.company_created(company.name), kind="success")
        if company.id is not None:
            self.company_created.emit(company.id)

    def _on_failed(self, error: BaseException) -> None:
        dialog = self._dialog
        if dialog is None:
            self._presenter.show(self._window, error)  # el dialogo ya no esta: se explica igual
            return
        dialog.set_busy(False)
        if isinstance(error, DuplicateCompanyNameError):
            dialog.show_name_error(strings.COMPANY_NAME_DUPLICATED)
        else:
            self._presenter.show(dialog, error)

    def _on_finished(self, _result: int) -> None:
        dialog, self._dialog = self._dialog, None
        if dialog is not None:
            dialog.deleteLater()
