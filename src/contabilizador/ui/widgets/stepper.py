"""Three-step flow indicator (Importar, Completar, Exportar); steps are clickable."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from contabilizador.shared import strings
from contabilizador.ui.widgets.common import make_label, set_property

DEFAULT_STEPS = (strings.STEP_IMPORT, strings.STEP_COMPLETE, strings.STEP_EXPORT)
STATES = ("todo", "current", "done")


class Stepper(QWidget):
    step_clicked = Signal(int)

    def __init__(
        self, labels: Sequence[str] = DEFAULT_STEPS, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._buttons: list[QToolButton] = []
        self._numbers: list[QLabel] = []
        self._lines: list[QFrame] = []
        self._states: list[str] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for index, label in enumerate(labels):
            if index:
                line = QFrame()
                line.setProperty("role", "step-line")
                line.setFixedSize(24, 1)
                layout.addWidget(line)
                self._lines.append(line)
            number = make_label(str(index + 1), role="step-number")
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(number)
            button = QToolButton()
            button.setText(label)
            button.setProperty("role", "step")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            button.setToolTip(label)
            button.clicked.connect(lambda _checked=False, i=index: self.step_clicked.emit(i))
            layout.addWidget(button)
            self._buttons.append(button)
            self._numbers.append(number)
            self._states.append("todo")
        layout.addStretch(1)
        if labels:
            self.set_current(0)

    def count(self) -> int:
        return len(self._buttons)

    def button(self, index: int) -> QToolButton:
        return self._buttons[index]

    def number(self, index: int) -> QLabel:
        return self._numbers[index]

    def state(self, index: int) -> str:
        return self._states[index]

    def set_state(self, index: int, state: str) -> None:
        if state not in STATES:
            raise ValueError(state)
        self._states[index] = state
        set_property(self._buttons[index], "state", state)
        set_property(self._numbers[index], "state", state)
        if index > 0:
            set_property(self._lines[index - 1], "state", "done" if state != "todo" else "todo")
        tooltip = self._buttons[index].text()
        if state == "done":
            tooltip = f"{tooltip}: {strings.STEP_DONE}"
        elif state == "current":
            tooltip = f"{tooltip}: {strings.STEP_CURRENT}"
        self._buttons[index].setToolTip(tooltip)

    def set_current(self, index: int) -> None:
        """Marks earlier steps done, ``index`` current and later steps pending."""
        for position in range(len(self._buttons)):
            if position < index:
                self.set_state(position, "done")
            elif position == index:
                self.set_state(position, "current")
            else:
                self.set_state(position, "todo")
