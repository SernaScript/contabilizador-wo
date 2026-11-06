"""Blocking overlay with a progress bar (determinate or not) and an optional Cancelar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets.common import make_label
from contabilizador.ui.widgets.drop_overlay import _CoverWidget


class BusyOverlay(_CoverWidget):
    cancel_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._running = False
        # Bloquea el raton del contenido mientras dura la tarea
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.card = QFrame()
        self.card.setProperty("role", "busy-card")
        self.card.setFixedWidth(420)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)
        self.message_label = make_label(strings.BUSY_DEFAULT_MESSAGE, role="section")
        card_layout.addWidget(self.message_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        card_layout.addWidget(self.progress_bar)
        footer = QHBoxLayout()
        self.progress_label = make_label("", role="caption")
        footer.addWidget(self.progress_label, 1)
        self.cancel_button = QPushButton(strings.ACTION_CANCEL)
        self.cancel_button.clicked.connect(self._on_cancel)
        footer.addWidget(self.cancel_button)
        card_layout.addLayout(footer)
        layout.addWidget(self.card)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(
        self, message: str = strings.BUSY_DEFAULT_MESSAGE, *, cancellable: bool = False
    ) -> None:
        self._running = True
        self.message_label.setText(message)
        self.progress_label.setText("")
        self.progress_bar.setRange(0, 0)
        self.cancel_button.setVisible(cancellable)
        self.cancel_button.setEnabled(True)
        self._cover()
        self.show()

    def set_message(self, text: str) -> None:
        self.message_label.setText(text)

    def set_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText("")
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_label.setText(strings.busy_progress(done, total))

    def finish(self) -> None:
        self._running = False
        self.hide()

    def _on_cancel(self) -> None:
        self.cancel_button.setEnabled(False)
        self.message_label.setText(strings.BUSY_CANCELLING)
        self.cancel_requested.emit()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        veil = QColor(TOKENS.mist)
        veil.setAlphaF(0.78)
        painter.fillRect(self.rect(), veil)
        painter.end()
        super().paintEvent(event)
