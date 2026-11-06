"""Lucide icon subset: packaged SVGs, semantic aliases, tinting and caching."""

from importlib.resources import files

import pytest
from PySide6.QtGui import QColor, QIcon

from contabilizador.ui import icons
from contabilizador.ui.theme import STATUS_STYLES, TOKENS

SEMANTIC_NAMES = [
    "import",
    "folder",
    "file",
    "search",
    "filter",
    "ready",
    "incomplete",
    "blocked",
    "mismatch",
    "archived",
    "memory",
    "supplier_default",
    "invoices",
    "suppliers",
    "catalogs",
    "batches",
    "company",
    "keyboard",
    "export",
    "open_external",
    "copy",
    "chevron_down",
    "chevron_right",
    "chevron_up",
    "chevron_left",
    "expand_all",
    "collapse_all",
    "panel_open",
    "panel_close",
    "close",
    "plus",
    "edit",
    "trash",
    "restore",
    "info",
    "check",
    "loader",
    "warning",
    "error",
]


def test_license_is_packaged() -> None:
    resource = files("contabilizador.ui.assets").joinpath("icons", "LICENSE")

    assert resource.is_file()
    assert "ISC" in resource.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SEMANTIC_NAMES)
def test_every_semantic_icon_resolves_to_a_packaged_svg(name: str) -> None:
    file_name = icons.resolve(name)
    resource = files("contabilizador.ui.assets").joinpath("icons", f"{file_name}.svg")

    assert resource.is_file(), name
    svg = resource.read_text(encoding="utf-8")
    assert 'viewBox="0 0 24 24"' in svg
    assert 'stroke="currentColor"' in svg


def test_status_icons_match_theme() -> None:
    for status, style in STATUS_STYLES.items():
        assert icons.resolve(status) == style.icon


def test_resolve_accepts_raw_lucide_names() -> None:
    assert icons.resolve("circle-check") == "circle-check"


def test_unknown_icon_raises_key_error() -> None:
    with pytest.raises(KeyError):
        icons.resolve("no-such-icon")


def test_icon_returns_a_non_null_qicon(qapp) -> None:
    icon = icons.icon("ready", TOKENS.ready, size=16)

    assert isinstance(icon, QIcon)
    assert not icon.isNull()
    assert not icon.pixmap(16, 16).isNull()


def test_pixmap_is_tinted_with_the_requested_color(qapp) -> None:
    pixmap = icons.pixmap("check", "#FF0000", size=32)
    image = pixmap.toImage()
    painted = {
        QColor(image.pixel(x, y)).name().upper()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }

    assert not pixmap.isNull()
    assert painted == {"#FF0000"}


def test_icon_is_cached_per_name_color_and_size(qapp) -> None:
    icons.clear_cache()
    first = icons.icon("copy", TOKENS.slate, size=16)
    second = icons.icon("copy", TOKENS.slate, size=16)
    other = icons.icon("copy", TOKENS.ink, size=16)

    assert first is second
    assert other is not first
    assert icons.cache_size() == 2


def test_default_color_is_slate(qapp) -> None:
    pixmap = icons.pixmap("info", size=32)
    image = pixmap.toImage()
    opaque = {
        image.pixelColor(x, y).name().upper()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }

    assert opaque == {TOKENS.slate}


def test_tinted_svg_path_writes_the_tinted_copy_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(icons, "user_cache_dir", lambda: tmp_path)

    target = icons.tinted_svg_path("chevron-down.svg", "#5A6B85")

    assert target.read_text(encoding="utf-8") == icons.svg_source("chevron-down", "#5A6B85")
    assert icons.tinted_svg_path("chevron-down.svg", "#5A6B85") == target


def test_tinted_svg_path_repairs_a_half_written_copy(tmp_path, monkeypatch) -> None:
    # Otra instancia (o pruebas en paralelo) pudo dejar el archivo a medias: se reescribe
    # entero y de forma atomica, sin dejar temporales en la carpeta
    monkeypatch.setattr(icons, "user_cache_dir", lambda: tmp_path)
    target = icons.tinted_svg_path("chevron-down.svg", "#5A6B85")
    target.write_text("<svg xmlns", encoding="utf-8")

    again = icons.tinted_svg_path("chevron-down.svg", "#5A6B85")

    assert again == target
    assert again.read_text(encoding="utf-8") == icons.svg_source("chevron-down", "#5A6B85")
    assert [path.name for path in target.parent.iterdir()] == [target.name]
