"""Desktop helpers: show_in_file_manager picks the right system command per platform
(nothing is launched)."""

from pathlib import Path
from typing import ClassVar

import pytest

from contabilizador.ui import desktop as file_manager


class FakeDesktopServices:
    opened: ClassVar[list[str]] = []

    @staticmethod
    def openUrl(url) -> bool:  # noqa: N802 - Qt API
        FakeDesktopServices.opened.append(url.toLocalFile())
        return True


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    monkeypatch.setattr(file_manager.subprocess, "run", lambda args, **_kw: calls.append(args))
    FakeDesktopServices.opened = []
    monkeypatch.setattr(file_manager, "QDesktopServices", FakeDesktopServices)
    return calls


def test_macos_selects_the_file_in_finder(monkeypatch: pytest.MonkeyPatch, runs: list[object]):
    monkeypatch.setattr(file_manager.sys, "platform", "darwin")

    file_manager.show_in_file_manager(Path("/tmp/carpeta con espacios/plantilla.xlsx"))

    assert runs == [["open", "-R", "/tmp/carpeta con espacios/plantilla.xlsx"]]


def test_windows_selects_the_file_in_explorer_keeping_the_quotes(
    monkeypatch: pytest.MonkeyPatch, runs: list[object]
):
    monkeypatch.setattr(file_manager.sys, "platform", "win32")

    file_manager.show_in_file_manager(Path("C:/Mis archivos/plantilla.xlsx"))

    assert runs == ['explorer /select,"C:/Mis archivos/plantilla.xlsx"']


def test_other_platforms_open_the_containing_folder(
    monkeypatch: pytest.MonkeyPatch, runs: list[object]
):
    monkeypatch.setattr(file_manager.sys, "platform", "linux")

    file_manager.show_in_file_manager(Path("/home/ana/plantilla.xlsx"))

    assert runs == []
    assert FakeDesktopServices.opened == ["/home/ana"]
