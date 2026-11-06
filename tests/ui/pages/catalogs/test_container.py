"""CatalogsContainer: loads both catalogs, runs every action through the runner and reports
with toasts, sheets and the error presenter."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import CONTEXT_CATALOG, CONTEXT_EXPORT
from contabilizador.ui.pages.catalogs.container import CatalogsContainer
from contabilizador.ui.pages.catalogs.model import ACTION_COLUMN
from contabilizador.ui.tasks import QtTaskRunner
from contabilizador.ui.widgets import ToastHost
from tests.ui.pages.catalogs.support import ManualRunner


@pytest.fixture
def make_container(qtbot, services, runner, presenter, host, dialogs, revealed):
    window, toasts = host

    def build(*, task_runner=None) -> CatalogsContainer:
        container = CatalogsContainer(
            services,
            task_runner or runner,
            presenter,
            toasts,
            dialogs=dialogs,
            reveal_file=revealed.append,
            parent=window,
        )
        container.setGeometry(0, 0, 1100, 760)
        container.show()
        return container

    return build


def codes(container: CatalogsContainer) -> list[str]:
    model = container.view.model
    return [model.index(row, 0).data() for row in range(model.rowCount())]


def seed(services: Services, company_id: int) -> None:
    services.save_product.execute(company_id, "1001", "Papelería")
    services.save_product.execute(company_id, "2002", "Servicios")
    services.save_cost_center.execute(company_id, "CC-1", "Administración")


def toast_messages(toasts: ToastHost) -> list[str]:
    return [toast.message() for toast in toasts.toasts()]


def write_workbook(path: Path, rows: list[tuple[str, str]]) -> Path:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["Código", "Nombre"])
    for row in rows:
        sheet.append(list(row))
    workbook.save(path)
    return path


# --- carga ----------------------------------------------------------------------


def test_without_a_company_the_page_asks_for_one(make_container) -> None:
    container = make_container()

    container.set_company(None)

    assert container.view.state() == "no_company"
    assert not container.view.new_button.isEnabled()


def test_lists_both_catalogs_of_the_company(make_container, services, company_id) -> None:
    seed(services, company_id)
    other = services.create_company.execute("OTRA S.A.S", "1").id
    assert other is not None
    services.save_product.execute(other, "9999", "De otra empresa")
    container = make_container()

    container.set_company(company_id)

    assert container.view.state() == "table"
    assert codes(container) == ["1001", "2002"]
    assert container.view.count_label.text() == "2 productos"
    container.view.set_kind(CatalogKind.COST_CENTER)
    assert codes(container) == ["CC-1"]


def test_an_empty_company_invites_to_import(make_container, company_id) -> None:
    container = make_container()

    container.set_company(company_id)

    assert container.view.state() == "empty"
    assert container.view.empty.action_button.text() == strings.ACTION_IMPORT_EXCEL


def test_refresh_keeps_the_kind_and_the_selection(make_container, services, company_id) -> None:
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)
    container.view.set_kind(CatalogKind.PRODUCT)
    container.view.select_code("2002")

    services.save_product.execute(company_id, "3003", "Nuevo desde fuera")
    container.refresh()

    assert codes(container) == ["1001", "2002", "3003"]
    assert container.view.selected_code() == "2002"
    assert container.view.current_kind() is CatalogKind.PRODUCT


def test_refresh_announces_no_badge(make_container, company_id, qtbot) -> None:
    container = make_container()
    badges: list[int] = []
    container.badge_changed.connect(badges.append)

    container.set_company(company_id)

    assert badges == [0]


def test_a_late_answer_for_the_previous_company_is_dropped(
    make_container, services, company_id
) -> None:
    services.save_product.execute(company_id, "1001", "De la primera")
    second = services.create_company.execute("SEGUNDA S.A.S", "2").id
    assert second is not None
    services.save_product.execute(second, "7777", "De la segunda")
    manual = ManualRunner()
    container = make_container(task_runner=manual)

    container.set_company(company_id)
    container.set_company(second)
    manual.run_all()

    assert codes(container) == ["7777"]


def test_refreshes_requested_while_loading_are_coalesced_into_one_more(
    make_container, services, company_id
) -> None:
    services.save_product.execute(company_id, "1001", "Papeleria")
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    assert len(manual.pending) == 1

    container.refresh()
    container.refresh()
    container.refresh()

    assert len(manual.pending) == 1  # ninguna carga extra mientras la primera sigue en curso
    services.save_product.execute(company_id, "2002", "Servicios")  # cambio que llega entre medias
    manual.run_next()
    assert len(manual.pending) == 1  # una sola recarga para todas las peticiones
    manual.run_next()
    assert manual.pending == []
    assert codes(container) == ["1001", "2002"]


def test_a_refresh_after_the_load_finished_starts_a_new_one(make_container, company_id) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()

    container.refresh()

    assert len(manual.pending) == 1


def test_company_change_clears_the_old_rows_while_loading(
    make_container, services, company_id
) -> None:
    seed(services, company_id)
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()
    assert codes(container) == ["1001", "2002"]

    container.set_company(company_id + 1)

    assert codes(container) == []
    assert container.view.state() == "table"  # cargando: no se afirma que este vacio


def test_a_failed_refresh_goes_to_the_error_presenter(
    make_container, services, company_id, presenter, monkeypatch
) -> None:
    def boom(_company_id: int) -> list[Product]:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(services.list_products, "execute", boom)
    container = make_container()

    container.set_company(company_id)

    assert [type(error) for error, _context in presenter.shown] == [RuntimeError]


def test_loads_in_a_worker_thread_with_the_real_runner(
    qtbot, make_container, services, company_id
) -> None:
    seed(services, company_id)
    task_runner = QtTaskRunner()
    try:
        container = make_container(task_runner=task_runner)

        container.set_company(company_id)

        qtbot.waitUntil(lambda: container.view.state() == "table" and bool(codes(container)))
        assert codes(container) == ["1001", "2002"]
    finally:
        task_runner.shutdown()


# --- crear y editar --------------------------------------------------------------


def test_new_product_is_saved_selected_and_announced(
    qtbot, make_container, services, company_id, host
) -> None:
    _window, toasts = host
    container = make_container()
    container.set_company(company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))

    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.windowTitle() == "Nuevo producto"
    assert sheet.code_edit is not None
    sheet.code_edit.setText("1001")
    sheet.name_edit.setText("Papelería")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert services.list_products.execute(company_id) == [Product(company_id, "1001", "Papelería")]
    assert container.entry_sheet is None
    assert toast_messages(toasts) == ["Producto guardado"]
    assert toasts.toasts()[0].kind == "success"
    assert container.view.selected_code() == "1001"
    assert changes == [1]


def test_new_cost_center_goes_to_the_cost_center_catalog(
    qtbot, make_container, services, company_id
) -> None:
    container = make_container()
    container.set_company(company_id)
    container.view.set_kind(CatalogKind.COST_CENTER)

    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.windowTitle() == "Nuevo centro de costo"
    assert sheet.code_edit is not None
    sheet.code_edit.setText("CC-9")
    sheet.name_edit.setText("Ventas")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert services.list_cost_centers.execute(company_id) == [
        CostCenter(company_id, "CC-9", "Ventas")
    ]
    assert services.list_products.execute(company_id) == []


def test_creating_an_existing_code_is_refused_without_overwriting(
    qtbot, make_container, services, company_id
) -> None:
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.code_edit is not None
    sheet.code_edit.setText("1001")
    sheet.name_edit.setText("Otro nombre")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert container.entry_sheet is sheet
    assert sheet.error_label.text() == strings.catalog_code_exists("product", "1001")
    assert sheet.code_edit.property("invalid") == "true"
    assert services.list_products.execute(company_id)[0].name == "Papelería"


def test_the_new_code_is_only_revealed_in_the_catalog_where_it_was_created(
    qtbot, make_container, services, company_id
) -> None:
    services.save_cost_center.execute(company_id, "9999", "Mismo codigo, otro catalogo")
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()

    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.code_edit is not None
    sheet.code_edit.setText("9999")
    sheet.name_edit.setText("Producto nuevo")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)
    manual.run_next()  # guardar
    container.view.set_kind(
        CatalogKind.COST_CENTER
    )  # la persona cambia de segmento mientras recarga
    manual.run_all()

    assert container.view.current_kind() is CatalogKind.COST_CENTER
    assert container.view.selected_code() is None


def test_cancelling_the_entry_sheet_saves_nothing(
    qtbot, make_container, services, company_id
) -> None:
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    qtbot.mouseClick(sheet.cancel_button, Qt.MouseButton.LeftButton)

    assert container.entry_sheet is None
    assert services.list_products.execute(company_id) == []


def test_editing_renames_but_never_changes_the_code(
    qtbot, make_container, services, company_id, host
) -> None:
    _window, toasts = host
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)
    link = container.view.model.index(container.view.model.row_of("2002"), ACTION_COLUMN)

    qtbot.mouseClick(
        container.view.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=container.view.table.visualRect(link).center(),
    )
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.windowTitle() == "Editar producto"
    assert sheet.code_edit is None
    assert sheet.name_edit.text() == "Servicios"
    sheet.name_edit.setText("Servicios técnicos")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    names = {p.code: p.name for p in services.list_products.execute(company_id)}
    assert names == {"1001": "Papelería", "2002": "Servicios técnicos"}
    assert toast_messages(toasts) == ["Producto guardado"]
    assert container.view.selected_code() == "2002"


def test_a_save_still_running_keeps_the_sheet_and_counts_even_if_it_closed(
    qtbot, make_container, services, company_id, host
) -> None:
    _window, toasts = host
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))
    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.code_edit is not None
    sheet.code_edit.setText("1001")
    sheet.name_edit.setText("Papelería")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    sheet.close()  # el boton de cerrar de la ventana mientras se guarda: no se cierra
    assert container.entry_sheet is sheet
    assert sheet.isVisible()

    sheet.done(0)  # se cerro por otra via y Qt la destruye
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    manual.run_all()

    # lo guardado cuenta igual: aviso, lista al dia y las demas paginas se enteran
    assert services.list_products.execute(company_id) == [Product(company_id, "1001", "Papelería")]
    assert toast_messages(toasts) == ["Producto guardado"]
    assert changes == [1]
    assert codes(container) == ["1001"]


def test_a_failed_save_keeps_the_sheet_open_and_explains(
    qtbot, make_container, services, company_id, presenter, monkeypatch
) -> None:
    def boom(*_args: object) -> Product:
        raise RuntimeError("disk I/O error")

    monkeypatch.setattr(services.save_product, "execute", boom)
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.new_button, Qt.MouseButton.LeftButton)
    sheet = container.entry_sheet
    assert sheet is not None
    assert sheet.code_edit is not None
    sheet.code_edit.setText("1001")
    sheet.name_edit.setText("Papelería")
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert container.entry_sheet is sheet
    assert sheet.primary_button.isEnabled()  # se puede reintentar
    assert [type(error) for error, _context in presenter.shown] == [RuntimeError]


# --- eliminar ---------------------------------------------------------------------


def test_deleting_asks_first_and_removes_on_confirmation(
    qtbot, make_container, services, company_id, host
) -> None:
    _window, toasts = host
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)
    container.view.select_code("2002")
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))

    qtbot.mouseClick(container.view.delete_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None
    assert confirmation.title_label.text() == strings.confirm_delete("2002 - Servicios")
    assert confirmation.message_label.text() == strings.CATALOG_DELETE_NOTE
    assert confirmation.primary_button.text() == strings.ACTION_DELETE
    assert [p.code for p in services.list_products.execute(company_id)] == ["1001", "2002"]

    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    assert [p.code for p in services.list_products.execute(company_id)] == ["1001"]
    assert container.confirmation is None
    assert toast_messages(toasts) == ["Producto eliminado"]
    assert codes(container) == ["1001"]
    assert container.view.selected_code() is None
    assert changes == [1]


def test_cancelling_the_confirmation_deletes_nothing(
    qtbot, make_container, services, company_id, host
) -> None:
    _window, toasts = host
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)
    container.view.select_code("2002")

    qtbot.mouseClick(container.view.delete_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None
    qtbot.mouseClick(confirmation.cancel_button, Qt.MouseButton.LeftButton)

    assert container.confirmation is None
    assert [p.code for p in services.list_products.execute(company_id)] == ["1001", "2002"]
    assert toast_messages(toasts) == []


def test_deleting_a_product_a_supplier_uses_names_the_supplier(
    qtbot, make_container, services, company_id
) -> None:
    seed(services, company_id)
    services.configure_supplier.execute(company_id, "900123456", "ACME S.A.S.", ["1001"], "1001")
    services.configure_supplier.execute(company_id, "800987654", "Otro Ltda", ["2002"], "2002")
    container = make_container()
    container.set_company(company_id)
    container.view.select_code("1001")

    qtbot.mouseClick(container.view.delete_button, Qt.MouseButton.LeftButton)

    confirmation = container.confirmation
    assert confirmation is not None
    assert confirmation.message_label.text().startswith("Lo usa el proveedor «ACME S.A.S.».")
    assert "bloqueadas" in confirmation.message_label.text()
    assert [label.text() for label in confirmation.note_labels] == [strings.CATALOG_DELETE_NOTE]


def test_deleting_a_cost_center_warns_about_invoices_that_use_it(
    qtbot, make_container, services, company_id, host
) -> None:
    _window, toasts = host
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)
    container.view.set_kind(CatalogKind.COST_CENTER)
    container.view.select_code("CC-1")

    qtbot.mouseClick(container.view.delete_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None
    assert confirmation.message_label.text() == strings.CATALOG_COST_CENTER_DELETE_NOTE
    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    assert services.list_cost_centers.execute(company_id) == []
    assert toast_messages(toasts) == ["Centro de costo eliminado"]


def test_two_quick_delete_clicks_open_one_confirmation(
    qtbot, make_container, services, company_id
) -> None:
    seed(services, company_id)
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()
    container.view.select_code("1001")

    container.view.delete_requested.emit("1001")
    container.view.delete_requested.emit("1001")
    manual.run_all()

    assert len(manual.pending) == 0
    assert container.confirmation is not None
    assert len(container.findChildren(type(container.confirmation))) == 1


# --- importar desde Excel ---------------------------------------------------------


def test_import_with_skipped_rows_opens_the_report(
    qtbot, make_container, services, company_id, dialogs, tmp_path
) -> None:
    dialogs.workbook = write_workbook(
        tmp_path / "productos.xlsx",
        [("1001", "Papelería"), ("2002", "Servicios"), ("", "Sin código"), ("1001", "Repetido")],
    )
    container = make_container()
    container.set_company(company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    report = container.report_sheet
    assert report is not None
    assert report.summary_label.text() == "2 productos creados. 2 filas no se importaron."
    assert report.invalid_list.count() == 2
    assert codes(container) == ["1001", "2002"]
    assert changes == [1]
    qtbot.mouseClick(report.primary_button, Qt.MouseButton.LeftButton)
    assert container.report_sheet is None


def test_clean_import_is_a_toast_not_a_dialog(
    qtbot, make_container, company_id, dialogs, tmp_path, host
) -> None:
    _window, toasts = host
    dialogs.workbook = write_workbook(tmp_path / "p.xlsx", [("1", "Uno"), ("2", "Dos")])
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert container.report_sheet is None
    assert toast_messages(toasts) == ["2 productos creados."]
    assert toasts.toasts()[0].kind == "success"
    assert container.view.state() == "table"


def test_importing_the_same_file_again_reports_updates(
    qtbot, make_container, company_id, dialogs, tmp_path, host
) -> None:
    _window, toasts = host
    dialogs.workbook = write_workbook(tmp_path / "p.xlsx", [("1", "Uno")])
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert toast_messages(toasts) == ["1 producto creado.", "1 producto actualizado."]


def test_import_follows_the_selected_kind(
    qtbot, make_container, services, company_id, dialogs, tmp_path
) -> None:
    dialogs.workbook = write_workbook(tmp_path / "cc.xlsx", [("CC-1", "Administración")])
    container = make_container()
    container.set_company(company_id)
    container.view.set_kind(CatalogKind.COST_CENTER)

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert [c.code for c in services.list_cost_centers.execute(company_id)] == ["CC-1"]
    assert services.list_products.execute(company_id) == []


def test_an_empty_workbook_warns_and_changes_nothing(
    qtbot, make_container, company_id, dialogs, tmp_path, host
) -> None:
    _window, toasts = host
    dialogs.workbook = write_workbook(tmp_path / "vacio.xlsx", [])
    container = make_container()
    container.set_company(company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert toast_messages(toasts) == ["El archivo no tiene filas para importar."]
    assert toasts.toasts()[0].kind == "warning"
    assert changes == []


def test_an_unreadable_file_goes_to_the_error_presenter(
    qtbot, make_container, company_id, dialogs, tmp_path, presenter, host
) -> None:
    _window, toasts = host
    broken = tmp_path / "roto.xlsx"
    broken.write_text("esto no es un libro", encoding="utf-8")
    dialogs.workbook = broken
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert len(presenter.shown) == 1
    error, context = presenter.shown[0]
    assert type(error).__name__ == "UnreadableCatalogFileError"
    assert context == CONTEXT_CATALOG
    assert toast_messages(toasts) == []
    assert container.report_sheet is None


def test_cancelling_the_file_dialog_does_nothing(
    qtbot, make_container, company_id, dialogs, runner
) -> None:
    dialogs.workbook = None
    container = make_container()
    container.set_company(company_id)
    submitted_before = len(runner.handles)

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert dialogs.workbook_asked == 1
    assert len(runner.handles) == submitted_before


def test_busy_changed_brackets_every_action_so_the_company_switcher_can_lock(
    qtbot, make_container, services, company_id, dialogs, tmp_path
) -> None:
    dialogs.workbook = write_workbook(tmp_path / "p.xlsx", [("1", "Uno")])
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()
    states: list[bool] = []
    container.busy_changed.connect(states.append)

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)
    assert states == [True]
    manual.run_all()

    assert states == [True, False]


def test_the_parent_can_be_passed_positionally_like_in_the_other_containers(
    qtbot, services, runner, presenter, host
) -> None:
    window, toasts = host

    container = CatalogsContainer(services, runner, presenter, toasts, window)

    assert container.parentWidget() is window


def test_actions_stay_locked_while_a_task_runs(
    qtbot, make_container, services, company_id, dialogs, tmp_path
) -> None:
    dialogs.workbook = write_workbook(tmp_path / "p.xlsx", [("1", "Uno")])
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()

    qtbot.mouseClick(container.view.import_button, Qt.MouseButton.LeftButton)

    assert not container.view.import_button.isEnabled()
    assert not container.view.new_button.isEnabled()
    manual.run_all()
    assert container.view.import_button.isEnabled()


# --- plantilla --------------------------------------------------------------------


def test_template_is_written_with_the_importer_headers(
    qtbot, make_container, company_id, dialogs, tmp_path, host, revealed
) -> None:
    _window, toasts = host
    dialogs.destination = tmp_path / "mi-plantilla"
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.template_button, Qt.MouseButton.LeftButton)

    assert dialogs.suggested[0].name == "plantilla-productos.xlsx"
    written = tmp_path / "mi-plantilla.xlsx"
    assert written.is_file()
    workbook = load_workbook(written)
    assert [cell.value for cell in workbook.active[1]] == ["Código", "Nombre"]  # type: ignore[index]
    workbook.close()
    assert toast_messages(toasts) == [strings.CATALOG_TEMPLATE_SAVED]
    toast = toasts.toasts()[0]
    assert toast.action_button.text() == strings.ACTION_SHOW_IN_FOLDER
    toast.action_button.click()
    assert revealed == [written]


def test_template_name_follows_the_selected_kind(
    qtbot, make_container, company_id, dialogs, tmp_path
) -> None:
    dialogs.destination = tmp_path / "cc.xlsx"
    container = make_container()
    container.set_company(company_id)
    container.view.set_kind(CatalogKind.COST_CENTER)

    qtbot.mouseClick(container.view.template_button, Qt.MouseButton.LeftButton)

    assert dialogs.suggested[0].name == "plantilla-centros-de-costo.xlsx"
    workbook = load_workbook(tmp_path / "cc.xlsx")
    assert workbook.sheetnames == ["Centros de costo"]
    workbook.close()


def test_template_that_cannot_be_written_asks_to_close_excel(
    qtbot, make_container, services, company_id, dialogs, tmp_path, presenter, host, monkeypatch
) -> None:
    _window, toasts = host

    def locked(*_args: object) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(services.write_catalog_template, "execute", locked)
    dialogs.destination = tmp_path / "plantilla.xlsx"
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.template_button, Qt.MouseButton.LeftButton)

    assert [type(error) for error, _context in presenter.shown] == [PermissionError]
    assert presenter.shown[0][1] == CONTEXT_EXPORT
    assert toast_messages(toasts) == []
    assert container.view.template_button.isEnabled()


def test_focus_search_is_delegated_to_the_view(make_container, services, company_id) -> None:
    seed(services, company_id)
    container = make_container()
    container.set_company(company_id)

    container.focus_search()

    assert container.view.focusWidget() is container.view.search
