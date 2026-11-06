"""Input widgets: SearchField, CodeCombo, SplitButton, Sheet."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QMenu

from contabilizador.shared import strings
from contabilizador.ui.widgets.code_combo import CodeCombo, CodeItem
from contabilizador.ui.widgets.search_field import SearchField
from contabilizador.ui.widgets.sheet import Sheet
from contabilizador.ui.widgets.split_button import SplitButton

# --- SearchField ----------------------------------------------------------------


def test_search_field_debounces_and_clears_with_escape(qtbot) -> None:
    field = SearchField(debounce_ms=20)
    qtbot.addWidget(field)
    field.show()

    assert field.placeholderText() == strings.SEARCH_PLACEHOLDER
    assert field.property("role") == "search"
    assert field.isClearButtonEnabled()

    with qtbot.waitSignal(field.search_changed, timeout=2000) as blocker:
        qtbot.keyClicks(field, "abc")
    assert blocker.args == ["abc"]

    with qtbot.waitSignal(field.search_changed, timeout=2000) as blocker:
        qtbot.keyClick(field, Qt.Key.Key_Escape)
    assert blocker.args == [""]
    assert field.text() == ""


def test_search_field_clear_now_announces_at_once_and_only_once(qtbot) -> None:
    field = SearchField(debounce_ms=20)
    qtbot.addWidget(field)
    with qtbot.waitSignal(field.search_changed, timeout=2000):
        qtbot.keyClicks(field, "abc")
    emitted: list[str] = []
    field.search_changed.connect(emitted.append)

    field.clear_now()

    assert field.text() == ""
    assert emitted == [""]  # sin esperar el debounce
    qtbot.wait(60)
    assert emitted == [""]  # el temporizador no lo repite
    field.clear_now()  # ya vacio: no hay nada que anunciar
    assert emitted == [""]


# --- CodeCombo ------------------------------------------------------------------


def _combo(qtbot, **kwargs) -> CodeCombo:
    combo = CodeCombo(**kwargs)
    qtbot.addWidget(combo)
    combo.set_items(
        preferred=[CodeItem("1001", "Papelería")],
        rest=[CodeItem("2001", "Servicios"), CodeItem("3001", "Aseo")],
    )
    combo.show()
    return combo


def test_code_combo_sections_and_display(qtbot) -> None:
    combo = _combo(qtbot)

    assert combo.current_code() is None
    assert combo.codes() == ["1001", "2001", "3001"]
    assert combo.itemText(0) == "1001 - Papelería"
    assert combo.is_separator(1)
    assert combo.set_current_code("2001") is True
    assert combo.current_code() == "2001"
    assert combo.currentText() == "2001 - Servicios"
    assert combo.set_current_code("nope") is False
    assert combo.current_code() is None


def test_code_combo_commits_on_completer_selection(qtbot) -> None:
    combo = _combo(qtbot)
    line_edit = combo.lineEdit()
    assert line_edit is not None

    with qtbot.waitSignal(combo.committed, timeout=2000) as blocker:
        qtbot.keyClicks(line_edit, "serv")
        completer = combo.completer()
        assert completer is not None
        popup = completer.popup()
        assert popup is not None
        qtbot.waitUntil(popup.isVisible, timeout=2000)
        # Flujo real de teclado: escribir, bajar a la primera coincidencia, Enter
        qtbot.keyClick(popup, Qt.Key.Key_Down)
        qtbot.keyClick(popup, Qt.Key.Key_Enter)

    assert blocker.args == ["2001"]
    assert combo.current_code() == "2001"


def test_code_combo_rejects_free_text(qtbot) -> None:
    combo = _combo(qtbot)
    combo.set_current_code("1001")
    line_edit = combo.lineEdit()
    assert line_edit is not None
    seen: list[object] = []
    combo.committed.connect(seen.append)

    line_edit.selectAll()
    qtbot.keyClicks(line_edit, "zzz")
    qtbot.keyClick(line_edit, Qt.Key.Key_Enter)

    assert combo.current_code() == "1001"
    assert line_edit.text() == "1001 - Papelería"
    assert seen == []


def test_code_combo_matches_typed_exact_display_text(qtbot) -> None:
    combo = _combo(qtbot)
    line_edit = combo.lineEdit()
    assert line_edit is not None

    with qtbot.waitSignal(combo.committed, timeout=2000) as blocker:
        qtbot.keyClicks(line_edit, "3001 - aseo")
        qtbot.keyClick(line_edit, Qt.Key.Key_Enter)

    assert blocker.args == ["3001"]


def test_code_combo_optional_empty_item(qtbot) -> None:
    combo = _combo(qtbot, allow_empty=True)

    assert combo.itemText(0) == strings.PLACEHOLDER_NONE
    assert combo.set_current_code(None) is True
    assert combo.currentIndex() == 0
    assert combo.current_code() is None

    combo.set_current_code("1001")
    with qtbot.waitSignal(combo.committed) as blocker:
        combo.activated.emit(0)  # el usuario elige "(ninguno)"
    assert blocker.args == [None]
    assert combo.current_code() is None


# --- SplitButton ----------------------------------------------------------------


def test_split_button_main_action_and_menu(qtbot) -> None:
    button = SplitButton(strings.ACTION_IMPORT, icon_name="import", shortcut_id="import_files")
    qtbot.addWidget(button)
    button.show()

    option = button.add_option(strings.ACTION_IMPORT_FOLDER_MENU, shortcut_id="import_folder")

    assert button.main_button.text() == strings.ACTION_IMPORT
    assert button.main_button.property("variant") == "primary"
    assert not button.main_button.icon().isNull()
    assert isinstance(option, QAction)
    assert isinstance(button.menu, QMenu)
    assert option in button.menu.actions()
    assert button.arrow_button.property("role") == "split-arrow"
    assert "Ctrl" in button.main_button.toolTip() or "⌘" in button.main_button.toolTip()

    with qtbot.waitSignal(button.clicked):
        button.main_button.click()

    button.setEnabled(False)
    assert button.main_button.isEnabled() is False
    assert button.arrow_button.isEnabled() is False


# --- Sheet ----------------------------------------------------------------------


def test_sheet_chrome_and_buttons(qtbot) -> None:
    sheet = Sheet(strings.EXPORT_DIALOG_TITLE, subtitle=strings.EXPORT_SHEET_SUBTITLE)
    qtbot.addWidget(sheet)
    body = QLabel("contenido")
    sheet.set_body(body)

    assert sheet.windowTitle() == strings.EXPORT_DIALOG_TITLE
    assert sheet.title_label.text() == strings.EXPORT_DIALOG_TITLE
    assert sheet.subtitle_label.text() == strings.EXPORT_SHEET_SUBTITLE
    assert sheet.property("role") == "sheet"
    assert sheet.primary_button.text() == strings.ACTION_SAVE
    assert sheet.cancel_button.text() == strings.ACTION_CANCEL
    assert sheet.primary_button.property("variant") == "primary"
    assert sheet.primary_button.isDefault()
    assert sheet.body_layout.indexOf(body) >= 0

    sheet.set_primary_label("Exportar")
    sheet.set_primary_enabled(False)
    assert sheet.primary_button.text() == "Exportar"
    assert sheet.primary_button.isEnabled() is False

    extra = sheet.add_button(strings.ACTION_SKIP)
    assert extra.text() == strings.ACTION_SKIP

    sheet.set_error("No se pudo guardar.")
    assert sheet.error_label.text() == "No se pudo guardar."
    assert not sheet.error_label.isHidden()
    sheet.set_error(None)
    assert sheet.error_label.isHidden()


def test_sheet_accepts_and_rejects(qtbot) -> None:
    sheet = Sheet("Título")
    qtbot.addWidget(sheet)
    sheet.show()

    with qtbot.waitSignal(sheet.accepted):
        sheet.primary_button.click()
    assert sheet.result() == QDialog.DialogCode.Accepted

    sheet.show()
    with qtbot.waitSignal(sheet.rejected):
        sheet.cancel_button.click()


def test_sheet_busy_disables_footer(qtbot) -> None:
    sheet = Sheet("Título")
    qtbot.addWidget(sheet)

    sheet.set_busy(True)
    assert sheet.primary_button.isEnabled() is False
    assert sheet.cancel_button.isEnabled() is False
    sheet.set_busy(False)
    assert sheet.primary_button.isEnabled() is True


def test_a_busy_sheet_cannot_be_closed_until_its_task_ends(qtbot) -> None:
    sheet = Sheet("Título")
    qtbot.addWidget(sheet)
    sheet.show()
    sheet.set_busy(True)

    sheet.reject()
    sheet.close()  # el boton de cerrar de la ventana tambien pasa por reject()

    assert sheet.isVisible()
    sheet.set_busy(False)
    with qtbot.waitSignal(sheet.rejected):
        sheet.close()
    assert not sheet.isVisible()


def test_sheet_enter_inside_a_field_presses_the_primary_button(qtbot) -> None:
    sheet = Sheet("Título")
    qtbot.addWidget(sheet)
    field = QLineEdit()
    sheet.set_body(field)
    sheet.show()
    sheet.activateWindow()
    qtbot.waitUntil(sheet.isActiveWindow)
    # el foco pasa por Cancelar antes de llegar al campo, como al tabular
    sheet.cancel_button.setFocus()
    field.setFocus()

    with qtbot.waitSignal(sheet.accepted, timeout=1000):
        qtbot.keyClick(field, Qt.Key.Key_Return)


def test_sheet_footer_buttons_keep_their_natural_width_at_the_right(qtbot) -> None:
    sheet = Sheet("Título")
    qtbot.addWidget(sheet)
    extra = sheet.add_button(strings.ACTION_SKIP)
    sheet.resize(560, 300)
    sheet.show()
    qtbot.wait(10)

    for button in (extra, sheet.cancel_button, sheet.primary_button):
        assert button.width() == button.sizeHint().width()
    footer_right = sheet.footer.rect().right() - 24  # margen derecho del pie
    assert abs(sheet.primary_button.geometry().right() - footer_right) <= 2
    assert extra.geometry().right() < sheet.cancel_button.geometry().left()
    assert sheet.cancel_button.geometry().right() < sheet.primary_button.geometry().left()


def test_sheet_error_takes_the_free_space_and_buttons_stay_put(qtbot) -> None:
    sheet = Sheet("Título")
    qtbot.addWidget(sheet)
    sheet.resize(560, 300)
    sheet.show()
    qtbot.wait(10)
    before = sheet.primary_button.geometry()

    sheet.set_error("No se pudo guardar. Revisa la conexión e inténtalo de nuevo.")
    qtbot.wait(10)

    after = sheet.primary_button.geometry()
    assert (after.left(), after.width()) == (before.left(), before.width())
    assert sheet.error_label.geometry().right() < sheet.cancel_button.geometry().left()
    assert sheet.error_label.width() > sheet.cancel_button.width()
