"""Design tokens and the application stylesheet (white version, forced light).

Widgets are styled through dynamic properties instead of object names:

- ``variant`` on buttons: ``primary`` | ``secondary`` | ``danger`` | ``ghost``
- ``status`` on labels/frames: ``ready`` | ``incomplete`` | ``blocked`` | ``mismatch`` |
  ``archived``
- ``role`` on labels/frames/tool buttons: ``page-title``, ``section``, ``caption``, ``muted``,
  ``error``, ``sidebar``, ``nav``, ``chip``, ``segment``, ``step``, ``toast``, ``banner``,
  ``sheet-header``, ``sheet-footer``, ``readiness``, ``badge``, ``panel``, ``toolbar``...

After changing a property on a visible widget call :func:`repolish`.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True, slots=True)
class Tokens:
    """Plan tokens. ``blue`` is for accents (focus ring, indicators, selection, icons);
    text and filled buttons use ``blue_hover`` so every text pair keeps 4.5:1 (white on
    ``blue`` is only 3.6:1)."""

    paper: str = "#FFFFFF"
    mist: str = "#F4F7FB"
    ink: str = "#0B1F45"
    slate: str = "#5A6B85"
    hairline: str = "#E1E7EF"
    hairline_strong: str = "#CBD3DF"
    blue: str = "#0A8BE5"
    blue_hover: str = "#0668B8"
    blue_pressed: str = "#055A9E"
    blue_tint: str = "#E6F3FD"
    on_blue: str = "#FFFFFF"
    ready: str = "#127A55"
    ready_bg: str = "#E5F5EE"
    incomplete: str = "#A35A00"
    incomplete_bg: str = "#FFF3E0"
    blocked: str = "#C42B3A"
    blocked_bg: str = "#FDEBED"
    blocked_hover: str = "#A3202E"
    mismatch: str = "#6B3FC4"
    mismatch_bg: str = "#F1EBFC"
    archived: str = "#5A6B85"
    archived_bg: str = "#EEF1F5"
    disabled_bg: str = "#EEF1F5"
    disabled_text: str = "#8A97AB"
    overlay: str = "rgba(11, 31, 69, 0.45)"
    shadow: str = "rgba(11, 31, 69, 0.18)"


TOKENS = Tokens()


@dataclass(frozen=True, slots=True)
class StatusStyle:
    fg: str
    bg: str
    icon: str


STATUS_STYLES: dict[str, StatusStyle] = {
    "ready": StatusStyle(TOKENS.ready, TOKENS.ready_bg, "circle-check"),
    "incomplete": StatusStyle(TOKENS.incomplete, TOKENS.incomplete_bg, "circle-alert"),
    "blocked": StatusStyle(TOKENS.blocked, TOKENS.blocked_bg, "octagon-alert"),
    "mismatch": StatusStyle(TOKENS.mismatch, TOKENS.mismatch_bg, "scale"),
    "archived": StatusStyle(TOKENS.archived, TOKENS.archived_bg, "archive"),
}


@dataclass(frozen=True, slots=True)
class FontSizes:
    caption: int = 12
    body: int = 13
    section: int = 15
    title: int = 21


FONT_SIZES = FontSizes()

# Medidas de pagina: las usan todas las vistas para que el titulo no salte al cambiar de
# seccion (margen lateral, margen superior y espacio entre cabecera y contenido)
PAGE_MARGIN = 32
PAGE_MARGIN_TOP = 28
PAGE_MARGIN_BOTTOM = 20
PAGE_GAP = 16
# Las paginas de formulario (Empresa, Primeros pasos) respiran un poco mas bajo el titulo
FORM_PAGE_GAP = 24


@dataclass(frozen=True, slots=True)
class Palette:
    """Legacy names used by the first UI; every value is an alias of a token."""

    background: str
    surface: str
    surface_alt: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    primary: str
    primary_hover: str
    primary_pressed: str
    primary_tint: str
    on_primary: str
    warning_bg: str
    warning_border: str
    warning_text: str
    danger: str
    danger_bg: str
    disabled_bg: str
    disabled_text: str


PALETTE = Palette(
    background=TOKENS.mist,
    surface=TOKENS.paper,
    surface_alt=TOKENS.mist,
    border=TOKENS.hairline,
    border_strong=TOKENS.hairline_strong,
    text=TOKENS.ink,
    text_muted=TOKENS.slate,
    primary=TOKENS.blue,
    primary_hover=TOKENS.blue_hover,
    primary_pressed=TOKENS.blue_pressed,
    primary_tint=TOKENS.blue_tint,
    on_primary=TOKENS.on_blue,
    warning_bg=TOKENS.incomplete_bg,
    warning_border="#F2C98A",
    warning_text=TOKENS.incomplete,
    danger=TOKENS.blocked,
    danger_bg=TOKENS.blocked_bg,
    disabled_bg=TOKENS.disabled_bg,
    disabled_text=TOKENS.disabled_text,
)

# Pares texto/fondo que la app usa; un test exige WCAG AA (>= 4.5:1) en todos
TEXT_BACKGROUND_PAIRS: tuple[tuple[str, str], ...] = (
    (TOKENS.ink, TOKENS.paper),
    (TOKENS.ink, TOKENS.mist),
    (TOKENS.ink, TOKENS.blue_tint),
    (TOKENS.slate, TOKENS.paper),
    (TOKENS.slate, TOKENS.mist),
    (TOKENS.blue_hover, TOKENS.paper),
    (TOKENS.blue_hover, TOKENS.mist),
    (TOKENS.blue_hover, TOKENS.blue_tint),
    (TOKENS.on_blue, TOKENS.blue_hover),
    (TOKENS.on_blue, TOKENS.blue_pressed),
    (TOKENS.on_blue, TOKENS.blocked),
    (TOKENS.on_blue, TOKENS.ink),
    *((style.fg, style.bg) for style in STATUS_STYLES.values()),
    *((style.fg, TOKENS.paper) for style in STATUS_STYLES.values()),
)


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    c = QColor(color)
    return 0.2126 * _linear(c.red()) + 0.7152 * _linear(c.green()) + 0.0722 * _linear(c.blue())


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG 2.x contrast ratio between two opaque colors."""
    lighter, darker = sorted((relative_luminance(foreground), relative_luminance(background)))
    return (darker + 0.05) / (lighter + 0.05)


