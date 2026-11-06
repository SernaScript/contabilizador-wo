"""Fixtures of the Lotes exportados page tests: real services on a temp database and a
synchronous runner."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from contabilizador.exports.domain.batch import Batch
from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.tasks import SyncTaskRunner
from contabilizador.ui.widgets import ToastHost
from tests.ui.pages.batches.support import RecordingPresenter, seed_batches


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
def revealed() -> list[Path]:
    return []


@pytest.fixture
def host(qtbot) -> tuple[QWidget, ToastHost]:
    window = QWidget()
    window.resize(1100, 760)
    qtbot.addWidget(window)
    window.show()
    return window, ToastHost(window)


@pytest.fixture
def batches(
    services: Services, company_id: int, xml_fixtures_dir: Path, tmp_path: Path
) -> list[Batch]:
    """Two real exported batches of the company, newest first."""
    return seed_batches(services, company_id, xml_fixtures_dir, tmp_path / "salidas")
