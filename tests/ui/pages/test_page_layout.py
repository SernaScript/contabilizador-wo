"""Every page opens with its title in the same place, so it does not jump between sections."""

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from contabilizador.ui.pages.batches.view import BatchesView
from contabilizador.ui.pages.catalogs.view import CatalogsView
from contabilizador.ui.pages.company.view import CompanyView
from contabilizador.ui.pages.invoices.view import InvoicesView
from contabilizador.ui.pages.onboarding.view import OnboardingView
from contabilizador.ui.pages.suppliers.view import SuppliersView
from contabilizador.ui.theme import PAGE_MARGIN, PAGE_MARGIN_TOP

VERTICAL_TOLERANCE = 4
PAGES: list[type[QWidget]] = [
    InvoicesView,
    SuppliersView,
    CatalogsView,
    BatchesView,
    CompanyView,
    OnboardingView,
]


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.__name__)
def test_the_title_starts_at_the_shared_page_margin(qtbot, page: type[QWidget]) -> None:
    view = page()
    qtbot.addWidget(view)
    view.resize(1048, 820)  # una ventana de 1280 menos la barra lateral de 232
    view.show()
    QApplication.processEvents()
    title = next(
        label for label in view.findChildren(QLabel) if label.property("role") == "page-title"
    )

    origin = title.mapTo(view, QPoint(0, 0))

    assert origin.x() == PAGE_MARGIN
    # Facturas centra el titulo con los botones de su cabecera: unos pixeles mas abajo
    assert abs(origin.y() - PAGE_MARGIN_TOP) <= VERTICAL_TOLERANCE
