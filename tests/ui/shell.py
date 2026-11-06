"""Helpers for the tests of the main window: real services on a temporary database, the
synchronous task runner, settings in a temporary INI file and an error presenter that
records instead of opening modal boxes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import QWidget

from contabilizador.ui.composition import Services
from contabilizador.ui.errors import ErrorPresentation, ErrorPresenter
from contabilizador.ui.main_window import MainWindow
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import SyncTaskRunner

# Proveedores de los XML de tests/fixtures/xml
SUPPLIERS = (
    ("900123456", "COMERCIALIZADORA EJEMPLO S.A.S."),
    ("1017000111", "PEDRO PRUEBA RESTREPO"),
    ("800987654", "SERVICIOS TECNICOS DEMO LTDA"),
)


class RecordingPresenter(ErrorPresenter):
    """Remembers the errors it was asked to show instead of opening a modal box."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[tuple[BaseException, str | None]] = []

    def show(
        self, parent: QWidget | None, error: BaseException, *, context: str | None = None
    ) -> ErrorPresentation:
        self.shown.append((error, context))
        return self.present(error, context=context)


@dataclass
class Shell:
    """Everything a main window test needs; ``build()`` opens one more window."""

    services: Services
    settings_path: Path
    presenter: RecordingPresenter = field(default_factory=RecordingPresenter)
    runner: SyncTaskRunner = field(default_factory=SyncTaskRunner)

    @property
    def settings(self) -> AppSettings:
        return AppSettings.in_file(self.settings_path)

    def build(self, qtbot, *, size: tuple[int, int] | None = (1280, 820)) -> MainWindow:
        """``size=None`` keeps the geometry the window restored from the settings."""
        window = MainWindow(
            self.services, self.runner, settings=self.settings, presenter=self.presenter
        )
        qtbot.addWidget(window)
        if size is not None:
            window.resize(*size)
        window.show()
        return window

    def company(self, name: str = "WEARE DEV S.A.S") -> int:
        company = self.services.create_company.execute(name, "1017")
        assert company.id is not None
        return company.id


def toast_messages(window: MainWindow) -> list[str]:
    return [toast.message() for toast in window.toasts.toasts()]
