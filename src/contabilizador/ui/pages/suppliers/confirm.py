"""Confirmation before deleting: the destructive button carries the verb, not "Sí"."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QPushButton, QWidget

from contabilizador.shared import strings


def build_confirmation(
    parent: QWidget | None, title: str, detail: str, accept_label: str
) -> tuple[QMessageBox, QPushButton]:
    """The box and its destructive button; Cancelar is the default so Enter is safe."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    # macOS no muestra el titulo de la ventana: la pregunta va en el texto principal
    box.setText(title)
    box.setInformativeText(detail)
    accept = box.addButton(accept_label, QMessageBox.ButtonRole.DestructiveRole)
    accept.setProperty("variant", "danger")
    cancel = box.addButton(strings.ACTION_CANCEL, QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box, accept


def ask_confirmation(parent: QWidget | None, title: str, detail: str, accept_label: str) -> bool:
    """Modal question; True only when the destructive button was chosen."""
    box, accept = build_confirmation(parent, title, detail, accept_label)
    box.exec()
    return box.clickedButton() is accept
