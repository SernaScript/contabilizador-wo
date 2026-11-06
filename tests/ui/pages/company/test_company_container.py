"""CompanyContainer: loads and saves the selected company through the task runner."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from contabilizador.companies.application.use_cases import ListCompanies, UpdateCompany
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.exports.infrastructure.repositories import SqlAlchemyConsecutiveRepository
from contabilizador.shared import strings
from contabilizador.shared.db import create_session_factory
from contabilizador.ui.composition import Services
from contabilizador.ui.pages.company.container import CompanyContainer
from contabilizador.ui.pages.company.form import CompanyValues
from contabilizador.ui.tasks import QtTaskRunner, TaskRunner
from contabilizador.ui.widgets.toast import ToastHost
from tests.ui.pages.company.support import RecordingPresenter


class Failing:
    """Stand-in use case that always raises and counts how often it was called."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise self.error


def _container(
    qtbot,
    services: Services,
    runner: TaskRunner,
    presenter: RecordingPresenter,
    toasts: ToastHost,
) -> CompanyContainer:
    container = CompanyContainer(services, runner, presenter, toasts)
    qtbot.addWidget(container)
    container.resize(900, 640)
    container.show()
    return container


def _use_last_numbers(services: Services, company_id: int, **numbers: int) -> None:
    repository = SqlAlchemyConsecutiveRepository(create_session_factory(services.engine))
    for kind, number in numbers.items():
        repository.set_last_used(company_id, DocumentType(kind.upper()), number)


def _names(services: Services) -> list[str]:
    return [company.name for company in services.list_companies.execute()]


def test_it_follows_the_page_container_contract(qtbot, services, runner, presenter, toasts) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)

    for signal in ("changed", "badge_changed", "navigate_requested", "create_company_requested"):
        assert hasattr(container, signal), signal


def test_nothing_is_shown_until_a_company_is_set(qtbot, services, runner, presenter, toasts):
    container = _container(qtbot, services, runner, presenter, toasts)

    assert container.view.form.isVisible() is False
    assert container.view.is_empty is False


def test_without_a_company_the_page_invites_to_create_one(
    qtbot, services, runner, presenter, toasts
) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(None)

    assert container.view.is_empty is True
    with qtbot.waitSignal(container.create_company_requested):
        container.view.empty_state.action_button.click()


