"""Brand assets loaded through importlib.resources so they work when packaged."""

from importlib.resources import files

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap

ASSETS_PACKAGE = "contabilizador.ui.assets"
LOGO_FILE = "logo.png"
ICON_FILE = "icon.png"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def load_pixmap(name: str) -> QPixmap:
    # Se lee como bytes: funciona aunque el paquete venga dentro de un zip
    pixmap = QPixmap()
    pixmap.loadFromData(files(ASSETS_PACKAGE).joinpath(name).read_bytes())
    return pixmap


def logo_pixmap(height: int) -> QPixmap:
    return load_pixmap(LOGO_FILE).scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


def mark_pixmap(height: int) -> QPixmap:
    """Hexagon mark only: legible at header size, unlike the full wordmark."""
    return load_pixmap(ICON_FILE).scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)


def app_icon() -> QIcon:
    source = load_pixmap(ICON_FILE)
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(
            source.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
    return icon
