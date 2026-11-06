"""App bootstrap: Spanish Qt translations, fonts and theme before any widget; runner
shut down before services."""

from typing import Any

from PySide6.QtCore import QCoreApplication, QTranslator
from PySide6.QtWidgets import QApplication, QMessageBox

from contabilizador.shared import strings
from contabilizador.ui import app as app_module
from contabilizador.ui.composition import build_services
from contabilizador.ui.fonts import FONT_FAMILY
from contabilizador.ui.main_window import MainWindow
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import SyncTaskRunner


def test_install_translator_makes_qt_buttons_spanish(qapp: QApplication, qtbot) -> None:
    translator = app_module.install_translator(qapp)

    assert isinstance(translator, QTranslator)
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancelar"
    box = QMessageBox()
    qtbot.addWidget(box)
    box.setStandardButtons(QMessageBox.StandardButton.Cancel)
    assert box.button(QMessageBox.StandardButton.Cancel).text() == "Cancelar"


def test_install_translator_is_idempotent(qapp: QApplication) -> None:
    first = app_module.install_translator(qapp)
    second = app_module.install_translator(qapp)

    assert first is second


def test_bootstrap_registers_fonts_theme_and_icon(qapp: QApplication) -> None:
    registration = app_module.bootstrap(qapp)

    assert registration.family == FONT_FAMILY
    assert qapp.font().family() == FONT_FAMILY
    assert qapp.font().pixelSize() == 13
    assert not qapp.windowIcon().isNull()
    assert qapp.styleSheet()


def test_shutdown_order_runner_before_services() -> None:
    order: list[str] = []

    class Runner:
        def shutdown(self) -> None:
            order.append("runner")

    class Services:
        def close(self) -> None:
            order.append("services")

    app_module.shutdown(Runner(), Services())  # type: ignore[arg-type]

    assert order == ["runner", "services"]


def test_shutdown_keeps_the_database_open_while_a_job_still_runs() -> None:
    order: list[str] = []

    class Runner:
        def shutdown(self) -> bool:
            order.append("runner")
            return False  # la espera vencio con una tarea aun escribiendo

    class Services:
        def close(self) -> None:
            order.append("services")

    app_module.shutdown(Runner(), Services())

    assert order == ["runner"]


def test_create_main_window_uses_the_runner_and_settings_it_gets(qtbot, tmp_path) -> None:
    services = build_services(tmp_path / "app.db")
    runner = SyncTaskRunner()
    settings = AppSettings.in_file(tmp_path / "settings.ini")

    window = app_module.create_main_window(services, runner, settings=settings)
    qtbot.addWidget(window)

    assert isinstance(window, MainWindow)
    assert runner.handles  # las empresas se leen a traves del ejecutor de tareas
    window.close()
    assert settings.window_geometry is not None
    services.close()


def test_main_shows_the_window_and_stops_the_runner_before_closing_services(
    qapp: QApplication, qtbot, tmp_path, monkeypatch
) -> None:
    shown: list[MainWindow] = []

    def fake_exec(*_args: object) -> int:
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, MainWindow) and widget.isVisible():
                shown.append(widget)
                qtbot.addWidget(widget)
        return 0

    stopped: list[str] = []
    real_shutdown = app_module.shutdown

    def recording_shutdown(runner: Any, services: Any) -> None:
        stopped.append(type(runner).__name__)
        real_shutdown(runner, services)

    monkeypatch.setattr(QApplication, "exec", fake_exec)
    monkeypatch.setattr(app_module, "shutdown", recording_shutdown)

    assert app_module.main(tmp_path / "app.db") == 0
    assert len(shown) == 1
    assert shown[0].windowTitle() == strings.APP_TITLE
    assert stopped == ["QtTaskRunner"]
    assert (tmp_path / "app.db").is_file()
