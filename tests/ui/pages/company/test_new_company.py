"""NewCompanyDialog (presentational Sheet) and NewCompanyFlow (container that creates it)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget

from contabilizador.companies.application.use_cases import CreateCompany
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.pages.company.form import CompanyValues
from contabilizador.ui.pages.company.new_company_dialog import NewCompanyDialog
from contabilizador.ui.pages.company.new_company_flow import NewCompanyFlow
from contabilizador.ui.tasks import TaskRunner
from contabilizador.ui.widgets.toast import ToastHost
from tests.ui.pages.company.support import DeferredRunner, RecordingPresenter

# --- dialog ------------------------------------------------------------------


def _dialog(qtbot) -> NewCompanyDialog:
    dialog = NewCompanyDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_names_the_action_and_explains_what_to_type(qtbot) -> None:
    dialog = _dialog(qtbot)

    assert dialog.title_label.text() == strings.ACTION_NEW_COMPANY
    assert dialog.subtitle_label.text() == strings.NEW_COMPANY_PURPOSE
    assert dialog.primary_button.text() == strings.NEW_COMPANY_SUBMIT
    assert dialog.cancel_button.text() == strings.ACTION_CANCEL


def test_dialog_starts_with_the_defaults_and_the_cursor_in_the_name(qtbot) -> None:
    dialog = _dialog(qtbot)

    dialog.show()

    assert dialog.values() == CompanyValues.defaults()
    assert dialog.focusWidget() is dialog.form.name_edit


def test_submitting_a_blank_name_explains_it_and_emits_nothing(qtbot) -> None:
    dialog = _dialog(qtbot)

    with qtbot.assertNotEmitted(dialog.submitted):
        dialog.primary_button.click()

    assert dialog.form.name_error_label.text() == strings.COMPANY_NAME_REQUIRED
    assert dialog.result() == 0  # sigue abierto: no se acepto


def test_submitting_emits_the_trimmed_values_and_stays_open(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.show()
    dialog.form.name_edit.setText("  EMPRESA DEMO S.A.S ")
    dialog.form.third_party_edit.setText("1017")

    with qtbot.waitSignal(dialog.submitted) as blocker:
        dialog.primary_button.click()

    assert blocker.args == [
        CompanyValues("EMPRESA DEMO S.A.S", "1017", "Principal", "Und.", "Credito")
    ]
    assert dialog.isVisible() is True


def test_enter_in_the_name_field_submits(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.show()
    qtbot.keyClicks(dialog.form.name_edit, "EMPRESA DEMO S.A.S")

    with qtbot.waitSignal(dialog.submitted):
        qtbot.keyClick(dialog.form.name_edit, Qt.Key.Key_Return)


def test_busy_locks_the_footer_buttons_only(qtbot) -> None:
    dialog = _dialog(qtbot)

    dialog.set_busy(True)
    assert dialog.primary_button.isEnabled() is False
    assert dialog.cancel_button.isEnabled() is False
    # Los campos no parpadean en gris durante unos milisegundos
    assert dialog.form.isEnabled() is True

    dialog.set_busy(False)
    assert dialog.primary_button.isEnabled() is True
    assert dialog.cancel_button.isEnabled() is True


def test_show_name_error_marks_the_name_and_returns_the_cursor_to_it(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.show()
    dialog.form.unit_edit.setFocus()

    dialog.show_name_error(strings.COMPANY_NAME_DUPLICATED)

    assert dialog.form.name_error_label.text() == strings.COMPANY_NAME_DUPLICATED
    assert dialog.focusWidget() is dialog.form.name_edit


def test_cancel_rejects_the_dialog(qtbot) -> None:
    dialog = _dialog(qtbot)

    with qtbot.waitSignal(dialog.rejected):
        dialog.cancel_button.click()


# --- flow --------------------------------------------------------------------


class Failing:
    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.calls = 0

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        raise self.error


def _flow(
    services: Services,
    runner: TaskRunner,
    presenter: RecordingPresenter,
    toasts: ToastHost,
    host: QWidget,
) -> NewCompanyFlow:
    return NewCompanyFlow(services, runner, presenter, toasts, host)


def _fill(dialog: NewCompanyDialog, name: str, third_party: str = "1017") -> None:
    dialog.form.name_edit.setText(name)
    dialog.form.third_party_edit.setText(third_party)


def _names(services: Services) -> list[str]:
    return [company.name for company in services.list_companies.execute()]


def test_open_shows_the_dialog_over_the_window(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    flow = _flow(services, runner, presenter, toasts, host)

    dialog = flow.open()
    qtbot.addWidget(dialog)

    assert dialog.isVisible() is True
    assert dialog.parent() is host
    assert flow.dialog is dialog


def test_opening_again_reuses_the_dialog_that_is_already_open(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    flow = _flow(services, runner, presenter, toasts, host)
    first = flow.open()
    qtbot.addWidget(first)

    assert flow.open() is first


def test_creating_stores_the_company_announces_it_and_closes(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    flow = _flow(services, runner, presenter, toasts, host)
    created: list[int] = []
    flow.company_created.connect(created.append)
    dialog = flow.open()
    qtbot.addWidget(dialog)
    _fill(dialog, "EMPRESA DEMO S.A.S")
    dialog.form.warehouse_edit.setText("Bodega 2")
    dialog.form.unit_edit.setText("Kg")
    dialog.form.payment_edit.setText("Contado")

    dialog.primary_button.click()

    stored = services.list_companies.execute()
    assert [
        (c.name, c.internal_third_party_id, c.warehouse, c.unit, c.payment_form) for c in stored
    ] == [("EMPRESA DEMO S.A.S", "1017", "Bodega 2", "Kg", "Contado")]
    assert created == [stored[0].id]
    assert dialog.isVisible() is False
    assert flow.dialog is None
    assert [toast.message() for toast in toasts.toasts()] == [
        strings.company_created("EMPRESA DEMO S.A.S")
    ]
    assert toasts.toasts()[0].kind == "success"


def test_a_duplicate_name_stays_in_the_dialog_with_an_inline_error(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    services.create_company.execute("EMPRESA DEMO S.A.S", "1")
    flow = _flow(services, runner, presenter, toasts, host)
    created: list[int] = []
    flow.company_created.connect(created.append)
    dialog = flow.open()
    qtbot.addWidget(dialog)
    _fill(dialog, "empresa  demo s.a.s")

    dialog.primary_button.click()

    assert dialog.isVisible() is True
    assert dialog.form.name_error_label.text() == strings.COMPANY_NAME_DUPLICATED
    assert dialog.form.name_edit.property("invalid") == "true"
    assert presenter.shown == []
    assert toasts.toasts() == []
    assert created == []
    assert _names(services) == ["EMPRESA DEMO S.A.S"]
    # Se puede corregir y volver a intentar
    assert dialog.primary_button.isEnabled() is True
    assert dialog.form.isEnabled() is True


def test_other_errors_go_to_the_error_presenter_and_the_dialog_stays_open(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    broken = replace(
        services, create_company=cast(CreateCompany, Failing(RuntimeError("database is locked")))
    )
    flow = _flow(broken, runner, presenter, toasts, host)
    dialog = flow.open()
    qtbot.addWidget(dialog)
    _fill(dialog, "EMPRESA DEMO S.A.S")

    dialog.primary_button.click()

    assert [type(error) for error in presenter.shown] == [RuntimeError]
    assert dialog.isVisible() is True
    assert dialog.primary_button.isEnabled() is True
    assert toasts.toasts() == []


def test_a_blank_name_never_reaches_the_use_case(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    spy = Failing(RuntimeError("must not be called"))
    flow = _flow(
        replace(services, create_company=cast(CreateCompany, spy)), runner, presenter, toasts, host
    )
    dialog = flow.open()
    qtbot.addWidget(dialog)

    dialog.primary_button.click()

    assert spy.calls == 0
    assert dialog.form.name_error_label.text() == strings.COMPANY_NAME_REQUIRED


def test_cancelling_creates_nothing_and_a_new_open_starts_from_the_defaults(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    flow = _flow(services, runner, presenter, toasts, host)
    dialog = flow.open()
    qtbot.addWidget(dialog)
    _fill(dialog, "EMPRESA DEMO S.A.S")

    dialog.cancel_button.click()

    assert _names(services) == []
    assert flow.dialog is None
    again = flow.open()
    qtbot.addWidget(again)
    assert again is not dialog
    assert again.values() == CompanyValues.defaults()


def test_the_dialog_is_locked_while_the_company_is_created(
    qtbot, services, deferred: DeferredRunner, presenter, toasts, host
) -> None:
    flow = _flow(services, deferred, presenter, toasts, host)
    dialog = flow.open()
    qtbot.addWidget(dialog)
    _fill(dialog, "EMPRESA DEMO S.A.S")

    dialog.primary_button.click()

    assert len(deferred.pending) == 1
    assert dialog.primary_button.isEnabled() is False
    assert dialog.cancel_button.isEnabled() is False
    deferred.run()
    assert dialog.isVisible() is False
    assert _names(services) == ["EMPRESA DEMO S.A.S"]


def test_a_company_created_after_its_dialog_closed_is_still_announced(
    qtbot, services, deferred: DeferredRunner, presenter, toasts, host
) -> None:
    flow = _flow(services, deferred, presenter, toasts, host)
    created: list[int] = []
    flow.company_created.connect(created.append)
    dialog = flow.open()
    _fill(dialog, "EMPRESA DEMO S.A.S")
    dialog.primary_button.click()

    dialog.close()  # el boton de cerrar de la ventana mientras se crea: no se cierra
    assert dialog.isVisible() is True

    dialog.done(0)  # se cerro por otra via y Qt lo destruye
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    deferred.run()

    # la empresa existe: el selector y Primeros pasos se enteran
    assert _names(services) == ["EMPRESA DEMO S.A.S"]
    assert created == [services.list_companies.execute()[0].id]
    assert [toast.message() for toast in toasts.toasts()] == [
        strings.company_created("EMPRESA DEMO S.A.S")
    ]


def test_a_failure_after_its_dialog_closed_is_still_explained(
    qtbot, services, deferred: DeferredRunner, presenter, toasts, host
) -> None:
    broken = replace(
        services, create_company=cast(CreateCompany, Failing(RuntimeError("database is locked")))
    )
    flow = _flow(broken, deferred, presenter, toasts, host)
    dialog = flow.open()
    _fill(dialog, "EMPRESA DEMO S.A.S")
    dialog.primary_button.click()
    dialog.done(0)
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    deferred.run()

    assert [type(error) for error in presenter.shown] == [RuntimeError]
    assert toasts.toasts() == []
