"""Fixtures of the Proveedores tests: a real database with imported invoices, a synchronous
task runner and recording doubles for the confirmation and the error presenter."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.pages.suppliers.container import SuppliersContainer
from contabilizador.ui.tasks import SyncTaskRunner, TaskRunner
from contabilizador.ui.widgets import ToastHost
from tests.ui.pages.suppliers.fakes import RecordingPresenter

# Los tres proveedores de los XML de prueba (ver tests/fixtures/xml)
SUPPLIERS = (
    ("900123456", "COMERCIALIZADORA EJEMPLO S.A.S."),
    ("1017000111", "PEDRO PRUEBA RESTREPO"),
    ("800987654", "SERVICIOS TECNICOS DEMO LTDA"),
)


class Confirmations:
    """Stands in for the confirmation box: records what was asked and answers as told."""

    def __init__(self) -> None:
        self.answer = True
        self.asked: list[tuple[str, str, str]] = []

    def __call__(self, parent: QWidget | None, title: str, detail: str, accept: str) -> bool:
        self.asked.append((title, detail, accept))
        return self.answer


@pytest.fixture
def services(tmp_path: Path) -> Iterator[Services]:
    built = build_services(tmp_path / "app.db")
    yield built
    built.close()


@pytest.fixture
def company_id(services: Services, xml_fixtures_dir: Path) -> int:
    company = services.create_company.execute("EMPRESA DEMO S.A.S", "1017")
    assert company.id is not None
    services.save_product.execute(company.id, "P-1", "Papelería")
    services.save_product.execute(company.id, "P-2", "Servicios")
    services.save_product.execute(company.id, "P-3", "Transporte")
    services.import_invoices.execute(company.id, [xml_fixtures_dir])
    return company.id


@pytest.fixture
def host(qtbot) -> QWidget:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(1100, 760)
    window.show()
    qtbot.waitExposed(window)
    return window


@pytest.fixture
def toasts(host: QWidget) -> ToastHost:
    return ToastHost(host)


@pytest.fixture
def presenter() -> RecordingPresenter:
    return RecordingPresenter()


@pytest.fixture
def confirmations() -> Confirmations:
    return Confirmations()


@pytest.fixture
def make_container(
    qtbot,
    host: QWidget,
    services: Services,
    presenter: RecordingPresenter,
    toasts: ToastHost,
    confirmations: Confirmations,
):
    def build(runner: TaskRunner | None = None) -> SuppliersContainer:
        container = SuppliersContainer(
            services,
            runner if runner is not None else SyncTaskRunner(),
            presenter,
            toasts,
            confirm=confirmations,
            parent=host,
        )
        container.resize(1000, 700)
        container.show()
        return container

    return build


@pytest.fixture
def container(make_container, company_id: int) -> SuppliersContainer:
    built = make_container()
    built.set_company(company_id)
    return built
