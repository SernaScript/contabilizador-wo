"""Status notice of the export sheet: icon + bold title + sentences, with an optional
fix button and an optional confirmation checkbox (status is never color alone)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from contabilizador.ui.theme import STATUS_STYLES
from contabilizador.ui.widgets import icon_label, make_label

ICON_SIZE = 18


class Notice(QFrame):
    action_triggered = Signal()
    confirmed_changed = Signal(bool)

    def __init__(
        self,
        status: str,
        *,
        confirm_label: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "banner")
        self.setProperty("status", status)
        style = STATUS_STYLES[status]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self.icon_label = icon_label(style.icon, style.fg, ICON_SIZE)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignTop)

        content = QVBoxLayout()
        content.setSpacing(4)
        self.title_label = make_label("", role="value")
        self.title_label.setWordWrap(True)
        content.addWidget(self.title_label)
        self.body_label = make_label("")
        self.body_label.setWordWrap(True)
        # Nombres de proveedores: nunca se interpretan como HTML
        self.body_label.setTextFormat(Qt.TextFormat.PlainText)
        self.body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content.addWidget(self.body_label)

        self.action_button = QPushButton("")
        self.action_button.hide()
        self.action_button.clicked.connect(self.action_triggered)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 4, 0, 0)
        actions.addWidget(self.action_button)
        actions.addStretch(1)
        content.addLayout(actions)

        self.checkbox = QCheckBox(confirm_label or "")
        self.checkbox.setVisible(bool(confirm_label))
        self.checkbox.toggled.connect(self.confirmed_changed)
        content.addWidget(self.checkbox)
        layout.addLayout(content, 1)

    def set_content(self, title: str, lines: Sequence[str]) -> None:
        self.title_label.setText(title)
        self.body_label.setText("\n".join(lines))
        self.body_label.setVisible(bool(lines))

    def set_action(self, label: str | None) -> None:
        self.action_button.setText(label or "")
        self.action_button.setVisible(bool(label))

    @property
    def confirmed(self) -> bool:
        return self.checkbox.isChecked()

    def reset_confirmation(self) -> None:
        self.checkbox.setChecked(False)
