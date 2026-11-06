"""Small building blocks shared by the presentational widgets."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QToolButton, QWidget

from contabilizador.ui import actions, icons
from contabilizador.ui.theme import TOKENS, repolish


def make_label(text: str = "", role: str | None = None, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    if role:
        label.setProperty("role", role)
    return label


def icon_label(
    name: str, color: str | None = None, size: int = 16, parent: QWidget | None = None
) -> QLabel:
    label = QLabel(parent)
    label.setPixmap(icons.pixmap(name, color, size))
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


def set_icon_label(label: QLabel, name: str, color: str | None = None, size: int = 16) -> None:
    label.setPixmap(icons.pixmap(name, color, size))
    label.setFixedSize(size, size)


def hairline(orientation: str = "horizontal", parent: QWidget | None = None) -> QFrame:
    line = QFrame(parent)
    line.setProperty("role", "hairline")
    line.setProperty("orientation", orientation)
    if orientation == "vertical":
        line.setFixedWidth(1)
    else:
        line.setFixedHeight(1)
    return line


class IconButton(QToolButton):
    """Icon-only tool button with a tooltip (and the shortcut hint when it has one)."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        *,
        shortcut_id: str | None = None,
        color: str | None = None,
        size: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self.setProperty("role", "icon")
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(size, size))
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.set_icon(icon_name, color)
        text = actions.with_shortcut(tooltip, shortcut_id) if shortcut_id else tooltip
        self.setToolTip(text)
        self.setAccessibleName(tooltip)

    def set_icon(self, icon_name: str, color: str | None = None) -> None:
        self.setIcon(icons.icon(icon_name, color, self._size))


def set_property(widget: QWidget, name: str, value: object) -> None:
    """Sets a dynamic property used by the stylesheet and re-polishes the widget."""
    widget.setProperty(name, value)
    repolish(widget)


def paint_row_action(painter: QPainter, area: QRect, text: str, font: QFont) -> None:
    """The link-like action at the end of a table row ("Editar", "Configurar"), right-aligned.
    Every list that offers one paints it the same way."""
    painter.save()
    link = QFont(font)
    link.setWeight(QFont.Weight.Medium)
    painter.setFont(link)
    painter.setPen(QColor(TOKENS.blue_hover))
    painter.drawText(area, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, text)
    painter.restore()


def flag(value: bool) -> str:
    """Dynamic boolean properties are matched as strings in QSS: ``[active="true"]``."""
    return "true" if value else "false"
