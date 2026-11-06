"""Lotes exportados container: lists the company's batches through the task runner and
drives the void and release confirmations, with the selection kept across refreshes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.errors import BatchNotFoundError
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.desktop import show_in_file_manager
from contabilizador.ui.errors import CONTEXT_EXPORT, ErrorPresenter
from contabilizador.ui.pages.batches.rows import BatchRow, VoidPlan, batch_rows, void_plan
from contabilizador.ui.pages.batches.view import BatchesView
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import TaskRunner
from contabilizador.ui.widgets import ConfirmSheet, ToastHost

SPLITTER_NAME = "batches"
INVOICES_PAGE = "invoices"


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """The company's batches, tagged with the request that asked for them."""

    token: tuple[int, int]  # (empresa, generacion)
    rows: tuple[BatchRow, ...]


@dataclass(frozen=True, slots=True)
class _VoidCheck:
    """What the batch list says right before asking for confirmation."""

    plan: VoidPlan | None  # None: el lote ya estaba anulado


class BatchesContainer(QWidget):
    """Lotes exportados page container.

    Wiring: ``BatchesContainer(services, runner, presenter, toasts, parent)``, then
    ``set_company(id | None)`` whenever the company changes and ``refresh()`` after an export
    (or any change made elsewhere). Keyword-only extras: ``reveal_file`` (shows the batch
    workbook in Finder/Explorer; it always receives the resolved absolute path) and
    ``settings`` (remembers the list/detail split).

    Signals: ``changed`` after a void or a release (reload Facturas: the invoices are
    pending again), ``busy_changed(bool)`` while voiding or releasing (lock the company
    switcher), ``navigate_requested("invoices")`` from the empty state and from the toast
    action, and ``badge_changed`` (always 0). ``confirmation`` exposes the sheet currently
    open, if any.
    """

    changed = Signal()  # un lote se anulo o se liberaron facturas: Facturas debe releerse
    badge_changed = Signal(int)  # esta pagina no lleva insignia: siempre 0
    navigate_requested = Signal(str)  # "invoices" para volver a trabajar con lo liberado
    busy_changed = Signal(bool)  # anulando o liberando: bloquea el selector de empresa

    def __init__(
        self,
        services: Services,
        runner: TaskRunner,
        presenter: ErrorPresenter,
        toasts: ToastHost,
        parent: QWidget | None = None,
        *,
        reveal_file: Callable[[Path], None] | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._presenter = presenter
        self._toasts = toasts
        self._reveal_file = reveal_file or show_in_file_manager
        self._settings = settings
        self._company_id: int | None = None
        self._generation = 0
        self._loading = False  # hay una carga en curso para la empresa actual
        self._reload_requested = False  # llegaron peticiones de recarga mientras cargaba
        self._action_running = False
        self._rows: dict[int, BatchRow] = {}
        # Hoja abierta: visible para quien necesite inspeccionarla (p. ej. las pruebas)
        self.confirmation: ConfirmSheet | None = None

        self.view = BatchesView()
        self.view.set_has_company(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.void_requested.connect(self._request_void)
        self.view.release_requested.connect(self._request_release)
        self.view.show_file_requested.connect(self._show_file)
        self.view.empty_action_requested.connect(
            lambda: self.navigate_requested.emit(INVOICES_PAGE)
        )
        self._restore_split()

    # --- contrato de paginas -------------------------------------------------
    def set_company(self, company_id: int | None) -> None:
        self._company_id = company_id
        self._generation += 1  # lo que llegue de la empresa anterior se descarta
        self._loading = False
        self._reload_requested = False
        self._rows = {}
        self.view.reset()
        self.view.set_has_company(company_id is not None)
        self._reload()

    def refresh(self) -> None:
        """Reloads the batches; requests that arrive while a load runs become one more."""
        if self._loading:
            self._reload_requested = True
            return
        self._reload()

    # --- carga ---------------------------------------------------------------
    def _reload(self) -> None:
        company_id = self._company_id
        if company_id is None:
            return
        self._generation += 1
        token = (company_id, self._generation)
        services = self._services
        self._loading = True
        self._reload_requested = False

        def job(_ctx: object) -> _Snapshot:
            return _Snapshot(token, tuple(batch_rows(services.list_batches.execute(company_id))))

        def done(snapshot: _Snapshot) -> None:
            if snapshot.token != (self._company_id, self._generation):
                return  # llego tarde: la empresa o una recarga mas reciente ya la reemplazo
            self._rows = {row.batch_id: row for row in snapshot.rows}
            self.view.set_batches(snapshot.rows)
            self.badge_changed.emit(0)
            self._load_finished()

        def failed(error: BaseException) -> None:
            if token != (self._company_id, self._generation):
                return
            self._presenter.show(self, error)
            self._load_finished()

        self._runner.submit(job, on_done=done, on_error=failed, owner=self)

    def _load_finished(self) -> None:
        self._loading = False
        if self._reload_requested:
            self._reload()

    # --- anular --------------------------------------------------------------
    def _request_void(self, batch_id: int) -> None:
        company_id = self._company_id
        if company_id is None or self._action_running or self.confirmation is not None:
            return
        services = self._services

        def job(_ctx: object) -> _VoidCheck:
            # la confirmacion se calcula con la lista de ahora, no con la de la ultima carga
            batches = services.list_batches.execute(company_id)
            batch = next((b for b in batches if b.id == batch_id), None)
            if batch is None:
                raise BatchNotFoundError(batch_id)
            return _VoidCheck(None if batch.is_voided else void_plan(batch, batches))

        self._begin_action()
        self._runner.submit(job, on_done=self._ask_void, on_error=self._action_failed, owner=self)

    def _ask_void(self, check: _VoidCheck) -> None:
        self._end_action()
        plan = check.plan
        if plan is None:
            self._toasts.show_toast(strings.BATCH_ALREADY_VOIDED, kind="warning")
            self._reload()
            return
        if plan.returns_numbers:
            emphasis = strings.confirm_void_returns(plan.ranges, plan.numbers)
        elif plan.later_batch_id is not None:
            emphasis = strings.confirm_void_keeps(plan.ranges, plan.numbers, plan.later_batch_id)
        else:
            emphasis = ""
        self._open_confirmation(
            ConfirmSheet(
                strings.confirm_void_title(plan.batch_id),
                strings.confirm_void_documents(plan.freed_documents),
                confirm_label=strings.ACTION_VOID_BATCH,
                emphasis=emphasis,
                parent=self,
            ),
            lambda: self._void(plan),
        )

    def _void(self, plan: VoidPlan) -> None:
        services = self._services

        def done(voided: Batch) -> None:
            self._end_action()
            # lo que dice el resultado, no lo que prometio el plan
            self._announce(strings.batch_voided(plan.batch_id, returned=voided.numbers_reused))
            self.changed.emit()
            self._reload()

        self._begin_action()
        self._runner.submit(
            lambda _ctx: services.void_batch.execute(plan.batch_id),
            on_done=done,
            on_error=self._action_failed,
            owner=self,
        )

    # --- liberar -------------------------------------------------------------
    def _request_release(self, batch_id: int, cufes: Sequence[str]) -> None:
        if self._company_id is None or self._action_running or self.confirmation is not None:
            return
        chosen = list(cufes)
        count = len(chosen)
        self._open_confirmation(
            ConfirmSheet(
                strings.confirm_release_title(count),
                strings.confirm_release_message(count),
                confirm_label=strings.ACTION_RELEASE_INVOICES,
                notes=[strings.CONFIRM_RELEASE_NOTE],
                parent=self,
            ),
            lambda: self._release(batch_id, chosen),
        )

    def _release(self, batch_id: int, cufes: list[str]) -> None:
        services = self._services

        def done(_result: object) -> None:
            self._end_action()
            self._announce(strings.documents_released(len(cufes)))
            self.changed.emit()
            self._reload()

        self._begin_action()
        self._runner.submit(
            lambda _ctx: services.release_documents.execute(batch_id, cufes),
            on_done=done,
            on_error=self._action_failed,
            owner=self,
        )

    # --- mostrar archivo -----------------------------------------------------
    def _show_file(self, batch_id: int) -> None:
        row = self._rows.get(batch_id)
        if row is None:
            return
        path = row.file_path.expanduser().resolve()
        if not path.is_file():
            self._toasts.show_toast(strings.BATCH_FILE_MISSING, kind="warning")
            return
        try:
            self._reveal_file(path)
        except OSError as error:
            self._presenter.show(self, error, context=CONTEXT_EXPORT)

    # --- confirmaciones y estado ---------------------------------------------
    def _open_confirmation(self, sheet: ConfirmSheet, on_accept: Callable[[], None]) -> None:
        sheet.accepted.connect(on_accept)
        sheet.finished.connect(lambda _result: self._confirmation_closed(sheet))
        self.confirmation = sheet
        sheet.open()

    def _confirmation_closed(self, sheet: ConfirmSheet) -> None:
        if self.confirmation is sheet:
            self.confirmation = None
        sheet.deleteLater()

    def _announce(self, message: str) -> None:
        """Success toast whose action takes the person to Facturas to keep working."""
        self._toasts.show_toast(
            message,
            kind="success",
            action_label=strings.BATCH_ACTION_SEE_INVOICES,
            on_action=lambda: self.navigate_requested.emit(INVOICES_PAGE),
        )

    def _begin_action(self) -> None:
        self._action_running = True
        self.view.set_busy(True)
        self.busy_changed.emit(True)

    def _end_action(self) -> None:
        if not self._action_running:
            return
        self._action_running = False
        self.view.set_busy(False)
        self.busy_changed.emit(False)

    def _action_failed(self, error: BaseException) -> None:
        self._end_action()
        self._presenter.show(self, error)
        self._reload()  # casi siempre es porque la lista estaba desactualizada

    # --- distribucion persistida ---------------------------------------------
    def _restore_split(self) -> None:
        settings = self._settings
        if settings is None:
            return
        state = settings.splitter_state(SPLITTER_NAME)
        if state is not None:
            self.view.restore_split_state(state)
        self.view.splitter.splitterMoved.connect(
            lambda *_args: settings.set_splitter_state(
                SPLITTER_NAME, self.view.splitter.saveState()
            )
        )
