"""SuppliersContainer: the Proveedores page wired to the real use cases."""

import pytest
from PySide6.QtWidgets import QDialog

from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.pages.suppliers.container import SuppliersContainer
from contabilizador.ui.tasks import QtTaskRunner
from contabilizador.ui.widgets import ToastHost
from tests.ui.pages.suppliers.conftest import SUPPLIERS, Confirmations
from tests.ui.pages.suppliers.fakes import ManualRunner, RecordingPresenter

NITS_BY_NAME = [nit for nit, _name in SUPPLIERS]  # ya vienen ordenados por nombre


def messages(toasts: ToastHost) -> list[str]:
    return [toast.message() for toast in toasts.toasts()]


def configure_all(container: SuppliersContainer) -> None:
    """Runs the wizard over the three suppliers choosing P-1 for each."""
    container.configure(list(SUPPLIERS))
    wizard = container.wizard
    assert wizard is not None
    for _ in SUPPLIERS:
        wizard.picker.set_checked("P-1", True)
        wizard.primary_button.click()


# --- carga ---------------------------------------------------------------------------


def test_without_company_the_page_asks_for_one(make_container) -> None:
    container = make_container()
    badges: list[int] = []
    container.badge_changed.connect(badges.append)

    container.set_company(None)

    assert container.view.state() == "no_company"
    assert badges == [0]


def test_company_loads_the_unconfigured_suppliers_and_reports_the_badge(
    make_container, company_id: int
) -> None:
    container = make_container()
    badges: list[int] = []
    container.badge_changed.connect(badges.append)

    container.set_company(company_id)

    assert container.view.state() == "list"
    assert container.view.visible_nits() == NITS_BY_NAME
    assert badges == [3]
    assert container.view.configure_button.text() == strings.configure_pending_action(3)


def test_company_without_invoices_or_suppliers_shows_the_empty_state(
    make_container, services: Services
) -> None:
    company = services.create_company.execute("OTRA EMPRESA", "1")
    container = make_container()

    container.set_company(company.id)

    assert container.view.state() == "empty"


def test_refresh_without_company_does_nothing(make_container) -> None:
    container = make_container()

    container.refresh()

    assert container.view.state() == "loading"


def test_configured_suppliers_show_up_after_a_refresh(
    container: SuppliersContainer, services: Services, company_id: int
) -> None:
    services.configure_supplier.execute(company_id, "900123456", "COMERCIALIZADORA", ["P-1"], "P-1")

    container.refresh()

    assert container.view.visible_nits()[-1] == "900123456"
    assert container.view.configure_button.text() == strings.configure_pending_action(2)


def test_suppliers_with_products_missing_from_the_catalog_are_flagged(
    container: SuppliersContainer, services: Services, company_id: int
) -> None:
    services.configure_supplier.execute(company_id, "900123456", "X", ["P-1", "P-9"], "P-1")

    container.refresh()

    model_row = container.view.table.model().index(
        container.view.visible_nits().index("900123456"), 1
    )
    assert model_row.data() == strings.SUPPLIER_PRODUCT_MISSING_PILL


# --- asistente --------------------------------------------------------------------------


def test_configure_opens_the_wizard_with_context_for_the_given_suppliers(
    container: SuppliersContainer,
) -> None:
    container.configure(list(SUPPLIERS))

    wizard = container.wizard
    assert wizard is not None
    assert wizard.isVisible()
    assert wizard.step_count() == 3
    assert [step.nit for step in (wizard.current_step(),)] == [SUPPLIERS[0][0]]
    assert wizard.identity.name_label.text() == SUPPLIERS[0][1]
    assert wizard.context.row_count() > 0
    assert wizard.picker.visible_codes() == ["P-1", "P-2", "P-3"]


def test_configure_ignores_an_empty_list_and_a_second_call_while_open(
    container: SuppliersContainer,
) -> None:
    container.configure([])
    assert container.wizard is None

    container.configure(list(SUPPLIERS))
    first = container.wizard
    container.configure(list(SUPPLIERS[:1]))

    assert container.wizard is first
    assert first is not None
    assert first.step_count() == 3


def test_configure_removes_repeated_suppliers(container: SuppliersContainer) -> None:
    container.configure([SUPPLIERS[0], SUPPLIERS[0], SUPPLIERS[1]])

    assert container.wizard is not None
    assert container.wizard.step_count() == 2


