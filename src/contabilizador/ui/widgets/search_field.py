"""Search box with a leading icon, clear button, Esc to clear and a debounced signal."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit, QWidget

from contabilizador.shared import strings
from contabilizador.ui import actions, icons
from contabilizador.ui.theme import TOKENS

DEFAULT_DEBOUNCE_MS = 150


class SearchField(QLineEdit):
    search_changed = Signal(str)

    def __init__(
        self,
        placeholder: str = strings.SEARCH_PLACEHOLDER,
        *,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setToolTip(actions.with_shortcut(strings.SHORTCUT_SEARCH, "search"))
        self.setAccessibleName(placeholder)
        self.addAction(icons.icon("search", TOKENS.slate), QLineEdit.ActionPosition.LeadingPosition)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(debounce_ms)
        self._timer.timeout.connect(self._emit)
        self._last_emitted = ""
        self.textChanged.connect(self._schedule)

    def set_debounce_ms(self, milliseconds: int) -> None:
        self._timer.setInterval(milliseconds)

    def clear_now(self) -> None:
        """Clears the text and announces it at once (no debounce), for code that must see
        every row right away (e.g. to open an editor on a row the search hid)."""
        self.clear()
        self._timer.stop()
        self._emit()

    def _schedule(self, _text: str) -> None:
        self._timer.start()

    def _emit(self) -> None:
        text = self.text()
        if text != self._last_emitted:
            self._last_emitted = text
            self.search_changed.emit(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt API
        if event.key() == Qt.Key.Key_Escape and self.text():
            self.clear()
            event.accept()
            return
        super().keyPressEvent(event)
