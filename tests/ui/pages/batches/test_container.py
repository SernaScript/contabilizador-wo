"""BatchesContainer: lists the company's batches, voids and releases through the runner,
and keeps the selection while the data changes underneath."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.errors import DocumentAlreadyReleasedError
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import CONTEXT_EXPORT
from contabilizador.ui.pages.batches.container import BatchesContainer
from contabilizador.ui.pages.batches.rows import ranges_sentence, void_plan
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import QtTaskRunner
from contabilizador.ui.widgets import ToastHost
from tests.ui.pages.batches.support import ManualRunner, seed_batches


@pytest.fixture
def make_container(qtbot, services, runner, presenter, host, revealed):
    window, toasts = host

    def build(*, task_runner=None, settings=None) -> BatchesContainer:
        container = BatchesContainer(
            services,
            task_runner or runner,
            presenter,
            toasts,
            reveal_file=revealed.append,
            settings=settings,
            parent=window,
        )
        container.setGeometry(0, 0, 1100, 760)
        container.show()
        return container

    return build


def toast_messages(toasts: ToastHost) -> list[str]:
    return [toast.message() for toast in toasts.toasts()]


def doc_cufes(container: BatchesContainer) -> list[str]:
    model = container.view.documents_model
    return [model.row_at(row).cufe for row in range(model.rowCount())]  # type: ignore[union-attr]


def fresh(services: Services, company_id: int) -> list[Batch]:
    return services.list_batches.execute(company_id)


# --- carga ----------------------------------------------------------------------


def test_without_a_company_the_page_asks_for_one(make_container) -> None:
    container = make_container()

    container.set_company(None)

    assert container.view.state() == "no_company"


def test_without_batches_the_empty_state_leads_to_facturas(make_container, company_id) -> None:
    container = make_container()
    asked: list[str] = []
    container.navigate_requested.connect(asked.append)

    container.set_company(company_id)
    assert container.view.state() == "empty"
    container.view.empty.action_button.click()

    assert asked == ["invoices"]


def test_lists_the_batches_newest_first_and_selects_the_newest(
    make_container, company_id, batches
) -> None:
    container = make_container()
    badges: list[int] = []
    container.badge_changed.connect(badges.append)

    container.set_company(company_id)

    view = container.view
    assert view.state() == "list"
    assert [view.batches_model.row_at(i).batch_id for i in range(2)] == [  # type: ignore[union-attr]
        batches[0].id,
        batches[1].id,
    ]
    assert view.selected_batch_id() == batches[0].id
    assert view.detail_title.text() == strings.batch_title(batches[0].id or 0)
    assert len(doc_cufes(container)) == len(batches[0].documents)
    assert badges == [0]


def test_other_companies_batches_are_not_shown(
    make_container, services, company_id, batches
) -> None:
    other = services.create_company.execute("OTRA S.A.S", "1").id
    assert other is not None
    container = make_container()

    container.set_company(other)

    assert container.view.state() == "empty"


def test_a_late_answer_for_the_previous_company_is_dropped(
    make_container, services, company_id, batches
) -> None:
    other = services.create_company.execute("OTRA S.A.S", "1").id
    assert other is not None
    manual = ManualRunner()
    container = make_container(task_runner=manual)

    container.set_company(company_id)
    container.set_company(other)
    manual.run_all()

    assert container.view.state() == "empty"


def test_refreshes_requested_while_loading_are_coalesced_into_one_more(
    make_container, company_id, batches
) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    assert len(manual.pending) == 1

    container.refresh()
    container.refresh()
    container.refresh()

    assert len(manual.pending) == 1  # ninguna carga extra mientras la primera sigue en curso
    manual.run_next()
    assert len(manual.pending) == 1  # una sola recarga para todas las peticiones
    manual.run_next()
    assert manual.pending == []
    assert container.view.batches_model.rowCount() == 2


def test_a_refresh_after_the_load_finished_starts_a_new_one(make_container, company_id) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()

    container.refresh()

    assert len(manual.pending) == 1


def test_company_change_clears_the_old_rows_while_loading(
    make_container, company_id, batches
) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()
    assert container.view.batches_model.rowCount() == 2

    container.set_company(company_id)

    assert container.view.batches_model.rowCount() == 0
    assert container.view.state() == "list"  # cargando: no se afirma que no haya lotes


def test_a_failed_refresh_goes_to_the_error_presenter(
    make_container, services, company_id, presenter, monkeypatch
) -> None:
    def boom(_company_id: int) -> list[Batch]:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(services.list_batches, "execute", boom)
    container = make_container()

    container.set_company(company_id)

    assert [type(error) for error, _context in presenter.shown] == [RuntimeError]


def test_loads_in_a_worker_thread_with_the_real_runner(
    qtbot, make_container, company_id, batches
) -> None:
    task_runner = QtTaskRunner()
    try:
        container = make_container(task_runner=task_runner)

        container.set_company(company_id)

        qtbot.waitUntil(lambda: container.view.batches_model.rowCount() == 2, timeout=5000)
        assert container.view.selected_batch_id() == batches[0].id
    finally:
        task_runner.shutdown()


# --- anular ---------------------------------------------------------------------


def test_voiding_the_last_batch_says_the_consecutives_come_back(
    qtbot, make_container, services, company_id, batches, host
) -> None:
    _window, toasts = host
    last = batches[0]
    container = make_container()
    container.set_company(company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))

    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)

    plan = void_plan(last, batches)
    confirmation = container.confirmation
    assert confirmation is not None
    assert plan.returns_numbers
    assert confirmation.title_label.text() == strings.confirm_void_title(last.id or 0)
    assert confirmation.message_label.text() == strings.confirm_void_documents(len(last.documents))
    assert confirmation.emphasis_label is not None
    assert confirmation.emphasis_label.text() == strings.confirm_void_returns(
        ranges_sentence(last), plan.numbers
    )
    assert confirmation.primary_button.text() == strings.ACTION_VOID_BATCH
    assert not fresh(services, company_id)[0].is_voided

    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    voided = fresh(services, company_id)[0]
    assert voided.is_voided
    assert voided.numbers_reused
    assert container.confirmation is None
    assert toast_messages(toasts) == [strings.batch_voided(last.id or 0, returned=True)]
    assert toasts.toasts()[0].action_button.text() == strings.BATCH_ACTION_SEE_INVOICES
    assert changes == [1]
    # el lote sigue seleccionado y ahora muestra su nuevo estado
    assert container.view.selected_batch_id() == last.id
    assert container.view.detail_pill.text == strings.BATCH_STATUS_VOIDED_RETURNED
    assert not container.view.void_button.isEnabled()
    # el consecutivo vuelve al inicio del rango anulado
    last_fc = min(r.first for t, r in last.ranges.items() if t is DocumentType.FC)
    assert services.plan_consecutives.suggest(company_id, DocumentType.FC) == last_fc


def test_voiding_an_older_batch_says_the_consecutives_stay_used(
    qtbot, make_container, services, company_id, batches, host
) -> None:
    _window, toasts = host
    older, newer = batches[1], batches[0]
    container = make_container()
    container.set_company(company_id)
    container.view.select_batch(older.id or 0)

    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)

    plan = void_plan(older, batches)
    confirmation = container.confirmation
    assert confirmation is not None
    assert not plan.returns_numbers
    assert plan.later_batch_id == newer.id
    assert confirmation.emphasis_label is not None
    assert confirmation.emphasis_label.text() == strings.confirm_void_keeps(
        ranges_sentence(older), plan.numbers, newer.id or 0
    )
    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    voided = next(b for b in fresh(services, company_id) if b.id == older.id)
    assert voided.is_voided
    assert not voided.numbers_reused
    assert toast_messages(toasts) == [strings.batch_voided(older.id or 0, returned=False)]
    assert container.view.selected_batch_id() == older.id
    assert container.view.detail_pill.text == strings.BATCH_STATUS_VOIDED


def test_cancelling_the_void_confirmation_changes_nothing(
    qtbot, make_container, services, company_id, batches, host
) -> None:
    _window, toasts = host
    container = make_container()
    container.set_company(company_id)
    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None

    qtbot.mouseClick(confirmation.cancel_button, Qt.MouseButton.LeftButton)

    assert container.confirmation is None
    assert not any(b.is_voided for b in fresh(services, company_id))
    assert toast_messages(toasts) == []


def test_a_batch_voided_elsewhere_is_not_confirmed_again(
    qtbot, make_container, services, company_id, batches, host
) -> None:
    _window, toasts = host
    container = make_container()
    container.set_company(company_id)
    services.void_batch.execute(
        batches[0].id or 0
    )  # otra via la anulo mientras la lista seguia abierta

    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)

    assert container.confirmation is None
    assert toast_messages(toasts) == [strings.BATCH_ALREADY_VOIDED]
    assert toasts.toasts()[0].kind == "warning"
    assert container.view.detail_pill.text == strings.BATCH_STATUS_VOIDED_RETURNED


def test_void_failure_goes_to_the_presenter_and_the_list_refreshes(
    qtbot, make_container, services, company_id, batches, presenter, monkeypatch
) -> None:
    def boom(_batch_id: int) -> Batch:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(services.void_batch, "execute", boom)
    container = make_container()
    container.set_company(company_id)
    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None

    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    assert [type(error) for error, _context in presenter.shown] == [RuntimeError]
    assert container.view.void_button.isEnabled()


# --- liberar --------------------------------------------------------------------


def test_releasing_asks_first_then_frees_only_the_selected_invoices(
    qtbot, make_container, services, company_id, batches, host
) -> None:
    _window, toasts = host
    newest = batches[0]
    container = make_container()
    container.set_company(company_id)
    changes: list[int] = []
    container.changed.connect(lambda: changes.append(1))
    chosen = [d.cufe for d in newest.documents][:2]
    container.view.select_cufes(chosen)
    pending_before = len(services.list_pending.execute(company_id).documents)

    qtbot.mouseClick(container.view.release_button, Qt.MouseButton.LeftButton)

    confirmation = container.confirmation
    assert confirmation is not None
    assert confirmation.title_label.text() == strings.confirm_release_title(2)
    assert confirmation.message_label.text() == strings.confirm_release_message(2)
    assert [label.text() for label in confirmation.note_labels] == [strings.CONFIRM_RELEASE_NOTE]
    assert confirmation.primary_button.text() == strings.ACTION_RELEASE_INVOICES

    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    released = next(b for b in fresh(services, company_id) if b.id == newest.id)
    assert sorted(d.cufe for d in released.released_documents) == sorted(chosen)
    assert len(services.list_pending.execute(company_id).documents) == pending_before + 2
    assert toast_messages(toasts) == [strings.documents_released(2)]
    assert toasts.toasts()[0].action_button.text() == strings.BATCH_ACTION_SEE_INVOICES
    assert changes == [1]
    # el lote sigue seleccionado, ahora parcial, y lo liberado ya no se puede volver a elegir
    assert container.view.selected_batch_id() == newest.id
    assert container.view.detail_pill.text == strings.BATCH_STATUS_PARTIAL
    assert container.view.selected_cufes() == []
    assert not container.view.release_button.isEnabled()


def test_releasing_every_invoice_leaves_the_batch_partial_and_selected(
    qtbot, make_container, services, company_id, batches
) -> None:
    newest = batches[0]
    container = make_container()
    container.set_company(company_id)
    cufes = [d.cufe for d in newest.documents]
    container.view.select_cufes(cufes)
    qtbot.mouseClick(container.view.release_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None
    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    assert container.view.detail_pill.text == strings.BATCH_STATUS_PARTIAL
    assert container.view.selected_batch_id() == newest.id


def test_cancelling_the_release_changes_nothing(
    qtbot, make_container, services, company_id, batches
) -> None:
    container = make_container()
    container.set_company(company_id)
    container.view.select_cufes([batches[0].documents[0].cufe])
    qtbot.mouseClick(container.view.release_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None

    qtbot.mouseClick(confirmation.cancel_button, Qt.MouseButton.LeftButton)

    assert not fresh(services, company_id)[0].released_documents


def test_releasing_what_was_already_released_goes_to_the_presenter_and_refreshes(
    qtbot, make_container, services, company_id, batches, presenter
) -> None:
    newest = batches[0]
    cufe = newest.documents[0].cufe
    container = make_container()
    container.set_company(company_id)
    container.view.select_cufes([cufe])
    services.release_documents.execute(newest.id or 0, [cufe])  # otra via ya la libero

    qtbot.mouseClick(container.view.release_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None
    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    assert [type(error) for error, _context in presenter.shown] == [DocumentAlreadyReleasedError]
    assert container.view.detail_pill.text == strings.BATCH_STATUS_PARTIAL
    assert container.view.selected_cufes() == []


# --- mostrar archivo -------------------------------------------------------------


def test_show_file_hands_the_resolved_absolute_path_to_the_opener(
    qtbot, make_container, services, company_id, revealed, tmp_path, xml_fixtures_dir
) -> None:
    # el destino queda guardado con ".." en la ruta: el abridor debe recibirla ya resuelta
    crooked = tmp_path / "salidas" / ".." / "salidas"
    seed_batches(services, company_id, xml_fixtures_dir, crooked)
    stored = fresh(services, company_id)[0].file_path
    assert ".." in stored.parts
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.show_file_button, Qt.MouseButton.LeftButton)

    assert revealed == [stored.resolve()]
    assert revealed[0].is_absolute()
    assert ".." not in revealed[0].parts


def test_show_file_warns_when_the_file_was_moved_or_deleted(
    qtbot, make_container, company_id, batches, revealed, host
) -> None:
    _window, toasts = host
    batches[0].file_path.unlink()
    container = make_container()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.show_file_button, Qt.MouseButton.LeftButton)

    assert revealed == []
    assert toast_messages(toasts) == [strings.BATCH_FILE_MISSING]
    assert toasts.toasts()[0].kind == "warning"


def test_an_opener_that_fails_goes_to_the_presenter(
    qtbot, services, runner, presenter, host, company_id, batches
) -> None:
    window, toasts = host

    def broken(_path: Path) -> None:
        raise OSError("no file manager")

    container = BatchesContainer(
        services, runner, presenter, toasts, reveal_file=broken, parent=window
    )
    container.setGeometry(0, 0, 1100, 760)
    container.show()
    container.set_company(company_id)

    qtbot.mouseClick(container.view.show_file_button, Qt.MouseButton.LeftButton)

    assert [type(error) for error, _context in presenter.shown] == [OSError]
    assert presenter.shown[0][1] == CONTEXT_EXPORT


# --- estado ocupado y navegacion --------------------------------------------------------


def test_actions_stay_locked_while_a_task_runs(qtbot, make_container, company_id, batches) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()

    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)

    assert not container.view.void_button.isEnabled()  # esperando la comprobacion previa
    manual.run_all()
    assert container.confirmation is not None
    assert container.view.void_button.isEnabled()


def test_busy_changed_brackets_voiding_so_the_company_switcher_can_lock(
    qtbot, make_container, company_id, batches
) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()
    states: list[bool] = []
    container.busy_changed.connect(states.append)

    qtbot.mouseClick(container.view.void_button, Qt.MouseButton.LeftButton)
    manual.run_all()  # comprobacion previa
    assert states == [True, False]
    confirmation = container.confirmation
    assert confirmation is not None
    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)
    assert states == [True, False, True]
    manual.run_all()

    assert states == [True, False, True, False]


def test_the_parent_can_be_passed_positionally_like_in_the_other_containers(
    qtbot, services, runner, presenter, host
) -> None:
    window, toasts = host

    container = BatchesContainer(services, runner, presenter, toasts, window)

    assert container.parentWidget() is window


def test_two_quick_void_clicks_open_one_confirmation(
    qtbot, make_container, company_id, batches
) -> None:
    manual = ManualRunner()
    container = make_container(task_runner=manual)
    container.set_company(company_id)
    manual.run_all()

    container.view.void_requested.emit(batches[0].id or 0)
    container.view.void_requested.emit(batches[0].id or 0)
    manual.run_all()

    assert container.confirmation is not None
    assert len(container.findChildren(type(container.confirmation))) == 1


def test_the_toast_action_goes_to_facturas(
    qtbot, make_container, company_id, batches, host
) -> None:
    _window, toasts = host
    container = make_container()
    container.set_company(company_id)
    asked: list[str] = []
    container.navigate_requested.connect(asked.append)
    container.view.select_cufes([batches[0].documents[0].cufe])
    qtbot.mouseClick(container.view.release_button, Qt.MouseButton.LeftButton)
    confirmation = container.confirmation
    assert confirmation is not None
    qtbot.mouseClick(confirmation.primary_button, Qt.MouseButton.LeftButton)

    toasts.toasts()[0].action_button.click()

    assert asked == ["invoices"]


# --- distribucion persistida ---------------------------------------------------------


def test_the_split_between_list_and_detail_is_remembered(
    qtbot, make_container, company_id, batches, tmp_path
) -> None:
    settings = AppSettings.in_file(tmp_path / "ui.ini")
    first = make_container(settings=settings)
    first.set_company(company_id)
    first.view.splitter.setSizes([320, 280])
    first.view.splitter.splitterMoved.emit(320, 1)
    chosen = first.view.splitter.sizes()

    assert settings.splitter_state("batches") is not None

    second = make_container(settings=settings)
    second.set_company(company_id)
    restored = second.view.splitter.sizes()
    assert abs(restored[0] - chosen[0]) <= 4
    assert restored[0] != 230  # no es la distribucion inicial
