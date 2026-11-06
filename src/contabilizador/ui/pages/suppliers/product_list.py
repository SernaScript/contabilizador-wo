"""Model, search proxy, delegate and view of the product checklist.

The list is a model/view with a custom delegate so a catalog of thousands of products stays
fast; the star is painted, not a widget per row. The rules of the selection live in the model
so every path (click, key, code) applies them the same way:

- the first product checked becomes the default;
- unchecking the default moves it to the first product still checked;
- choosing a default checks the product;
- a product that left the catalog stays listed (checked, flagged) until it is unchecked,
  and it can never be the default.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QPointF,
    QRect,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QHelpEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.formatting import code_and_name
from contabilizador.ui.pages.suppliers.rows import fold
from contabilizador.ui.theme import FONT_SIZES, TOKENS

CODE_ROLE = int(Qt.ItemDataRole.UserRole) + 1
NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 2
CHECKED_ROLE = int(Qt.ItemDataRole.UserRole) + 3
DEFAULT_ROLE = int(Qt.ItemDataRole.UserRole) + 4
MISSING_ROLE = int(Qt.ItemDataRole.UserRole) + 5
# Roles de accion: el delegado no conoce el modelo, solo pide "alternar" o "elegir"
TOGGLE_ROLE = int(Qt.ItemDataRole.UserRole) + 6
STAR_ROLE = int(Qt.ItemDataRole.UserRole) + 7
SEARCH_ROLE = int(Qt.ItemDataRole.UserRole) + 8

DEFAULT_SHORTCUT = "Ctrl+D"
ROW_HEIGHT = 34
PAD_X = 12
CHECK_SIZE = 16
STAR_SIZE = 18
TEXT_GAP = 10


def star_tooltip(*, is_default: bool) -> str:
    if is_default:
        return strings.PICKER_STAR_IS_DEFAULT
    shortcut = QKeySequence(DEFAULT_SHORTCUT).toString(QKeySequence.SequenceFormat.NativeText)
    return f"{strings.PICKER_STAR_SET} ({shortcut})"


def star_rect(row_rect: QRect) -> QRect:
    """Where the star of a row is painted and clicked."""
    left = row_rect.right() - PAD_X - STAR_SIZE + 1
    top = row_rect.top() + (row_rect.height() - STAR_SIZE) // 2
    return QRect(left, top, STAR_SIZE, STAR_SIZE)


@dataclass(slots=True)
class Entry:
    code: str
    name: str
    checked: bool = False
    missing: bool = False
    # Se pliega una vez al cargar: filtrar miles de filas por tecla no repite la normalizacion
    folded: str = field(init=False, default="")

    def __post_init__(self) -> None:
        self.folded = fold(f"{self.code} {self.name}")


class ProductsModel(QAbstractListModel):
    """Catalog rows with their checked state; ``changed`` fires on user-driven edits only."""

    changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._entries: list[Entry] = []
        self._default: str | None = None

    # --- lectura ---------------------------------------------------------------
    def checked_codes(self) -> tuple[str, ...]:
        return tuple(entry.code for entry in self._entries if entry.checked)

    def missing_codes(self) -> tuple[str, ...]:
        return tuple(entry.code for entry in self._entries if entry.missing)

    def default_code(self) -> str | None:
        return self._default

    def name_of(self, code: str) -> str:
        return next((entry.name for entry in self._entries if entry.code == code), "")

    def row_of(self, code: str) -> int:
        return next((row for row, entry in enumerate(self._entries) if entry.code == code), -1)

    # --- carga (sin avisar de cambios del usuario) -----------------------------
    def reset(self, entries: list[Entry], default: str | None) -> None:
        self.beginResetModel()
        self._entries = entries
        self._default = default
        self._normalise_default()
        self.endResetModel()

    # --- cambios del usuario -----------------------------------------------------
    def set_checked(self, code: str, checked: bool) -> None:
        row = self.row_of(code)
        if row < 0 or self._entries[row].checked == checked:
            return
        previous = self._default
        entry = self._entries[row]
        entry.checked = checked
        if not checked and entry.missing:
            # Un producto que ya no existe solo se puede quitar de la lista
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._entries[row]
            self.endRemoveRows()
        else:
            self._emit_row(row)
        self._normalise_default()
        self._refresh_default_rows(previous)
        self.changed.emit()

    def set_default(self, code: str) -> None:
        row = self.row_of(code)
        if row < 0 or self._entries[row].missing:
            return
        previous = self._default
        entry = self._entries[row]
        if not entry.checked:
            entry.checked = True
            self._emit_row(row)
        if previous == code and entry.checked:
            return
        self._default = code
        self._refresh_default_rows(previous)
        self.changed.emit()

    def _normalise_default(self) -> None:
        candidates = [e.code for e in self._entries if e.checked and not e.missing]
        if self._default not in candidates:
            self._default = candidates[0] if candidates else None

    def _refresh_default_rows(self, previous: str | None) -> None:
        for code in {previous, self._default} - {None}:
            row = self.row_of(code) if code is not None else -1
            if row >= 0:
                self._emit_row(row)

    def _emit_row(self, row: int) -> None:
        index = self.index(row)
        self.dataChanged.emit(index, index)

    # --- API de Qt ---------------------------------------------------------------
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008, N802
        return 0 if parent.isValid() else len(self._entries)

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = 0) -> object:
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return code_and_name(entry.code, entry.name)
        if role == Qt.ItemDataRole.ToolTipRole:
            if entry.missing:
                return strings.PICKER_MISSING_BADGE
            return code_and_name(entry.code, entry.name)
        if role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if entry.checked else Qt.CheckState.Unchecked
        if role == CODE_ROLE:
            return entry.code
        if role == NAME_ROLE:
            return entry.name
        if role == CHECKED_ROLE:
            return entry.checked
        if role == DEFAULT_ROLE:
            return entry.code == self._default
        if role == MISSING_ROLE:
            return entry.missing
        if role == SEARCH_ROLE:
            return entry.folded
        return None

    def setData(  # noqa: N802
        self, index: QModelIndex | QPersistentModelIndex, value: object, role: int = 0
    ) -> bool:
        if not index.isValid():
            return False
        entry = self._entries[index.row()]
        if role == TOGGLE_ROLE:
            self.set_checked(entry.code, not entry.checked)
            return True
        if role == STAR_ROLE:
            self.set_default(entry.code)
            return True
        if role == Qt.ItemDataRole.CheckStateRole:
            self.set_checked(entry.code, value == Qt.CheckState.Checked or value == 2)
            return True
        return False


class FilterProxy(QSortFilterProxyModel):
    """Contains-match on code and name that ignores case and accents."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._query = ""

    def set_query(self, text: str) -> None:
        self.beginFilterChange()
        self._query = fold(text).strip()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(  # noqa: N802
        self, source_row: int, source_parent: QModelIndex | QPersistentModelIndex
    ) -> bool:
        if not self._query:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        if index.data(MISSING_ROLE):
            return True  # hay que poder verlo para quitarlo
        return self._query in str(index.data(SEARCH_ROLE))


