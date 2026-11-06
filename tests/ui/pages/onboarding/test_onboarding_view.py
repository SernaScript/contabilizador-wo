"""OnboardingView: the Primeros pasos checklist as pure presentation."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from contabilizador.shared import strings
from contabilizador.ui.pages.onboarding.view import (
    STEP_CATALOG,
    STEP_COMPANY,
    STEP_IMPORT,
    OnboardingView,
    StepStatus,
)

FIRST_RUN = [StepStatus(), StepStatus(locked=True), StepStatus(locked=True)]
COMPANY_CREATED = [StepStatus(done=True), StepStatus(), StepStatus()]


def _view(qtbot) -> OnboardingView:
    view = OnboardingView()
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    return view


def test_header_has_the_page_title_and_purpose(qtbot) -> None:
    view = _view(qtbot)

    assert view.title_label.text() == strings.ONBOARDING_TITLE
    assert view.title_label.property("role") == "page-title"
    assert view.purpose_label.text() == strings.ONBOARDING_PURPOSE
    assert view.purpose_label.property("role") == "purpose"


def test_three_steps_in_the_order_of_the_plan(qtbot) -> None:
    view = _view(qtbot)

    expected = [
        (
            STEP_COMPANY,
            strings.ONBOARDING_STEP_COMPANY,
            strings.ONBOARDING_STEP_COMPANY_TEXT,
            strings.ONBOARDING_ACTION_COMPANY,
        ),
        (
            STEP_CATALOG,
            strings.ONBOARDING_STEP_CATALOG,
            strings.ONBOARDING_STEP_CATALOG_TEXT,
            strings.ONBOARDING_ACTION_CATALOG,
        ),
        (
            STEP_IMPORT,
            strings.ONBOARDING_STEP_IMPORT,
            strings.ONBOARDING_STEP_IMPORT_TEXT,
            strings.ONBOARDING_ACTION_IMPORT,
        ),
    ]
    actual = [
        (
            row.key,
            row.title_label.text(),
            row.text_label.text(),
            row.action_button.text(),
        )
        for row in view.steps()
    ]
    assert actual == expected
    assert [row.indicator.text() for row in view.steps()] == ["1", "2", "3"]


def test_a_fresh_view_is_the_first_run_state(qtbot) -> None:
    view = _view(qtbot)

    assert [row.state for row in view.steps()] == ["current", "todo", "todo"]
    assert [row.locked for row in view.steps()] == [False, True, True]


def test_steps_that_need_a_company_are_disabled_and_say_why(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps(FIRST_RUN)

    company, catalog, imports = view.steps()

    assert company.action_button.isEnabled() is True
    for locked in (catalog, imports):
        assert locked.action_button.isEnabled() is False
        assert not locked.detail_label.isHidden()
        assert locked.detail_label.text() == strings.ONBOARDING_NEEDS_COMPANY
    assert company.detail_label.isHidden()


def test_locked_buttons_use_a_style_that_looks_disabled(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps(FIRST_RUN)

    # El tema no define un aspecto deshabilitado para "secondary": se usa el neutro
    for row in view.steps()[1:]:
        assert row.action_button.property("variant") == "neutral"
        assert row.title_label.property("locked") == "true"
    assert view.step(STEP_COMPANY).title_label.property("locked") == "false"

    view.set_steps(COMPANY_CREATED)
    assert view.step(STEP_IMPORT).action_button.property("variant") == "secondary"
    assert view.step(STEP_IMPORT).title_label.property("locked") == "false"


def test_creating_the_company_unlocks_the_rest_and_moves_the_focus_of_the_list(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps(COMPANY_CREATED)

    company, catalog, imports = view.steps()

    assert [row.state for row in view.steps()] == ["done", "current", "todo"]
    assert catalog.action_button.isEnabled() is True
    assert imports.action_button.isEnabled() is True
    assert catalog.detail_label.isHidden()
    assert company.action_button.isHidden()


def test_a_done_step_says_so_with_an_icon_and_text(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps(COMPANY_CREATED)

    company, catalog, _imports = view.steps()

    assert not company.done_pill.isHidden()
    assert company.done_pill.text == strings.STEP_DONE
    assert company.done_pill.status == "ready"
    assert catalog.done_pill.isHidden()
    # La secuencia 1-2-3 se conserva; el estado lo da el estilo del indicador y la etiqueta
    assert [row.indicator.text() for row in view.steps()] == ["1", "2", "3"]
    assert [row.indicator.property("state") for row in view.steps()] == ["done", "current", "todo"]


def test_only_the_current_step_has_the_primary_button(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps(COMPANY_CREATED)

    _company, catalog, imports = view.steps()

    assert catalog.action_button.property("variant") == "primary"
    assert imports.action_button.property("variant") == "secondary"


def test_partial_progress_in_a_step_is_spelled_out(qtbot) -> None:
    view = _view(qtbot)

    view.set_steps(
        [
            StepStatus(done=True),
            StepStatus(detail=strings.ONBOARDING_MISSING_COST_CENTERS),
            StepStatus(),
        ]
    )

    catalog = view.step(STEP_CATALOG)
    assert not catalog.detail_label.isHidden()
    assert catalog.detail_label.text() == strings.ONBOARDING_MISSING_COST_CENTERS


@pytest.mark.parametrize("key", [STEP_COMPANY, STEP_CATALOG, STEP_IMPORT])
def test_each_button_reports_its_step(qtbot, key: str) -> None:
    view = _view(qtbot)
    view.set_steps([StepStatus(), StepStatus(), StepStatus()])

    with qtbot.waitSignal(view.step_triggered) as blocker:
        view.step(key).action_button.click()

    assert blocker.args == [key]


def test_enter_on_a_focused_button_activates_it(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps(COMPANY_CREATED)
    button = view.step(STEP_CATALOG).action_button
    button.setFocus()

    with qtbot.waitSignal(view.step_triggered) as blocker:
        qtbot.keyClick(button, Qt.Key.Key_Return)

    assert blocker.args == [STEP_CATALOG]


def test_when_everything_is_done_the_page_offers_the_next_place(qtbot) -> None:
    view = _view(qtbot)
    assert view.finish_panel.isHidden()

    view.set_steps([StepStatus(done=True), StepStatus(done=True), StepStatus(done=True)])

    assert [row.state for row in view.steps()] == ["done", "done", "done"]
    assert view.all_done is True
    assert not view.finish_panel.isHidden()
    assert view.finish_title_label.text() == strings.ONBOARDING_ALL_DONE_TITLE
    assert view.finish_text_label.text() == strings.ONBOARDING_ALL_DONE_TEXT
    assert view.finish_button.text() == strings.ONBOARDING_ACTION_FINISH
    assert view.finish_button.property("variant") == "primary"
    with qtbot.waitSignal(view.finish_requested):
        view.finish_button.click()


def test_the_finish_panel_hides_again_when_a_step_is_pending(qtbot) -> None:
    view = _view(qtbot)
    view.set_steps([StepStatus(done=True), StepStatus(done=True), StepStatus(done=True)])

    view.set_steps(COMPANY_CREATED)

    assert view.all_done is False
    assert view.finish_panel.isHidden()


def test_set_steps_needs_exactly_one_status_per_step(qtbot) -> None:
    view = _view(qtbot)

    with pytest.raises(ValueError):
        view.set_steps([StepStatus()])


def test_step_texts_are_plain_sentences_without_arrows(qtbot) -> None:
    view = _view(qtbot)

    texts = [label.text() for label in view.findChildren(QLabel)]

    assert all("→" not in text for text in texts)
