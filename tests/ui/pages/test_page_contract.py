"""Every page container offers the page contract of the plan, so the main window wires any
page the same way: ``(services, runner, presenter, toasts)``, ``set_company``, ``refresh``
and the signals ``changed``, ``badge_changed`` and ``navigate_requested``."""

import inspect

import pytest
from PySide6.QtCore import Signal

from contabilizador.ui.pages.batches import BatchesContainer
from contabilizador.ui.pages.catalogs import CatalogsContainer
from contabilizador.ui.pages.company.container import CompanyContainer
from contabilizador.ui.pages.invoices import InvoicesPage
from contabilizador.ui.pages.onboarding.container import OnboardingContainer
from contabilizador.ui.pages.suppliers import SuppliersContainer

PAGES = (
    InvoicesPage,
    SuppliersContainer,
    CatalogsContainer,
    BatchesContainer,
    CompanyContainer,
    OnboardingContainer,
)


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.__name__)
def test_every_page_offers_the_page_contract(page: type) -> None:
    for name in ("changed", "badge_changed", "navigate_requested"):
        assert isinstance(getattr(page, name, None), Signal), name
    assert callable(getattr(page, "set_company", None))
    assert callable(getattr(page, "refresh", None))
    parameters = list(inspect.signature(page.__init__).parameters)
    assert parameters[1:5] == ["services", "runner", "presenter", "toasts"]
