"""Empty state: icon, title, explanation and one primary action that invites to act."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets.common import flag, icon_label, make_label, set_property

ICON_SIZE = 40
# Ancho maximo de la columna de texto: lineas comodas de leer en ventanas anchas
COLUMN_MAX_WIDTH = 440


class EmptyState(QFrame):
    action_triggered = Signal()

    def __init__(
        self,
        icon_name: str,
        title: str,
        text: str = "",
        action_label: str | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "empty-state")
        self.setProperty("active", flag(False))
        # Columna centrada con estiramientos y no con alineacion del layout: un elemento
        # alineado conserva el ancho que sugiere, pero su altura se calcularia para todo el
        # ancho disponible y el texto partido en lineas quedaria cortado
        column = QWidget()
        column.setMaximumWidth(COLUMN_MAX_WIDTH)
        content = QVBoxLayout(column)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        self.icon_label = icon_label(icon_name, TOKENS.blue, ICON_SIZE)
        content.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title_label = make_label(title, role="section")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setWordWrap(True)
        content.addWidget(self.title_label)
        self.text_label: QLabel = make_label(text, role="muted")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setVisible(bool(text))
        content.addWidget(self.text_label)
        self.action_button = QPushButton(action_label or "")
        self.action_button.setProperty("variant", "primary")
        self.action_button.setVisible(bool(action_label))
        self.action_button.clicked.connect(self.action_triggered)
        content.addSpacing(6)
        content.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(column)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 40, 32, 40)
        layout.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_text(self, text: str) -> None:
        self.text_label.setText(text)
        self.text_label.setVisible(bool(text))

    def set_action(self, label: str | None) -> None:
        self.action_button.setText(label or "")
        self.action_button.setVisible(bool(label))

    def set_active(self, active: bool) -> None:
        """Highlights the drop zone while something is dragged over the window."""
        set_property(self, "active", flag(active))