def test_set_company_loads_the_form_from_the_database(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute(
        "EMPRESA DEMO S.A.S", "1017", "Bodega 2", "Kg", "Contado"
    )
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(company.id)

    assert container.view.form.values() == CompanyValues(
        "EMPRESA DEMO S.A.S", "1017", "Bodega 2", "Kg", "Contado"
    )
    assert container.view.is_dirty() is False


def test_consecutives_show_the_last_number_used_per_document_type(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    assert company.id is not None
    _use_last_numbers(services, company.id, fc=5748)
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(company.id)

    assert container.view.fc_value.text() == "5748"
    assert container.view.nc_value.text() == strings.COMPANY_CONSECUTIVE_NONE


def test_a_company_that_no_longer_exists_shows_the_empty_state(
    qtbot, services, runner, presenter, toasts
) -> None:
    container = _container(qtbot, services, runner, presenter, toasts)

    container.set_company(999)

    assert container.view.is_empty is True


def test_save_updates_the_company_and_confirms_with_a_toast(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company.id)
    saved: list[int] = []
    container.changed.connect(lambda: saved.append(1))
    form = container.view.form
    form.name_edit.setText("NUEVO NOMBRE S.A.S")
    form.warehouse_edit.setText("Bodega 2")
    form.unit_edit.setText("Kg")
    form.payment_edit.setText("Contado")

    container.view.save_button.click()

    stored = services.list_companies.execute()[0]
    assert (stored.name, stored.warehouse, stored.unit, stored.payment_form) == (
        "NUEVO NOMBRE S.A.S",
        "Bodega 2",
        "Kg",
        "Contado",
    )
    assert saved == [1]
    assert [toast.message() for toast in toasts.toasts()] == [strings.COMPANY_SAVED]
    assert toasts.toasts()[0].kind == "success"
    assert container.view.is_dirty() is False
    assert container.view.save_button.isEnabled() is False


def test_a_duplicate_name_is_explained_next_to_the_field(
    qtbot, services, runner, presenter, toasts
) -> None:
    services.create_company.execute("OTRA EMPRESA", "1")
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company.id)
    saved: list[int] = []
    container.changed.connect(lambda: saved.append(1))
    # mismas letras que otra empresa aunque cambien mayusculas y espacios
    container.view.form.name_edit.setText("otra   empresa")

    container.view.save_button.click()

    form = container.view.form
    assert form.name_error_label.text() == strings.COMPANY_NAME_DUPLICATED
    assert form.name_edit.property("invalid") == "true"
    assert presenter.shown == []
    assert toasts.toasts() == []
    assert saved == []
    assert sorted(_names(services)) == ["EMPRESA DEMO S.A.S", "OTRA EMPRESA"]
    # Sigue editable para corregir el nombre
    assert container.view.save_button.isEnabled() is True
    assert form.isEnabled() is True


def test_other_errors_go_to_the_error_presenter_and_keep_the_edits(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    broken = replace(
        services, update_company=cast(UpdateCompany, Failing(RuntimeError("database is locked")))
    )
    container = _container(qtbot, broken, runner, presenter, toasts)
    container.set_company(company.id)
    saved: list[int] = []
    container.changed.connect(lambda: saved.append(1))
    container.view.form.unit_edit.setText("Kg")

    container.view.save_button.click()

    assert [type(error) for error in presenter.shown] == [RuntimeError]
    assert saved == []
    assert toasts.toasts() == []
    assert container.view.form.unit_edit.text() == "Kg"
    assert container.view.save_button.isEnabled() is True


def test_a_blank_name_never_reaches_the_use_case(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    spy = Failing(RuntimeError("must not be called"))
    spied = replace(services, update_company=cast(UpdateCompany, spy))
    container = _container(qtbot, spied, runner, presenter, toasts)
    container.set_company(company.id)
    container.view.form.name_edit.setText("   ")

    container.view.save_button.click()

    assert spy.calls == 0
    assert container.view.form.name_error_label.text() == strings.COMPANY_NAME_REQUIRED


def test_a_second_save_while_one_is_running_is_ignored(
    qtbot, services, deferred, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(company.id)
    deferred.run()
    container.view.form.unit_edit.setText("Kg")
    values = container.view.form.values()

    container.view.save_requested.emit(values)
    container.view.save_requested.emit(values)

    assert len(deferred.pending) == 1
    assert container.view.save_button.isEnabled() is False
    deferred.run()
    assert container.view.save_button.isEnabled() is False  # nada pendiente de guardar


def test_a_save_for_another_company_is_not_blocked_by_one_still_running(
    qtbot, services, deferred, presenter, toasts
) -> None:
    first = services.create_company.execute("PRIMERA S.A.S", "1")
    second = services.create_company.execute("SEGUNDA S.A.S", "2")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(first.id)
    deferred.run()
    container.view.form.name_edit.setText("PRIMERA RENOMBRADA")
    container.view.save_button.click()  # guardado de la primera, aun en curso
    container.set_company(second.id)
    deferred.run(1)  # llega la carga de la segunda
    container.view.form.name_edit.setText("SEGUNDA RENOMBRADA")

    container.view.save_button.click()

    assert len(deferred.pending) == 2
    deferred.run()
    deferred.run()
    assert sorted(_names(services)) == ["PRIMERA RENOMBRADA", "SEGUNDA RENOMBRADA"]


def test_a_refresh_while_saving_does_not_leave_the_form_dirty(
    qtbot, services, deferred, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(company.id)
    deferred.run()
    container.view.form.name_edit.setText("NUEVO NOMBRE S.A.S")
    container.view.save_button.click()

    container.refresh()  # p. ej. otra pagina avisa de un cambio mientras se guarda
    deferred.run(0)  # termina el guardado
    deferred.run(0)  # llega la recarga

    assert container.view.is_dirty() is False
    assert container.view.form.name_edit.text() == "NUEVO NOMBRE S.A.S"
    assert container.view.save_button.isEnabled() is False


def test_a_save_that_ends_after_a_refresh_arrived_first_still_cleans_the_form(
    qtbot, services, deferred, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(company.id)
    deferred.run()
    container.view.form.name_edit.setText("NUEVO NOMBRE S.A.S")
    container.view.save_button.click()

    container.refresh()
    deferred.run(1)  # la recarga llega antes que el final del guardado
    deferred.run(0)

    assert container.view.is_dirty() is False
    assert container.view.save_button.isEnabled() is False


def test_edits_made_while_saving_are_kept(qtbot, services, deferred, presenter, toasts) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(company.id)
    deferred.run()
    container.view.form.name_edit.setText("NUEVO NOMBRE S.A.S")
    container.view.save_button.click()

    container.view.form.unit_edit.setText("Kg")  # el usuario sigue escribiendo
    deferred.run()

    assert services.list_companies.execute()[0].name == "NUEVO NOMBRE S.A.S"
    assert container.view.form.unit_edit.text() == "Kg"
    assert container.view.is_dirty() is True
    assert container.view.save_button.isEnabled() is True


def test_switching_company_hides_the_previous_one_until_the_new_data_arrives(
    qtbot, services, deferred, presenter, toasts
) -> None:
    first = services.create_company.execute("PRIMERA S.A.S", "1")
    second = services.create_company.execute("SEGUNDA S.A.S", "2")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(first.id)
    deferred.run()
    container.view.form.name_edit.setText("Editado")

    container.set_company(second.id)

    assert container.view.form.isVisible() is False
    assert container.view.save_button.isVisible() is False
    deferred.run()
    assert container.view.form.name_edit.text() == "SEGUNDA S.A.S"
    assert container.view.is_dirty() is False


def test_a_late_result_for_a_previous_company_is_dropped(
    qtbot, services, deferred, presenter, toasts
) -> None:
    first = services.create_company.execute("PRIMERA S.A.S", "1")
    second = services.create_company.execute("SEGUNDA S.A.S", "2")
    container = _container(qtbot, services, deferred, presenter, toasts)

    container.set_company(first.id)
    container.set_company(second.id)
    deferred.run(1)  # primero llega la carga de la segunda
    deferred.run(0)  # la de la primera llega tarde

    assert container.view.form.name_edit.text() == "SEGUNDA S.A.S"


def test_a_save_that_finishes_after_switching_company_confirms_but_leaves_the_new_form(
    qtbot, services, deferred, presenter, toasts
) -> None:
    first = services.create_company.execute("PRIMERA S.A.S", "1")
    second = services.create_company.execute("SEGUNDA S.A.S", "2")
    container = _container(qtbot, services, deferred, presenter, toasts)
    container.set_company(first.id)
    deferred.run()
    saved: list[int] = []
    container.changed.connect(lambda: saved.append(1))
    container.view.form.name_edit.setText("PRIMERA RENOMBRADA")
    container.view.save_button.click()

    container.set_company(second.id)
    deferred.run(0)  # termina el guardado de la primera
    deferred.run(0)  # llega la carga de la segunda

    assert "PRIMERA RENOMBRADA" in _names(services)
    assert saved == [1]
    assert [toast.message() for toast in toasts.toasts()] == [strings.COMPANY_SAVED]
    assert container.view.form.name_edit.text() == "SEGUNDA S.A.S"
    assert container.view.form.isEnabled() is True


def test_refresh_keeps_unsaved_edits_but_updates_the_consecutives(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    assert company.id is not None
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company.id)
    container.view.form.name_edit.setText("En edición")
    _use_last_numbers(services, company.id, fc=9, nc=2)

    container.refresh()

    assert container.view.form.name_edit.text() == "En edición"
    assert container.view.fc_value.text() == "9"
    assert container.view.nc_value.text() == "2"
    assert container.view.is_dirty() is True


def test_refresh_reloads_the_form_when_nothing_was_edited(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    assert company.id is not None
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company.id)
    services.update_company.execute(company.id, name="RENOMBRADA S.A.S")

    container.refresh()

    assert container.view.form.name_edit.text() == "RENOMBRADA S.A.S"


def test_setting_the_same_company_again_does_not_discard_edits(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(company.id)
    container.view.form.unit_edit.setText("Kg")

    container.set_company(company.id)

    assert container.view.form.unit_edit.text() == "Kg"


def test_refresh_without_a_company_does_nothing(qtbot, services, runner, presenter, toasts):
    container = _container(qtbot, services, runner, presenter, toasts)
    container.set_company(None)

    container.refresh()

    assert container.view.is_empty is True
    assert presenter.shown == []


def test_a_failed_load_goes_to_the_error_presenter(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    broken = replace(
        services, list_companies=cast(ListCompanies, Failing(RuntimeError("database is locked")))
    )
    container = _container(qtbot, broken, runner, presenter, toasts)

    container.set_company(company.id)

    assert [type(error) for error in presenter.shown] == [RuntimeError]


def test_jobs_run_through_the_runner_with_the_container_as_owner(
    qtbot, services, deferred, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    container = _container(qtbot, services, deferred, presenter, toasts)

    container.set_company(company.id)

    assert len(deferred.pending) == 1
    assert deferred.pending[0].owner is container


def test_it_loads_and_saves_on_a_real_worker_thread(qtbot, services, presenter, toasts) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    threaded = QtTaskRunner()
    try:
        container = _container(qtbot, services, threaded, presenter, toasts)
        container.set_company(company.id)
        qtbot.waitUntil(lambda: container.view.form.isVisible(), timeout=5000)
        assert container.view.form.name_edit.text() == "EMPRESA DEMO S.A.S"

        container.view.form.unit_edit.setText("Kg")
        container.view.save_button.click()
        qtbot.waitUntil(lambda: len(toasts.toasts()) == 1, timeout=5000)

        assert services.list_companies.execute()[0].unit == "Kg"
        assert toasts.toasts()[0].message() == strings.COMPANY_SAVED
        assert presenter.shown == []
    finally:
        threaded.shutdown()