def test_saving_every_step_configures_the_suppliers_and_announces_it_once(
    container: SuppliersContainer,
    services: Services,
    company_id: int,
    toasts: ToastHost,
) -> None:
    changes: list[int] = []
    badges: list[int] = []
    container.changed.connect(lambda: changes.append(1))
    container.badge_changed.connect(badges.append)

    configure_all(container)

    configs = {c.nit: c for c in services.list_supplier_configs.execute(company_id)}
    assert set(configs) == {nit for nit, _name in SUPPLIERS}
    assert all(c.product_codes == ("P-1",) for c in configs.values())
    assert all(c.default_product_code == "P-1" for c in configs.values())
    assert container.wizard is None
    assert changes == [1]
    assert messages(toasts) == [strings.suppliers_configured(3)]
    assert badges[-1] == 0
    assert not container.view.configure_button.isVisible()


def test_closing_the_wizard_after_one_save_keeps_that_one_and_announces_it(
    container: SuppliersContainer, services: Services, company_id: int, toasts: ToastHost
) -> None:
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))
    container.configure(list(SUPPLIERS))
    wizard = container.wizard
    assert wizard is not None

    wizard.picker.set_checked("P-2", True)
    wizard.primary_button.click()
    wizard.cancel_button.click()

    assert [c.nit for c in services.list_supplier_configs.execute(company_id)] == [SUPPLIERS[0][0]]
    assert container.wizard is None
    assert changes == [1]
    assert messages(toasts) == [strings.suppliers_configured(1)]


def test_skipping_everything_changes_nothing_and_stays_quiet(
    container: SuppliersContainer, services: Services, company_id: int, toasts: ToastHost
) -> None:
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))
    container.configure(list(SUPPLIERS))
    wizard = container.wizard
    assert wizard is not None

    for _ in SUPPLIERS:
        assert wizard.skip_button is not None
        wizard.skip_button.click()

    assert services.list_supplier_configs.execute(company_id) == []
    assert changes == []
    assert messages(toasts) == []
    assert container.wizard is None


def test_a_supplier_that_is_already_configured_comes_prefilled(
    container: SuppliersContainer, services: Services, company_id: int
) -> None:
    services.configure_supplier.execute(
        company_id, SUPPLIERS[1][0], SUPPLIERS[1][1], ["P-2", "P-3"], "P-3"
    )

    container.configure([SUPPLIERS[1]])

    wizard = container.wizard
    assert wizard is not None
    assert wizard.picker.selected_codes() == ("P-2", "P-3")
    assert wizard.picker.default_code() == "P-3"


def test_a_failed_save_keeps_the_wizard_on_the_same_supplier_and_says_so(
    container: SuppliersContainer,
    services: Services,
    presenter: RecordingPresenter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(services.configure_supplier, "execute", failing)
    container.configure(list(SUPPLIERS))
    wizard = container.wizard
    assert wizard is not None
    wizard.picker.set_checked("P-1", True)

    wizard.primary_button.click()

    assert wizard.current_index() == 0
    assert wizard.error_note.text() == strings.SUPPLIER_SAVE_FAILED
    assert wizard.primary_button.isEnabled()
    assert [str(error) for error in presenter.shown] == ["database is locked"]


def test_the_catalog_request_closes_the_wizard_and_navigates(
    qtbot, container: SuppliersContainer, services: Services, company_id: int
) -> None:
    for code in ("P-1", "P-2", "P-3"):
        services.delete_product.execute(company_id, code)
    container.configure(list(SUPPLIERS))
    wizard = container.wizard
    assert wizard is not None

    with qtbot.waitSignal(container.navigate_requested, timeout=1000) as blocker:
        wizard.picker.catalog_button.click()

    assert blocker.args == ["catalogs"]
    assert container.wizard is None


# --- edicion -------------------------------------------------------------------------------


def with_first_supplier_configured(
    container: SuppliersContainer, services: Services, company_id: int
) -> SuppliersContainer:
    services.configure_supplier.execute(
        company_id, SUPPLIERS[0][0], SUPPLIERS[0][1], ["P-1", "P-2"], "P-1"
    )
    container.refresh()
    return container


def test_editing_an_unconfigured_supplier_opens_the_wizard_for_it(
    container: SuppliersContainer,
) -> None:
    container.view.edit_requested.emit(SUPPLIERS[2][0])

    wizard = container.wizard
    assert wizard is not None
    assert wizard.step_count() == 1
    assert wizard.current_step().nit == SUPPLIERS[2][0]
    assert container.sheet is None


def test_editing_a_configured_supplier_opens_the_sheet_with_its_products(
    container: SuppliersContainer, services: Services, company_id: int
) -> None:
    with_first_supplier_configured(container, services, company_id)

    container.view.edit_requested.emit(SUPPLIERS[0][0])

    sheet = container.sheet
    assert sheet is not None
    assert sheet.isVisible()
    assert sheet.picker.selected_codes() == ("P-1", "P-2")
    assert sheet.picker.default_code() == "P-1"
    assert container.wizard is None


def test_saving_the_sheet_updates_the_supplier(
    container: SuppliersContainer, services: Services, company_id: int, toasts: ToastHost
) -> None:
    with_first_supplier_configured(container, services, company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))
    container.view.edit_requested.emit(SUPPLIERS[0][0])
    sheet = container.sheet
    assert sheet is not None

    sheet.picker.set_checked("P-3", True)
    sheet.picker.set_default_code("P-3")
    sheet.primary_button.click()

    saved = services.suppliers.get(company_id, SUPPLIERS[0][0])
    assert saved is not None
    assert saved.product_codes == ("P-1", "P-2", "P-3")
    assert saved.default_product_code == "P-3"
    assert container.sheet is None
    assert changes == [1]
    assert messages(toasts) == [strings.SUPPLIER_SAVED]


