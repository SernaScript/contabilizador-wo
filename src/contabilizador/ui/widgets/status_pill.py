"""Status pill (icon + text, never color alone) as a widget and as a paint helper for
item delegates."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QPainter, QPaintEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.theme import STATUS_STYLES

PILL_HEIGHT = 22
ICON_SIZE = 14
PAD_X = 8
GAP = 5
ELLIPSIS = "…"


def _pill_font(font: QFont) -> QFont:
    styled = QFont(font)
    styled.setWeight(QFont.Weight.Medium)
    return styled


def _text_width(font: QFont, text: str) -> int:
    # Avance fraccional redondeado hacia arriba: evita elidir por un pixel
    return math.ceil(QFontMetricsF(font).horizontalAdvance(text))


def elide_pill_text(font: QFont, text: str, width: int) -> str:
    """``text`` as it is drawn in ``width`` px: whole when it fits, else cut after the last
    whole word that fits ("Falta centro…"), and only when not even one fits by characters."""
    pill_font = _pill_font(font)
    if _text_width(pill_font, text) <= width:
        return text
    words = text.split(" ")
    for count in range(len(words) - 1, 0, -1):
        candidate = " ".join(words[:count]) + ELLIPSIS
        if _text_width(pill_font, candidate) <= width:
            return candidate
    return QFontMetrics(pill_font).elidedText(text, Qt.TextElideMode.ElideRight, width)


def status_pill_size(status: str, text: str, font: QFont) -> QSize:
    pill_font = _pill_font(font)
    width = PAD_X + ICON_SIZE + GAP + _text_width(pill_font, text) + PAD_X
    height = max(PILL_HEIGHT, QFontMetrics(pill_font).height() + 4)
    return QSize(width, height)


def paint_status_pill(
    painter: QPainter,
    rect: QRect,
    status: str,
    text: str,
    font: QFont,
    *,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
) -> QRect:
    """Draws the pill inside ``rect`` (left/right/center aligned) and returns its rect."""
    style = STATUS_STYLES[status]
    wanted = status_pill_size(status, text, font)
    width = min(wanted.width(), rect.width())
    height = min(wanted.height(), rect.height())
    if align & Qt.AlignmentFlag.AlignRight:
        x = rect.right() - width + 1
    elif align & Qt.AlignmentFlag.AlignHCenter:
        x = rect.left() + (rect.width() - width) // 2
    else:
        x = rect.left()
    y = rect.top() + (rect.height() - height) // 2
    pill = QRect(x, y, width, height)

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(style.bg))
    radius = height / 2
    painter.drawRoundedRect(pill, radius, radius)

    device = painter.device()
    ratio = device.devicePixelRatio() if device is not None else 1.0
    icon_rect = QRect(
        pill.left() + PAD_X, pill.top() + (height - ICON_SIZE) // 2, ICON_SIZE, ICON_SIZE
    )
    painter.drawPixmap(
        icon_rect, icons.pixmap(style.icon, style.fg, ICON_SIZE, device_pixel_ratio=ratio)
    )

    text_left = icon_rect.right() + 1 + GAP
    text_rect = QRect(text_left, pill.top(), pill.right() - PAD_X - text_left + 1, height)
    painter.setFont(_pill_font(font))
    painter.setPen(QColor(style.fg))
    shown = elide_pill_text(font, text, text_rect.width())
    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, shown)
    painter.restore()
    return pill


class StatusPill(QWidget):
    def __init__(
        self, status: str = "ready", text: str | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._status = status
        self._text = ""
        self.setProperty("role", "pill")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.set_status(status, text)

    @property
    def status(self) -> str:
        return self._status

    @property
    def text(self) -> str:
        return self._text

    def set_status(self, status: str, text: str | None = None) -> None:
        self._status = status
        self._text = text if text is not None else strings.STATUS_LABELS.get(status, status)
        self.setProperty("status", status)
        self.setToolTip(self._text)
        self.setAccessibleName(self._text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return status_pill_size(self._status, self._text, self.font())

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return self.sizeHint()

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt API
        # La hoja de estilos cambia la fuente despues del primer layout
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.updateGeometry()
        super().changeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        paint_status_pill(painter, self.rect(), self._status, self._text, self.font())
        painter.end()
