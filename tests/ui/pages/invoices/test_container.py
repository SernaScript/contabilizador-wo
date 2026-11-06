"""Facturas container on real services (temp SQLite) with the synchronous task runner:
refresh, readiness from the preview, edits through the use cases, import with progress,
toasts, export request, persistence of the layout."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from contabilizador.exports.domain.readiness import Readiness
from contabilizador.invoices.application.assign_line_mapping import LineAssignment
from contabilizador.invoices.application.errors import ImportCancelledError, InvoiceNotFoundError
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.suggestion import MappingSource
from contabilizador.shared import strings
from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.errors import CONTEXT_IMPORT, ErrorPresentation, ErrorPresenter
from contabilizador.ui.pages.invoices import InvoicesPage
from contabilizador.ui.pages.invoices.container import InvoicesPage as ContainerClass
from contabilizador.ui.pages.invoices.import_report import ImportReportDialog
from contabilizador.ui.pages.invoices.model import Column
from contabilizador.ui.pages.invoices.rows import FIELD_COST_CENTER, FIELD_PRODUCT
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import SyncTaskRunner, TaskHandle
from contabilizador.ui.widgets.code_combo import CodeCombo
from contabilizador.ui.widgets.toast import ToastHost

SUPPLIERS = (
    ("900123456", "COMERCIALIZADORA EJEMPLO S.A.S."),
    ("1017000111", "PEDRO PRUEBA RESTREPO"),
    ("800987654", "SERVICIOS TECNICOS DEMO LTDA"),
)


class RecordingPresenter(ErrorPresenter):
    """Never opens a modal box: records what would be shown."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[tuple[BaseException, str | None, ErrorPresentation]] = []

    def show(self, parent, error, *, context=None) -> ErrorPresentation:
        presentation = self.present(error, context=context)
        self.shown.append((error, context, presentation))
        return presentation


@dataclass
class Env:
    services: Services
    company_id: int
    runner: SyncTaskRunner
    presenter: RecordingPresenter
    window: QWidget
    toasts: ToastHost
    settings: AppSettings
    page: InvoicesPage
    settings_path: Path

    def new_page(self) -> InvoicesPage:
        page = InvoicesPage(
            self.services,
            self.runner,
            self.presenter,
            self.toasts,
            settings=AppSettings.in_file(self.settings_path),
            parent=self.window,
        )
        page.set_company(self.company_id)
        return page

    def last_toast(self):
        toasts = self.toasts.toasts()
        assert toasts, "no toast shown"
        return toasts[-1]


@pytest.fixture
def env(qtbot, tmp_path: Path) -> Iterator[Env]:
    services = build_services(tmp_path / "db.sqlite")
    company = services.create_company.execute("WEARE DEV S.A.S", "1017")
    assert company.id is not None
    services.save_product.execute(company.id, "P-SERV", "Servicios")
    services.save_product.execute(company.id, "P-PAPEL", "Papeleria")
    services.save_cost_center.execute(company.id, "CC-ADM", "Administracion")
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(1280, 820)
    toasts = ToastHost(window)
    runner = SyncTaskRunner()
    presenter = RecordingPresenter()
    settings_path = tmp_path / "settings.ini"
    settings = AppSettings.in_file(settings_path)
    page = InvoicesPage(services, runner, presenter, toasts, settings=settings, parent=window)
    layout = QVBoxLayout(window)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(page)
    window.show()
    yield Env(
        services, company.id, runner, presenter, window, toasts, settings, page, settings_path
    )
    services.close()


def _import_fixtures(env: Env, xml_fixtures_dir: Path) -> None:
    env.page.set_company(env.company_id)
    env.page.import_paths([xml_fixtures_dir])


def _configure_suppliers(env: Env) -> None:
    for nit, name in SUPPLIERS:
        env.services.configure_supplier.execute(
            env.company_id, nit, name, ["P-SERV", "P-PAPEL"], "P-SERV"
        )


