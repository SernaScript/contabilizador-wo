"""CompanyForm: presentational fields shared by the Empresa page and the new company dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from contabilizador.companies.application.use_cases import DEFAULT_UNIT, DEFAULT_WAREHOUSE
from contabilizador.companies.domain.company import DEFAULT_PAYMENT_FORM
from contabilizador.shared import strings
from contabilizador.ui.pages.company.form import CompanyForm, CompanyValues

DEMO = CompanyValues("EMPRESA DEMO S.A.S", "1017", "Bodega 2", "Kg", "Contado")


def _form(qtbot) -> CompanyForm:
    form = CompanyForm()
    qtbot.addWidget(form)
    form.show()
    return form


def _label_for(form: CompanyForm, text: str) -> QLabel:
    return next(label for label in form.findChildren(QLabel) if label.text() == text)


def test_a_new_form_starts_with_the_world_office_defaults(qtbot) -> None:
    form = _form(qtbot)

    expected = CompanyValues("", "", DEFAULT_WAREHOUSE, DEFAULT_UNIT, DEFAULT_PAYMENT_FORM)
    assert form.values() == expected == CompanyValues.defaults()
    assert form.is_dirty() is False


def test_values_are_trimmed(qtbot) -> None:
    form = _form(qtbot)

    form.name_edit.setText("  EMPRESA DEMO S.A.S ")
    form.third_party_edit.setText(" 1017 ")
    form.warehouse_edit.setText(" Bodega 2 ")

    values = form.values()
    assert values.name == "EMPRESA DEMO S.A.S"
    assert values.internal_third_party_id == "1017"
    assert values.warehouse == "Bodega 2"


def test_set_values_loads_the_fields_without_reporting_an_edit(qtbot) -> None:
    form = _form(qtbot)
    edits: list[int] = []
    form.edited.connect(lambda: edits.append(1))

    form.set_values(DEMO)

    assert form.values() == DEMO
    assert form.is_dirty() is False
    assert edits == []


def test_editing_marks_the_form_dirty_and_reverting_clears_it(qtbot) -> None:
    form = _form(qtbot)
    form.set_values(DEMO)

    with qtbot.waitSignal(form.edited):
        form.warehouse_edit.setText("Bodega 3")
    assert form.is_dirty() is True

    form.warehouse_edit.setText("Bodega 2")
    assert form.is_dirty() is False


def test_mark_saved_takes_the_saved_values_as_the_new_baseline(qtbot) -> None:
    form = _form(qtbot)
    form.set_values(DEMO)
    form.warehouse_edit.setText("Bodega 3")
    assert form.is_dirty() is True

    form.mark_saved(CompanyValues("EMPRESA DEMO S.A.S", "1017", "Bodega 3", "Kg", "Contado"))

    assert form.is_dirty() is False
    assert form.warehouse_edit.text() == "Bodega 3"
    # Lo escrito despues de guardar sigue contando como cambio
    form.unit_edit.setText("Und.")
    assert form.is_dirty() is True


def test_validate_requires_a_name_and_says_so_next_to_the_field(qtbot) -> None:
    form = _form(qtbot)

    assert form.validate() is False

    assert form.name_error_label.text() == strings.COMPANY_NAME_REQUIRED
    assert not form.name_error_label.isHidden()
    assert form.name_edit.property("invalid") == "true"
    assert form.focusWidget() is form.name_edit


def test_a_name_of_only_spaces_is_still_blank(qtbot) -> None:
    form = _form(qtbot)
    form.name_edit.setText("     ")

    assert form.validate() is False


def test_validate_passes_with_a_name_and_leaves_no_error(qtbot) -> None:
    form = _form(qtbot)
    form.name_edit.setText("EMPRESA DEMO S.A.S")

    assert form.validate() is True

    assert form.name_error_label.isHidden()
    assert form.name_edit.property("invalid") == "false"


def test_typing_in_the_name_clears_its_error(qtbot) -> None:
    form = _form(qtbot)
    form.validate()

    form.name_edit.setText("E")

    assert form.name_error_label.isHidden()
    assert form.name_edit.property("invalid") == "false"


def test_showing_the_name_error_moves_nothing(qtbot) -> None:
    form = _form(qtbot)
    form.resize(472, form.sizeHint().height())
    qtbot.wait(10)

    def layout_of_fields() -> list[tuple[int, int]]:
        # Posicion y alto de cada campo en coordenadas del formulario
        return [
            (edit.mapTo(form, edit.rect().topLeft()).y(), edit.height())
            for edit in (
                form.name_edit,
                form.third_party_edit,
                form.warehouse_edit,
                form.unit_edit,
                form.payment_edit,
            )
        ]

    before = layout_of_fields()
    form.set_name_error(strings.COMPANY_NAME_DUPLICATED)
    qtbot.wait(10)

    # El espacio del mensaje esta reservado: ni salta el resto ni se aprietan los campos
    assert layout_of_fields() == before


def test_editing_another_field_keeps_the_name_error(qtbot) -> None:
    form = _form(qtbot)
    form.set_name_error(strings.COMPANY_NAME_DUPLICATED)

    form.unit_edit.setText("Kg")

    assert not form.name_error_label.isHidden()
    assert form.name_edit.property("invalid") == "true"


def test_set_name_error_shows_and_clears_the_message(qtbot) -> None:
    form = _form(qtbot)

    form.set_name_error(strings.COMPANY_NAME_DUPLICATED)
    assert form.name_error_label.text() == strings.COMPANY_NAME_DUPLICATED
    assert not form.name_error_label.isHidden()
    assert form.name_edit.property("invalid") == "true"
    assert form.name_edit.accessibleDescription() == strings.COMPANY_NAME_DUPLICATED

    form.set_name_error(None)
    assert form.name_error_label.isHidden()
    assert form.name_edit.property("invalid") == "false"
    assert form.name_edit.accessibleDescription() == ""


def test_loading_values_clears_a_previous_error(qtbot) -> None:
    form = _form(qtbot)
    form.set_name_error(strings.COMPANY_NAME_DUPLICATED)

    form.set_values(DEMO)

    assert form.name_error_label.isHidden()


def test_enter_in_any_field_asks_to_submit(qtbot) -> None:
    form = _form(qtbot)

    with qtbot.waitSignal(form.submitted):
        qtbot.keyClick(form.unit_edit, Qt.Key.Key_Return)
    with qtbot.waitSignal(form.submitted):
        qtbot.keyClick(form.name_edit, Qt.Key.Key_Return)


def test_every_field_has_a_label_buddy_and_accessible_name(qtbot) -> None:
    form = _form(qtbot)
    fields = [
        (strings.FIELD_COMPANY_NAME, form.name_edit),
        (strings.FIELD_INTERNAL_THIRD_PARTY, form.third_party_edit),
        (strings.FIELD_WAREHOUSE, form.warehouse_edit),
        (strings.FIELD_UNIT, form.unit_edit),
        (strings.FIELD_PAYMENT_FORM, form.payment_edit),
    ]

    for text, edit in fields:
        assert _label_for(form, text).buddy() is edit
        assert edit.accessibleName() == text


def test_groups_are_titled_and_the_name_has_an_example(qtbot) -> None:
    form = _form(qtbot)

    for title in (strings.SECTION_WORLD_OFFICE, strings.SECTION_DEFAULTS):
        assert _label_for(form, title).property("role") == "section"
    assert form.name_edit.placeholderText() == strings.COMPANY_NAME_PLACEHOLDER


def test_tab_walks_the_fields_in_reading_order(qtbot) -> None:
    form = _form(qtbot)
    form.focus_name()

    visited = []
    for _ in range(4):
        qtbot.keyClick(form.focusWidget(), Qt.Key.Key_Tab)
        visited.append(form.focusWidget())

    assert visited == [
        form.third_party_edit,
        form.warehouse_edit,
        form.unit_edit,
        form.payment_edit,
    ]


def test_focus_name_puts_the_cursor_in_the_name_field(qtbot) -> None:
    form = _form(qtbot)
    form.third_party_edit.setFocus()

    form.focus_name()

    assert form.focusWidget() is form.name_edit
