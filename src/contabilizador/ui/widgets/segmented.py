"""Segmented control (Productos | Centros de costo): one option active, no tabs."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from contabilizador.ui.widgets.exclusive_buttons import ExclusiveButtons


class Segmented(ExclusiveButtons):
    ROLE = "segment"
    SPACING = 0

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
