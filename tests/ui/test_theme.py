from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from contabilizador.ui import theme


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#1a1a1a"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#eeeeee"))
    return palette


def test_apply_theme_forces_light_palette_over_dark(qapp: QApplication) -> None:
    qapp.setPalette(_dark_palette())

    theme.apply_theme(qapp)

    palette = qapp.palette()
    assert palette.color(QPalette.ColorRole.Window).lightness() > 230
    assert palette.color(QPalette.ColorRole.Base).lightness() > 240
    assert palette.color(QPalette.ColorRole.WindowText).lightness() < 80


def test_apply_theme_uses_fusion_and_brand_stylesheet(qapp: QApplication) -> None:
    theme.apply_theme(qapp)
    sheet = qapp.styleSheet()
    # Con hoja de estilos activa Qt envuelve el estilo; se retira para ver el base
    qapp.setStyleSheet("")
    base_style = qapp.style()
    qapp.setStyleSheet(sheet)

    assert base_style is not None
    assert base_style.name().lower() == "fusion"
    assert theme.PALETTE.primary.lower() in sheet.lower()