def test_page_is_exported_and_without_company_shows_the_empty_state(env: Env, qtbot) -> None:
    assert InvoicesPage is ContainerClass
    badges: list[int] = []
    env.page.badge_changed.connect(badges.append)

    env.page.set_company(None)

    assert env.page.company_id is None
    assert env.page.view.empty_state.isVisible()
    assert badges == [0]
    env.page.import_paths([Path("whatever.xml")])
    assert env.toasts.toasts() == []
    assert env.page.rows() == ()


def test_import_reports_progress_refreshes_and_toasts_with_detail(
    env: Env, qtbot, xml_fixtures_dir: Path
) -> None:
    progress: list[tuple[int, int]] = []
    env.page.view.set_progress = lambda done, total: progress.append((done, total))  # type: ignore[method-assign]
    busy: list[bool] = []
    env.page.busy_changed.connect(busy.append)
    changed: list[int] = []
    env.page.changed.connect(lambda: changed.append(1))
    badges: list[int] = []
    env.page.badge_changed.connect(badges.append)

    _import_fixtures(env, xml_fixtures_dir)

    rows = env.page.rows()
    assert len(rows) == 6
    assert progress[0][0] == 0 and progress[-1][0] == progress[-1][1] > 0
    assert busy == [True, False]
    assert changed == [1]
    assert not env.page.view.busy_overlay.is_running
    assert env.page.view.import_button.isEnabled()
    # sin proveedores configurados todas quedan bloqueadas: el badge cuenta las 6
    assert badges[-1] == 6
    assert all(row.readiness is Readiness.BLOCKED for row in rows)
    assert env.page.view.banner.isVisible()
    # tres proveedores sin configurar retienen las seis facturas
    assert env.page.view.banner.text() == strings.unconfigured_suppliers_banner(3, 6)
    assert env.page.view.banner.action_button.text() == strings.configure_pending_action(3)
    assert env.page.view.readiness.counts() == {"blocked": 6}
    assert env.settings.last_import_folder == xml_fixtures_dir

    toast = env.last_toast()
    assert toast.kind == "success"
    assert toast.message() == strings.import_result_sentence(6, 2, 1, 0)
    assert toast.action_button.text() == strings.ACTION_SHOW_DETAILS
    toast.action_button.click()
    dialog = env.page.report_dialog()
    assert isinstance(dialog, ImportReportDialog)
    assert dialog.isVisible()
    assert strings.IMPORT_REPORT_DUPLICATES in dialog.sections
    dialog.close()


def test_import_cancelled_and_failed_paths(env: Env, monkeypatch, xml_fixtures_dir: Path) -> None:
    env.page.set_company(env.company_id)

    def cancelled(*args, **kwargs):
        raise ImportCancelledError()

    monkeypatch.setattr(env.services.import_invoices, "execute", cancelled)
    env.page.import_paths([xml_fixtures_dir / "invoice_plain.xml"])
    assert env.last_toast().kind == "info"
    assert env.last_toast().message() == strings.IMPORT_CANCELLED
    assert env.presenter.shown == []
    assert not env.page.view.busy_overlay.is_running

    def broken(*args, **kwargs):
        raise OSError("disk")

    monkeypatch.setattr(env.services.import_invoices, "execute", broken)
    env.page.import_paths([xml_fixtures_dir / "invoice_plain.xml"])
    assert len(env.presenter.shown) == 1
    error, context, presentation = env.presenter.shown[0]
    assert isinstance(error, OSError)
    assert context == CONTEXT_IMPORT
    assert presentation.title == strings.ERROR_FILE_READ_TITLE
    assert env.page.view.import_button.isEnabled()
    assert env.page.rows() == ()


