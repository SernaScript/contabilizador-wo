"""Item delegate that paints a status pill (icon + text) in a table cell."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPersistentModelIndex, QSize
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionViewItem

from contabilizador.ui.pages.batches.models import STATUS_ROLE
from contabilizador.ui.widgets import paint_status_pill, status_pill_size

type ModelIndex = QModelIndex | QPersistentModelIndex

PAD_X = 8
PAD_Y = 8


class StatusPillDelegate(QStyledItemDelegate):
    """Draws the ``(status, text)`` found under ``STATUS_ROLE``; cells without it paint
    as plain text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        status = index.data(STATUS_ROLE)
        if not status:
            super().paint(painter, option, index)
            return
        token, text = status
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        styled.text = ""  # fondo, seleccion y foco los pinta el estilo; el texto es la pastilla
        widget = styled.widget
        style = widget.style() if widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, styled, painter, widget)
        paint_status_pill(
            painter, styled.rect.adjusted(PAD_X, 0, -PAD_X, 0), token, text, styled.font
        )

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:  # noqa: N802
        base = super().sizeHint(option, index)
        status = index.data(STATUS_ROLE)
        if not status:
            return base
        token, text = status
        pill = status_pill_size(token, text, option.font)
        return QSize(pill.width() + 2 * PAD_X, max(base.height(), pill.height() + PAD_Y))
