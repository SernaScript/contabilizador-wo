"""Empresa page container: loads and saves the selected company through the task runner.

Page contract (see the redesign plan): ``(services, runner, presenter, toasts)``,
``set_company``, ``refresh`` and the signals ``changed`` / ``badge_changed`` /
``navigate_requested``. This page has no badge and never navigates, so it only emits
``changed`` (after a save, so the company switcher reloads the names) and
``create_company_requested`` (the empty state's action).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from contabilizador.companies.application.errors import DuplicateCompanyNameError
from contabilizador.companies.domain.company import Company
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.pages.company.form import CompanyValues
from contabilizador.ui.pages.company.view import CompanyView
from contabilizador.ui.tasks import TaskContext, TaskRunner
from contabilizador.ui.widgets.toast import ToastHost


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """What the page shows for one company, read in a single background job."""

    values: CompanyValues
    last_fc: int
    last_nc: int


def _last_used(services: Services, company_id: int, document_type: DocumentType) -> int:
    # suggest() devuelve ultimo usado + 1 (1 sin historial), asi que 0 = ninguno todavia
    return services.plan_consecutives.suggest(company_id, document_type) - 1


def _values_of(company: Company) -> CompanyValues:
    return CompanyValues(
        company.name,
        company.internal_third_party_id,
        company.warehouse,
        company.unit,
        company.payment_form,
    )


def _read_snapshot(services: Services, company_id: int) -> _Snapshot | None:
    company = next(
        (item for item in services.list_companies.execute() if item.id == company_id), None
    )
    if company is None:
        return None
    return _Snapshot(
        _values_of(company),
        _last_used(services, company_id, DocumentType.FC),
        _last_used(services, company_id, DocumentType.NC),
    )


class CompanyContainer(QWidget):
    changed = Signal()
    badge_changed = Signal(int)
    navigate_requested = Signal(str)
    create_company_requested = Signal()

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
        # Cada carga lleva la generacion con que nacio; una respuesta tardia se descarta
        self._generation = 0
        # Empresas con un guardado en curso: evita duplicados sin bloquear a otra empresa
        self._saving: set[int] = set()
        self.view = CompanyView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.save_requested.connect(self._on_save_requested)
        self.view.create_company_requested.connect(self.create_company_requested)

    # --- contrato de pagina -------------------------------------------------
    def set_company(self, company_id: int | None) -> None:
        switched = company_id != self._company_id
        self._company_id = company_id
        self._generation += 1
        if company_id is None:
            self.view.show_empty()
            return
        if switched:
            # Nunca se muestra (ni se guarda) el formulario de la empresa anterior
            self.view.show_loading()
        self._load(company_id, keep_edits=not switched)

    def refresh(self) -> None:
        if self._company_id is None:
            return
        self._generation += 1
        self._load(self._company_id, keep_edits=True)

    # --- carga --------------------------------------------------------------
    def _load(self, company_id: int, *, keep_edits: bool) -> None:
        token = self._generation
        services = self._services

        def job(_context: TaskContext) -> _Snapshot | None:
            return _read_snapshot(services, company_id)

        self._runner.submit(
            job,
            on_done=lambda snapshot: self._on_loaded(token, snapshot, keep_edits),
            on_error=lambda error: self._on_load_failed(token, error),
            owner=self,
        )

    def _on_loaded(self, token: int, snapshot: _Snapshot | None, keep_edits: bool) -> None:
        if token == self._generation:
            self._apply(snapshot, keep_edits=keep_edits)

    def _on_load_failed(self, token: int, error: BaseException) -> None:
        if token == self._generation:
            self._presenter.show(self, error)

    def _apply(self, snapshot: _Snapshot | None, *, keep_edits: bool) -> None:
        self.view.set_busy(False)
        if snapshot is None:
            self.view.show_empty()
        elif keep_edits and self.view.is_dirty():
            # Un refresco no pisa lo que el usuario esta escribiendo: solo actualiza los numeros
            self.view.set_consecutives(snapshot.last_fc, snapshot.last_nc)
        else:
            self.view.show_company(snapshot.values, snapshot.last_fc, snapshot.last_nc)

    def _apply_saved(self, snapshot: _Snapshot | None) -> None:
        self.view.set_busy(False)
        if snapshot is None:
            self.view.show_empty()
        else:
            self.view.show_saved(snapshot.values, snapshot.last_fc, snapshot.last_nc)

    # --- guardado -----------------------------------------------------------
    def _on_save_requested(self, values: CompanyValues) -> None:
        company_id = self._company_id
        if company_id is None or company_id in self._saving:
            return
        self._saving.add(company_id)
        self.view.set_busy(True)
        services = self._services

        def job(_context: TaskContext) -> _Snapshot | None:
            services.update_company.execute(
                company_id,
                name=values.name,
                internal_third_party_id=values.internal_third_party_id,
                warehouse=values.warehouse,
                unit=values.unit,
                payment_form=values.payment_form,
            )
            return _read_snapshot(services, company_id)

        self._runner.submit(
            job,
            on_done=lambda snapshot: self._on_saved(company_id, snapshot),
            on_error=lambda error: self._on_save_failed(company_id, error),
            owner=self,
        )

    def _on_saved(self, company_id: int, snapshot: _Snapshot | None) -> None:
        self._saving.discard(company_id)
        # El guardado ya ocurrio aunque el usuario haya cambiado de empresa mientras tanto
        self._toasts.show_toast(strings.COMPANY_SAVED, kind="success")
        self.changed.emit()
        # Un refresco intermedio no cambia de quien es el formulario: solo importa la empresa
        if company_id == self._company_id:
            self._apply_saved(snapshot)

    def _on_save_failed(self, company_id: int, error: BaseException) -> None:
        self._saving.discard(company_id)
        current = company_id == self._company_id
        if current:
            self.view.set_busy(False)
        if current and isinstance(error, DuplicateCompanyNameError):
            self.view.show_name_error(strings.COMPANY_NAME_DUPLICATED)
            return
        self._presenter.show(self, error)