def test_readiness_comes_from_the_preview_and_edits_run_the_use_cases(
    env: Env, xml_fixtures_dir: Path
) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    changed: list[int] = []
    env.page.changed.connect(lambda: changed.append(1))

    env.page.refresh()

    rows = env.page.rows()
    assert all(row.readiness is Readiness.INCOMPLETE for row in rows)
    assert all(line.source is MappingSource.SUPPLIER_DEFAULT for row in rows for line in row.lines)
    assert env.page.view.readiness.counts() == {"incomplete": 6}
    assert env.page.view.chips.chip("incomplete").text() == f"{strings.FILTER_INCOMPLETE} (6)"
    assert env.page.view.stepper.state(1) == "current"
    assert not env.page.view.banner.isVisible()

    # edicion en la fila de factura: centro de costo para todas sus lineas
    first = rows[0]
    model = env.page.model
    assert model.setData(model.index(0, Column.COST_CENTER), "CC-ADM", Qt.ItemDataRole.EditRole)
    assert changed == [1]
    assert env.page.has_pending_refresh()
    env.page.flush_refresh()
    assert not env.page.has_pending_refresh()
    updated = env.page.rows()[0]
    assert updated.invoice_id == first.invoice_id
    assert updated.readiness is Readiness.READY
    assert all(line.cost_center_code == "CC-ADM" for line in updated.lines)
    stored = env.services.invoices.get(env.company_id, first.invoice_id)
    assert stored is not None
    assert all(line.assigned == LineMapping("P-SERV", "CC-ADM") for line in stored.lines)
    assert env.page.view.readiness.counts() == {"ready": 1, "incomplete": 5}

    # edicion en una linea: producto distinto, conserva el centro de costo efectivo
    second = env.page.rows()[1]
    line_index = model.index(0, Column.PRODUCT, model.index(1, 0))
    assert model.setData(line_index, "P-PAPEL", Qt.ItemDataRole.EditRole)
    env.page.flush_refresh()
    edited = env.page.rows()[1].lines[0]
    assert edited.product_code == "P-PAPEL"
    assert edited.source is MappingSource.ASSIGNED
    stored = env.services.invoices.get(env.company_id, second.invoice_id)
    assert stored is not None
    assert stored.lines[0].assigned == LineMapping("P-PAPEL", None)


def test_a_click_on_a_cost_center_cell_picks_it_for_the_whole_invoice(
    env: Env, qtbot, xml_fixtures_dir: Path
) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    env.page.refresh()
    view = env.page.view
    first = env.page.rows()[0]
    assert first.readiness is Readiness.INCOMPLETE

    # la mano del puntero no miente: un clic abre el selector y elegir guarda el valor
    cell = view.tree.visualRect(view.proxy.index(0, Column.COST_CENTER))
    qtbot.mouseClick(view.tree.viewport(), Qt.MouseButton.LeftButton, pos=cell.center())
    editor = view.tree.findChild(CodeCombo)
    assert editor is not None
    editor.activated.emit(editor.row_for_code("CC-ADM"))
    env.page.flush_refresh()

    updated = env.page.rows()[0]
    assert updated.invoice_id == first.invoice_id
    assert updated.readiness is Readiness.READY
    assert all(line.cost_center_code == "CC-ADM" for line in updated.lines)
    stored = env.services.invoices.get(env.company_id, first.invoice_id)
    assert stored is not None
    assert all(line.assigned == LineMapping("P-SERV", "CC-ADM") for line in stored.lines)


