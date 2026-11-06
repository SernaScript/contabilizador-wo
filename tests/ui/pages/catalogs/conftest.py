"""Fixtures of the Catálogos page tests: real services on a temp database, a synchronous
runner, and recording fakes for everything that would open a native dialog."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.tasks import SyncTaskRunner
from contabilizador.ui.widgets import ToastHost
from tests.ui.pages.catalogs.support import FakeDialogs, RecordingPresenter


@pytest.fixture
def services(tmp_path: Path) -> Iterator[Services]:
    built = build_services(tmp_path / "app.db")
    yield built
    built.close()


@pytest.fixture
def company_id(services: Services) -> int:
    company = services.create_company.execute("WEARE DEV S.A.S", "1017")
    assert company.id is not None
    return company.id


@pytest.fixture
def presenter() -> RecordingPresenter:
    return RecordingPresenter()


@pytest.fixture
def runner() -> SyncTaskRunner:
    return SyncTaskRunner()


@pytest.fixture
def dialogs() -> FakeDialogs:
    return FakeDialogs()


@pytest.fixture
def revealed() -> list[Path]:
    return []


@pytest.fixture
def host(qtbot) -> tuple[QWidget, ToastHost]:
    window = QWidget()
    window.resize(1100, 760)
    qtbot.addWidget(window)
    window.show()
    return window, ToastHost(window)
