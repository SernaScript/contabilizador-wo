"""Main window: sidebar navigation, company switching, first run, global shortcuts, drops,
toasts and the wiring between pages (pages never import each other)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QLabel

from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.shared import strings
from contabilizador.ui.composition import build_services
from contabilizador.ui.main_window import DEFAULT_SIZE, PAGE_ONBOARDING, MainWindow
from contabilizador.ui.pages.invoices.model import Column
from contabilizador.ui.pages.onboarding.view import STEP_CATALOG, STEP_COMPANY
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import QtTaskRunner
from tests.ui.shell import Shell, toast_messages


@pytest.fixture
def shell(tmp_path: Path) -> Iterator[Shell]:
    services = build_services(tmp_path / "app.db")
    yield Shell(services, tmp_path / "settings.ini")
    services.close()


def _spy(
    monkeypatch: pytest.MonkeyPatch, target: object, name: str, *, call_through: bool = True
) -> list[tuple]:
    calls: list[tuple] = []
    original = getattr(target, name)

    def record(*args: object) -> object:
        calls.append(args)
        return original(*args) if call_through else None

    monkeypatch.setattr(target, name, record)
    return calls


def _drop(window: MainWindow, paths: list[Path]) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    event = QDropEvent(
        QPointF(300, 300),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)


# --- primera ejecucion -------------------------------------------------------------------


def test_first_run_shows_the_checklist_in_a_branded_window(qtbot, shell: Shell) -> None:
    window = shell.build(qtbot)

    assert window.windowTitle() == strings.APP_TITLE
    assert window.findChild(QLabel, "headerLogo") is window.sidebar.logo
    assert window.current_page() == PAGE_ONBOARDING
    assert window.sidebar.active_key is None
    assert window.company_switcher.current_company_id() is None
    assert [item.key for item in window.sidebar.items()] == [
        "invoices",
        "suppliers",
        "catalogs",
        "batches",
        "company",
        "shortcuts",
    ]


def test_without_a_company_actions_explain_instead_of_doing_nothing(qtbot, shell: Shell) -> None:
    window = shell.build(qtbot)

    window.sidebar.item("catalogs").click()
    window.shortcut_actions["import_files"].trigger()
    window.shortcut_actions["export"].trigger()
    window.shortcut_actions["nav_batches"].trigger()

    assert window.current_page() == PAGE_ONBOARDING
    assert toast_messages(window) == [strings.ONBOARDING_NEEDS_COMPANY] * 4


def test_the_first_company_keeps_the_checklist_and_opens_the_pages(qtbot, shell: Shell) -> None:
    window = shell.build(qtbot)

    window.onboarding_page.view.step(STEP_COMPANY).action_button.click()
    dialog = window.new_company_flow.dialog
    assert dialog is not None
    dialog.form.name_edit.setText("EMPRESA DEMO S.A.S")
    dialog.form.third_party_edit.setText("1017")
    dialog.primary_button.click()

    company_id = shell.services.list_companies.execute()[0].id
    assert window.company_switcher.current_company_id() == company_id
    assert window.current_page() == PAGE_ONBOARDING
    assert [row.state for row in window.onboarding_page.view.steps()] == [
        "done",
        "current",
        "todo",
    ]
    assert shell.settings.last_company_id == company_id
    window.sidebar.item("catalogs").click()
    assert window.current_page() == "catalogs"
    assert window.sidebar.active_key == "catalogs"


def test_opens_on_invoices_with_the_last_company(qtbot, shell: Shell) -> None:
    shell.company("PRIMERA S.A.S")
    second = shell.company("SEGUNDA S.A.S")
    settings = shell.settings
    settings.last_company_id = second
    settings.sync()

    window = shell.build(qtbot)

    assert window.company_switcher.current_company_id() == second
    assert window.current_page() == "invoices"
    assert window.sidebar.active_key == "invoices"
    assert window.invoices_page.company_id == second


def test_switching_company_reaches_every_page(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = shell.company("PRIMERA S.A.S")
    second = shell.company("SEGUNDA S.A.S")
    window = shell.build(qtbot)
    assert window.company_switcher.current_company_id() == first
    pages = (
        window.invoices_page,
        window.suppliers_page,
        window.catalogs_page,
        window.batches_page,
        window.company_page,
    )
    calls = [_spy(monkeypatch, page, "set_company") for page in pages]

    window.company_switcher.set_current(second)

    assert [spied for spied in calls] == [[(second,)]] * len(pages)
    assert shell.settings.last_company_id == second
    assert window.current_page() == "invoices"


def test_switching_company_reaches_the_export_sheet(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell.company("PRIMERA S.A.S")
    second = shell.company("SEGUNDA S.A.S")
    window = shell.build(qtbot)
    calls = _spy(monkeypatch, window.export_sheet, "set_company")

    window.company_switcher.set_current(second)

    # una hoja que aun se esta preparando para la empresa anterior ya no se abre
    assert calls == [(second,)]


def test_sidebar_and_shortcuts_switch_pages(qtbot, shell: Shell) -> None:
    shell.company()
    window = shell.build(qtbot)

    window.shortcut_actions["nav_suppliers"].trigger()
    assert window.current_page() == "suppliers"
    assert window.sidebar.active_key == "suppliers"

    window.sidebar.item("batches").click()
    assert window.current_page() == "batches"
    assert window.stack.currentWidget() is window.batches_page

    window.navigate("company")
    assert window.sidebar.item("company").is_active
    assert not window.sidebar.item("batches").is_active


def test_shortcuts_dialog_opens_from_the_sidebar_and_its_shortcut(qtbot, shell: Shell) -> None:
    shell.company()
    window = shell.build(qtbot)

    window.sidebar.item("shortcuts").click()
    dialog = window.shortcuts_dialog
    assert dialog is not None
    assert dialog.isVisible()
    assert window.current_page() == "invoices"  # no es una pagina
    dialog.reject()
    assert window.shortcuts_dialog is None

    window.shortcut_actions["show_shortcuts"].trigger()
    assert window.shortcuts_dialog is not None


def test_search_goes_to_the_page_on_screen(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell.company()
    window = shell.build(qtbot)
    invoices = _spy(monkeypatch, window.invoices_page, "focus_search")
    catalogs = _spy(monkeypatch, window.catalogs_page, "focus_search")

    window.shortcut_actions["search"].trigger()
    window.navigate("catalogs")
    window.shortcut_actions["search"].trigger()
    window.navigate("company")
    window.shortcut_actions["search"].trigger()  # Empresa no tiene busqueda: no pasa nada

    assert (len(invoices), len(catalogs)) == (1, 1)


# --- datos y avisos entre paginas -----------------------------------------------------------


def test_badges_count_invoices_to_review_and_unconfigured_suppliers(
    qtbot, shell: Shell, xml_fixtures_dir: Path
) -> None:
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])

    window = shell.build(qtbot)

    suppliers = window.sidebar.item("suppliers").badge
    invoices = window.sidebar.item("invoices").badge
    assert suppliers.text() == "3"
    assert suppliers.property("status") == "blocked"
    assert invoices.text() == "6"
    assert not invoices.isHidden()


def test_a_busy_page_locks_the_company_switcher(qtbot, shell: Shell) -> None:
    shell.company()
    window = shell.build(qtbot)
    combo = window.company_switcher.combo

    window.invoices_page.busy_changed.emit(True)
    window.catalogs_page.busy_changed.emit(True)
    assert not combo.isEnabled()
    window.invoices_page.busy_changed.emit(False)
    assert not combo.isEnabled()  # el catalogo sigue trabajando
    window.catalogs_page.busy_changed.emit(False)

    assert combo.isEnabled()
    assert not window.company_switcher.new_button.isHidden()


def test_unconfigured_suppliers_go_to_the_wizard(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    shell.company()
    window = shell.build(qtbot)
    configure = _spy(monkeypatch, window.suppliers_page, "configure")
    refresh = _spy(monkeypatch, window.invoices_page, "refresh")

    window.invoices_page.configure_suppliers_requested.emit([("900123456", "EJEMPLO")])
    window.suppliers_page.changed.emit()

    assert configure == [([("900123456", "EJEMPLO")],)]
    assert refresh == [()]
    assert window.current_page() == "invoices"  # el asistente se abre sobre Facturas


def test_export_request_opens_the_export_sheet_and_refreshes_after(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    company_id = shell.company()
    window = shell.build(qtbot)
    opened = _spy(monkeypatch, window.export_sheet, "open", call_through=False)
    refreshed = {
        key: _spy(monkeypatch, window.page(key), "refresh")
        for key in ("invoices", "batches", "company", "suppliers")
    }

    window.invoices_page.export_requested.emit(["cufe-1", "cufe-2"])
    window.export_sheet.changed.emit()

    assert opened == [(company_id, ["cufe-1", "cufe-2"])]
    assert {key: len(calls) for key, calls in refreshed.items()} == {
        "invoices": 1,
        "batches": 1,
        "company": 1,
        "suppliers": 1,
    }


@pytest.mark.parametrize(
    ("source", "targets"),
    [
        ("catalogs", ("invoices", "suppliers")),
        ("batches", ("invoices", "suppliers")),
        ("invoices", ("suppliers",)),
    ],
)
def test_changes_on_one_page_refresh_the_pages_that_show_that_data(
    qtbot,
    shell: Shell,
    monkeypatch: pytest.MonkeyPatch,
    source: str,
    targets: tuple[str, ...],
) -> None:
    shell.company()
    window = shell.build(qtbot)
    refreshed = {key: _spy(monkeypatch, window.page(key), "refresh") for key in targets}
    sources = {
        "catalogs": window.catalogs_page,
        "batches": window.batches_page,
        "invoices": window.invoices_page,
    }

    sources[source].changed.emit()

    assert {key: len(calls) for key, calls in refreshed.items()} == dict.fromkeys(targets, 1)


def test_renaming_the_company_reloads_the_switcher(qtbot, shell: Shell) -> None:
    company_id = shell.company("ANTES S.A.S")
    window = shell.build(qtbot)
    shell.services.update_company.execute(company_id, name="DESPUES S.A.S")

    window.company_page.changed.emit()

    assert window.company_switcher.combo.currentText() == "DESPUES S.A.S"
    assert window.company_switcher.current_company_id() == company_id


def test_pages_ask_the_window_to_navigate(qtbot, shell: Shell) -> None:
    shell.company()
    window = shell.build(qtbot)

    window.batches_page.navigate_requested.emit("catalogs")
    assert window.current_page() == "catalogs"
    window.onboarding_page.navigate_requested.emit("invoices")
    assert window.current_page() == "invoices"


# --- archivos arrastrados ---------------------------------------------------------------------


def test_files_dropped_anywhere_are_imported_in_invoices(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch, xml_fixtures_dir: Path
) -> None:
    shell.company()
    window = shell.build(qtbot)
    window.navigate("catalogs")
    imported = _spy(monkeypatch, window.invoices_page, "import_paths")

    _drop(window, [xml_fixtures_dir / "invoice_plain.xml"])

    assert imported == [([xml_fixtures_dir / "invoice_plain.xml"],)]
    assert window.current_page() == "invoices"
    assert not window.drop_overlay.is_active


def test_files_dropped_without_a_company_are_not_imported(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch, xml_fixtures_dir: Path
) -> None:
    window = shell.build(qtbot)
    imported = _spy(monkeypatch, window.invoices_page, "import_paths")

    _drop(window, [xml_fixtures_dir / "invoice_plain.xml"])

    assert imported == []
    assert toast_messages(window) == [strings.ONBOARDING_NEEDS_COMPANY]


# --- avisos y preferencias ----------------------------------------------------------------


def test_toasts_never_cover_the_readiness_footer(
    qtbot, shell: Shell, xml_fixtures_dir: Path
) -> None:
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])
    window = shell.build(qtbot)
    readiness = window.invoices_page.view.readiness

    assert readiness.isVisible()
    assert window.toasts.bottom_offset == readiness.sizeHint().height()
    toast = window.toasts.show_toast("Listo")
    footer_top = readiness.mapTo(window.page_area, readiness.rect().topLeft()).y()
    assert toast.geometry().bottom() < footer_top

    window.navigate("catalogs")
    assert window.toasts.bottom_offset == 0


def test_window_size_and_company_survive_a_restart(qtbot, shell: Shell) -> None:
    company_id = shell.company()
    first = shell.build(qtbot, size=(1100, 720))
    first.close()

    saved = AppSettings.in_file(shell.settings_path)
    assert saved.window_geometry is not None
    assert saved.last_company_id == company_id
    second = shell.build(qtbot, size=None)

    # La pantalla virtual de las pruebas mide 800 px de ancho: Qt recorta el ancho restaurado
    # a la pantalla, pero el alto guardado (720) se respeta en lugar del tamano por defecto
    assert second.height() == 720
    assert second.size() != DEFAULT_SIZE


def test_errors_loading_companies_go_to_the_presenter(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> list:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(shell.services.list_companies, "execute", broken)

    window = shell.build(qtbot)

    assert [type(error) for error, _context in shell.presenter.shown] == [RuntimeError]
    assert window.current_page() == PAGE_ONBOARDING


def test_the_window_fits_a_1024_pixel_wide_screen(
    qtbot, shell: Shell, xml_fixtures_dir: Path
) -> None:
    # Todas las paginas viven en la misma pila: la mas ancha decide el minimo de la ventana
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])

    window = shell.build(qtbot, size=(1024, 700))

    assert window.minimumSizeHint().width() <= 1024
    assert window.width() == 1024
    view = window.invoices_page.view
    assert view.chips.geometry().right() <= view.width()


@pytest.mark.parametrize("size", [(1024, 700), (1280, 820)])
def test_selecting_invoices_never_widens_the_window(
    qtbot, shell: Shell, xml_fixtures_dir: Path, size: tuple[int, int]
) -> None:
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])
    window = shell.build(qtbot, size=size)
    view = window.invoices_page.view

    view.select_invoices([row.invoice_id for row in window.invoices_page.rows()[:3]])

    assert view.bulk_bar.isVisible()
    assert window.minimumSizeHint().width() <= size[0]
    assert window.width() == size[0]
    assert view.bulk_bar.geometry().right() <= view.width()


@pytest.mark.parametrize(
    ("size", "detail"), [((1280, 820), True), ((1280, 820), False), ((1024, 700), False)]
)
def test_the_status_column_is_always_on_screen(
    qtbot, shell: Shell, xml_fixtures_dir: Path, size: tuple[int, int], detail: bool
) -> None:
    # La pastilla de estado y el importe son lo primero que se lee: nunca quedan fuera de la
    # vista, ni a 1024 ni a 1280 con el panel de detalle abierto
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])
    window = shell.build(qtbot, size=size)
    view = window.invoices_page.view
    view.set_detail_visible(detail)
    qtbot.wait(10)
    view.fit_columns()

    header = view.tree.header()
    for column in (
        Column.DOCUMENT,
        Column.TOTAL,
        Column.PRODUCT,
        Column.COST_CENTER,
        Column.STATUS,
    ):
        assert not view.tree.isColumnHidden(column)
        right = header.sectionViewportPosition(column) + header.sectionSize(column)
        assert right <= view.tree.viewport().width(), column.name
    # unas 15 letras del nombre del proveedor
    assert header.sectionSize(Column.SUPPLIER) >= 128


def test_the_detail_panel_starts_closed(qtbot, shell: Shell) -> None:
    shell.company()

    window = shell.build(qtbot)

    assert window.invoices_page.view.is_detail_visible() is False


def test_keyboard_focus_starts_in_the_page_not_in_the_sidebar(
    qtbot, shell: Shell, xml_fixtures_dir: Path
) -> None:
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])

    window = shell.build(qtbot)

    assert window.focusWidget() is window.invoices_page.view.tree


def test_first_run_focuses_the_first_step(qtbot, shell: Shell) -> None:
    window = shell.build(qtbot)

    step = window.onboarding_page.view.step(STEP_COMPANY)
    assert window.focusWidget() is step.action_button


def test_changing_page_moves_the_keyboard_focus_into_the_new_page(
    qtbot, shell: Shell, xml_fixtures_dir: Path
) -> None:
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])
    window = shell.build(qtbot)

    for key in ("catalogs", "suppliers", "batches", "company", "invoices"):
        window.navigate(key)
        focused = window.focusWidget()
        page = window.page(key)
        assert focused is page or page.isAncestorOf(focused), key
    assert window.focusWidget() is window.invoices_page.view.tree


def test_after_creating_the_first_company_the_focus_goes_to_the_next_step(
    qtbot, shell: Shell
) -> None:
    window = shell.build(qtbot)

    company = shell.services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    window.new_company_flow.company_created.emit(company.id)

    catalog_step = window.onboarding_page.view.step(STEP_CATALOG)
    assert window.focusWidget() is catalog_step.action_button


def test_keyboard_navigation_through_the_sidebar_keeps_the_focus_there(qtbot, shell: Shell) -> None:
    shell.company()
    window = shell.build(qtbot)
    item = window.sidebar.item("catalogs")
    item.setFocus()

    item.click()

    assert window.current_page() == "catalogs"
    assert window.focusWidget() is item


def test_the_checklist_reads_its_progress_only_while_it_is_on_screen(
    qtbot, shell: Shell, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Saber si hay facturas lee todas las facturas: solo se hace con Primeros pasos a la vista
    first = shell.company("PRIMERA S.A.S")
    second = shell.company("SEGUNDA S.A.S")
    window = shell.build(qtbot)
    calls = _spy(monkeypatch, shell.services.invoices, "list_by_status")

    def checklist_reads() -> list[object]:
        # la lista de pendientes tambien usa list_by_status, pero solo con un estado
        return [args[0] for args in calls if len(args[1]) == len(InvoiceStatus)]

    window.company_switcher.set_current(second)
    window.invoices_page.changed.emit()
    window.catalogs_page.changed.emit()
    assert checklist_reads() == []

    window.navigate(PAGE_ONBOARDING)
    assert checklist_reads() == [second]
    window.catalogs_page.changed.emit()
    assert checklist_reads() == [second, second]

    window.company_switcher.set_current(first)
    assert checklist_reads() == [second, second, first]


def test_the_window_works_with_the_background_runner(
    qtbot, shell: Shell, xml_fixtures_dir: Path
) -> None:
    # La app real: un hilo de trabajo, resultados de vuelta en el hilo de la interfaz
    company_id = shell.company()
    shell.services.import_invoices.execute(company_id, [xml_fixtures_dir])
    runner = QtTaskRunner()
    window = MainWindow(shell.services, runner, settings=shell.settings, presenter=shell.presenter)
    qtbot.addWidget(window)
    window.show()
    try:
        qtbot.waitUntil(lambda: window.current_page() == "invoices", timeout=5000)
        qtbot.waitUntil(lambda: window.invoices_page.summary() is not None, timeout=5000)
        qtbot.waitUntil(lambda: window.sidebar.item("suppliers").badge.text() == "3", timeout=5000)
        summary = window.invoices_page.summary()
        assert summary is not None and summary.total == 6
        assert window.company_switcher.current_company_id() == company_id

        window.navigate("catalogs")
        qtbot.waitUntil(lambda: not runner.is_busy, timeout=5000)
        assert shell.presenter.shown == []
    finally:
        runner.shutdown()
