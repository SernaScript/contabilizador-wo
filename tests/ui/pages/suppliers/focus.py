"""Helper to read the Tab order of a dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


def focus_order_after(start: QWidget, owner: QWidget, count: int) -> list[QWidget]:
    """The next ``count`` widgets Tab would reach after ``start`` (visible and focusable)."""
    order: list[QWidget] = []
    current = start.nextInFocusChain()
    while current is not None and current is not start and len(order) < count:
        if current.isVisibleTo(owner) and current.focusPolicy() != Qt.FocusPolicy.NoFocus:
            order.append(current)
        current = current.nextInFocusChain()
    return order
