from importlib.resources import files

import pytest

from contabilizador.ui import branding


@pytest.mark.parametrize("name", ["logo.png", "icon.png", "icon.ico", "icon.icns"])
def test_asset_is_packaged_resource(name: str) -> None:
    resource = files("contabilizador.ui.assets").joinpath(name)

    assert resource.is_file()


def test_logo_pixmap_scales_to_requested_height(qtbot) -> None:
    pixmap = branding.logo_pixmap(40)

    assert not pixmap.isNull()
    assert pixmap.height() == 40


def test_app_icon_is_not_null(qtbot) -> None:
    icon = branding.app_icon()

    assert not icon.isNull()
    assert icon.availableSizes()
