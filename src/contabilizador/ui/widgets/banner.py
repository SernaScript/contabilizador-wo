"""Inline banner (status-colored) with an optional action button."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from contabilizador.ui.theme import STATUS_STYLES
from contabilizador.ui.widgets.common import icon_label, set_icon_label, set_property


class Banner(QFrame):
    action_triggered = Signal()

    def __init__(
        self,
        text: str = "",
        *,
        status: str = "incomplete",
        action_label: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "banner")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)
        style = STATUS_STYLES[status]
        self.icon_label = icon_label(style.icon, style.fg, 18)
        layout.addWidget(self.icon_label)
        self.text_label = QLabel(text)
        self.text_label.setWordWrap(True)
        layout.addWidget(self.text_label, 1)
        self.action_button = QPushButton(action_label or "")
        self.action_button.setProperty("variant", "secondary")
        self.action_button.setVisible(bool(action_label))
        self.action_button.clicked.connect(self.action_triggered)
        layout.addWidget(self.action_button)
        self.set_status(status)

    def text(self) -> str:
        return self.text_label.text()

    def set_text(self, text: str) -> None:
        self.text_label.setText(text)

    def set_status(self, status: str) -> None:
        style = STATUS_STYLES[status]
        set_icon_label(self.icon_label, style.icon, style.fg, 18)
        set_property(self, "status", status)

    def set_action(self, label: str | None) -> None:
        self.action_button.setText(label or "")
        self.action_button.setVisible(bool(label))
