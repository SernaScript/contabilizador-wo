"""Container of the Proveedores page: calls the use cases through the task runner and
drives the wizard and the edit sheet.

Contract with the main window (pages never import each other):

- ``set_company(id | None)`` and ``refresh()`` load the list;
- ``configure([(nit, name), ...])`` opens the wizard (the Facturas banner uses it);
- ``changed`` fires when a supplier was saved or deleted (readiness of the invoices moved);
- ``badge_changed(n)`` is the number of unconfigured suppliers (sidebar badge);
- ``navigate_requested(key)`` asks the window to open another page.

Results of a task are dropped when the company changed meanwhile: every request carries a
``(company_id, generation)`` token and only the current one is applied.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from contabilizador.catalog.domain.catalog import Product
from contabilizador.invoices.application.list_pending_documents import PendingDocuments
from contabilizador.shared import strings
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.pages.suppliers.confirm import ask_confirmation
from contabilizador.ui.pages.suppliers.rows import (
    SupplierRow,
    SupplierStep,
    SupplierValues,
    build_context,
    build_rows,
)
from contabilizador.ui.pages.suppliers.sheet import SupplierSheet
from contabilizador.ui.pages.suppliers.view import SuppliersView
from contabilizador.ui.pages.suppliers.wizard import SupplierWizard
from contabilizador.ui.tasks import TaskContext, TaskRunner
from contabilizador.ui.widgets import CodeItem, ToastHost

Token = tuple[int | None, int]
ConfirmFn = Callable[[QWidget | None, str, str, str], bool]


@dataclass(frozen=True, slots=True)
class SuppliersData:
    """Everything the page needs, read in one task so the three reads agree."""

    configs: tuple[SupplierConfig, ...]
    pending: PendingDocuments
    products: tuple[Product, ...]

    def catalog_items(self) -> list[CodeItem]:
        return [CodeItem(product.code, product.name) for product in self.products]

    def product_names(self) -> dict[str, str]:
        return {product.code: product.name for product in self.products}

    def rows(self) -> list[SupplierRow]:
        return build_rows(self.configs, self.pending, {product.code for product in self.products})


def _load_job(services: Services, company_id: int) -> Callable[[TaskContext], SuppliersData]:
    def job(_context: TaskContext) -> SuppliersData:
        return SuppliersData(
            tuple(services.list_supplier_configs.execute(company_id)),
            services.list_pending.execute(company_id),
            tuple(services.list_products.execute(company_id)),
        )

    return job


class SuppliersContainer(QWidget):
    changed = Signal()
    badge_changed = Signal(int)
    navigate_requested = Signal(str)

    def __init__(
        self,
        services: Services,
        runner: TaskRunner,
        presenter: ErrorPresenter,
        toasts: ToastHost,
        *,
        confirm: ConfirmFn = ask_confirmation,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._presenter = presenter
        self._toasts = toasts
        self._confirm = confirm
        self._company_id: int | None = None
        self._generation = 0
        self._inflight: Token | None = None
        self._reload_requested = False
        self._data: SuppliersData | None = None
        self._rows: dict[str, SupplierRow] = {}
        self._wizard: SupplierWizard | None = None
        self._opening_wizard = False
        self._configured_in_wizard = 0
        self._sheet: SupplierSheet | None = None

        self.view = SuppliersView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.edit_requested.connect(self._edit)
        self.view.delete_requested.connect(self._delete)
        self.view.configure_all_requested.connect(self.configure_unconfigured)
        self.view.navigate_requested.connect(self.navigate_requested)
        self.view.retry_requested.connect(self._retry)

    # --- estado visible para pruebas e integracion -----------------------------------------
    @property
    def wizard(self) -> SupplierWizard | None:
        return self._wizard

    @property
    def sheet(self) -> SupplierSheet | None:
        return self._sheet

    def focus_search(self) -> None:
        self.view.focus_search()

    # --- empresa y datos ---------------------------------------------------------------------
    def _token(self) -> Token:
        return (self._company_id, self._generation)

    def set_company(self, company_id: int | None) -> None:
        self._close_dialogs()
        self._generation += 1
        self._company_id = company_id
        self._data = None
        self._rows = {}
        self._inflight = None
        self._reload_requested = False
        self._opening_wizard = False
        if company_id is None:
            self.view.show_no_company()
            self.badge_changed.emit(0)
            return
        self.view.show_loading()
        self.refresh()

    def refresh(self) -> None:
        """Reloads the list. Calls made while a load is running become one more load."""
        company_id = self._company_id
        if company_id is None:
            return
        token = self._token()
        if self._inflight == token:
            self._reload_requested = True
            return
        self._inflight = token
        self._reload_requested = False
        self._runner.submit(
            _load_job(self._services, company_id),
            on_done=partial(self._loaded, token),
            on_error=partial(self._load_failed, token),
            owner=self,
        )

    def _retry(self) -> None:
        self.view.show_loading()
        self.refresh()

    def _loaded(self, token: Token, data: SuppliersData) -> None:
        if token != self._token():
            return  # llego tarde: ya se cambio de empresa
        self._inflight = None
        self._data = data
        rows = data.rows()
        self._rows = {row.nit: row for row in rows}
        self.view.set_suppliers(rows, data.product_names())
        self.badge_changed.emit(sum(1 for row in rows if not row.configured))
        if self._reload_requested:
            self.refresh()

    def _load_failed(self, token: Token, error: BaseException) -> None:
        if token != self._token():
            return
        self._inflight = None
        self._reload_requested = False
        if self._data is None:
            self.view.show_failure()
        self._presenter.show(self, error)

    # --- asistente ---------------------------------------------------------------------------
    def configure_unconfigured(self) -> None:
        """Wizard over every supplier still waiting for its configuration."""
        waiting = [(row.nit, row.name) for row in self._rows.values() if not row.configured]
        self.configure(waiting)

    def configure(self, suppliers: Sequence[tuple[str, str]]) -> None:
        """Runs the wizard over ``(nit, name)`` pairs, in the given order.

        The data is read again first, so the context and any previous configuration are
        current even if the page was not visited since the last import.
        """
        company_id = self._company_id
        wanted: dict[str, str] = {}
        for nit, name in suppliers:
            wanted.setdefault(nit, name)
        if company_id is None or not wanted or self._wizard is not None or self._opening_wizard:
            return
        self._opening_wizard = True
        token = self._token()
        self._runner.submit(
            _load_job(self._services, company_id),
            on_done=partial(self._open_wizard, token, wanted),
            on_error=partial(self._wizard_not_opened, token),
            owner=self,
        )

    def _wizard_not_opened(self, token: Token, error: BaseException) -> None:
        if token != self._token():
            return
        self._opening_wizard = False
        self._presenter.show(self, error)

    def _open_wizard(self, token: Token, wanted: dict[str, str], data: SuppliersData) -> None:
        if token != self._token():
            return  # la empresa cambio mientras se leian los datos
        self._opening_wizard = False
        steps = tuple(_step(nit, name, data) for nit, name in wanted.items())
        wizard = SupplierWizard(steps, data.catalog_items(), parent=self)
        self._wizard = wizard
        self._configured_in_wizard = 0
        wizard.save_requested.connect(partial(self._save_from_wizard, wizard, token))
        wizard.catalog_requested.connect(self._go_to_catalog)
        wizard.finished.connect(partial(self._wizard_finished, wizard))
        wizard.open()

    def _save_from_wizard(
        self, wizard: SupplierWizard, token: Token, values: SupplierValues
    ) -> None:
        def saved(_config: SupplierConfig) -> None:
            if token != self._token() or wizard is not self._wizard:
                return
            self._configured_in_wizard += 1
            wizard.mark_saved()

        def failed(error: BaseException) -> None:
            if token != self._token() or wizard is not self._wizard:
                return
            wizard.mark_failed(strings.SUPPLIER_SAVE_FAILED)
            self._presenter.show(wizard, error)

        self._runner.submit(self._save_job(values), on_done=saved, on_error=failed, owner=self)

    def _wizard_finished(self, wizard: SupplierWizard, _result: int) -> None:
        if wizard is not self._wizard:
            return
        self._wizard = None
        wizard.deleteLater()
        count, self._configured_in_wizard = self._configured_in_wizard, 0
        if count:
            self._toasts.show_toast(strings.suppliers_configured(count), kind="success")
            self.refresh()
            self.changed.emit()

    # --- hoja de edicion ----------------------------------------------------------------------
    def _edit(self, nit: str) -> None:
        row = self._rows.get(nit)
        busy = self._wizard is not None or self._sheet is not None or self._opening_wizard
        if row is None or busy or self._data is None:
            return
        if not row.configured:
            self.configure([(row.nit, row.name)])  # con el contexto de sus lineas pendientes
            return
        token = self._token()
        sheet = SupplierSheet(row, self._data.catalog_items(), parent=self)
        self._sheet = sheet
        sheet.save_requested.connect(partial(self._save_from_sheet, sheet, token))
        sheet.delete_requested.connect(partial(self._delete, sheet=sheet))
        sheet.catalog_requested.connect(self._go_to_catalog)
        sheet.finished.connect(partial(self._sheet_finished, sheet))
        sheet.open()

    def _save_from_sheet(self, sheet: SupplierSheet, token: Token, values: SupplierValues) -> None:
        def saved(_config: SupplierConfig) -> None:
            if token != self._token() or sheet is not self._sheet:
                return
            sheet.finish()
            self._announce(strings.SUPPLIER_SAVED)

        def failed(error: BaseException) -> None:
            if token != self._token() or sheet is not self._sheet:
                return
            sheet.mark_failed(strings.SUPPLIER_SAVE_FAILED)
            self._presenter.show(sheet, error)

        self._runner.submit(self._save_job(values), on_done=saved, on_error=failed, owner=self)

    def _sheet_finished(self, sheet: SupplierSheet, _result: int) -> None:
        if sheet is not self._sheet:
            return
        self._sheet = None
        sheet.deleteLater()

    # --- eliminar -----------------------------------------------------------------------------
    def _delete(self, nit: str, *, sheet: SupplierSheet | None = None) -> None:
        company_id = self._company_id
        row = self._rows.get(nit)
        if company_id is None or row is None or not row.configured:
            return
        asked = self._confirm(
            sheet or self,
            strings.confirm_delete(row.name),
            strings.SUPPLIER_DELETE_DETAIL,
            strings.ACTION_DELETE,
        )
        if not asked:
            return
        token = self._token()
        if sheet is not None:
            sheet.set_busy(True)

        def deleted(_result: object) -> None:
            if token != self._token():
                return
            if sheet is not None and sheet is self._sheet:
                sheet.finish()
            self._announce(strings.SUPPLIER_DELETED)

        def failed(error: BaseException) -> None:
            if token != self._token():
                return
            if sheet is not None and sheet is self._sheet:
                sheet.set_busy(False)
            self._presenter.show(sheet or self, error)

        services = self._services

        def job(_context: TaskContext) -> None:
            services.delete_supplier_config.execute(company_id, nit)

        self._runner.submit(job, on_done=deleted, on_error=failed, owner=self)

    # --- utilidades ---------------------------------------------------------------------------
    def _save_job(self, values: SupplierValues) -> Callable[[TaskContext], SupplierConfig]:
        services = self._services
        company_id = self._company_id
        assert company_id is not None

        def job(_context: TaskContext) -> SupplierConfig:
            return services.configure_supplier.execute(
                company_id,
                values.nit,
                values.name,
                values.product_codes,
                values.default_product_code,
            )

        return job

    def _announce(self, message: str) -> None:
        """Success toast, then reload the list and tell the window the data moved."""
        self._toasts.show_toast(message, kind="success")
        self.refresh()
        self.changed.emit()

    def _go_to_catalog(self) -> None:
        self._close_dialogs()
        self.navigate_requested.emit("catalogs")

    def _close_dialogs(self) -> None:
        """Closes the wizard and the sheet without announcing anything (company change,
        navigation); ``done`` skips the guard that keeps a saving dialog open."""
        self._configured_in_wizard = 0
        for dialog in (self._wizard, self._sheet):
            if dialog is not None:
                dialog.done(QDialog.DialogCode.Rejected)


def _step(nit: str, name: str, data: SuppliersData) -> SupplierStep:
    config = next((item for item in data.configs if item.nit == nit), None)
    return SupplierStep(
        nit,
        name,
        build_context(data.pending, nit),
        config.product_codes if config is not None else (),
        config.default_product_code if config is not None else "",
    )
