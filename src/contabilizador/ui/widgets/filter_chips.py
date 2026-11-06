"""Filter chips with counts: ``Listas (18)``. Exactly one chip is active."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QToolButton, QWidget

from contabilizador.ui.widgets.exclusive_buttons import ExclusiveButtons


class FilterChips(ExclusiveButtons):
    """Wraps onto more rows when narrow: six chips with counts never widen the window."""

    filter_changed = Signal(str)
    ROLE = "chip"
    WRAP = True

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts: dict[str, int] = {}
        self.changed.connect(self.filter_changed)

    def set_chips(self, chips: Sequence[tuple[str, str]]) -> None:
        self.set_options(chips)
        self._counts = {}

    def set_counts(self, counts: Mapping[str, int]) -> None:
        self._counts = dict(counts)
        for key, label in self._labels.items():
            count = self._counts.get(key)
            self._refresh_label(key, f"{label} ({count})" if count is not None else label)

    def chip(self, key: str) -> QToolButton:
        return self.button(key)