def _star_path(rect: QRect) -> QPainterPath:
    center = QPointF(rect.center()) + QPointF(0.5, 1.0)
    outer = rect.width() / 2 - 1
    inner = outer * 0.42
    points = [
        QPointF(
            center.x() + (outer if i % 2 == 0 else inner) * math.cos(math.radians(-90 + i * 36)),
            center.y() + (outer if i % 2 == 0 else inner) * math.sin(math.radians(-90 + i * 36)),
        )
        for i in range(10)
    ]
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    path.closeSubpath()
    return path


class ProductDelegate(QStyledItemDelegate):
    """Paints checkbox, ``code  name`` and, on checked rows, the star of the default."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pixmaps: dict[tuple[str, str, int, float], QPixmap] = {}

    def _pixmap(self, painter: QPainter, name: str, color: str, size: int) -> QPixmap:
        """Icon rendered once per (name, color, size, pixel ratio) of the painter's device."""
        device = painter.device()
        ratio = device.devicePixelRatio() if device is not None else 1.0
        key = (name, color, size, ratio)
        if key not in self._pixmaps:
            self._pixmaps[key] = icons.pixmap(name, color, size, device_pixel_ratio=ratio)
        return self._pixmaps[key]

    def sizeHint(  # noqa: N802
        self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> QSize:
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        rect = option.rect
        checked = bool(index.data(CHECKED_ROLE))
        missing = bool(index.data(MISSING_ROLE))
        is_default = bool(index.data(DEFAULT_ROLE))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(rect, QColor(TOKENS.mist))
        painter.setPen(QColor(TOKENS.hairline))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        box = QRect(rect.left() + PAD_X, rect.top() + (rect.height() - CHECK_SIZE) // 2, 16, 16)
        self._paint_checkbox(painter, box, checked)

        caption = QFont(option.font)
        caption.setPixelSize(FONT_SIZES.caption)
        caption.setWeight(QFont.Weight.Medium)
        right_edge = rect.right() - PAD_X
        if missing:
            right_edge = self._paint_missing(painter, rect, caption)
        elif checked:
            right_edge = self._paint_star(painter, rect, caption, is_default)
        self._paint_text(painter, option, box, right_edge, index)

        if option.state & QStyle.StateFlag.State_HasFocus:
            painter.setPen(QPen(QColor(TOKENS.blue), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 6, 6)
        painter.restore()

    def _paint_checkbox(self, painter: QPainter, box: QRect, checked: bool) -> None:
        frame = box.adjusted(1, 1, -1, -1)
        if checked:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(TOKENS.blue_hover))
            painter.drawRoundedRect(frame, 4, 4)
            tick = self._pixmap(painter, "check", TOKENS.on_blue, 14)
            painter.drawPixmap(QRect(box.left() + 1, box.top() + 1, 14, 14), tick)
        else:
            painter.setPen(QPen(QColor(TOKENS.slate), 1.2))
            painter.setBrush(QColor(TOKENS.paper))
            painter.drawRoundedRect(frame, 4, 4)

    @staticmethod
    def _paint_star(painter: QPainter, rect: QRect, caption: QFont, is_default: bool) -> int:
        """Draws the star (and the "Por defecto" label) and returns the free right edge."""
        area = star_rect(rect)
        color = QColor(TOKENS.blue_hover if is_default else TOKENS.slate)
        painter.setPen(
            QPen(
                color,
                1.4,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.setBrush(color if is_default else Qt.BrushStyle.NoBrush)
        painter.drawPath(_star_path(area))
        edge = area.left() - TEXT_GAP
        if is_default:
            width = QFontMetrics(caption).horizontalAdvance(strings.PICKER_DEFAULT_BADGE)
            label = QRect(edge - width, rect.top(), width, rect.height())
            painter.setFont(caption)
            painter.setPen(QColor(TOKENS.blue_hover))
            painter.drawText(
                label,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                strings.PICKER_DEFAULT_BADGE,
            )
            edge = label.left() - TEXT_GAP
        return edge

    def _paint_missing(self, painter: QPainter, rect: QRect, caption: QFont) -> int:
        """Warning icon + text for a product that left the catalog; returns the free edge."""
        icon_rect = star_rect(rect)
        painter.drawPixmap(
            icon_rect.adjusted(1, 1, -1, -1),
            self._pixmap(painter, "blocked", TOKENS.blocked, STAR_SIZE - 2),
        )
        width = QFontMetrics(caption).horizontalAdvance(strings.PICKER_MISSING_BADGE)
        label = QRect(icon_rect.left() - 6 - width, rect.top(), width, rect.height())
        painter.setFont(caption)
        painter.setPen(QColor(TOKENS.blocked))
        painter.drawText(
            label,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            strings.PICKER_MISSING_BADGE,
        )
        return label.left() - TEXT_GAP

    @staticmethod
    def _paint_text(
        painter: QPainter,
        option: QStyleOptionViewItem,
        box: QRect,
        right_edge: int,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        rect = option.rect
        left = box.right() + 1 + TEXT_GAP
        available = max(0, right_edge - left)
        code = str(index.data(CODE_ROLE))
        name = str(index.data(NAME_ROLE))
        strong = QFont(option.font)
        strong.setWeight(QFont.Weight.Medium)
        code_width = QFontMetrics(strong).horizontalAdvance(code)
        painter.setFont(strong)
        painter.setPen(QColor(TOKENS.ink))
        shown_code = QFontMetrics(strong).elidedText(code, Qt.TextElideMode.ElideRight, available)
        painter.drawText(
            QRect(left, rect.top(), available, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            shown_code,
        )
        room = available - code_width - TEXT_GAP
        if name and room > 24:
            plain = QFont(option.font)
            elided = QFontMetrics(plain).elidedText(name, Qt.TextElideMode.ElideRight, room)
            painter.setFont(plain)
            painter.setPen(QColor(TOKENS.slate))
            painter.drawText(
                QRect(left + code_width + TEXT_GAP, rect.top(), room, rect.height()),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided,
            )

    # --- interaccion --------------------------------------------------------------
    def editorEvent(  # noqa: N802
        self,
        event: QEvent,
        model: object,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        target = getattr(model, "setData", None)
        if target is None:
            return False
        if isinstance(event, QMouseEvent):
            if event.type() != QEvent.Type.MouseButtonRelease:
                return False
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            if self._hits_star(option.rect, event.position().toPoint(), index):
                target(index, True, STAR_ROLE)
            else:
                target(index, None, TOGGLE_ROLE)
            return True
        is_toggle_key = (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)
        )
        if is_toggle_key:
            target(index, None, TOGGLE_ROLE)
            return True
        return False

    @staticmethod
    def _hits_star(
        row_rect: QRect, position: QPoint, index: QModelIndex | QPersistentModelIndex
    ) -> bool:
        if not index.data(CHECKED_ROLE) or index.data(MISSING_ROLE):
            return False
        return star_rect(row_rect).adjusted(-6, -6, 6, 6).contains(position)

    def helpEvent(  # noqa: N802
        self,
        event: QHelpEvent,
        view: QAbstractItemView,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        if event.type() == QEvent.Type.ToolTip and self._hits_star(option.rect, event.pos(), index):
            text = star_tooltip(is_default=bool(index.data(DEFAULT_ROLE)))
            QToolTip.showText(event.globalPos(), text, view)
            return True
        return super().helpEvent(event, view, option, index)


class ProductListView(QListView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # La seleccion no se pinta: el estado de cada fila es su casilla
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(ProductDelegate(self))
        self.setMinimumHeight(ROW_HEIGHT * 5)
