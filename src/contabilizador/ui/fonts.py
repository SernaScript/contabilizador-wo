"""IBM Plex Sans (OFL, see ``assets/fonts/OFL.txt``) registered from packaged TTFs.

Falls back to the system font when the files are missing (the download step is optional
at build time). ``app_font`` enables tabular figures so money columns align.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication

from contabilizador.ui.theme import FONT_SIZES

ASSETS_PACKAGE = "contabilizador.ui.assets"
FONTS_DIR = "fonts"
FONT_FAMILY = "IBM Plex Sans"
FONT_FILES = ("IBMPlexSans-Regular.ttf", "IBMPlexSans-Medium.ttf", "IBMPlexSans-SemiBold.ttf")
LICENSE_FILE = "OFL.txt"
TABULAR_FIGURES = "tnum"


@dataclass(frozen=True, slots=True)
class FontRegistration:
    family: str
    loaded: tuple[str, ...]
    fallback: bool


_registrations: dict[Path | None, FontRegistration] = {}


def system_family() -> str:
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()


def _read_font(directory: Path | None, name: str) -> bytes | None:
    if directory is not None:
        path = directory / name
        return path.read_bytes() if path.is_file() else None
    resource = files(ASSETS_PACKAGE).joinpath(FONTS_DIR, name)
    return resource.read_bytes() if resource.is_file() else None


def register_fonts(directory: Path | None = None) -> FontRegistration:
    """Loads the bundled TTFs once; ``directory`` overrides the package (tests)."""
    cached = _registrations.get(directory)
    if cached is not None:
        return cached
    loaded: list[str] = []
    for name in FONT_FILES:
        data = _read_font(directory, name)
        if data is None:
            continue
        if QFontDatabase.addApplicationFontFromData(data) >= 0:
            loaded.append(name)
    available = bool(loaded) and FONT_FAMILY in QFontDatabase.families()
    registration = FontRegistration(
        family=FONT_FAMILY if available else system_family(),
        loaded=tuple(loaded),
        fallback=not available,
    )
    _registrations[directory] = registration
    return registration


def current_family() -> str:
    registration = _registrations.get(None)
    return registration.family if registration is not None else system_family()


def app_font(
    size: int = FONT_SIZES.body,
    weight: QFont.Weight = QFont.Weight.Normal,
    *,
    family: str | None = None,
) -> QFont:
    font = QFont(family or current_family())
    font.setPixelSize(size)
    font.setWeight(weight)
    font.setFeature(QFont.Tag(TABULAR_FIGURES), 1)
    return font


def has_tabular_figures(font: QFont) -> bool:
    tag = QFont.Tag(TABULAR_FIGURES)
    return font.isFeatureSet(tag) and font.featureValue(tag) == 1


def apply_app_font(app: QGuiApplication, size: int = FONT_SIZES.body) -> FontRegistration:
    registration = register_fonts()
    app.setFont(app_font(size, family=registration.family))
    return registration
