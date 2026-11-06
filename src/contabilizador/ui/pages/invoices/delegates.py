"""Delegates of the document tree.

``CodeDelegate`` edits product / cost center cells with the searchable ``CodeCombo``
(supplier products first, then the catalog; free text rejected) and commits as soon as
the user picks a value. ``StatusDelegate`` paints the readiness pill on invoice rows and
``DocumentDelegate`` the FC/NC badge before the document label. A line has no supplier, so
``DocumentDelegate`` and ``SupplierDelegate`` draw it across both columns: "Línea 1" and the
description it is about.

The editable cells say so: a chevron at their right edge on the hovered / current row (the
tree reports it through ``is_row_active``) and always on the amber "Elegir…". The table stays
quiet otherwise.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QPersistentModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QAbstractItemDelegate,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeView,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.pages.invoices.model import Column, Role
from contabilizador.ui.theme import FONT_SIZES, STATUS_STYLES, TOKENS
from contabilizador.ui.widgets.code_combo import CodeCombo
from contabilizador.ui.widgets.status_pill import paint_status_pill, status_pill_size

type ModelIndex = QModelIndex | QPersistentModelIndex

CELL_PADDING = 6
BADGE_PAD_X = 6
BADGE_HEIGHT = 18
BADGE_GAP = 8
BADGE_RADIUS = 4
LINE_LABEL_GAP = 8
CHEVRON_SIZE = 12
CHEVRON_LEAD = 4  # aire entre el texto y el chevron
CHEVRON_FADE = 8  # el texto largo se desvanece bajo el chevron: no se reserva ancho a la celda


def row_is_active(widget: QWidget | None, index: ModelIndex) -> bool:
    """Whether the tree says the row of ``index`` is hovered or current (a plain view: no)."""
    check = getattr(widget, "is_row_active", None)
    return bool(check(index)) if callable(check) else False


class CodeDelegate(QStyledItemDelegate):
    """Editor for product / cost center cells. ``catalog_missing(field)`` fires instead of
    opening an editor when the catalog has nothing to choose from."""

    catalog_missing = Signal(str)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        super().paint(painter, option, index)
        empty = bool(index.data(Role.IS_EMPTY))
        if empty or row_is_active(option.widget, index):
            _paint_chevron(painter, option, amber=empty)

    def createEditor(  # noqa: N802 - Qt API
        self, parent: QWidget, option: QStyleOptionViewItem, index: ModelIndex
    ) -> QWidget:
        # Devolver None es el contrato de Qt para "sin editor"; el stub no lo tipa
        items = index.data(Role.EDITOR_ITEMS)
        if items is None:
            return None  # type: ignore[return-value]
        preferred, rest = items
        if not preferred and not rest:
            self.catalog_missing.emit(index.data(Role.FIELD) or "")
            return None  # type: ignore[return-value]
        combo = CodeCombo(parent)
        combo.set_items(preferred, rest)
        # El completador roba el foco: se confirma en cuanto el usuario elige
        combo.committed.connect(lambda _code, editor=combo: self._commit(editor))
        return combo

    def _commit(self, editor: QWidget) -> None:
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QAbstractItemDelegate.EndEditHint.NoHint)

    def setEditorData(self, editor: QWidget, index: ModelIndex) -> None:  # noqa: N802
        if not isinstance(editor, CodeCombo):
            return
        editor.set_current_code(index.data(Qt.ItemDataRole.EditRole))
        line_edit = editor.lineEdit()
        if line_edit is not None:
            line_edit.selectAll()

    def setModelData(  # noqa: N802
        self, editor: QWidget, model: QAbstractItemModel, index: ModelIndex
    ) -> None:
        if not isinstance(editor, CodeCombo):
            return
        code = editor.current_code()
        if code is not None:
            model.setData(index, code, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(  # noqa: N802
        self, editor: QWidget, option: QStyleOptionViewItem, index: ModelIndex
    ) -> None:
        editor.setGeometry(option.rect)


def _veil_color(state: QStyle.StateFlag) -> QColor:
    """Background the style paints for a cell in ``state`` (selected, hovered or plain)."""
    if state & QStyle.StateFlag.State_Selected:
        return QColor(TOKENS.blue_tint)
    if state & QStyle.StateFlag.State_MouseOver:
        return QColor(TOKENS.mist)
    return QColor(TOKENS.paper)


def _paint_chevron(painter: QPainter, option: QStyleOptionViewItem, *, amber: bool) -> None:
    """Chevron at the right edge of an editable cell, over a veil of the row's own color so a
    long text fades out under it instead of running into it."""
    rect = option.rect
    glyph = QRect(
        rect.right() - CELL_PADDING - CHEVRON_SIZE + 1,
        rect.top() + (rect.height() - 1 - CHEVRON_SIZE) // 2,
        CHEVRON_SIZE,
        CHEVRON_SIZE,
    )
    # sin pisar el filete de abajo ni el marco de foco de la fila actual
    top, height = rect.top() + 1, rect.height() - 3
    solid_left = glyph.left() - CHEVRON_LEAD
    background = _veil_color(option.state)
    clear = QColor(background)
    clear.setAlpha(0)
    fade = QRect(solid_left - CHEVRON_FADE, top, CHEVRON_FADE, height)
    gradient = QLinearGradient(fade.left(), 0, solid_left, 0)
    gradient.setColorAt(0, clear)
    gradient.setColorAt(1, background)
    painter.save()
    painter.fillRect(fade, QBrush(gradient))
    painter.fillRect(QRect(solid_left, top, rect.right() - solid_left + 1, height), background)
    device = painter.device()
    ratio = device.devicePixelRatio() if device is not None else 1.0
    color = TOKENS.incomplete if amber else TOKENS.slate
    painter.drawPixmap(
        glyph, icons.pixmap("chevron_down", color, CHEVRON_SIZE, device_pixel_ratio=ratio)
    )
    painter.restore()


def _draw_background(
    delegate: QStyledItemDelegate,
    painter: QPainter,
    option: QStyleOptionViewItem,
    index: ModelIndex,
) -> QStyleOptionViewItem:
    """Draws selection/hover like the default delegate but without text; returns the
    initialized option."""
    opt = QStyleOptionViewItem(option)
    delegate.initStyleOption(opt, index)
    opt.text = ""
    opt.icon = opt.icon.__class__()
    widget = opt.widget
    style = widget.style() if widget is not None else QApplication.style()
    style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)
    return opt


def status_column_width(font: QFont) -> int:
    """Width of the Estado column that shows the longest pill whole (icon, text, padding)."""
    widest = max(
        status_pill_size("blocked", text, font).width() for text in strings.PILL_LABELS.values()
    )
    return widest + 2 * CELL_PADDING


class StatusDelegate(QStyledItemDelegate):
    """Readiness pill (icon + text) on invoice rows; line rows keep the default text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        if not index.data(Role.IS_INVOICE):
            super().paint(painter, option, index)
            return
        opt = _draw_background(self, painter, option, index)
        status = index.data(Role.STATUS) or "blocked"
        text = index.data(Role.PILL_TEXT) or ""
        rect = option.rect.adjusted(CELL_PADDING, 0, -CELL_PADDING, 0)
        paint_status_pill(painter, rect, status, text, opt.font)

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:  # noqa: N802
        base = super().sizeHint(option, index)
        if not index.data(Role.IS_INVOICE):
            return base
        pill = status_pill_size(
            index.data(Role.STATUS) or "blocked", index.data(Role.PILL_TEXT) or "", option.font
        )
        return QSize(pill.width() + 2 * CELL_PADDING, max(base.height(), pill.height() + 6))


