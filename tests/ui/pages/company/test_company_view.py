"""CompanyView: the Empresa page as pure presentation (values in, signals out)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from contabilizador.shared import strings
from contabilizador.ui.pages.company.form import CompanyValues
from contabilizador.ui.pages.company.view import CompanyView

DEMO = CompanyValues("EMPRESA DEMO S.A.S", "1017", "Bodega 2", "Kg", "Contado")


def _view(qtbot) -> CompanyView:
    view = CompanyView()
    qtbot.addWidget(view)
    view.resize(900, 640)
    view.show()
    return view


def _texts(view: CompanyView) -> dict[str, QLabel]:
    return {label.text(): label for label in view.findChildren(QLabel)}


def test_header_has_the_page_title_and_one_line_purpose(qtbot) -> None:
    view = _view(qtbot)

    assert view.title_label.text() == strings.COMPANY_PAGE_TITLE
    assert view.title_label.property("role") == "page-title"
    assert view.purpose_label.text() == strings.COMPANY_PAGE_PURPOSE
    assert view.purpose_label.property("role") == "purpose"


def test_starts_blank_until_the_data_arrives(qtbot) -> None:
    view = _view(qtbot)

    assert view.form.isVisible() is False
    assert view.empty_state.isVisible() is False
    assert view.is_empty is False


def test_show_loading_hides_stale_content(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.unit_edit.setText("Und.")

    view.show_loading()

    assert view.form.isVisible() is False
    assert view.save_button.isVisible() is False
    assert view.empty_state.isVisible() is False
    # Lo editado de la empresa anterior ya no cuenta como cambios pendientes
    assert view.is_dirty() is False


def test_show_company_loads_the_form_and_the_last_consecutives(qtbot) -> None:
    view = _view(qtbot)

    view.show_company(DEMO, last_fc=5748, last_nc=0)

    assert view.is_empty is False
    assert view.form.values() == DEMO
    assert view.fc_value.text() == "5748"
    assert view.nc_value.text() == strings.COMPANY_CONSECUTIVE_NONE
    assert view.is_dirty() is False
    assert view.save_button.isEnabled() is False
    assert view.unsaved_label.isHidden()


def test_consecutives_are_read_only_facts_with_an_explanation(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=5748, last_nc=12)

    texts = _texts(view)

    assert texts[strings.SECTION_CONSECUTIVES].property("role") == "section"
    assert texts[strings.LABEL_LAST_FC].property("role") == "label"
    assert texts[strings.LABEL_LAST_NC].property("role") == "label"
    assert texts[strings.COMPANY_CONSECUTIVES_HINT].property("role") == "hint"
    assert view.fc_value.property("role") == "value"
    assert view.nc_value.text() == "12"


def test_editing_enables_save_and_says_there_are_unsaved_changes(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)

    view.form.unit_edit.setText("Und.")

    assert view.is_dirty() is True
    assert view.save_button.isEnabled() is True
    assert not view.unsaved_label.isHidden()
    assert view.unsaved_label.text() == strings.COMPANY_UNSAVED_CHANGES

    view.form.unit_edit.setText("Kg")
    assert view.save_button.isEnabled() is False
    assert view.unsaved_label.isHidden()


def test_save_is_the_primary_action(qtbot) -> None:
    view = _view(qtbot)

    assert view.save_button.text() == strings.ACTION_SAVE
    assert view.save_button.property("variant") == "primary"


def test_enter_on_the_focused_save_button_saves(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.unit_edit.setText("Und.")
    view.save_button.setFocus()

    with qtbot.waitSignal(view.save_requested):
        qtbot.keyClick(view.save_button, Qt.Key.Key_Return)


def test_save_emits_the_trimmed_values(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.name_edit.setText("  NUEVO NOMBRE  ")

    with qtbot.waitSignal(view.save_requested) as blocker:
        view.save_button.click()

    assert blocker.args == [CompanyValues("NUEVO NOMBRE", "1017", "Bodega 2", "Kg", "Contado")]


def test_save_with_a_blank_name_explains_it_and_emits_nothing(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.name_edit.setText("")

    with qtbot.assertNotEmitted(view.save_requested):
        view.save_button.click()

    assert view.form.name_error_label.text() == strings.COMPANY_NAME_REQUIRED
    assert not view.form.name_error_label.isHidden()


def test_enter_saves_only_when_something_changed(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)

    with qtbot.assertNotEmitted(view.save_requested):
        qtbot.keyClick(view.form.unit_edit, Qt.Key.Key_Return)

    view.form.unit_edit.setText("Und.")
    with qtbot.waitSignal(view.save_requested):
        qtbot.keyClick(view.form.unit_edit, Qt.Key.Key_Return)


def test_busy_locks_only_the_save_button(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.unit_edit.setText("Und.")

    view.set_busy(True)
    # Los campos siguen activos: deshabilitarlos durante unos milisegundos solo parpadea
    assert view.form.isEnabled() is True
    assert view.save_button.isEnabled() is False

    view.set_busy(False)
    assert view.save_button.isEnabled() is True


def test_show_saved_marks_the_form_clean_and_updates_the_numbers(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.name_edit.setText("NUEVO NOMBRE")
    saved = CompanyValues("NUEVO NOMBRE", "1017", "Bodega 2", "Kg", "Contado")

    view.show_saved(saved, last_fc=2, last_nc=1)

    assert view.is_dirty() is False
    assert view.save_button.isEnabled() is False
    assert view.unsaved_label.isHidden()
    assert (view.fc_value.text(), view.nc_value.text()) == ("2", "1")


def test_show_saved_keeps_what_was_typed_while_saving(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.name_edit.setText("NUEVO NOMBRE")
    saved = CompanyValues("NUEVO NOMBRE", "1017", "Bodega 2", "Kg", "Contado")
    view.form.unit_edit.setText("Und.")  # escrito mientras se guardaba

    view.show_saved(saved, last_fc=2, last_nc=0)

    assert view.form.unit_edit.text() == "Und."
    assert view.is_dirty() is True
    assert view.save_button.isEnabled() is True


def test_show_name_error_marks_the_name_and_puts_the_cursor_there(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.third_party_edit.setFocus()

    view.show_name_error(strings.COMPANY_NAME_DUPLICATED)

    assert view.form.name_error_label.text() == strings.COMPANY_NAME_DUPLICATED
    assert view.form.name_edit.property("invalid") == "true"
    assert view.focusWidget() is view.form.name_edit


def test_without_a_company_the_page_invites_to_create_one(qtbot) -> None:
    view = _view(qtbot)

    view.show_empty()

    assert view.is_empty is True
    assert view.empty_state.title_label.text() == strings.COMPANY_EMPTY_TITLE
    assert view.empty_state.text_label.text() == strings.COMPANY_EMPTY_TEXT
    assert view.empty_state.action_button.text() == strings.ACTION_NEW_COMPANY
    assert view.form.isVisible() is False
    with qtbot.waitSignal(view.create_company_requested):
        view.empty_state.action_button.click()


def test_showing_a_company_after_the_empty_state_brings_the_form_back(qtbot) -> None:
    view = _view(qtbot)
    view.show_empty()

    view.show_company(DEMO, last_fc=3, last_nc=1)

    assert view.is_empty is False
    assert view.form.isVisible() is True
    assert view.empty_state.isVisible() is False


def test_set_consecutives_refreshes_the_numbers_but_keeps_the_edits(qtbot) -> None:
    view = _view(qtbot)
    view.show_company(DEMO, last_fc=1, last_nc=0)
    view.form.name_edit.setText("Cambio sin guardar")

    view.set_consecutives(last_fc=7, last_nc=3)

    assert view.fc_value.text() == "7"
    assert view.nc_value.text() == "3"
    assert view.form.name_edit.text() == "Cambio sin guardar"
    assert view.is_dirty() is True
