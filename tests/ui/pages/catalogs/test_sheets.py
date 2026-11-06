"""Catálogos sheets: entry form (immutable code), delete confirmation and import report."""

from PySide6.QtCore import Qt

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared import strings
from contabilizador.ui.pages.catalogs.entry_sheet import CatalogEntrySheet
from contabilizador.ui.pages.catalogs.report_sheet import CatalogImportReportSheet
from contabilizador.ui.pages.catalogs.rows import ImportOutcome
from contabilizador.ui.widgets.confirm_sheet import ConfirmSheet

# --- CatalogEntrySheet ----------------------------------------------------------


def entry_sheet(qtbot, kind=CatalogKind.PRODUCT, **kwargs) -> CatalogEntrySheet:
    sheet = CatalogEntrySheet(kind, **kwargs)
    qtbot.addWidget(sheet)
    sheet.show()
    return sheet


def test_create_sheet_names_the_kind_and_focuses_the_code(qtbot) -> None:
    sheet = entry_sheet(qtbot)

    assert sheet.windowTitle() == "Nuevo producto"
    assert sheet.title_label.text() == "Nuevo producto"
    assert sheet.primary_button.text() == strings.ACTION_SAVE
    assert sheet.code_edit is not None
    assert sheet.focusWidget() is sheet.code_edit
    assert sheet.hint_label.text() == strings.CATALOG_ENTRY_CODE_HINT
    assert entry_sheet(qtbot, CatalogKind.COST_CENTER).windowTitle() == "Nuevo centro de costo"


def test_create_sheet_rejects_an_empty_code_and_does_not_submit(qtbot) -> None:
    sheet = entry_sheet(qtbot)
    submitted: list[tuple[str, str]] = []
    sheet.submitted.connect(lambda code, name: submitted.append((code, name)))

    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert submitted == []
    assert sheet.error_label.text() == strings.CATALOG_CODE_REQUIRED
    assert sheet.error_label.isVisibleTo(sheet)
    assert sheet.code_edit is not None
    assert sheet.code_edit.property("invalid") == "true"
    assert sheet.focusWidget() is sheet.code_edit
    assert sheet.isVisible()


def test_create_sheet_rejects_a_blank_name(qtbot) -> None:
    sheet = entry_sheet(qtbot)
    assert sheet.code_edit is not None
    qtbot.keyClicks(sheet.code_edit, "1001")

    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert sheet.error_label.text() == strings.CATALOG_NAME_REQUIRED
    assert sheet.name_edit.property("invalid") == "true"
    assert sheet.focusWidget() is sheet.name_edit


def test_create_sheet_submits_trimmed_values_and_stays_open(qtbot) -> None:
    sheet = entry_sheet(qtbot)
    assert sheet.code_edit is not None
    submitted: list[tuple[str, str]] = []
    sheet.submitted.connect(lambda code, name: submitted.append((code, name)))
    qtbot.keyClicks(sheet.code_edit, "  1001 ")
    qtbot.keyClicks(sheet.name_edit, " Papeleria  ")

    qtbot.keyClick(sheet.name_edit, Qt.Key.Key_Return)

    assert submitted == [("1001", "Papeleria")]
    assert sheet.isVisible()  # el contenedor cierra cuando termina de guardar


def test_typing_clears_the_invalid_mark(qtbot) -> None:
    sheet = entry_sheet(qtbot)
    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)
    assert sheet.code_edit is not None
    assert sheet.code_edit.property("invalid") == "true"

    qtbot.keyClicks(sheet.code_edit, "1")

    assert sheet.code_edit.property("invalid") == "false"
    assert not sheet.error_label.isVisibleTo(sheet)


def test_edit_sheet_shows_the_code_as_text_that_cannot_change(qtbot) -> None:
    sheet = entry_sheet(qtbot, code="1001", name="Papelería")

    assert sheet.windowTitle() == "Editar producto"
    assert sheet.code_edit is None
    assert sheet.code_value_label is not None
    assert sheet.code_value_label.text() == "1001"
    assert sheet.hint_label.text() == strings.CATALOG_CODE_IMMUTABLE
    assert sheet.name_edit.text() == "Papelería"
    assert sheet.focusWidget() is sheet.name_edit


def test_edit_sheet_submits_the_original_code_with_the_new_name(qtbot) -> None:
    sheet = entry_sheet(qtbot, code="1001", name="Papelería")
    submitted: list[tuple[str, str]] = []
    sheet.submitted.connect(lambda code, name: submitted.append((code, name)))
    sheet.name_edit.selectAll()
    qtbot.keyClicks(sheet.name_edit, "Papeleria y utiles")

    qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    assert submitted == [("1001", "Papeleria y utiles")]


def test_saving_locks_the_form_until_it_fails(qtbot) -> None:
    sheet = entry_sheet(qtbot)
    assert sheet.code_edit is not None

    sheet.set_saving(True)
    assert not sheet.primary_button.isEnabled()
    assert not sheet.cancel_button.isEnabled()
    assert not sheet.name_edit.isEnabled()

    sheet.show_error("Algo falló", field="code")
    sheet.set_saving(False)

    assert sheet.primary_button.isEnabled()
    assert sheet.name_edit.isEnabled()
    assert sheet.error_label.text() == "Algo falló"
    assert sheet.code_edit.property("invalid") == "true"


