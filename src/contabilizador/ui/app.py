"""Application entry point (`contabilizador` script).

Order matters: the Qt translator (Spanish standard buttons) is installed before any
widget exists, then fonts and theme; the window runs every use case in one background
thread (``QtTaskRunner``) and remembers its preferences in ``AppSettings``; on exit the
task runner finishes the queued jobs before the services close so no job touches a
disposed engine (if one is still running after the wait, the engine is left open).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator
from PySide6.QtWidgets import QApplication, QMainWindow

from contabilizador.shared.paths import default_database_path
from contabilizador.ui.branding import app_icon
from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.fonts import FontRegistration, apply_app_font
from contabilizador.ui.main_window import MainWindow
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import QtTaskRunner, TaskRunner
from contabilizador.ui.theme import apply_theme

TRANSLATOR_PROPERTY = "contabilizador_translator"
log = logging.getLogger(__name__)


class _Stoppable(Protocol):
    def shutdown(self) -> bool | None: ...


class _Closable(Protocol):
    def close(self) -> None: ...


def install_translator(app: QCoreApplication) -> QTranslator | None:
    """Loads ``qtbase_es.qm`` from the Qt install; returns None when it is missing."""
    existing = app.property(TRANSLATOR_PROPERTY)
    if isinstance(existing, QTranslator):
        return existing
    translator = QTranslator(app)
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(QLocale(QLocale.Language.Spanish), "qtbase", "_", path):
        return None
    app.installTranslator(translator)
    app.setProperty(TRANSLATOR_PROPERTY, translator)
    return translator


def bootstrap(app: QApplication) -> FontRegistration:
    """Translator, fonts, theme and icon: call before creating any widget."""
    install_translator(app)
    registration = apply_app_font(app)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    return registration


def create_main_window(
    services: Services, runner: TaskRunner | None = None, *, settings: AppSettings | None = None
) -> QMainWindow:
    """Without a runner the window runs the use cases inline (tests and scripts)."""
    return MainWindow(services, runner, settings=settings)


def shutdown(runner: _Stoppable, services: _Closable) -> None:
    """Lets the queued jobs finish, then closes the database. A job still running after
    the wait keeps the engine: closing it under a write would break that write, and the
    process ends anyway."""
    if runner.shutdown() is False:
        log.warning("a background job was still running at exit; database left open")
        return
    services.close()


def main(db_path: Path | None = None) -> int:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    bootstrap(app)
    settings = AppSettings()
    services = build_services(db_path or default_database_path())
    runner = QtTaskRunner()
    try:
        window = create_main_window(services, runner, settings=settings)
        window.show()
        return app.exec()
    finally:
        shutdown(runner, services)
        settings.sync()
