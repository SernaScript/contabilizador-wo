"""Whole-window overlay shown while files are dragged over the app, plus mime helpers.

The overlay is transparent for mouse events: the window keeps receiving the drag/drop
events and only tells the overlay to show or hide.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets.common import icon_label, make_label


def paths_from_mime(mime: QMimeData) -> list[Path]:
    """Local file paths in a drag payload (remote URLs are ignored)."""
    if not mime.hasUrls():
        return []
    return [Path(url.toLocalFile()) for url in mime.urls() if url.isLocalFile()]


class _CoverWidget(QFrame):
    """Base for overlays that cover their parent and follow its size.

    The parent is read from Qt (``parentWidget``), never kept in a Python attribute: Qt can
    still call ``eventFilter`` while Python tears the wrapper down (the cycle collector
    empties ``__dict__`` before the C++ object dies), and a filter that needs Python state
    would raise inside Qt at that moment.
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        parent.installEventFilter(self)
        self.hide()

    def _cover(self) -> None:
        host = self.parentWidget()
        if host is not None:
            self.setGeometry(host.rect())
        self.raise_()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        # isHidden y no isVisible: tambien sigue al padre mientras la ventana esta oculta
        if (
            event.type() == QEvent.Type.Resize
            and not self.isHidden()
            and watched is self.parentWidget()
        ):
            self._cover()
        return super().eventFilter(watched, event)


class DropOverlay(_CoverWidget):
    def __init__(self, parent: QWidget, text: str = strings.DROP_OVERLAY_TEXT) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAcceptDrops(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(48, 48, 48, 48)
        self.card = QFrame()
        self.card.setProperty("role", "drop-overlay")
        card_layout = QVBoxLayout(self.card)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(12)
        card_layout.addWidget(
            icon_label("import", TOKENS.blue, 48), 0, Qt.AlignmentFlag.AlignHCenter
        )
        self.label: QLabel = make_label(text, role="section")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.label)
        layout.addWidget(self.card)

    @property
    def is_active(self) -> bool:
        return self.isVisible()

    def show_overlay(self) -> None:
        self._cover()
        self.show()

    def hide_overlay(self) -> None:
        self.hide()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        veil = QColor(TOKENS.paper)
        veil.setAlphaF(0.72)
        painter.fillRect(self.rect(), veil)
        painter.end()
        super().paintEvent(event)