def test_close_saved_accepts_the_dialog(qtbot) -> None:
    sheet = entry_sheet(qtbot)

    with qtbot.waitSignal(sheet.accepted, timeout=1000):
        sheet.close_saved()

    assert not sheet.isVisible()


def test_cancel_rejects_without_submitting(qtbot) -> None:
    sheet = entry_sheet(qtbot)
    submitted: list[object] = []
    sheet.submitted.connect(lambda *args: submitted.append(args))

    with qtbot.waitSignal(sheet.rejected, timeout=1000):
        qtbot.mouseClick(sheet.cancel_button, Qt.MouseButton.LeftButton)

    assert submitted == []


# --- ConfirmSheet ---------------------------------------------------------------


def confirm_sheet(
    qtbot, *, notes: tuple[str, ...] | list[str] = (), destructive: bool = True
) -> ConfirmSheet:
    sheet = ConfirmSheet(
        "¿Eliminar «1001 - Papelería»?",
        "Esta acción no se puede deshacer.",
        confirm_label=strings.ACTION_DELETE,
        notes=notes,
        destructive=destructive,
    )
    qtbot.addWidget(sheet)
    sheet.show()
    return sheet


def test_confirm_sheet_states_title_message_and_action(qtbot) -> None:
    sheet = confirm_sheet(qtbot, notes=["Lo usa el proveedor «ACME»."])

    assert sheet.title_label.text() == "¿Eliminar «1001 - Papelería»?"
    assert sheet.message_label.text() == "Esta acción no se puede deshacer."
    assert [label.text() for label in sheet.note_labels] == ["Lo usa el proveedor «ACME»."]
    assert sheet.primary_button.text() == strings.ACTION_DELETE


def test_destructive_confirmation_is_red_and_focuses_cancel(qtbot) -> None:
    sheet = confirm_sheet(qtbot)

    assert sheet.primary_button.property("variant") == "danger"
    assert sheet.primary_button.property("filled") == "true"
    assert sheet.focusWidget() is sheet.cancel_button


def test_plain_confirmation_keeps_the_primary_style_and_focus(qtbot) -> None:
    sheet = confirm_sheet(qtbot, destructive=False)

    assert sheet.primary_button.property("variant") == "primary"
    assert sheet.focusWidget() is sheet.primary_button


def test_confirmation_accepts_and_rejects(qtbot) -> None:
    sheet = confirm_sheet(qtbot)
    with qtbot.waitSignal(sheet.accepted, timeout=1000):
        qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)

    other = confirm_sheet(qtbot)
    with qtbot.waitSignal(other.rejected, timeout=1000):
        qtbot.keyClick(other, Qt.Key.Key_Escape)


# --- CatalogImportReportSheet ---------------------------------------------------


def test_report_sheet_summarizes_and_lists_the_skipped_rows(qtbot) -> None:
    outcome = ImportOutcome(
        created=5, updated=2, invalid=((4, "code is required"), (9, "duplicate code in file"))
    )
    sheet = CatalogImportReportSheet(CatalogKind.PRODUCT, outcome)
    qtbot.addWidget(sheet)
    sheet.show()

    assert sheet.windowTitle() == strings.CATALOG_IMPORT_TITLE
    assert sheet.summary_label.text() == (
        "5 productos creados y 2 actualizados. 2 filas no se importaron."
    )
    assert [sheet.invalid_list.item(i).text() for i in range(sheet.invalid_list.count())] == [
        "Fila 4: falta el código",
        "Fila 9: código repetido en el archivo",
    ]
    assert sheet.invalid_list.isVisibleTo(sheet)
    assert sheet.fix_hint_label.text() == strings.CATALOG_IMPORT_FIX_HINT
    assert sheet.primary_button.text() == strings.ACTION_DONE
    assert sheet.cancel_button.isHidden()


def test_report_sheet_without_skipped_rows_hides_the_list(qtbot) -> None:
    sheet = CatalogImportReportSheet(CatalogKind.COST_CENTER, ImportOutcome(created=3, updated=0))
    qtbot.addWidget(sheet)
    sheet.show()

    assert sheet.summary_label.text() == "3 centros de costo creados."
    assert sheet.invalid_list.isHidden()
    assert sheet.fix_hint_label.isHidden()


def test_report_sheet_done_closes_it(qtbot) -> None:
    sheet = CatalogImportReportSheet(CatalogKind.PRODUCT, ImportOutcome(created=1, updated=0))
    qtbot.addWidget(sheet)
    sheet.show()

    with qtbot.waitSignal(sheet.accepted, timeout=1000):
        qtbot.mouseClick(sheet.primary_button, Qt.MouseButton.LeftButton)


# --- pie de las hojas ---------------------------------------------------------------


def test_footer_buttons_keep_their_size_and_sit_on_the_right(qtbot) -> None:
    sheets = [
        entry_sheet(qtbot),
        confirm_sheet(qtbot),
    ]
    report = CatalogImportReportSheet(CatalogKind.PRODUCT, ImportOutcome(created=1, updated=0))
    qtbot.addWidget(report)
    report.show()
    sheets.append(report)

    for sheet in sheets:
        button = sheet.primary_button
        assert button.width() <= button.sizeHint().width() + 8, type(sheet).__name__
        footer_right = sheet.footer.rect().right() - 24  # margen derecho del pie
        assert abs(button.geometry().right() - footer_right) <= 2, type(sheet).__name__
