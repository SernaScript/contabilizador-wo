"""Toasts: short confirmations at the bottom-right of a window, auto-dismissed."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPropertyAnimation,
    QTimer,
    Signal,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui.theme import STATUS_STYLES, TOKENS
from contabilizador.ui.widgets.common import IconButton, icon_label

WRAP_THRESHOLD = 56
KIND_STATUS = {"success": "ready", "error": "blocked", "warning": "incomplete", "info": None}
KIND_ICON = {"success": "ready", "error": "blocked", "warning": "incomplete", "info": "info"}


class Toast(QFrame):
    dismissed = Signal()
    action_triggered = Signal()
    FADE_MS = 160

    def __init__(
        self,
        message: str,
        *,
        kind: str = "info",
        action_label: str | None = None,
        timeout_ms: int = 5000,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._kind = kind
        self._dismissing = False
        self.setProperty("role", "toast")
        self.setProperty("status", KIND_STATUS.get(kind))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 8, 10)
        layout.setSpacing(10)
        style = STATUS_STYLES.get(KIND_STATUS.get(kind) or "")
        color = style.fg if style is not None and kind != "info" else TOKENS.on_blue
        self.icon_label = icon_label(KIND_ICON.get(kind, "info"), color, 18)
        self.icon_label.setProperty("role", "toast-icon")
        layout.addWidget(self.icon_label)
        self.message_label = QLabel(message)
        # Solo los mensajes largos se parten en lineas; los cortos van en una sola
        self.message_label.setWordWrap(len(message) > WRAP_THRESHOLD)
        self.message_label.setMaximumWidth(360)
        layout.addWidget(self.message_label, 1)
        self.action_button = QPushButton(action_label or "")
        self.action_button.setVisible(bool(action_label))
        self.action_button.clicked.connect(self._on_action)
        layout.addWidget(self.action_button)
        self.close_button = IconButton("close", strings.TOAST_CLOSE, color=TOKENS.on_blue)
        self.close_button.clicked.connect(self.dismiss)
        layout.addWidget(self.close_button)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        if timeout_ms > 0:
            self._timer.start(timeout_ms)

    @property
    def kind(self) -> str:
        return self._kind

    def message(self) -> str:
        return self.message_label.text()

    def set_message(self, text: str) -> None:
        self.message_label.setWordWrap(len(text) > WRAP_THRESHOLD)
        self.message_label.setText(text)
        self.adjustSize()

    def _on_action(self) -> None:
        self.action_triggered.emit()
        self.dismiss()

    def dismiss(self) -> None:
        if self._dismissing:
            return
        self._dismissing = True
        self._timer.stop()
        if not self.isVisible():
            self._finish()
            return
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(self.FADE_MS)
        animation.setStartValue(1.0)
        animation.setEndValue(0.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(self._finish)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _finish(self) -> None:
        self.hide()
        self.dismissed.emit()
        self.deleteLater()


class ToastHost(QObject):
    """Owns the toasts of one window; stacks them bottom-right and follows resizes.

    The host widget is read from Qt (``parent()``) instead of a Python attribute, and the
    resize filter tolerates a wrapper whose Python state is already gone: Qt can call it
    while the cycle collector tears the window down.
    """

    MARGIN = 16
    SPACING = 8

    def __init__(self, parent: QWidget, *, bottom_offset: int = 0) -> None:
        super().__init__(parent)
        self._toasts: list[Toast] = []
        self._bottom_offset = max(0, bottom_offset)
        parent.installEventFilter(self)

    @property
    def bottom_offset(self) -> int:
        return self._bottom_offset

    def set_bottom_offset(self, pixels: int) -> None:
        """Lifts the stack above a footer (e.g. the readiness bar) so it never hides the CTA."""
        self._bottom_offset = max(0, pixels)
        self._relayout()

    def show_toast(
        self,
        message: str,
        *,
        kind: str = "info",
        action_label: str | None = None,
        on_action: Callable[[], None] | None = None,
        timeout_ms: int = 5000,
    ) -> Toast:
        toast = Toast(
            message,
            kind=kind,
            action_label=action_label,
            timeout_ms=timeout_ms,
            parent=self._host(),
        )
        if on_action is not None:
            toast.action_triggered.connect(on_action)
        toast.dismissed.connect(lambda t=toast: self._remove(t))
        self._toasts.append(toast)
        toast.adjustSize()
        toast.show()
        toast.raise_()
        self._relayout()
        return toast

    def toasts(self) -> list[Toast]:
        return list(self._toasts)

    def dismiss_all(self) -> None:
        for toast in list(self._toasts):
            toast.dismiss()

    def _host(self) -> QWidget | None:
        parent = self.parent()
        return parent if isinstance(parent, QWidget) else None

    def _remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._relayout()

    def _relayout(self) -> None:
        host = self._host()
        # Sin estado de Python (ventana a medio destruir) no hay nada que acomodar
        toasts: list[Toast] | None = getattr(self, "_toasts", None)
        if host is None or toasts is None:
            return
        bottom = host.height() - self.MARGIN - getattr(self, "_bottom_offset", 0)
        right = host.width() - self.MARGIN
        # El mas antiguo queda en la esquina; los nuevos se apilan encima sin mover a los demas
        for toast in toasts:
            size = toast.sizeHint()
            toast.resize(size)
            toast.move(right - size.width(), bottom - size.height())
            bottom -= size.height() + self.SPACING

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if event.type() == QEvent.Type.Resize and watched is self.parent():
            self._relayout()
        return super().eventFilter(watched, event)
