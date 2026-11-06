"""Sheet: dialog chrome with header (title, subtitle), body and footer (Cancelar + primary).

Pages build their forms inside ``body_layout`` (or ``set_body``) and react to
``accepted``/``rejected``; ``set_busy`` locks the footer, Esc and the window close button
while a task runs (its result still finds the sheet). Enter presses the
primary button from any field, and the footer buttons keep their natural width at the right
edge whether or not an error is shown.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui.widgets.common import make_label


class Sheet(QDialog):
    def __init__(
        self,
        title: str,
        *,
        subtitle: str | None = None,
        primary_label: str = strings.ACTION_SAVE,
        cancel_label: str = strings.ACTION_CANCEL,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("role", "sheet")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(520)
        self._busy = False
        self._primary_enabled = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = QFrame()
        self.header.setProperty("role", "sheet-header")
        header_layout = QVBoxLayout(self.header)
        header_layout.setContentsMargins(24, 20, 24, 16)
        header_layout.setSpacing(4)
        self.title_label = make_label(title, role="page-title")
        header_layout.addWidget(self.title_label)
        self.subtitle_label: QLabel = make_label(subtitle or "", role="purpose")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        header_layout.addWidget(self.subtitle_label)
        root.addWidget(self.header)

        self.body = QFrame()
        self.body.setProperty("role", "sheet-body")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(24, 20, 24, 20)
        self.body_layout.setSpacing(12)
        root.addWidget(self.body, 1)

        self.footer = QFrame()
        self.footer.setProperty("role", "sheet-footer")
        self._footer_layout = QHBoxLayout(self.footer)
        self._footer_layout.setContentsMargins(24, 12, 24, 12)
        self._footer_layout.setSpacing(8)
        self.error_label = make_label("", role="error")
        self.error_label.setWordWrap(True)
        # Oculto sigue ocupando el espacio libre: los botones no se estiran por todo el pie
        policy = self.error_label.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.error_label.setSizePolicy(policy)
        self.error_label.hide()
        self._footer_layout.addWidget(self.error_label, 1)
        self.cancel_button = QPushButton(cancel_label)
        self.cancel_button.clicked.connect(self.reject)
        self._footer_layout.addWidget(self.cancel_button)
        self.primary_button = QPushButton(primary_label)
        self.primary_button.setProperty("variant", "primary")
        self.primary_button.clicked.connect(self.accept)
        self._footer_layout.addWidget(self.primary_button)
        root.addWidget(self.footer)
        # Ya dentro del dialogo: solo asi QDialog lo registra como boton por defecto (si se
        # marca antes, al pasar el foco por Cancelar este queda como predeterminado)
        self.primary_button.setDefault(True)
        self._extra_buttons: list[QPushButton] = []

    # --- cuerpo --------------------------------------------------------------
    def set_body(self, widget: QWidget) -> None:
        self.body_layout.addWidget(widget)

    # --- pie -----------------------------------------------------------------
    def add_button(self, text: str, *, variant: str = "secondary") -> QPushButton:
        """Extra footer button placed before Cancelar (e.g. Omitir)."""
        button = QPushButton(text)
        if variant != "secondary":
            button.setProperty("variant", variant)
        position = self._footer_layout.indexOf(self.cancel_button)
        self._footer_layout.insertWidget(position, button)
        self._extra_buttons.append(button)
        return button

    def set_primary_label(self, text: str) -> None:
        self.primary_button.setText(text)

    def set_primary_enabled(self, enabled: bool) -> None:
        self._primary_enabled = enabled
        self._sync_buttons()

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._sync_buttons()

    def set_error(self, text: str | None) -> None:
        self.error_label.setText(text or "")
        self.error_label.setVisible(bool(text))

    def _sync_buttons(self) -> None:
        self.primary_button.setEnabled(self._primary_enabled and not self._busy)
        self.cancel_button.setEnabled(not self._busy)
        for button in self._extra_buttons:
            button.setEnabled(not self._busy)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if self.primary_button.isEnabled():
            self.primary_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._busy and event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def reject(self) -> None:
        # Cancelar, Esc y el boton de cerrar pasan por aqui: a medio guardar no se cierra
        if self._busy:
            return
        super().reject()