def test_bulk_apply_and_restore_suggestion(env: Env, xml_fixtures_dir: Path) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    env.page.refresh()
    rows = env.page.rows()
    ids = [rows[0].invoice_id, rows[1].invoice_id]

    env.page.view.select_invoices(ids)
    assert env.page.view.bulk_bar.isVisible()
    env.page.view.bulk_apply_requested.emit(ids, None, "CC-ADM")
    env.page.flush_refresh()

    updated = {row.invoice_id: row for row in env.page.rows()}
    assert updated[ids[0]].readiness is Readiness.READY
    assert updated[ids[1]].readiness is Readiness.READY
    assert env.last_toast().message() == strings.invoices_updated(2)
    assert env.page.view.selected_invoice_ids() == ids  # la seleccion sobrevive al refresco

    line_id = updated[ids[0]].lines[0].line_id
    env.page.view.restore_suggestion_requested.emit([line_id])
    env.page.flush_refresh()
    restored = {row.invoice_id: row for row in env.page.rows()}[ids[0]].lines[0]
    # la asignacion manual desaparece; la memoria (que guardo el cambio masivo) sugiere
    assert restored.source is MappingSource.MEMORY
    assert restored.cost_center_code == "CC-ADM"
    stored = env.services.invoices.get(env.company_id, ids[0])
    assert stored is not None
    line = stored.line(line_id)
    assert line is not None and line.assigned is None


def test_export_request_uses_only_exportable_cufes(env: Env, xml_fixtures_dir: Path) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    env.page.refresh()
    requests: list[list[str]] = []
    env.page.export_requested.connect(requests.append)

    env.page.request_export()
    assert requests == []
    assert env.last_toast().kind == "warning"
    assert env.last_toast().message() == strings.EXPORT_NOTHING_READY

    rows = env.page.rows()
    env.page.view.bulk_apply_requested.emit(
        [rows[0].invoice_id, rows[1].invoice_id], None, "CC-ADM"
    )
    env.page.flush_refresh()
    # la memoria tambien completa otras lineas iguales del mismo proveedor (p. ej. la nota credito)
    ready = [row for row in env.page.rows() if row.exportable]
    incomplete = [row for row in env.page.rows() if not row.exportable]
    ready_cufes = [row.cufe for row in ready]
    assert {rows[0].cufe, rows[1].cufe} <= set(ready_cufes)
    assert incomplete

    env.page.request_export()
    assert requests[-1] == ready_cufes

    env.page.view.select_invoices([ready[0].invoice_id, incomplete[0].invoice_id])
    env.page.request_export()
    assert requests[-1] == [ready[0].cufe]

    env.page.view.select_invoices([incomplete[0].invoice_id])
    env.page.request_export()
    assert requests[-1] == ready_cufes  # nada exportable en la seleccion: todas las listas


def test_configure_suppliers_requests_carry_nit_and_name(env: Env, xml_fixtures_dir: Path) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    requests: list[list[tuple[str, str]]] = []
    env.page.configure_suppliers_requested.connect(requests.append)

    env.page.view.banner.action_button.click()
    assert sorted(requests[-1]) == sorted(SUPPLIERS)

    env.page.view.select_invoices([env.page.rows()[0].invoice_id])
    env.page.view.detail.configure_button.click()
    assert len(requests[-1]) == 1
    assert requests[-1][0] in SUPPLIERS


def test_stale_edit_is_reported_with_its_own_copy_and_refreshes(
    env: Env, monkeypatch, xml_fixtures_dir: Path
) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    env.page.refresh()
    calls: list[int] = []
    original = env.services.list_pending.execute

    def counting(company_id: int):
        calls.append(company_id)
        return original(company_id)

    monkeypatch.setattr(env.services.list_pending, "execute", counting)

    def missing(*args, **kwargs):
        raise InvoiceNotFoundError(99)

    monkeypatch.setattr(env.services.assign_document_mapping, "execute", missing)
    model = env.page.model
    model.setData(model.index(0, Column.COST_CENTER), "CC-ADM", Qt.ItemDataRole.EditRole)

    assert len(env.presenter.shown) == 1
    _error, _context, presentation = env.presenter.shown[0]
    assert presentation.title == strings.INVOICE_NOT_FOUND_TITLE
    assert presentation.hint == strings.INVOICE_NOT_FOUND_HINT
    assert calls == [env.company_id]  # se refresca de inmediato
    assert env.page.rows()[0].lines[0].cost_center_code is None  # el optimismo se deshizo


