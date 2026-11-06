"""Delete confirmation: a destructive action named by its verb, Cancelar as the default."""

from PySide6.QtWidgets import QMessageBox

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.confirm import build_confirmation


def test_confirmation_names_the_action_and_defaults_to_cancel(qtbot) -> None:
    box, accept = build_confirmation(
        None, strings.confirm_delete("Beta"), strings.SUPPLIER_DELETE_DETAIL, strings.ACTION_DELETE
    )
    qtbot.addWidget(box)

    assert box.text() == strings.confirm_delete("Beta")
    assert box.informativeText() == strings.SUPPLIER_DELETE_DETAIL
    assert accept.text() == strings.ACTION_DELETE
    assert accept.property("variant") == "danger"
    # El orden de los botones depende de la plataforma (macOS pone Cancelar primero)
    assert {button.text() for button in box.buttons()} == {
        strings.ACTION_DELETE,
        strings.ACTION_CANCEL,
    }
    default = box.defaultButton()
    assert default is not None
    assert default.text() == strings.ACTION_CANCEL
    assert box.icon() == QMessageBox.Icon.Warning
