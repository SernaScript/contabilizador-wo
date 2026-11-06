"""Primeros pasos container: step states computed from the services of the selected company.

The page asks the main window for things through signals and never imports another page:
``create_company_requested`` (open the new company flow), ``navigate_requested`` (page key
from ``actions.PAGE_ORDER``) and ``import_requested`` (start the invoice import).
``changed`` and ``badge_changed`` complete the page contract; this page only reads, so it
never emits them.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.pages.onboarding.view import (
    FIRST_RUN,
    STEP_CATALOG,
    STEP_COMPANY,
    STEP_IMPORT,
    OnboardingView,
    StepStatus,
)
from contabilizador.ui.tasks import TaskContext, TaskRunner
from contabilizador.ui.widgets.toast import ToastHost

PAGE_CATALOGS = "catalogs"
PAGE_INVOICES = "invoices"


@dataclass(frozen=True, slots=True)
class _Progress:
    has_products: bool
    has_cost_centers: bool
    has_invoices: bool


def _read_progress(services: Services, company_id: int) -> _Progress:
    products = services.list_products.execute(company_id)
    cost_centers = services.list_cost_centers.execute(company_id)
    # Importada = existe en cualquier estado, tambien si ya se exporto
    invoices = services.invoices.list_by_status(company_id, tuple(InvoiceStatus))
    return _Progress(bool(products), bool(cost_centers), bool(invoices))


def _catalog_detail(progress: _Progress) -> str:
    if progress.has_products and not progress.has_cost_centers:
        return strings.ONBOARDING_MISSING_COST_CENTERS
    if progress.has_cost_centers and not progress.has_products:
        return strings.ONBOARDING_MISSING_PRODUCTS
    return ""


def _statuses(has_company: bool, progress: _Progress | None) -> tuple[StepStatus, ...]:
    if not has_company:
        return FIRST_RUN
    if progress is None:
        # Con empresa pero sin saber aun lo demas: nada bloqueado, nada hecho
        return (StepStatus(done=True), StepStatus(), StepStatus())
    catalog_done = progress.has_products and progress.has_cost_centers
    return (
        StepStatus(done=True),
        StepStatus(done=catalog_done, detail="" if catalog_done else _catalog_detail(progress)),
        StepStatus(done=progress.has_invoices),
    )


class OnboardingContainer(QWidget):
    changed = Signal()  # contrato de paginas: esta pagina solo lee, nunca cambia datos
    badge_changed = Signal(int)  # contrato de paginas: sin insignia en la barra lateral
    navigate_requested = Signal(str)
    create_company_requested = Signal()
    import_requested = Signal()

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
        self._company_id: int | None = None
        # Una respuesta que llega despues de cambiar de empresa se descarta
        self._generation = 0
        self.view = OnboardingView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.step_triggered.connect(self._on_step_triggered)
        self.view.finish_requested.connect(lambda: self.navigate_requested.emit(PAGE_INVOICES))

    # --- contrato de pagina -------------------------------------------------
    def set_company(self, company_id: int | None) -> None:
        self._company_id = company_id
        self._generation += 1
        self.view.set_steps(_statuses(company_id is not None, None))
        if company_id is not None:
            self._load(company_id)

    def refresh(self) -> None:
        if self._company_id is None:
            return
        self._generation += 1
        self._load(self._company_id)

    def explain_needs_company(self) -> None:
        """For any action that needs a company: say why nothing happened instead of nothing."""
        self._toasts.show_toast(strings.ONBOARDING_NEEDS_COMPANY, kind="warning")

    # --- carga --------------------------------------------------------------
    def _load(self, company_id: int) -> None:
        token = self._generation
        services = self._services

        def job(_context: TaskContext) -> _Progress:
            return _read_progress(services, company_id)

        self._runner.submit(
            job,
            on_done=lambda progress: self._on_loaded(token, progress),
            on_error=lambda error: self._on_load_failed(token, error),
            owner=self,
        )

    def _on_loaded(self, token: int, progress: _Progress) -> None:
        if token == self._generation:
            self.view.set_steps(_statuses(self._company_id is not None, progress))

    def _on_load_failed(self, token: int, error: BaseException) -> None:
        if token == self._generation:
            self._presenter.show(self, error)

    # --- acciones -----------------------------------------------------------
    def _on_step_triggered(self, key: str) -> None:
        if key == STEP_COMPANY:
            self.create_company_requested.emit()
        elif self._company_id is None:
            # El boton deshabilitado ya lo evita; esto cubre cualquier otra via
            self.explain_needs_company()
        elif key == STEP_CATALOG:
            self.navigate_requested.emit(PAGE_CATALOGS)
        elif key == STEP_IMPORT:
            self.import_requested.emit()