class QueuedRunner(QObject):
    """One job after the other like the real runner (FIFO), each one when the test says."""

    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[tuple[Callable[[Any], Any], Callable[[Any], None] | None]] = []

    @property
    def is_busy(self) -> bool:
        return bool(self.jobs)

    def submit(
        self,
        job: Callable[[Any], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        self.jobs.append((job, on_done))
        return TaskHandle()

    def run_next(self) -> None:
        job, on_done = self.jobs.pop(0)
        result = job(SimpleNamespace(report=lambda done, total: None, cancelled=lambda: False))
        if on_done is not None:
            on_done(result)

    def run_all(self) -> None:
        while self.jobs:
            self.run_next()

    def shutdown(self) -> None:
        self.jobs.clear()


def test_a_refresh_read_before_an_edit_never_undoes_it(
    env: Env, tmp_path: Path, xml_fixtures_dir: Path
) -> None:
    env.services.import_invoices.execute(env.company_id, [xml_fixtures_dir])
    _configure_suppliers(env)
    runner = QueuedRunner()
    page = InvoicesPage(
        env.services,
        runner,
        env.presenter,
        env.toasts,
        settings=AppSettings.in_file(tmp_path / "queued.ini"),
        parent=env.window,
    )
    page.set_company(env.company_id)
    runner.run_all()
    model = page.model
    invoice_id = page.rows()[0].invoice_id
    line = page.rows()[0].lines[0]
    assert line.product_code == "P-SERV"

    page.refresh()  # una lectura queda en cola delante de la edicion
    product_cell = model.index_for_line(line.line_id).siblingAtColumn(Column.PRODUCT)
    assert model.setData(product_cell, "P-PAPEL", Qt.ItemDataRole.EditRole)
    runner.run_next()  # la lectura corre primero y trae lo que habia antes de la edicion

    edited = model.line_at(model.index_for_line(line.line_id))
    assert edited is not None and edited.product_code == "P-PAPEL"  # no se deshace

    runner.run_next()  # se guarda el producto
    cost_center_cell = model.index_for_line(line.line_id).siblingAtColumn(Column.COST_CENTER)
    assert model.setData(cost_center_cell, "CC-ADM", Qt.ItemDataRole.EditRole)
    runner.run_all()
    page.flush_refresh()
    runner.run_all()

    stored = env.services.invoices.get(env.company_id, invoice_id)
    assert stored is not None
    stored_line = stored.line(line.line_id)
    assert stored_line is not None
    assert stored_line.assigned == LineMapping("P-PAPEL", "CC-ADM")
    shown = model.line_at(model.index_for_line(line.line_id))
    assert shown is not None
    assert (shown.product_code, shown.cost_center_code) == ("P-PAPEL", "CC-ADM")


def test_a_line_edit_saves_only_the_field_that_was_edited(env: Env, xml_fixtures_dir: Path) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    env.page.refresh()
    model = env.page.model
    invoice_id = env.page.rows()[0].invoice_id
    line = env.page.rows()[0].lines[0]
    # otra edicion ya guardo un producto que la pantalla aun no muestra
    env.services.assign_mapping.execute(
        env.company_id, [LineAssignment(line.line_id, LineMapping("P-PAPEL", None))]
    )

    cost_center_cell = model.index_for_line(line.line_id).siblingAtColumn(Column.COST_CENTER)
    assert model.setData(cost_center_cell, "CC-ADM", Qt.ItemDataRole.EditRole)

    stored = env.services.invoices.get(env.company_id, invoice_id)
    assert stored is not None
    stored_line = stored.line(line.line_id)
    assert stored_line is not None
    assert stored_line.assigned == LineMapping("P-PAPEL", "CC-ADM")


def test_refresh_is_debounced_and_stale_results_are_dropped(
    env: Env, monkeypatch, xml_fixtures_dir: Path
) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    _configure_suppliers(env)
    env.page.refresh()
    calls: list[int] = []
    original = env.services.list_pending.execute
    monkeypatch.setattr(
        env.services.list_pending, "execute", lambda cid: (calls.append(cid), original(cid))[1]
    )
    model = env.page.model
    ids = [row.invoice_id for row in env.page.rows()[:2]]

    env.page.view.bulk_apply_requested.emit([ids[0]], None, "CC-ADM")
    env.page.view.bulk_apply_requested.emit([ids[1]], None, "CC-ADM")
    assert calls == []
    env.page.flush_refresh()
    assert calls == [env.company_id]
    assert all(row.readiness is Readiness.READY for row in env.page.rows()[:2])

    # un resultado de otra empresa o generacion anterior no toca la pantalla
    before = env.page.rows()
    env.page.set_company(None)
    assert env.page.rows() == ()
    env.page.set_company(env.company_id)
    assert len(env.page.rows()) == len(before)
    assert model.rowCount() == len(before)


def test_file_pickers_are_injectable_and_remember_the_folder(
    env: Env, xml_fixtures_dir: Path
) -> None:
    env.page.set_company(env.company_id)
    asked: list[Path | None] = []

    def ask_files(start: Path | None) -> list[Path]:
        asked.append(start)
        return [xml_fixtures_dir / "invoice_plain.xml"]

    env.page.ask_files = ask_files
    env.page.open_files_dialog()
    assert asked == [None]
    assert len(env.page.rows()) == 1
    assert env.settings.last_import_folder == xml_fixtures_dir

    env.page.ask_folder = lambda start: (asked.append(start), xml_fixtures_dir / "nope")[1]
    env.page.open_folder_dialog()
    assert asked[-1] == xml_fixtures_dir
    env.page.ask_folder = lambda start: None
    env.page.open_folder_dialog()  # cancelado: nada pasa
    assert len(env.page.rows()) == 1


def test_copy_cufe_show_in_folder_and_catalog_toasts(env: Env, xml_fixtures_dir: Path) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    row = env.page.rows()[0]
    opened: list[Path] = []
    env.page.open_folder = lambda folder: (opened.append(folder), True)[1]
    navigations: list[str] = []
    env.page.navigate_requested.connect(navigations.append)

    env.page.view.copy_cufe_requested.emit(row.cufe)
    assert QApplication.clipboard().text() == row.cufe
    assert env.last_toast().message() == strings.COPIED

    env.page.view.show_in_folder_requested.emit(row.source_file)
    assert opened == [row.source_file.parent]
    env.page.view.show_in_folder_requested.emit(Path("missing") / "x.xml")
    assert opened == [row.source_file.parent]
    assert env.last_toast().message() == strings.FILE_NOT_FOUND_TOAST

    env.page.view.catalog_missing.emit(FIELD_PRODUCT)
    toast = env.last_toast()
    assert toast.message() == strings.CATALOG_EMPTY_PRODUCTS
    assert toast.action_button.text() == strings.ACTION_GO_TO_CATALOGS
    toast.action_button.click()
    assert navigations == ["catalogs"]
    env.page.view.catalog_missing.emit(FIELD_COST_CENTER)
    assert env.last_toast().message() == strings.CATALOG_EMPTY_COST_CENTERS


def test_layout_preferences_are_persisted(env: Env, qtbot) -> None:
    env.page.set_company(env.company_id)
    assert env.page.view.is_detail_visible() is False  # cerrado al empezar

    env.page.view.detail_button.click()
    assert env.settings.detail_panel_visible is True
    env.settings.sync()

    again = env.new_page()
    qtbot.addWidget(again)
    assert again.view.is_detail_visible() is True


def test_shortcut_slots(env: Env, xml_fixtures_dir: Path) -> None:
    _import_fixtures(env, xml_fixtures_dir)
    env.page.view.select_invoices([env.page.rows()[0].invoice_id])
    assert env.page.view.selected_invoice_ids()

    env.page.clear_selection()
    assert env.page.view.selected_invoice_ids() == []
    env.page.focus_search()
    assert env.page.view.focusWidget() is env.page.view.search