def build_palette(p: Palette = PALETTE) -> QPalette:
    roles = QPalette.ColorRole
    palette = QPalette()
    colors = {
        roles.Window: p.background,
        roles.WindowText: p.text,
        roles.Base: p.surface,
        roles.AlternateBase: p.surface_alt,
        roles.ToolTipBase: p.text,
        roles.ToolTipText: p.on_primary,
        roles.PlaceholderText: p.text_muted,
        roles.Text: p.text,
        roles.Button: p.surface,
        roles.ButtonText: p.text,
        roles.BrightText: p.on_primary,
        roles.Light: p.surface,
        roles.Midlight: p.surface_alt,
        roles.Mid: p.border,
        roles.Dark: p.border_strong,
        roles.Shadow: p.border_strong,
        roles.Highlight: p.primary_tint,
        roles.HighlightedText: p.text,
        roles.Link: p.primary_hover,
        roles.LinkVisited: p.primary_pressed,
        roles.Accent: p.primary,
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    # Estado deshabilitado legible sobre blanco
    disabled = QPalette.ColorGroup.Disabled
    for role in (roles.WindowText, roles.Text, roles.ButtonText):
        palette.setColor(disabled, role, QColor(p.disabled_text))
    palette.setColor(disabled, roles.Button, QColor(p.disabled_bg))
    return palette


def _asset_url(file_name: str) -> str:
    """File URL of a tinted copy of a bundled SVG, for ``image: url(...)`` in QSS."""
    from contabilizador.ui.icons import tinted_svg_path

    return tinted_svg_path(file_name, TOKENS.slate).as_posix()


def _status_rules(t: Tokens) -> str:
    rules = []
    for name, style in STATUS_STYLES.items():
        rules.append(
            f"""
    QLabel[role="pill"][status="{name}"], QFrame[role="pill"][status="{name}"] {{
        color: {style.fg};
        background: {style.bg};
        border: 1px solid {style.bg};
        border-radius: 10px;
        padding: 1px 8px 1px 6px;
        font-weight: 500;
    }}
    QLabel[role="badge"][status="{name}"] {{
        color: {style.fg};
        background: {style.bg};
        border-radius: 9px;
        padding: 0 6px;
        min-width: 10px;
        font-size: {FONT_SIZES.caption}px;
        font-weight: 600;
    }}
    QFrame[role="banner"][status="{name}"] {{
        background: {style.bg};
        border: 1px solid {style.bg};
        border-left: 4px solid {style.fg};
        border-radius: 6px;
    }}
    QFrame[role="banner"][status="{name}"] QLabel {{
        color: {style.fg};
        background: transparent;
        border: none;
        padding: 0;
    }}
    QFrame[role="toast"][status="{name}"] QLabel[role="toast-icon"] {{ color: {style.fg}; }}
    """
        )
    return "".join(rules)


def build_stylesheet(p: Palette = PALETTE, t: Tokens = TOKENS) -> str:
    body = FONT_SIZES.body
    caption = FONT_SIZES.caption
    return f"""
    QWidget {{
        color: {t.ink};
        font-size: {body}px;
        selection-background-color: {t.blue_tint};
        selection-color: {t.ink};
    }}
    QMainWindow, QDialog {{ background: {t.mist}; }}
    QDialog[role="sheet"] {{ background: {t.paper}; }}
    QLabel {{ background: transparent; }}

    /* --- Tipografia por rol: jerarquia por peso y tamano, no por cajas --- */
    QLabel[role="page-title"] {{
        font-size: {FONT_SIZES.title}px;
        font-weight: 600;
        color: {t.ink};
    }}
    QLabel[role="section"] {{
        font-size: {FONT_SIZES.section}px;
        font-weight: 600;
        color: {t.ink};
    }}
    QLabel[role="caption"] {{ font-size: {caption}px; color: {t.slate}; }}
    QLabel[role="muted"], QLabel[role="purpose"] {{ color: {t.slate}; }}
    QLabel[role="error"] {{ color: {t.blocked}; font-weight: 500; }}
    QLabel[role="hint"] {{ color: {t.slate}; font-size: {caption}px; }}
    QLabel[role="label"] {{ color: {t.slate}; }}
    QLabel[role="value"] {{ color: {t.ink}; font-weight: 500; }}
    QLabel[role="money"] {{ color: {t.ink}; font-weight: 500; }}
    QLabel[role="link"] {{ color: {t.blue_hover}; text-decoration: underline; }}
    QLabel[role="brand"] {{ font-size: {FONT_SIZES.section}px; font-weight: 600; }}
    QLabel[role="keycap"] {{
        color: {t.ink};
        background: {t.mist};
        border: 1px solid {t.hairline_strong};
        border-bottom: 2px solid {t.hairline_strong};
        border-radius: 4px;
        padding: 1px 7px;
        min-width: 14px;
        font-size: {caption}px;
        font-weight: 600;
    }}
    /* Despues de los roles: un texto deshabilitado siempre se ve gris */
    QLabel:disabled {{ color: {t.disabled_text}; }}

    /* --- Botones: variante por propiedad dinamica ------------------------ */
    QPushButton {{
        background: {t.paper};
        color: {t.ink};
        border: 1px solid {t.hairline_strong};
        border-radius: 6px;
        padding: 6px 14px;
        min-height: 18px;
        font-weight: 500;
    }}
    QPushButton:hover {{ background: {t.mist}; border-color: {t.slate}; }}
    QPushButton:pressed {{ background: {t.hairline}; }}
    QPushButton:focus {{ border: 2px solid {t.blue}; padding: 5px 13px; }}
    QPushButton:disabled {{
        background: {t.disabled_bg};
        color: {t.disabled_text};
        border-color: {t.hairline};
    }}
    QPushButton[variant="primary"] {{
        background: {t.blue_hover};
        color: {t.on_blue};
        border: 1px solid {t.blue_hover};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {t.blue_pressed};
        border-color: {t.blue_pressed};
        color: {t.on_blue};
    }}
    QPushButton[variant="primary"]:pressed {{ background: {t.ink}; border-color: {t.ink}; }}
    QPushButton[variant="primary"]:focus {{
        border: 2px solid {t.blue};
        padding: 5px 13px;
    }}
    QPushButton[variant="primary"]:disabled {{
        background: {t.disabled_bg};
        color: {t.disabled_text};
        border-color: {t.hairline};
    }}
    QPushButton[variant="primary"][size="large"] {{
        padding: 10px 22px;
        font-size: {FONT_SIZES.section}px;
        border-radius: 8px;
    }}
    QPushButton[variant="secondary"] {{
        background: {t.paper};
        color: {t.blue_hover};
        border: 1px solid {t.blue_hover};
    }}
    QPushButton[variant="secondary"]:hover {{ background: {t.blue_tint}; }}
    QPushButton[variant="danger"] {{
        background: {t.paper};
        color: {t.blocked};
        border: 1px solid {t.blocked};
    }}
    QPushButton[variant="danger"]:hover {{ background: {t.blocked_bg}; }}
    QPushButton[variant="danger"][filled="true"] {{
        background: {t.blocked};
        color: {t.on_blue};
    }}
    QPushButton[variant="danger"][filled="true"]:hover {{ background: {t.blocked_hover}; }}
    QPushButton[variant="ghost"] {{
        background: transparent;
        color: {t.blue_hover};
        border: 1px solid transparent;
        padding: 6px 10px;
    }}
    QPushButton[variant="ghost"]:hover {{ background: {t.blue_tint}; }}
    /* Ninguna variante deshabilitada debe parecer pulsable */
    QPushButton[variant="secondary"]:disabled,
    QPushButton[variant="danger"]:disabled,
    QPushButton[variant="danger"][filled="true"]:disabled {{
        background: {t.disabled_bg};
        color: {t.disabled_text};
        border-color: {t.hairline};
    }}
    QPushButton[variant="ghost"]:disabled {{
        background: transparent;
        color: {t.disabled_text};
        border-color: transparent;
    }}
    QPushButton::menu-indicator {{ width: 0; height: 0; image: none; }}

    QToolButton {{
        background: transparent;
        color: {t.ink};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 4px;
    }}
    QToolButton:hover {{ background: {t.blue_tint}; }}
    QToolButton:pressed {{ background: {t.hairline}; }}
    QToolButton:focus {{ border: 2px solid {t.blue}; }}
    QToolButton:disabled {{ color: {t.disabled_text}; }}
    QToolButton[role="split-arrow"] {{
        background: {t.blue_hover};
        color: {t.on_blue};
        border: 1px solid {t.blue_hover};
        border-top-left-radius: 0;
        border-bottom-left-radius: 0;
        border-left: 1px solid {t.blue_pressed};
        padding: 4px 6px;
    }}
    QToolButton[role="split-arrow"]:hover {{ background: {t.blue_pressed}; }}
    QToolButton[role="split-arrow"]::menu-indicator {{ image: none; width: 0; }}
    QToolButton[role="icon"] {{ padding: 5px; }}
    /* Un icono suelto solo se lee como boton al pasar el puntero: borde fino al hover */
    QToolButton[role="icon"]:hover {{ border-color: {t.hairline_strong}; }}

    /* --- Barra lateral ------------------------------------------------- */
    QFrame[role="sidebar"] {{
        background: {t.mist};
        border-right: 1px solid {t.hairline};
    }}
    QPushButton[role="nav"] {{
        background: transparent;
        color: {t.ink};
        border: 1px solid transparent;
        border-left: 3px solid transparent;
        border-radius: 0;
        padding: 8px 12px 8px 13px;
        text-align: left;
        font-weight: 500;
    }}
    QPushButton[role="nav"]:hover {{ background: {t.blue_tint}; border-color: transparent; }}
    QPushButton[role="nav"]:focus {{
        border: 2px solid {t.blue};
        border-radius: 6px;
        padding: 7px 11px 7px 12px;
    }}
    QPushButton[role="nav"]:pressed {{ background: {t.blue_tint}; }}
    QPushButton[role="nav"][active="true"] {{
        background: {t.blue_tint};
        border-left: 3px solid {t.blue};
        font-weight: 600;
    }}
    QPushButton[role="nav"]:disabled {{ color: {t.disabled_text}; background: transparent; }}
    QLabel[role="badge"] {{
        color: {t.slate};
        background: {t.hairline};
        border-radius: 9px;
        padding: 0 6px;
        min-width: 10px;
        font-size: {caption}px;
        font-weight: 600;
    }}

    /* --- Chips y control segmentado ---------------------------------- */
    QToolButton[role="chip"] {{
        background: {t.paper};
        color: {t.slate};
        border: 1px solid {t.hairline_strong};
        border-radius: 14px;
        padding: 4px 12px;
        font-weight: 500;
    }}
    QToolButton[role="chip"]:hover {{ background: {t.mist}; color: {t.ink}; }}
    QToolButton[role="chip"]:checked {{
        background: {t.blue_tint};
        color: {t.blue_hover};
        border-color: {t.blue};
    }}
    QToolButton[role="chip"]:focus {{ border: 2px solid {t.blue}; }}
    QToolButton[role="segment"] {{
        background: {t.mist};
        color: {t.slate};
        border: 1px solid {t.hairline};
        border-radius: 0;
        padding: 5px 14px;
        font-weight: 500;
    }}
    QToolButton[role="segment"][position="first"] {{
        border-top-left-radius: 6px;
        border-bottom-left-radius: 6px;
    }}
    QToolButton[role="segment"][position="last"] {{
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }}
    QToolButton[role="segment"]:checked {{
        background: {t.paper};
        color: {t.ink};
        border-color: {t.blue};
        font-weight: 600;
    }}
    QToolButton[role="segment"]:focus {{ border: 2px solid {t.blue}; }}

    /* --- Stepper (la unica numeracion de la app) ----------------------- */
    QToolButton[role="step"] {{
        background: transparent;
        color: {t.slate};
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 4px 8px;
        font-weight: 500;
    }}
    QToolButton[role="step"][state="current"] {{ color: {t.ink}; font-weight: 600; }}
    QToolButton[role="step"][state="done"] {{ color: {t.ready}; }}
    QToolButton[role="step"]:hover {{ background: {t.blue_tint}; }}
    QToolButton[role="step"]:focus {{ border: 2px solid {t.blue}; }}
    QLabel[role="step-number"] {{
        color: {t.slate};
        background: {t.paper};
        border: 1px solid {t.hairline_strong};
        border-radius: 10px;
        min-width: 18px;
        max-width: 18px;
        min-height: 18px;
        max-height: 18px;
        font-size: {caption}px;
        font-weight: 600;
    }}
    QLabel[role="step-number"][state="current"] {{
        color: {t.on_blue};
        background: {t.blue_hover};
        border-color: {t.blue_hover};
    }}
    QLabel[role="step-number"][state="done"] {{
        color: {t.ready};
        background: {t.ready_bg};
        border-color: {t.ready_bg};
    }}
    QFrame[role="step-line"] {{
        background: {t.hairline_strong};
        max-height: 1px;
        min-width: 18px;
    }}
    QFrame[role="step-line"][state="done"] {{ background: {t.ready}; }}

    /* --- Campos ---------------------------------------------------------- */
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
        background: {t.paper};
        color: {t.ink};
        border: 1px solid {t.hairline_strong};
        border-radius: 6px;
        padding: 5px 8px;
        selection-background-color: {t.blue};
        selection-color: {t.on_blue};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
    QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 2px solid {t.blue};
        padding: 4px 7px;
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background: {t.disabled_bg};
        color: {t.disabled_text};
    }}
    QLineEdit[role="search"] {{ padding-left: 6px; border-radius: 16px; }}
    QLineEdit[role="search"]:focus {{ padding-left: 5px; }}
    QLineEdit[invalid="true"], QComboBox[invalid="true"] {{ border-color: {t.blocked}; }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 22px;
        border: none;
    }}
    QComboBox::down-arrow {{
        image: url({_asset_url("chevron-down.svg")});
        width: 14px;
        height: 14px;
    }}
    QComboBox QAbstractItemView {{
        background: {t.paper};
        border: 1px solid {t.hairline};
        outline: none;
        selection-background-color: {t.blue_tint};
        selection-color: {t.ink};
    }}
    QCheckBox, QRadioButton {{
        spacing: 8px;
        border: 2px solid transparent;
        border-radius: 4px;
        padding: 2px 4px;
    }}
    QCheckBox:focus, QRadioButton:focus {{ border-color: {t.blue}; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}

    /* --- Listas, arboles y tablas -------------------------------------- */
    QTableView, QListWidget, QListView, QTreeView, QTreeWidget {{
        background: {t.paper};
        alternate-background-color: {t.paper};
        border: 1px solid {t.hairline};
        border-radius: 6px;
        gridline-color: {t.hairline};
        selection-background-color: {t.blue_tint};
        selection-color: {t.ink};
        outline: none;
    }}
    QTreeView::item, QTableView::item {{ padding: 4px 6px; border-bottom: 1px solid {t.hairline}; }}
    QTreeView::item:hover, QTableView::item:hover, QListView::item:hover {{ background: {t.mist}; }}
    QTreeView::item:selected, QTableView::item:selected, QListView::item:selected {{
        background: {t.blue_tint};
        color: {t.ink};
    }}
    QTreeView::branch {{ background: {t.paper}; }}
    QTreeView::branch:selected {{ background: {t.blue_tint}; }}
    /* Estilizar la rama quita la flecha nativa: se dibuja un chevron solo donde hay hijos */
    QTreeView::branch:has-children:closed {{ image: url({_asset_url("chevron-right.svg")}); }}
    QTreeView::branch:has-children:open {{ image: url({_asset_url("chevron-down.svg")}); }}
    QHeaderView {{ background: {t.paper}; }}
    QHeaderView::section {{
        background: {t.paper};
        color: {t.slate};
        border: none;
        border-bottom: 1px solid {t.hairline};
        padding: 6px 8px;
        font-weight: 600;
        font-size: {caption}px;
    }}
    QTableCornerButton::section {{
        background: {t.paper};
        border: none;
        border-bottom: 1px solid {t.hairline};
    }}

    /* --- Paneles, toolbar y pie de preparacion ------------------------- */
    QFrame[role="panel"] {{
        background: {t.paper};
        border: 1px solid {t.hairline};
        border-radius: 8px;
    }}
    QFrame[role="toolbar"] {{ background: transparent; border: none; }}
    QFrame[role="page-header"] {{ background: transparent; border: none; }}
    QFrame[role="detail"] {{ background: {t.paper}; border-left: 1px solid {t.hairline}; }}
    QFrame[role="bulk-bar"] {{
        background: {t.blue_tint};
        border: 1px solid {t.blue};
        border-radius: 8px;
    }}
    QFrame[role="readiness"] {{
        background: {t.paper};
        border-top: 1px solid {t.hairline};
    }}
    QFrame[role="hairline"] {{ background: {t.hairline}; max-height: 1px; border: none; }}
    QFrame[role="hairline"][orientation="vertical"] {{ max-height: 10000px; max-width: 1px; }}
    QFrame[role="empty-state"] {{
        background: {t.paper};
        border: 2px dashed {t.hairline_strong};
        border-radius: 12px;
    }}
    QFrame[role="empty-state"][active="true"] {{
        border-color: {t.blue};
        background: {t.blue_tint};
    }}
    QFrame[role="drop-overlay"] {{
        background: {t.blue_tint};
        border: 2px dashed {t.blue};
        border-radius: 12px;
    }}
    QFrame[role="busy-card"] {{
        background: {t.paper};
        border: 1px solid {t.hairline};
        border-radius: 10px;
    }}
    QProgressBar {{
        background: {t.hairline};
        border: none;
        border-radius: 3px;
        height: 6px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{ background: {t.blue}; border-radius: 3px; }}

    /* --- Toasts y banners ---------------------------------------------- */
    QFrame[role="toast"] {{
        background: {t.ink};
        border: 1px solid {t.ink};
        border-radius: 8px;
    }}
    QFrame[role="toast"] QLabel {{ color: {t.on_blue}; background: transparent; }}
    QFrame[role="toast"] QPushButton {{
        background: transparent;
        color: {t.on_blue};
        border: 1px solid rgba(255, 255, 255, 0.45);
        padding: 3px 10px;
        font-weight: 600;
    }}
    QFrame[role="toast"] QPushButton:hover {{ background: rgba(255, 255, 255, 0.12); }}
    QFrame[role="toast"] QToolButton {{ color: {t.on_blue}; }}
    QFrame[role="toast"] QToolButton:hover {{ background: rgba(255, 255, 255, 0.12); }}
    QFrame[role="banner"] {{
        background: {t.mist};
        border: 1px solid {t.hairline};
        border-radius: 6px;
    }}

    /* --- Sheet (dialogo con cabecera, cuerpo y pie) -------------------- */
    QFrame[role="sheet-header"] {{
        background: {t.paper};
        border-bottom: 1px solid {t.hairline};
    }}
    QFrame[role="sheet-body"] {{ background: {t.paper}; border: none; }}
    QFrame[role="sheet-footer"] {{
        background: {t.mist};
        border-top: 1px solid {t.hairline};
    }}

    /* --- Menus, tooltips, scroll --------------------------------------- */
    QMenu {{
        background: {t.paper};
        border: 1px solid {t.hairline};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {t.blue_tint}; color: {t.ink}; }}
    QMenu::separator {{ height: 1px; background: {t.hairline}; margin: 4px 8px; }}
    QToolTip {{
        background: {t.ink};
        color: {t.on_blue};
        border: none;
        border-radius: 4px;
        padding: 5px 8px;
        font-size: {caption}px;
    }}
    QSplitter::handle {{ background: {t.hairline}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}
    QStatusBar {{ background: {t.paper}; border-top: 1px solid {t.hairline}; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle {{ background: {t.hairline_strong}; border-radius: 3px; }}
    QScrollBar::handle:vertical {{ min-height: 24px; }}
    QScrollBar::handle:horizontal {{ min-width: 24px; }}
    QScrollBar::handle:hover {{ background: {t.slate}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    {_status_rules(t)}
    """


def apply_theme(app: QApplication) -> None:
    # Fusion + paleta explicita: mismo aspecto en macOS y Windows, ignora modo oscuro
    hints = QGuiApplication.styleHints()
    if hints is not None:
        hints.setColorScheme(Qt.ColorScheme.Light)
    app.setStyle("Fusion")
    app.setPalette(build_palette())
    app.setStyleSheet(build_stylesheet())


def repolish(widget: QWidget) -> None:
    """Re-applies the stylesheet after a dynamic property changed on a visible widget."""
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_variant(widget: QWidget, variant: str) -> None:
    widget.setProperty("variant", variant)
    repolish(widget)


def set_role(widget: QWidget, role: str) -> None:
    widget.setProperty("role", role)
    repolish(widget)


def set_status(widget: QWidget, status: str | None) -> None:
    widget.setProperty("status", status)
    repolish(widget)
