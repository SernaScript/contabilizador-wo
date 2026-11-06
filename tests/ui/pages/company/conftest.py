"""Fixtures of the Empresa and new company tests: real services on a temp database."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QWidget

from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.tasks import SyncTaskRunner
from contabilizador.ui.widgets.toast import ToastHost
from tests.ui.pages.company.support import DeferredRunner, RecordingPresenter


@pytest.fixture
def services(tmp_path) -> Iterator[Services]:
    built = build_services(tmp_path / "app.db")
    yield built
    built.close()


@pytest.fixture
def runner() -> SyncTaskRunner:
    return SyncTaskRunner()


@pytest.fixture
def deferred() -> DeferredRunner:
    return DeferredRunner()


@pytest.fixture
def presenter() -> RecordingPresenter:
    return RecordingPresenter()


@pytest.fixture
def host(qtbot) -> QWidget:
    widget = QWidget()
    qtbot.addWidget(widget)
    widget.resize(900, 640)
    widget.show()
    return widget


@pytest.fixture
def toasts(host: QWidget) -> ToastHost:
    return ToastHost(host)
