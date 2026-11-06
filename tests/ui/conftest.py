"""UI test plumbing: isolated QSettings and a deterministic widget teardown.

pytest-qt only keeps weak references to the widgets passed to ``qtbot.addWidget`` and
closes them with ``deleteLater``, which Qt never runs without an event loop. A widget that
is only reachable through Python reference cycles can then be destroyed by the cycle
collector at any moment, even while Qt is painting it after the test returned ("Cannot
destroy paint device that is being painted", then a crash). Here every added widget stays
referenced until its test is torn down, and then the deferred deletions run while Python
still holds the wrappers, so Qt destroys them at a known moment.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from pytestqt.qtbot import QtBot

_KEPT_WIDGETS = pytest.StashKey[list[Any]]()


@pytest.fixture(autouse=True, scope="session")
def qsettings_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Folder of every ``AppSettings()`` built without an explicit file: never the real
    preferences of the person running the tests."""
    folder = tmp_path_factory.mktemp("qsettings")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    for scope in (QSettings.Scope.UserScope, QSettings.Scope.SystemScope):
        QSettings.setPath(QSettings.Format.IniFormat, scope, str(folder))
    return folder


@pytest.fixture(autouse=True)
def _keep_widgets_until_teardown(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    kept: list[Any] = []
    request.node.stash[_KEPT_WIDGETS] = kept
    original = QtBot.addWidget

    def add_widget(self: QtBot, widget: Any, *args: Any, **kwargs: Any) -> None:
        kept.append(widget)
        original(self, widget, *args, **kwargs)

    monkeypatch.setattr(QtBot, "addWidget", add_widget)
    yield
    # pytest-qt ya cerro los widgets con deleteLater: se borran ahora, con Python aun
    # sosteniendo sus envoltorios, y solo despues se sueltan
    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    kept.clear()


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> Iterator[None]:
    # Antes de que pytest-qt cierre los widgets: los que ya no existen en C++ (borrados
    # durante la prueba) se sueltan; si no, pytest-qt llamaria close() sobre un objeto muerto
    kept = item.stash.get(_KEPT_WIDGETS, None)
    if kept is not None:
        kept[:] = [widget for widget in kept if shiboken6.isValid(widget)]
    return (yield)
