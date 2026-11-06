from pathlib import Path

from PySide6.QtWidgets import QLabel

from contabilizador.shared import strings
from contabilizador.ui.app import create_main_window
from contabilizador.ui.composition import build_services


def test_main_window_has_spanish_title_and_tabs(qtbot, tmp_path: Path) -> None:
    services = build_services(tmp_path / "app.db")
    window = create_main_window(services)
    qtbot.addWidget(window)

    assert window.windowTitle() == strings.APP_TITLE
    services.close()


def test_main_window_shows_brand_icon_and_header_logo(qtbot, tmp_path: Path) -> None:
    services = build_services(tmp_path / "app.db")
    window = create_main_window(services)
    qtbot.addWidget(window)

    assert not window.windowIcon().isNull()
    logo = window.findChild(QLabel, "headerLogo")
    assert logo is not None
    assert not logo.pixmap().isNull()
    assert 36 <= logo.pixmap().height() <= 44
    services.close()
