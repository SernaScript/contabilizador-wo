"""Design tokens: contrast, dynamic-property styling and the legacy palette aliases."""

import re

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from contabilizador.ui import theme


def test_tokens_match_the_plan() -> None:
    t = theme.TOKENS
    assert t.paper == "#FFFFFF"
    assert t.mist == "#F4F7FB"
    assert t.ink == "#0B1F45"
    assert t.slate == "#5A6B85"
    assert t.hairline == "#E1E7EF"
    assert t.blue == "#0A8BE5"
    assert t.blue_hover == "#0668B8"
    assert t.blue_tint == "#E6F3FD"


def test_legacy_palette_aliases_point_to_tokens() -> None:
    assert theme.PALETTE.primary == theme.TOKENS.blue
    assert theme.PALETTE.text == theme.TOKENS.ink
    assert theme.PALETTE.background == theme.TOKENS.mist
    assert theme.PALETTE.surface == theme.TOKENS.paper
    assert theme.PALETTE.border == theme.TOKENS.hairline


@pytest.mark.parametrize("status", ["ready", "incomplete", "blocked", "mismatch", "archived"])
def test_status_styles_have_text_background_and_icon(status: str) -> None:
    style = theme.STATUS_STYLES[status]

    assert style.fg.startswith("#") and style.bg.startswith("#")
    assert style.icon


def test_contrast_ratio_is_wcag_formula() -> None:
    assert theme.contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert theme.contrast_ratio("#FFFFFF", "#FFFFFF") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize(("fg", "bg"), theme.TEXT_BACKGROUND_PAIRS)
def test_every_text_background_pair_meets_aa(fg: str, bg: str) -> None:
    assert theme.contrast_ratio(fg, bg) >= 4.5, f"{fg} on {bg}"


def test_text_background_pairs_cover_status_and_primary() -> None:
    pairs = set(theme.TEXT_BACKGROUND_PAIRS)
    for style in theme.STATUS_STYLES.values():
        assert (style.fg, style.bg) in pairs
        assert (style.fg, theme.TOKENS.paper) in pairs
    assert (theme.TOKENS.ink, theme.TOKENS.paper) in pairs
    assert (theme.TOKENS.slate, theme.TOKENS.mist) in pairs
    assert (theme.TOKENS.on_blue, theme.TOKENS.blue_hover) in pairs


def test_font_scale_matches_the_plan() -> None:
    assert theme.FONT_SIZES.caption == 12
    assert theme.FONT_SIZES.body == 13
    assert theme.FONT_SIZES.section == 15
    assert theme.FONT_SIZES.title == 21


def test_stylesheet_targets_dynamic_properties_not_object_names() -> None:
    sheet = theme.build_stylesheet()

    for selector in (
        'QPushButton[variant="primary"]',
        'QPushButton[variant="secondary"]',
        'QPushButton[variant="danger"]',
        'QPushButton[variant="ghost"]',
        'QLabel[role="page-title"]',
        'QLabel[role="section"]',
        'QLabel[role="caption"]',
        '[role="pill"][status="ready"]',
        '[role="pill"][status="blocked"]',
        'QFrame[role="banner"][status="blocked"]',
        'QFrame[role="sidebar"]',
        'QPushButton[role="nav"]',
        'QToolButton[role="chip"]',
        'QFrame[role="toast"]',
        'QFrame[role="sheet-header"]',
        "QToolTip",
        "QScrollBar:vertical",
        "QTreeView",
        "QHeaderView::section",
    ):
        assert selector in sheet, selector
    assert theme.TOKENS.blue.lower() in sheet.lower()


def test_apply_theme_sets_variant_colors(qapp: QApplication, qtbot) -> None:
    theme.apply_theme(qapp)
    primary = QPushButton("Exportar")
    qtbot.addWidget(primary)
    theme.set_variant(primary, "primary")
    primary.show()

    assert primary.property("variant") == "primary"
    # Relleno con el azul oscuro: blanco sobre #0A8BE5 da 3.6:1, sobre #0668B8 da 5.7:1
    fill = primary.palette().color(primary.backgroundRole()).name().upper()
    assert fill == theme.TOKENS.blue_hover


def test_repolish_refreshes_style_after_property_change(qapp: QApplication, qtbot) -> None:
    theme.apply_theme(qapp)
    label = QLabel("Lista")
    qtbot.addWidget(label)
    label.show()
    # Los estados se aplican a widgets con role="pill" (los banners y toasts tienen su regla)
    label.setProperty("role", "pill")
    label.setProperty("status", "ready")
    theme.repolish(label)

    assert label.palette().color(label.foregroundRole()).name().upper() == (
        theme.STATUS_STYLES["ready"].fg
    )


