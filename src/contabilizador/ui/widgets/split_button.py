"""Split button: a primary action plus a menu of alternatives (Importar ▾)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QToolButton, QWidget

from contabilizador.ui import actions, icons
from contabilizador.ui.theme import TOKENS


class SplitButton(QWidget):
    clicked = Signal()

    def __init__(
        self,
        text: str,
        *,
        icon_name: str | None = None,
        shortcut_id: str | None = None,
        variant: str = "primary",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.main_button = QPushButton(text)
        self.main_button.setProperty("variant", variant)
        self.main_button.setProperty("split", "main")
        self.main_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.main_button.setStyleSheet(
            "QPushButton { border-top-right-radius: 0; border-bottom-right-radius: 0; }"
        )
        if icon_name:
            self.main_button.setIcon(icons.icon(icon_name, TOKENS.on_blue))
            self.main_button.setIconSize(QSize(16, 16))
        self.main_button.setToolTip(
            actions.with_shortcut(text, shortcut_id) if shortcut_id else text
        )
        self.main_button.clicked.connect(self.clicked)
        layout.addWidget(self.main_button)

        self.menu = QMenu(self)
        self.arrow_button = QToolButton()
        self.arrow_button.setProperty("role", "split-arrow")
        self.arrow_button.setIcon(icons.icon("chevron_down", TOKENS.on_blue))
        self.arrow_button.setIconSize(QSize(14, 14))
        self.arrow_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.arrow_button.setMenu(self.menu)
        self.arrow_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arrow_button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.arrow_button.setToolTip(text)
        self.arrow_button.setAccessibleName(f"{text}: más opciones")
        layout.addWidget(self.arrow_button)

    def add_option(
        self, text: str, *, icon_name: str | None = None, shortcut_id: str | None = None
    ) -> QAction:
        """Menu entry; the caller connects ``action.triggered``."""
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icons.icon(icon_name, TOKENS.slate))
        if shortcut_id:
            action.setShortcut(actions.shortcut(shortcut_id).sequence())
            action.setShortcutVisibleInContextMenu(True)
            # El atajo real lo registra la ventana; aqui solo se muestra
            action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.menu.addAction(action)
        return action

    def set_text(self, text: str) -> None:
        self.main_button.setText(text)