def test_a_failed_sheet_save_stays_open_and_says_so(
    container: SuppliersContainer,
    services: Services,
    company_id: int,
    presenter: RecordingPresenter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with_first_supplier_configured(container, services, company_id)

    def failing(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(services.configure_supplier, "execute", failing)
    container.view.edit_requested.emit(SUPPLIERS[0][0])
    sheet = container.sheet
    assert sheet is not None

    sheet.primary_button.click()

    assert sheet.isVisible()
    assert sheet.error_note.text() == strings.SUPPLIER_SAVE_FAILED
    assert sheet.primary_button.isEnabled()
    assert len(presenter.shown) == 1


def test_the_sheet_ignores_a_supplier_that_is_not_in_the_list(
    container: SuppliersContainer,
) -> None:
    container.view.edit_requested.emit("000")

    assert container.sheet is None
    assert container.wizard is None


# --- eliminar -----------------------------------------------------------------------------------


def test_deleting_asks_first_and_does_nothing_when_declined(
    container: SuppliersContainer,
    services: Services,
    company_id: int,
    confirmations: Confirmations,
    toasts: ToastHost,
) -> None:
    with_first_supplier_configured(container, services, company_id)
    confirmations.answer = False

    container.view.delete_requested.emit(SUPPLIERS[0][0])

    assert confirmations.asked == [
        (
            strings.confirm_delete(SUPPLIERS[0][1]),
            strings.SUPPLIER_DELETE_DETAIL,
            strings.ACTION_DELETE,
        )
    ]
    assert services.suppliers.get(company_id, SUPPLIERS[0][0]) is not None
    assert messages(toasts) == []


def test_confirmed_delete_removes_the_configuration_and_announces_it(
    container: SuppliersContainer,
    services: Services,
    company_id: int,
    toasts: ToastHost,
) -> None:
    with_first_supplier_configured(container, services, company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))

    container.view.delete_requested.emit(SUPPLIERS[0][0])

    assert services.suppliers.get(company_id, SUPPLIERS[0][0]) is None
    assert changes == [1]
    assert messages(toasts) == [strings.SUPPLIER_DELETED]
    # sus facturas siguen pendientes: vuelve a la lista como sin configurar
    assert SUPPLIERS[0][0] in container.view.visible_nits()
    assert container.view.configure_button.text() == strings.configure_pending_action(3)


def test_deleting_from_the_sheet_closes_it(
    container: SuppliersContainer, services: Services, company_id: int
) -> None:
    with_first_supplier_configured(container, services, company_id)
    container.view.edit_requested.emit(SUPPLIERS[0][0])
    sheet = container.sheet
    assert sheet is not None

    sheet.delete_button.click()

    assert services.suppliers.get(company_id, SUPPLIERS[0][0]) is None
    assert container.sheet is None


def test_declining_the_delete_from_the_sheet_keeps_it_open(
    container: SuppliersContainer,
    services: Services,
    company_id: int,
    confirmations: Confirmations,
) -> None:
    with_first_supplier_configured(container, services, company_id)
    confirmations.answer = False
    container.view.edit_requested.emit(SUPPLIERS[0][0])
    sheet = container.sheet
    assert sheet is not None

    sheet.delete_button.click()

    assert container.sheet is sheet
    assert sheet.isVisible()


def test_a_failed_delete_is_reported_and_nothing_is_announced(
    container: SuppliersContainer,
    services: Services,
    company_id: int,
    presenter: RecordingPresenter,
    toasts: ToastHost,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with_first_supplier_configured(container, services, company_id)

    def failing(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("locked")

    monkeypatch.setattr(services.delete_supplier_config, "execute", failing)

    container.view.delete_requested.emit(SUPPLIERS[0][0])

    assert len(presenter.shown) == 1
    assert messages(toasts) == []


# --- tareas en segundo plano ---------------------------------------------------------------------


def test_a_result_for_a_previous_company_is_dropped(
    make_container, services: Services, company_id: int
) -> None:
    other = services.create_company.execute("SEGUNDA EMPRESA", "2")
    runner = ManualRunner()
    container = make_container(runner)

    container.set_company(company_id)
    container.set_company(other.id)
    runner.run_next()  # llega tarde la carga de la primera empresa

    assert container.view.state() == "loading"

    runner.run_next()
    assert container.view.state() == "empty"


def test_refreshes_requested_while_loading_are_coalesced(make_container, company_id: int) -> None:
    runner = ManualRunner()
    container = make_container(runner)
    container.set_company(company_id)

    container.refresh()
    container.refresh()
    container.refresh()
    assert len(runner.queue) == 1

    runner.run_next()
    assert len(runner.queue) == 1  # una sola recarga pendiente, no tres
    runner.run_next()
    assert container.view.state() == "list"
    assert runner.queue == []


def test_a_failed_load_shows_the_error_state_and_reports_the_error(
    make_container,
    company_id: int,
    services: Services,
    presenter: RecordingPresenter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("cannot read")

    monkeypatch.setattr(services.list_supplier_configs, "execute", failing)
    container = make_container()

    container.set_company(company_id)

    assert container.view.state() == "error"
    assert len(presenter.shown) == 1

    monkeypatch.undo()
    container.view.retry_button.click()
    assert container.view.state() == "list"


def test_switching_company_closes_open_dialogs(
    container: SuppliersContainer, services: Services
) -> None:
    other = services.create_company.execute("SEGUNDA EMPRESA", "2")
    container.configure(list(SUPPLIERS))
    wizard = container.wizard
    assert wizard is not None

    container.set_company(other.id)

    assert container.wizard is None
    assert not wizard.isVisible()
    assert wizard.result() == QDialog.DialogCode.Rejected


def test_navigation_requests_of_the_view_are_forwarded(
    qtbot, make_container, services: Services
) -> None:
    company = services.create_company.execute("VACIA", "3")
    container = make_container()
    container.set_company(company.id)

    with qtbot.waitSignal(container.navigate_requested, timeout=1000) as blocker:
        container.view.empty_state.action_button.click()

    assert blocker.args == ["invoices"]


def test_the_header_button_configures_every_unconfigured_supplier(
    container: SuppliersContainer,
) -> None:
    container.view.configure_button.click()

    wizard = container.wizard
    assert wizard is not None
    assert wizard.step_count() == 3
    assert wizard.current_step().nit == SUPPLIERS[0][0]


def test_focus_search_reaches_the_view(container: SuppliersContainer) -> None:
    container.focus_search()

    # focusWidget() no exige ventana activa (en pantalla virtual no siempre lo esta)
    assert container.window().focusWidget() is container.view.search


# --- con el ejecutor real (hilo de trabajo) ----------------------------------------------------


def test_with_the_real_runner_loads_and_configures_from_the_worker_thread(
    qtbot, make_container, services: Services, company_id: int
) -> None:
    runner = QtTaskRunner()
    container = make_container(runner)
    try:
        container.set_company(company_id)
        qtbot.waitUntil(lambda: container.view.state() == "list", timeout=5000)
        assert container.view.visible_nits() == NITS_BY_NAME

        container.configure(list(SUPPLIERS[:1]))
        qtbot.waitUntil(lambda: container.wizard is not None, timeout=5000)
        wizard = container.wizard
        assert wizard is not None
        wizard.picker.set_checked("P-1", True)
        wizard.primary_button.click()

        qtbot.waitUntil(lambda: container.wizard is None, timeout=5000)
        qtbot.waitUntil(
            lambda: container.view.configure_button.text() == strings.configure_pending_action(2),
            timeout=5000,
        )
        assert services.suppliers.get(company_id, SUPPLIERS[0][0]) is not None
    finally:
        runner.shutdown()


def test_a_wizard_requested_for_a_previous_company_never_opens(
    make_container, services: Services, company_id: int
) -> None:
    other = services.create_company.execute("SEGUNDA EMPRESA", "2")
    runner = ManualRunner()
    container = make_container(runner)
    container.set_company(company_id)
    runner.run_next()
    container.configure(list(SUPPLIERS))
    container.set_company(other.id)

    runner.run_next()  # llega tarde la lectura del asistente de la primera empresa

    assert container.wizard is None
    container.configure(list(SUPPLIERS[:1]))  # la empresa nueva puede pedir el suyo
    while runner.queue:
        runner.run_next()
    assert container.wizard is not None
