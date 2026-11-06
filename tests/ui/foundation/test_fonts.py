"""IBM Plex Sans bundled fonts: registration, tabular figures and the system fallback."""

from importlib.resources import files
from pathlib import Path

import pytest
from PySide6.QtGui import QFont, QFontDatabase

from contabilizador.ui import fonts


@pytest.mark.parametrize(
    "name",
    ["IBMPlexSans-Regular.ttf", "IBMPlexSans-Medium.ttf", "IBMPlexSans-SemiBold.ttf", "OFL.txt"],
)
def test_font_files_are_packaged(name: str) -> None:
    assert files("contabilizador.ui.assets").joinpath("fonts", name).is_file()


def test_register_fonts_loads_the_family(qapp) -> None:
    registration = fonts.register_fonts()

    assert registration.fallback is False
    assert registration.family == fonts.FONT_FAMILY
    assert len(registration.loaded) == 3
    assert fonts.FONT_FAMILY in QFontDatabase.families()


def test_register_fonts_falls_back_when_files_are_missing(qapp, tmp_path: Path) -> None:
    registration = fonts.register_fonts(directory=tmp_path)

    assert registration.fallback is True
    assert registration.loaded == ()
    assert registration.family == fonts.system_family()


def test_register_fonts_is_idempotent(qapp) -> None:
    first = fonts.register_fonts()
    second = fonts.register_fonts()

    assert second.loaded == first.loaded
    assert second.family == first.family


def test_app_font_uses_pixel_scale_and_tabular_figures(qapp) -> None:
    font = fonts.app_font(size=13)

    assert font.pixelSize() == 13
    assert fonts.has_tabular_figures(font)


def test_font_for_weight_and_size(qapp) -> None:
    fonts.register_fonts()
    semibold = fonts.app_font(size=21, weight=QFont.Weight.DemiBold)

    assert semibold.weight() == QFont.Weight.DemiBold
    assert semibold.pixelSize() == 21


def test_apply_app_font_sets_the_application_font(qapp) -> None:
    registration = fonts.apply_app_font(qapp)

    assert qapp.font().pixelSize() == 13
    assert qapp.font().family() == registration.family