def test_set_role_marks_label(qtbot) -> None:
    label = QLabel("Facturas")
    qtbot.addWidget(label)
    theme.set_role(label, "page-title")

    assert label.property("role") == "page-title"


def _themed_host(qapp: QApplication, qtbot) -> tuple[QWidget, QVBoxLayout]:
    theme.apply_theme(qapp)
    host = QWidget()
    layout = QVBoxLayout(host)
    qtbot.addWidget(host)
    return host, layout


@pytest.mark.parametrize(
    ("variant", "filled"),
    [("secondary", False), ("danger", False), ("danger", True), ("ghost", False)],
)
def test_disabled_variants_never_look_clickable(
    qapp: QApplication, qtbot, variant: str, filled: bool
) -> None:
    host, layout = _themed_host(qapp, qtbot)
    button = QPushButton("Eliminar")
    button.setProperty("variant", variant)
    if filled:
        button.setProperty("filled", "true")
    layout.addWidget(button)
    host.show()

    button.setEnabled(False)
    theme.repolish(button)

    text = button.palette().color(QPalette.ColorRole.ButtonText).name().upper()
    assert text == theme.TOKENS.disabled_text


def test_disabled_labels_turn_grey_whatever_their_role(qapp: QApplication, qtbot) -> None:
    host, layout = _themed_host(qapp, qtbot)
    labels = []
    for role in ("muted", "section", "value", "caption"):
        label = QLabel("Texto")
        label.setProperty("role", role)
        layout.addWidget(label)
        labels.append(label)
    host.show()

    host.setEnabled(False)
    for label in labels:
        theme.repolish(label)
        color = label.palette().color(QPalette.ColorRole.WindowText).name().upper()
        assert color == theme.TOKENS.disabled_text, label.property("role")


def test_keycaps_and_checkbox_focus_ring_come_from_the_theme() -> None:
    sheet = theme.build_stylesheet()

    assert 'QLabel[role="keycap"]' in sheet
    # Las confirmaciones obligatorias son casillas: el foco del teclado debe verse
    assert "QCheckBox:focus" in sheet
    assert "outline: none" not in sheet.split("QCheckBox:focus", 1)[1].split("}", 1)[0]


def test_focused_checkbox_draws_the_blue_ring(qapp: QApplication, qtbot) -> None:
    host, layout = _themed_host(qapp, qtbot)
    box = QCheckBox("Usar estos consecutivos")
    layout.addWidget(box)
    host.show()
    host.activateWindow()
    qtbot.waitUntil(host.isActiveWindow)

    box.setFocus()
    qtbot.waitUntil(box.hasFocus)
    image = box.grab().toImage()
    edge = {QColor(image.pixel(x, image.height() // 2)).name().upper() for x in range(0, 3)}

    assert theme.TOKENS.blue in edge


def _rule(sheet: str, selector: str) -> str:
    """Body of the first rule whose selector list contains ``selector`` (comments ignored)."""
    for block in re.sub(r"/\*.*?\*/", "", sheet, flags=re.DOTALL).split("}"):
        head, _, body = block.partition("{")
        if selector in [part.strip() for part in head.split(",")]:
            return body
    raise AssertionError(f"no rule for {selector}")


def test_tree_branches_draw_slate_chevrons_for_rows_that_have_children() -> None:
    sheet = theme.build_stylesheet()

    closed = _rule(sheet, "QTreeView::branch:has-children:closed")
    opened = _rule(sheet, "QTreeView::branch:has-children:open")
    assert "chevron-right-" in closed and "image: url(" in closed
    assert "chevron-down-" in opened and "image: url(" in opened
    # chevrons teñidos de slate (5A6B85): ni la flecha nativa ni un color de estado
    assert theme.TOKENS.slate.lstrip("#").lower() in closed.lower()
    assert theme.TOKENS.slate.lstrip("#").lower() in opened.lower()
    # la fila seleccionada conserva su fondo en el hueco de las ramas
    assert theme.TOKENS.blue_tint in _rule(sheet, "QTreeView::branch:selected")


def test_icon_buttons_get_a_hairline_border_on_hover() -> None:
    sheet = theme.build_stylesheet()

    hover = _rule(sheet, 'QToolButton[role="icon"]:hover')
    assert f"border-color: {theme.TOKENS.hairline_strong}" in hover


def test_one_page_margin_for_every_page() -> None:
    assert theme.PAGE_MARGIN == 32
    assert theme.PAGE_MARGIN_TOP == 28
    assert theme.PAGE_GAP == 16
    assert theme.FORM_PAGE_GAP == 24
