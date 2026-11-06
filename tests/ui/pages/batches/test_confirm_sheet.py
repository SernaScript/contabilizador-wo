"""Confirmation sheet of the batch actions: says what will happen, starts on Cancelar."""

from PySide6.QtCore import Qt

from contabilizador.shared import strings
from contabilizador.ui.widgets.confirm_sheet import ConfirmSheet


def make_sheet(
    qtbot, *, emphasis: str = "", notes: tuple[str, ...] | list[str] = (), destructive: bool = True
) -> ConfirmSheet:
    sheet = ConfirmSheet(
        "¿Anular el lote 3?",
        "Las 3 facturas volverán a estar pendientes.",
        confirm_label=strings.ACTION_VOID_BATCH,
        emphasis=emphasis,
        notes=notes,
        destructive=destructive,
    )
    qtbot.addWidget(sheet)
    sheet.show()
    return sheet


def test_states_the_title_the_consequence_and_the_emphasized_sentence(qtbot) -> None:
    sheet = make_sheet(
        qtbot,
        emphasis="Los consecutivos FC 100 a 102 quedarán disponibles otra vez.",
        notes=["Esto no se puede deshacer."],
    )

    assert sheet.title_label.text() == "¿Anular el lote 3?"
    assert sheet.message_label.text() == "Las 3 facturas volverán a estar pendientes."
    assert sheet.emphasis_label is not None
    assert (
        sheet.emphasis_label.text()
        == "Los consecutivos FC 100 a 102 quedarán disponibles otra vez."
    )
    assert sheet.emphasis_label.property("role") == "value"
    assert [label.text() for label in sheet.note_labels] == ["Esto no se puede deshacer."]
    assert sheet.primary_button.text() == strings.ACTION_VOID_BATCH


def test_without_emphasis_there_is_no_emphasis_label(qtbot) -> None:
    sheet = make_sheet(qtbot)

    assert sheet.emphasis_label is None


def test_destructive_confirmation_is_red_and_starts_on_cancelar(qtbot) -> None:
    sheet = make_sheet(qtbot)

    assert sheet.primary_button.property("variant") == "danger"
    assert sheet.primary_button.property("filled") == "true"
    assert sheet.focusWidget() is sheet.cancel_button


def test_enter_on_the_dialog_confirms_the_default_button_not_cancel(qtbot) -> None:
    sheet = make_sheet(qtbot, destructive=False)
    sheet.message_label.setFocus()

    with qtbot.waitSignal(sheet.accepted, timeout=1000):
        qtbot.keyClick(sheet, Qt.Key.Key_Return)


def test_buttons_keep_their_size_and_sit_on_the_right(qtbot) -> None:
    sheet = make_sheet(qtbot)

    button = sheet.primary_button
    assert button.width() <= button.sizeHint().width() + 8
    assert abs(button.geometry().right() - (sheet.footer.rect().right() - 24)) <= 2


def test_escape_rejects(qtbot) -> None:
    sheet = make_sheet(qtbot)

    with qtbot.waitSignal(sheet.rejected, timeout=1000):
        qtbot.keyClick(sheet, Qt.Key.Key_Escape)
