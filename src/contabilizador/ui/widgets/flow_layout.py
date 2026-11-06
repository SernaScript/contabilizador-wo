"""Flow layout: items left to right, wrapping onto a new row when the width runs out.

Its preferred size is one single row; its minimum width is the widest item, so a row of
chips never forces the window wider than the screen.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    def __init__(
        self, parent: QWidget | None = None, *, spacing: int = 6, row_spacing: int = 6
    ) -> None:
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._spacing = spacing
        self._row_spacing = row_spacing
        self.setContentsMargins(0, 0, 0, 0)

    # --- contenido (API de QLayout) -------------------------------------------------------
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 - Qt API
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt API
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802 - Qt API
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    # --- tamanos -------------------------------------------------------------------------
    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802 - Qt API
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - Qt API
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - Qt API
        return self._arrange(QRect(0, 0, width, 0), apply=False)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        visible = self._visible_items()
        if not visible:
            return QSize(0, 0)
        width = sum(item.sizeHint().width() for item in visible)
        width += self._spacing * (len(visible) - 1)
        height = max(item.sizeHint().height() for item in visible)
        return self._with_margins(QSize(width, height))

    def minimumSize(self) -> QSize:  # noqa: N802 - Qt API
        size = QSize(0, 0)
        for item in self._visible_items():
            size = size.expandedTo(item.minimumSize())
        return self._with_margins(size)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802 - Qt API
        super().setGeometry(rect)
        self._arrange(rect, apply=True)

    # --- distribucion ----------------------------------------------------------------------
    def _visible_items(self) -> list[QLayoutItem]:
        return [item for item in self._items if not item.isEmpty()]

    def _with_margins(self, size: QSize) -> QSize:
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _rows(self, width: int) -> list[list[QLayoutItem]]:
        """Splits the visible items into rows that fit ``width`` (at least one per row)."""
        rows: list[list[QLayoutItem]] = []
        row: list[QLayoutItem] = []
        used = 0
        for item in self._visible_items():
            item_width = item.sizeHint().width()
            needed = item_width if not row else used + self._spacing + item_width
            if row and needed > width:
                rows.append(row)
                row, used = [], 0
                needed = item_width
            row.append(item)
            used = needed
        if row:
            rows.append(row)
        return rows

    def _arrange(self, rect: QRect, *, apply: bool) -> int:
        """Places the items (when ``apply``) and returns the height they need; items of
        different heights are centered vertically within their row."""
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        y = area.y()
        for position, row in enumerate(self._rows(area.width())):
            if position:
                y += self._row_spacing
            row_height = max(item.sizeHint().height() for item in row)
            x = area.x()
            for item in row:
                hint = item.sizeHint()
                if apply:
                    top = y + (row_height - hint.height()) // 2
                    item.setGeometry(QRect(QPoint(x, top), hint))
                x += hint.width() + self._spacing
            y += row_height
        return y - rect.y() + margins.bottom()
