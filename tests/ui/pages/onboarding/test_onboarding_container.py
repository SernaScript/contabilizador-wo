"""OnboardingContainer: step states computed from the services, actions routed to signals."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from contabilizador.catalog.application.use_cases import ListProducts
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.shared import strings
from contabilizador.ui import actions
from contabilizador.ui.composition import Services
from contabilizador.ui.pages.onboarding.container import (
    PAGE_CATALOGS,
    PAGE_INVOICES,
    OnboardingContainer,
)
from contabilizador.ui.pages.onboarding.view import STEP_CATALOG, STEP_COMPANY, STEP_IMPORT
from contabilizador.ui.tasks import QtTaskRunner, TaskRunner
from contabilizador.ui.widgets.toast import ToastHost
from tests.ui.pages.company.support import DeferredRunner, RecordingPresenter


def _container(
    qtbot,
    services: Services,
    runner: TaskRunner,
    presenter: RecordingPresenter,
    toasts: ToastHost,
) -> OnboardingContainer:
    container = OnboardingContainer(services, runner, presenter, toasts)
    qtbot.addWidget(container)
    container.resize(900, 640)
    container.show()
    return container


def _states(container: OnboardingContainer) -> list[str]:
    return [row.state for row in container.view.steps()]


def _locked(container: OnboardingContainer) -> list[bool]:
    return [row.locked for row in container.view.steps()]


def _company(services: Services, name: str = "EMPRESA DEMO S.A.S") -> int:
    company_id = services.create_company.execute(name, "1017").id
    assert company_id is not None
    return company_id


def _fill_catalog(services: Services, company_id: int) -> None:
    services.save_product.execute(company_id, "P-1", "Papelería")
    services.save_cost_center.execute(company_id, "CC-1", "Administración")


def _import_invoices(services: Services, company_id: int, xml_dir: Path) -> None:
    services.import_invoices.execute(company_id, [xml_dir])


def test_it_exposes_the_requests_the_main_window_wires(
    qtbot, services, runner, presenter, toasts
) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)

    for signal in ("create_company_requested", "navigate_requested", "import_requested"):
        assert hasattr(container, signal), signal


def test_the_destinations_are_real_pages() -> None:
    assert PAGE_CATALOGS in actions.PAGE_ORDER
    assert PAGE_INVOICES in actions.PAGE_ORDER


def test_without_a_company_only_creating_one_is_possible(
    qtbot, services, runner, presenter, toasts
) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(None)

    assert _states(container) == ["current", "todo", "todo"]
    assert _locked(container) == [False, True, True]


def test_a_new_company_completes_the_first_step_and_points_to_the_catalog(
    qtbot, services, runner, presenter, toasts
) -> None:
    company_id = _company(services)
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(company_id)

    assert _states(container) == ["done", "current", "todo"]
    assert _locked(container) == [False, False, False]
    assert container.view.step(STEP_CATALOG).detail_label.isHidden()


def test_the_catalog_step_needs_both_products_and_cost_centers(
    qtbot, services, runner, presenter, toasts
) -> None:
    company_id = _company(services)
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company_id)
    catalog = container.view.step(STEP_CATALOG)

    services.save_product.execute(company_id, "P-1", "Papelería")
    container.refresh()
    assert catalog.state == "current"
    assert catalog.detail_label.text() == strings.ONBOARDING_MISSING_COST_CENTERS

    services.save_cost_center.execute(company_id, "CC-1", "Administración")
    container.refresh()
    assert catalog.state == "done"
    assert catalog.detail_label.isHidden()


def test_only_cost_centers_loaded_asks_for_products(
    qtbot, services, runner, presenter, toasts
) -> None:
    company_id = _company(services)
    services.save_cost_center.execute(company_id, "CC-1", "Administración")
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(company_id)

    assert (
        container.view.step(STEP_CATALOG).detail_label.text() == strings.ONBOARDING_MISSING_PRODUCTS
    )


def test_importing_invoices_completes_the_last_step(
    qtbot, services, runner, presenter, toasts, xml_fixtures_dir: Path
) -> None:
    company_id = _company(services)
    _fill_catalog(services, company_id)
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company_id)
    assert _states(container) == ["done", "done", "current"]
    assert container.view.all_done is False

    _import_invoices(services, company_id, xml_fixtures_dir)
    container.refresh()

    assert _states(container) == ["done", "done", "done"]
    assert container.view.all_done is True
    assert not container.view.finish_panel.isHidden()


def test_invoices_that_were_already_exported_still_count_as_imported(
    qtbot, services, runner, presenter, toasts, xml_fixtures_dir: Path
) -> None:
    company_id = _company(services)
    _import_invoices(services, company_id, xml_fixtures_dir)
    cufes = [
        document.invoice.document.cufe
        for document in services.list_pending.execute(company_id).documents
    ]
    services.invoices.set_status(company_id, cufes, InvoiceStatus.EXPORTED)
    assert services.list_pending.execute(company_id).documents == ()
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(company_id)

    assert container.view.step(STEP_IMPORT).state == "done"


def test_progress_is_per_company(qtbot, services, runner, presenter, toasts) -> None:
    equipped = _company(services, "CON CATALOGO")
    empty = _company(services, "SIN CATALOGO")
    _fill_catalog(services, equipped)
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(equipped)
    assert container.view.step(STEP_CATALOG).state == "done"

    container.set_company(empty)
    assert container.view.step(STEP_CATALOG).state == "current"


def test_going_back_to_no_company_restores_the_first_run_state(
    qtbot, services, runner, presenter, toasts
) -> None:
    company_id = _company(services)
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company_id)

    container.set_company(None)

    assert _states(container) == ["current", "todo", "todo"]
    assert _locked(container) == [False, True, True]


def test_each_button_asks_the_window_for_the_right_thing(
    qtbot, services, runner, presenter, toasts
) -> None:
    company_id = _company(services)
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(None)
    with qtbot.waitSignal(container.create_company_requested):
        container.view.step(STEP_COMPANY).action_button.click()

    container.set_company(company_id)
    with qtbot.waitSignal(container.navigate_requested) as catalogs:
        container.view.step(STEP_CATALOG).action_button.click()
    with qtbot.waitSignal(container.import_requested):
        container.view.step(STEP_IMPORT).action_button.click()

    assert catalogs.args == [PAGE_CATALOGS]


def test_finishing_goes_to_the_invoices_page(
    qtbot, services, runner, presenter, toasts, xml_fixtures_dir: Path
) -> None:
    company_id = _company(services)
    _fill_catalog(services, company_id)
    _import_invoices(services, company_id, xml_fixtures_dir)
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company_id)

    with qtbot.waitSignal(container.navigate_requested) as blocker:
        container.view.finish_button.click()

    assert blocker.args == [PAGE_INVOICES]


def test_an_action_that_needs_a_company_explains_instead_of_doing_nothing(
    qtbot, services, runner, presenter, toasts
) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(None)

    with (
        qtbot.assertNotEmitted(container.navigate_requested),
        qtbot.assertNotEmitted(container.import_requested),
    ):
        container.view.step_triggered.emit(STEP_CATALOG)
        container.view.step_triggered.emit(STEP_IMPORT)

    assert [toast.message() for toast in toasts.toasts()] == [
        strings.ONBOARDING_NEEDS_COMPANY,
        strings.ONBOARDING_NEEDS_COMPANY,
    ]


def test_the_window_can_ask_for_the_same_explanation(
    qtbot, services, runner, presenter, toasts
) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)

    container.explain_needs_company()

    toast = toasts.toasts()[0]
    assert toast.message() == strings.ONBOARDING_NEEDS_COMPANY
    assert toast.kind == "warning"


def test_a_late_result_for_a_previous_company_is_dropped(
    qtbot, services, deferred: DeferredRunner, presenter, toasts
) -> None:
    equipped = _company(services, "CON CATALOGO")
    empty = _company(services, "SIN CATALOGO")
    _fill_catalog(services, equipped)
    container = _container(qtbot, services, deferred, presenter, toasts)

    container.set_company(equipped)
    container.set_company(empty)
    deferred.run(1)  # primero llega la carga de la empresa vacia
    deferred.run(0)  # la de la anterior llega tarde

    assert container.view.step(STEP_CATALOG).state == "current"


def test_refresh_without_a_company_does_nothing(
    qtbot, services, deferred: DeferredRunner, presenter, toasts
) -> None:
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(None)

    container.refresh()

    assert deferred.pending == []


def test_a_failed_load_goes_to_the_error_presenter(
    qtbot, services, runner, presenter, toasts
) -> None:
    company_id = _company(services)

    class Failing:
        def execute(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("database is locked")

    broken = replace(services, list_products=cast(ListProducts, Failing()))
    container = _container(qtbot, broken, runner, presenter, toasts)

    container.set_company(company_id)

    assert [type(error) for error in presenter.shown] == [RuntimeError]


def test_jobs_run_through_the_runner_with_the_container_as_owner(
    qtbot, services, deferred: DeferredRunner, presenter, toasts
) -> None:
    company_id = _company(services)
    container = _container(qtbot, services, deferred, presenter, toasts)

    container.set_company(company_id)

    assert len(deferred.pending) == 1
    assert deferred.pending[0].owner is container


def test_it_loads_the_progress_on_a_real_worker_thread(qtbot, services, presenter, toasts) -> None:
    company_id = _company(services)
    _fill_catalog(services, company_id)
    threaded = QtTaskRunner()
    try:
        container = _container(qtbot, services, threaded, presenter, toasts)
        container.set_company(company_id)

        qtbot.waitUntil(lambda: container.view.step(STEP_CATALOG).state == "done", timeout=5000)

        assert presenter.shown == []
    finally:
        threaded.shutdown()
