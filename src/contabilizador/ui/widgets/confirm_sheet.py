"""Confirmation sheet: says what will happen and asks once (delete, void, release)."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QWidget

from contabilizador.ui.theme import set_variant
from contabilizador.ui.widgets.common import make_label
from contabilizador.ui.widgets.sheet import Sheet


class ConfirmSheet(Sheet):
    """Says what will happen and asks once.

    ``message`` is the main consequence; ``emphasis`` is the sentence that must not be
    missed (for example whether consecutives come back); ``notes`` are quieter details.
    Destructive confirmations are red and start with the focus on Cancelar, so a stray Enter
    never executes them.
    """

    def __init__(
        self,
        title: str,
        message: str,
        *,
        confirm_label: str,
        emphasis: str = "",
        notes: Sequence[str] = (),
        destructive: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, primary_label=confirm_label, parent=parent)
        self._destructive = destructive
        self.title_label.setWordWrap(True)
        self.message_label = make_label(message)
        self.message_label.setWordWrap(True)
        self.body_layout.addWidget(self.message_label)
        self.emphasis_label = None
        if emphasis:
            self.emphasis_label = make_label(emphasis, role="value")
            self.emphasis_label.setWordWrap(True)
            self.body_layout.addWidget(self.emphasis_label)
        self.note_labels = []
        for note in notes:
            label = make_label(note, role="muted")
            label.setWordWrap(True)
            self.body_layout.addWidget(label)
            self.note_labels.append(label)
        if destructive:
            self.primary_button.setProperty("filled", "true")
            set_variant(self.primary_button, "danger")

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if self._destructive:
            self.cancel_button.setFocus(Qt.FocusReason.OtherFocusReason)
