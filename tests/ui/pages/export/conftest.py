"""Fixtures of the export sheet tests: real services on a temporary database."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QWidget

from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.settings import AppSettings
from tests.ui.pages.export.support import Opener, Seed, SpyPresenter, seed_company


@pytest.fixture
def services(tmp_path: Path) -> Iterator[Services]:
    built = build_services(tmp_path / "db.sqlite")
    yield built
    built.close()


@pytest.fixture
def seed(services: Services, tmp_path: Path) -> Seed:
    return seed_company(services, tmp_path)


@pytest.fixture
def presenter() -> SpyPresenter:
    return SpyPresenter()


@pytest.fixture
def settings(tmp_path: Path, qapp) -> AppSettings:
    return AppSettings.in_file(tmp_path / "settings.ini")


@pytest.fixture
def window(qtbot) -> QWidget:
    widget = QWidget()
    widget.resize(900, 700)
    qtbot.addWidget(widget)
    return widget


@pytest.fixture
def opener() -> Opener:
    return Opener()


@pytest.fixture
def documents_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "Documentos"
    folder.mkdir()
    return folder
