"""Base for exclusive button rows (filter chips, segmented control)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLayout, QToolButton, QWidget

from contabilizador.ui.widgets.common import flag, set_property
from contabilizador.ui.widgets.flow_layout import FlowLayout


class ExclusiveButtons(QWidget):
    """One checkable ``QToolButton`` per option; exactly one checked at a time.

    ``WRAP`` buttons flow onto more rows when the width runs out (filter chips); otherwise
    they stay on one row (segmented control).
    """

    changed = Signal(str)
    ROLE = "chip"
    SPACING = 6
    WRAP = False

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._buttons: dict[str, QToolButton] = {}
        self._labels: dict[str, str] = {}
        self._current: str | None = None
        self._layout: QLayout
        if self.WRAP:
            self._layout = FlowLayout(self, spacing=self.SPACING, row_spacing=self.SPACING)
        else:
            row = QHBoxLayout(self)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(self.SPACING)
            row.addStretch(1)
            self._layout = row
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(self._on_clicked)

    def set_options(self, options: Sequence[tuple[str, str]]) -> None:
        for button in self._buttons.values():
            self._group.removeButton(button)
            self._layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        self._labels.clear()
        for index, (key, label) in enumerate(options):
            button = QToolButton()
            button.setText(label)
            button.setCheckable(True)
            button.setProperty("role", self.ROLE)
            button.setProperty("key", key)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            if index == 0:
                button.setProperty("position", "first")
            if index == len(options) - 1:
                button.setProperty("position", "last" if index else "only")
            self._group.addButton(button)
            if isinstance(self._layout, QHBoxLayout):
                self._layout.insertWidget(self._layout.count() - 1, button)  # antes del resorte
            else:
                self._layout.addWidget(button)
            self._buttons[key] = button
            self._labels[key] = label
        self._current = None
        if options:
            self.set_current(options[0][0])

    def button(self, key: str) -> QToolButton:
        return self._buttons[key]

    def keys(self) -> list[str]:
        return list(self._buttons)

    def current(self) -> str | None:
        return self._current

    def set_current(self, key: str) -> None:
        button = self._buttons[key]
        button.setChecked(True)
        self._set_current(key, emit=False)

    def _set_current(self, key: str, *, emit: bool) -> None:
        if key == self._current:
            return
        self._current = key
        for other_key, other in self._buttons.items():
            set_property(other, "active", flag(other_key == key))
        if emit:
            self.changed.emit(key)

    def _on_clicked(self, button: QToolButton) -> None:
        key = button.property("key")
        if isinstance(key, str):
            self._set_current(key, emit=True)

    def _refresh_label(self, key: str, text: str) -> None:
        self._buttons[key].setText(text)