def _badge_font(font: QFont) -> QFont:
    styled = QFont(font)
    styled.setPixelSize(FONT_SIZES.caption)
    styled.setWeight(QFont.Weight.DemiBold)
    return styled


def badge_size(text: str, font: QFont) -> QSize:
    metrics = QFontMetrics(_badge_font(font))
    return QSize(metrics.horizontalAdvance(text) + 2 * BADGE_PAD_X, BADGE_HEIGHT)


def paint_type_badge(painter: QPainter, rect: QRect, text: str, font: QFont) -> QRect:
    """Small neutral badge (FC / NC) left-aligned and vertically centered in ``rect``."""
    style = STATUS_STYLES["archived"]
    size = badge_size(text, font)
    badge = QRect(
        rect.left(), rect.top() + (rect.height() - size.height()) // 2, size.width(), size.height()
    )
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(style.bg))
    painter.drawRoundedRect(badge, BADGE_RADIUS, BADGE_RADIUS)
    painter.setFont(_badge_font(font))
    painter.setPen(QColor(style.fg))
    painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)
    painter.restore()
    return badge


def _paint_line_row(
    delegate: QStyledItemDelegate,
    painter: QPainter,
    option: QStyleOptionViewItem,
    index: ModelIndex,
) -> None:
    """A line is "Línea 1" (muted) followed by its description (ink), drawn across Documento
    and Proveedor. Both cells paint the whole line, each clipped to its own rectangle, so
    repainting only one of them (hover, focus) never leaves the text half drawn."""
    tree = option.widget
    own = QRect(option.rect)
    span = QRect(own)
    if isinstance(tree, QTreeView):
        first = tree.visualRect(index.sibling(index.row(), Column.DOCUMENT))
        last = tree.visualRect(index.sibling(index.row(), Column.SUPPLIER))
        if first.isValid() and last.isValid():
            span = QRect(first.left(), own.top(), last.right() - first.left() + 1, own.height())
    painter.save()
    painter.setClipRect(own, Qt.ClipOperation.IntersectClip)
    background = QStyleOptionViewItem(option)
    delegate.initStyleOption(background, index)
    background.text = ""
    background.icon = QIcon()
    background.rect = span
    # El resalte por puntero es de una celda; en una linea que ocupa dos se omite
    background.state &= ~QStyle.StateFlag.State_MouseOver
    style = tree.style() if tree is not None else QApplication.style()
    style.drawControl(QStyle.ControlElement.CE_ItemViewItem, background, painter, tree)

    label = str(index.sibling(index.row(), Column.DOCUMENT).data(Qt.ItemDataRole.DisplayRole) or "")
    description = str(
        index.sibling(index.row(), Column.SUPPLIER).data(Qt.ItemDataRole.DisplayRole) or ""
    )
    inner = span.adjusted(CELL_PADDING, 0, -CELL_PADDING, 0)
    metrics = QFontMetrics(option.font)
    painter.setFont(option.font)
    painter.setPen(QColor(TOKENS.slate))
    painter.drawText(inner, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
    taken = metrics.horizontalAdvance(label) + LINE_LABEL_GAP
    text_rect = inner.adjusted(taken, 0, 0, 0)
    painter.setPen(QColor(TOKENS.ink))
    painter.drawText(
        text_rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        metrics.elidedText(description, Qt.TextElideMode.ElideRight, max(text_rect.width(), 0)),
    )
    painter.restore()


class SupplierDelegate(QStyledItemDelegate):
    """Supplier name on invoice rows; on a line it paints its share of the line text."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        if index.data(Role.IS_INVOICE):
            super().paint(painter, option, index)
            return
        _paint_line_row(self, painter, option, index)


class DocumentDelegate(QStyledItemDelegate):
    """FC/NC badge plus the document label on invoice rows."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: ModelIndex) -> None:
        if not index.data(Role.IS_INVOICE):
            _paint_line_row(self, painter, option, index)
            return
        opt = _draw_background(self, painter, option, index)
        label = index.data(Qt.ItemDataRole.DisplayRole) or ""
        badge = paint_type_badge(
            painter,
            option.rect.adjusted(CELL_PADDING - 2, 0, 0, 0),
            index.data(Role.DOCUMENT_TYPE) or "FC",
            opt.font,
        )
        text_left = badge.right() + 1 + BADGE_GAP
        text_rect = QRect(
            text_left,
            option.rect.top(),
            option.rect.right() - CELL_PADDING - text_left + 1,
            option.rect.height(),
        )
        painter.save()
        label_font = QFont(opt.font)
        label_font.setWeight(QFont.Weight.Medium)
        painter.setFont(label_font)
        painter.setPen(QColor(TOKENS.ink))
        shown = QFontMetrics(label_font).elidedText(
            label, Qt.TextElideMode.ElideRight, max(text_rect.width(), 0)
        )
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, shown
        )
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: ModelIndex) -> QSize:  # noqa: N802
        base = super().sizeHint(option, index)
        if not index.data(Role.IS_INVOICE):
            return base
        badge = badge_size(index.data(Role.DOCUMENT_TYPE) or "FC", option.font)
        return QSize(
            base.width() + badge.width() + BADGE_GAP, max(base.height(), badge.height() + 8)
        )


__all__ = [
    "CodeDelegate",
    "DocumentDelegate",
    "StatusDelegate",
    "SupplierDelegate",
    "badge_size",
    "paint_type_badge",
    "row_is_active",
    "status_column_width",
]
