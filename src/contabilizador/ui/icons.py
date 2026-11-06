"""Lucide icon subset (ISC, see ``assets/icons/LICENSE``) tinted with theme tokens.

``icon("ready", color, size)`` accepts a semantic name (``import``, ``blocked``...) or a
raw Lucide file name (``circle-check``). Pixmaps are rendered from the 24x24 stroke SVG
with ``QSvgRenderer`` at the device pixel ratio and cached per (name, color, size).
"""

from __future__ import annotations

import os
import threading
from importlib.resources import files
from pathlib import Path

from platformdirs import user_cache_path
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from contabilizador.ui.theme import TOKENS

ASSETS_PACKAGE = "contabilizador.ui.assets"
ICONS_DIR = "icons"
DEFAULT_SIZE = 16

# Nombre semantico -> archivo Lucide (24x24, stroke 2)
ICON_ALIASES: dict[str, str] = {
    "import": "upload",
    "upload": "upload",
    "folder": "folder",
    "folder_open": "folder-open",
    "file": "file-text",
    "excel": "file-spreadsheet",
    "search": "search",
    "filter": "filter",
    "ready": "circle-check",
    "incomplete": "circle-alert",
    "blocked": "octagon-alert",
    "mismatch": "scale",
    "archived": "archive",
    "memory": "history",
    "supplier_default": "store",
    "invoices": "receipt",
    "suppliers": "truck",
    "catalogs": "book-open",
    "batches": "layers",
    "company": "building-2",
    "settings": "settings",
    "keyboard": "keyboard",
    "export": "download",
    "download": "download",
    "open_external": "external-link",
    "copy": "copy",
    "chevron_down": "chevron-down",
    "chevron_right": "chevron-right",
    "chevron_up": "chevron-up",
    "chevron_left": "chevron-left",
    # Arbol de facturas: desplegar / plegar todas las filas y mostrar / ocultar el detalle
    "expand_all": "chevrons-up-down",
    "collapse_all": "chevrons-down-up",
    "panel_open": "panel-right-open",
    "panel_close": "panel-right-close",
    "close": "x",
    "plus": "plus",
    "edit": "pencil",
    "trash": "trash-2",
    "restore": "rotate-ccw",
    "info": "info",
    "check": "check",
    "loader": "loader-circle",
    "warning": "triangle-alert",
    "error": "circle-x",
    "checklist": "list-checks",
    "mark": "hexagon",
}


def user_cache_dir() -> Path:
    return user_cache_path("contabilizador", "WhileCorp")


_svg_cache: dict[str, str] = {}
_icon_cache: dict[tuple[str, str, int], QIcon] = {}


def resolve(name: str) -> str:
    """Returns the Lucide file name for a semantic or raw name; ``KeyError`` if unknown."""
    file_name = ICON_ALIASES.get(name, name)
    if file_name not in _svg_cache:
        resource = files(ASSETS_PACKAGE).joinpath(ICONS_DIR, f"{file_name}.svg")
        if not resource.is_file():
            raise KeyError(name)
        _svg_cache[file_name] = resource.read_text(encoding="utf-8")
    return file_name


def svg_source(name: str, color: str | None = None) -> str:
    """SVG text with ``currentColor`` replaced by ``color`` (default slate)."""
    file_name = resolve(name)
    return _svg_cache[file_name].replace("currentColor", color or TOKENS.slate)


def pixmap(
    name: str,
    color: str | None = None,
    size: int = DEFAULT_SIZE,
    *,
    device_pixel_ratio: float | None = None,
) -> QPixmap:
    ratio = device_pixel_ratio
    if ratio is None:
        screen = QGuiApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen is not None else 1.0
    pixels = max(1, round(size * ratio))
    image = QImage(pixels, pixels, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(svg_source(name, color).encode("utf-8"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    result = QPixmap.fromImage(image)
    result.setDevicePixelRatio(ratio)
    return result


def icon(name: str, color: str | None = None, size: int = DEFAULT_SIZE) -> QIcon:
    """Cached ``QIcon`` with a normal pixmap in ``color`` and a disabled pixmap in grey."""
    key = (name, color or TOKENS.slate, size)
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    result = QIcon()
    result.addPixmap(pixmap(name, key[1], size), QIcon.Mode.Normal)
    result.addPixmap(pixmap(name, TOKENS.disabled_text, size), QIcon.Mode.Disabled)
    _icon_cache[key] = result
    return result


def tinted_svg_path(file_name: str, color: str) -> Path:
    """Writes (once) a tinted copy of a bundled SVG under the user cache; QSS ``url()``
    needs a real file.

    The copy is written to a temporary file and moved into place, so another instance of
    the app (or a parallel test run) never reads it half-written; a copy left incomplete
    by an earlier run is rewritten.
    """
    name = file_name.removesuffix(".svg")
    target = user_cache_dir() / "icons" / f"{name}-{color.lstrip('#').lower()}.svg"
    wanted = svg_source(name, color)
    if _read_text(target) == wanted:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        temporary.write_text(wanted, encoding="utf-8")
        temporary.replace(target)
    except OSError:
        # Windows no reemplaza un archivo abierto por otro proceso: queda la copia que habia
        temporary.unlink(missing_ok=True)
    return target


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def clear_cache() -> None:
    _icon_cache.clear()


def cache_size() -> int:
    return len(_icon_cache)
