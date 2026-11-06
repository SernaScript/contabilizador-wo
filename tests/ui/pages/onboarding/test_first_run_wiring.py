"""The wiring the main window does for the first run, as an executable example."""

from __future__ import annotations

from contabilizador.shared import strings
from contabilizador.ui.pages.company.container import CompanyContainer
from contabilizador.ui.pages.company.new_company_flow import NewCompanyFlow
from contabilizador.ui.pages.onboarding.container import OnboardingContainer
from contabilizador.ui.pages.onboarding.view import STEP_CATALOG, STEP_COMPANY


def test_creating_the_first_company_from_the_checklist(
    qtbot, services, runner, presenter, toasts, host
) -> None:
    onboarding = OnboardingContainer(services, runner, presenter, toasts)
    company_page = CompanyContainer(services, runner, presenter, toasts)
    qtbot.addWidget(onboarding)
    qtbot.addWidget(company_page)
    flow = NewCompanyFlow(services, runner, presenter, toasts, host)
    selected: list[int] = []

    def select(company_id: int) -> None:
        selected.append(company_id)
        for page in (onboarding, company_page):
            page.set_company(company_id)

    # Lo que conecta la ventana principal
    onboarding.create_company_requested.connect(flow.open)
    company_page.create_company_requested.connect(flow.open)
    flow.company_created.connect(select)
    onboarding.set_company(None)
    company_page.set_company(None)

    onboarding.view.step(STEP_COMPANY).action_button.click()
    dialog = flow.dialog
    assert dialog is not None
    qtbot.addWidget(dialog)
    dialog.form.name_edit.setText("EMPRESA DEMO S.A.S")
    dialog.form.third_party_edit.setText("1017")
    dialog.primary_button.click()

    assert selected == [services.list_companies.execute()[0].id]
    assert [row.state for row in onboarding.view.steps()] == ["done", "current", "todo"]
    assert onboarding.view.step(STEP_CATALOG).action_button.isEnabled() is True
    assert company_page.view.form.name_edit.text() == "EMPRESA DEMO S.A.S"
    assert [toast.message() for toast in toasts.toasts()] == [
        strings.company_created("EMPRESA DEMO S.A.S")
    ]


def test_renaming_the_company_tells_the_window_to_reload_the_switcher(
    qtbot, services, runner, presenter, toasts
) -> None:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    company_page = CompanyContainer(services, runner, presenter, toasts)
    qtbot.addWidget(company_page)
    company_page.set_company(company.id)
    reloaded: list[list[str]] = []
    company_page.changed.connect(
        lambda: reloaded.append([item.name for item in services.list_companies.execute()])
    )

    company_page.view.form.name_edit.setText("RENOMBRADA S.A.S")
    company_page.view.save_button.click()

    assert reloaded == [["RENOMBRADA S.A.S"]]
