"""Export sheet view: lays out the view-model and emits what the user asks for."""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.ui.errors import ErrorPresentation
from contabilizador.ui.pages.export.model import (
    CollisionNotice,
    ExportSheetState,
    MismatchNotice,
    SuccessSummary,
    TypeRow,
)
from contabilizador.ui.pages.export.view import SHEET_WIDTH, ExportSheet

FC = DocumentType.FC
NC = DocumentType.NC


def make_state(
    *,
    rows: tuple[TypeRow, ...] = (
        TypeRow(FC, "Facturas de compra (FC)", 2, 41),
        TypeRow(NC, "Notas crédito (NC)", 1, 7),
    ),
    skipped_text: str = "",
    mismatches: MismatchNotice | None = None,
    collisions: CollisionNotice | None = None,
) -> ExportSheetState:
    return ExportSheetState(
        rows=rows,
        exportable_count=sum(row.count for row in rows),
        skipped_text=skipped_text,
        mismatches=mismatches,
        collisions=collisions,
        labels={},
    )


@pytest.fixture
def sheet(qtbot, tmp_path: Path) -> ExportSheet:
    view = ExportSheet()
    qtbot.addWidget(view)
    view.set_destination(tmp_path / "lote.xlsx")
    return view


def test_each_type_shows_its_count_first_consecutive_and_resulting_range(
    sheet: ExportSheet,
) -> None:
    sheet.set_state(make_state())

    fc, nc = sheet.rows[FC], sheet.rows[NC]
    assert (fc.label.text(), fc.count.text(), fc.start.value(), fc.range.text()) == (
        "Facturas de compra (FC)",
        "2",
        41,
        "41 a 42",
    )
    assert (nc.label.text(), nc.count.text(), nc.start.value(), nc.range.text()) == (
        "Notas crédito (NC)",
        "1",
        7,
        "7",
    )
    assert sheet.start_numbers() == {FC: 41, NC: 7}
    assert sheet.primary_button.text() == "Exportar 3 facturas"
    assert sheet.primary_button.isEnabled()


def test_typing_a_start_number_updates_its_range_at_once_and_notifies(
    qtbot, sheet: ExportSheet
) -> None:
    sheet.set_state(make_state())

    with qtbot.waitSignal(sheet.start_numbers_changed) as signal:
        sheet.rows[FC].start.setValue(100)

    assert signal.args == [{FC: 100, NC: 7}]
    assert sheet.rows[FC].range.text() == "100 a 101"


def test_a_new_preview_never_overwrites_what_the_user_typed(sheet: ExportSheet) -> None:
    sheet.set_state(make_state())
    sheet.rows[FC].start.setValue(100)

    sheet.set_state(make_state(rows=(TypeRow(FC, "Facturas de compra (FC)", 3, 41),)))

    assert sheet.rows[FC].start.value() == 100
    assert sheet.rows[FC].range.text() == "100 a 102"
    # el tipo que ya no se exporta desaparece y no aporta consecutivo
    assert sheet.rows[NC].start.isHidden()
    assert sheet.start_numbers() == {FC: 100}
    assert sheet.primary_button.text() == "Exportar 3 facturas"


def test_skipped_documents_are_explained_only_when_there_are_some(sheet: ExportSheet) -> None:
    sheet.set_state(make_state(skipped_text="2 facturas no están listas y quedan pendientes."))

    assert sheet.skipped_label.text() == "2 facturas no están listas y quedan pendientes."
    assert not sheet.skipped_label.isHidden()

    sheet.set_state(make_state())

    assert sheet.skipped_label.isHidden()


MISMATCHES = MismatchNotice(
    title="1 factura tiene descuadre",
    explanation="El total de sus líneas no coincide con el total del XML.",
    items=("FPI-5731 · FERRETERIA CENTRAL: las líneas suman $ 1.500 más que el XML.",),
)


def test_mismatched_invoices_are_an_opt_in_and_never_block_the_clean_ones(
    qtbot, sheet: ExportSheet
) -> None:
    sheet.set_state(make_state(mismatches=MISMATCHES))

    notice = sheet.mismatch_notice
    assert not notice.isHidden()
    assert notice.title_label.text() == "1 factura tiene descuadre"
    assert notice.body_label.text() == (
        "El total de sus líneas no coincide con el total del XML.\n"
        "FPI-5731 · FERRETERIA CENTRAL: las líneas suman $ 1.500 más que el XML."
    )
    assert notice.checkbox.text() == "Exportar también las facturas con descuadre"
    assert not sheet.mismatch_confirmed()
    # sin marcar la casilla se exportan las facturas que cuadran: el boton no espera
    assert sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == ""

    with qtbot.waitSignal(sheet.mismatch_inclusion_changed) as blocker:
        notice.checkbox.click()

    assert blocker.args == [True]
    assert sheet.mismatch_confirmed()
    assert sheet.primary_button.isEnabled()

    with qtbot.waitSignal(sheet.mismatch_inclusion_changed) as blocker:
        notice.checkbox.click()
    assert blocker.args == [False]


def test_a_confirmation_cleared_by_the_sheet_itself_is_not_announced(
    qtbot, sheet: ExportSheet
) -> None:
    sheet.set_state(make_state(mismatches=MISMATCHES))
    sheet.mismatch_notice.checkbox.click()
    announced: list[bool] = []
    sheet.mismatch_inclusion_changed.connect(announced.append)

    # otra lista de descuadres: la casilla vuelve a vacia sola, sin avisar a nadie
    other = MismatchNotice("2 facturas tienen descuadre", MISMATCHES.explanation, ("a", "b"))
    sheet.set_state(make_state(mismatches=other))

    assert not sheet.mismatch_confirmed()
    assert announced == []


def test_the_checkbox_and_its_explanation_agree_with_how_many_invoices_there_are(
    sheet: ExportSheet,
) -> None:
    one = MismatchNotice(
        "1 factura tiene descuadre",
        MISMATCHES.explanation,
        MISMATCHES.items,
        include_label="Exportar también la factura con descuadre",
    )
    sheet.set_state(make_state(mismatches=one))

    assert sheet.mismatch_notice.checkbox.text() == "Exportar también la factura con descuadre"

    sheet.set_state(make_state(mismatches=MISMATCHES))

    assert sheet.mismatch_notice.checkbox.text() == "Exportar también las facturas con descuadre"


def test_when_only_mismatched_invoices_remain_the_sheet_explains_the_opt_in(
    sheet: ExportSheet,
) -> None:
    sheet.set_state(
        ExportSheetState(
            rows=(),
            exportable_count=0,
            skipped_text="",
            mismatches=MISMATCHES,
            collisions=None,
            labels={},
        )
    )

    assert sheet.rows == {}
    assert not sheet.mismatch_notice.isHidden()
    assert sheet.primary_button.text() == "Exportar"
    assert not sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == (
        "Solo hay facturas con descuadre. Marca la casilla para exportarlas."
    )


def test_mismatch_confirmation_is_asked_again_only_when_the_list_changes(
    sheet: ExportSheet,
) -> None:
    sheet.set_state(make_state(mismatches=MISMATCHES))
    sheet.mismatch_notice.checkbox.click()

    sheet.set_state(make_state(mismatches=MISMATCHES))
    assert sheet.mismatch_confirmed()

    other = MismatchNotice("2 facturas tienen descuadre", MISMATCHES.explanation, ("a", "b"))
    sheet.set_state(make_state(mismatches=other))
    assert not sheet.mismatch_confirmed()

    sheet.set_state(make_state())
    assert sheet.mismatch_notice.isHidden()
    assert sheet.primary_button.isEnabled()


COLLISIONS = CollisionNotice(
    title="Los consecutivos se cruzan con un lote anterior",
    items=("FC 41 a 42 se cruza con el lote 12, que ya usó FC 30 a 41.",),
    suggested_starts={FC: 42},
    action_label="Empezar en 42",
)


def test_colliding_consecutives_must_be_changed_or_confirmed(sheet: ExportSheet) -> None:
    sheet.set_state(make_state(collisions=COLLISIONS))

    notice = sheet.collision_notice
    assert not notice.isHidden()
    assert notice.title_label.text() == "Los consecutivos se cruzan con un lote anterior"
    assert notice.body_label.text() == COLLISIONS.items[0]
    assert notice.action_button.text() == "Empezar en 42"
    assert notice.checkbox.text() == "Usar estos consecutivos aunque se crucen"
    assert not sheet.collision_confirmed()
    assert not sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == (
        "Cambia el consecutivo inicial o confirma que quieres usarlo aunque se cruce."
    )

    notice.checkbox.click()

    assert sheet.collision_confirmed()
    assert sheet.primary_button.isEnabled()


def test_the_fix_button_moves_each_type_to_its_first_free_consecutive(
    qtbot, sheet: ExportSheet
) -> None:
    sheet.set_state(make_state(collisions=COLLISIONS))

    with qtbot.waitSignal(sheet.start_numbers_changed) as signal:
        sheet.collision_notice.action_button.click()

    assert sheet.rows[FC].start.value() == 42
    assert sheet.rows[FC].range.text() == "42 a 43"
    assert signal.args == [{FC: 42, NC: 7}]


def test_collision_confirmation_is_asked_again_when_the_collisions_change(
    sheet: ExportSheet,
) -> None:
    sheet.set_state(make_state(collisions=COLLISIONS))
    sheet.collision_notice.checkbox.click()

    sheet.set_state(make_state(collisions=COLLISIONS))
    assert sheet.collision_confirmed()

    moved = CollisionNotice(
        COLLISIONS.title,
        ("FC 40 a 41 se cruza con el lote 12, que ya usó FC 30 a 41.",),
        {FC: 42},
        "Empezar en 42",
    )
    sheet.set_state(make_state(collisions=moved))
    assert not sheet.collision_confirmed()

    sheet.set_state(make_state())
    assert sheet.collision_notice.isHidden()
    assert not sheet.collision_confirmed()
    assert sheet.primary_button.isEnabled()


def test_exportar_asks_for_the_export_and_keeps_the_sheet_open(qtbot, sheet: ExportSheet) -> None:
    sheet.set_state(make_state())
    sheet.open()

    with qtbot.waitSignal(sheet.export_requested):
        sheet.primary_button.click()
    assert sheet.isVisible()

    # Enter dispara el boton por defecto: tambien exporta sin cerrar
    with qtbot.waitSignal(sheet.export_requested):
        qtbot.keyClick(sheet, Qt.Key.Key_Return)
    assert sheet.isVisible()


def test_destination_shows_file_name_and_folder_and_can_be_changed(qtbot, tmp_path: Path) -> None:
    sheet = ExportSheet()
    qtbot.addWidget(sheet)
    sheet.set_state(make_state())

    assert sheet.destination() is None
    assert not sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == "Elige dónde guardar el archivo."

    sheet.set_destination(tmp_path / "salidas" / "lote.xlsx")

    assert sheet.destination() == tmp_path / "salidas" / "lote.xlsx"
    assert sheet.destination_name.text() == "lote.xlsx"
    assert sheet.destination_folder.text() == str(tmp_path / "salidas")
    assert sheet.primary_button.isEnabled()
    with qtbot.waitSignal(sheet.browse_requested):
        sheet.browse_button.click()


def test_exporting_locks_the_sheet_until_it_finishes(qtbot, sheet: ExportSheet) -> None:
    sheet.set_state(make_state())
    sheet.open()

    sheet.set_exporting(True, "Exportando 3 facturas…")

    assert sheet.busy_overlay.is_running
    assert sheet.busy_overlay.message_label.text() == "Exportando 3 facturas…"
    assert not sheet.primary_button.isEnabled()
    assert not sheet.cancel_button.isEnabled()
    assert not sheet.rows[FC].start.isEnabled()
    assert not sheet.browse_button.isEnabled()
    qtbot.keyClick(sheet, Qt.Key.Key_Escape)
    sheet.reject()
    sheet.close()
    assert sheet.isVisible()

    sheet.set_exporting(False)

    assert not sheet.busy_overlay.is_running
    assert sheet.primary_button.isEnabled()
    assert sheet.cancel_button.isEnabled()
    assert sheet.rows[FC].start.isEnabled()


def test_errors_say_what_happened_and_how_to_fix_it(sheet: ExportSheet) -> None:
    sheet.set_state(make_state())

    sheet.show_error(
        ErrorPresentation(
            "No se pudo guardar el archivo",
            "El archivo está en uso o la carpeta no permite escribir.",
            "Cierra el archivo en Excel e inténtalo de nuevo.",
            "PermissionError: [Errno 13] Permission denied",
        )
    )

    notice = sheet.error_notice
    assert not notice.isHidden()
    assert notice.title_label.text() == "No se pudo guardar el archivo"
    assert notice.body_label.text() == (
        "El archivo está en uso o la carpeta no permite escribir.\n"
        "Cierra el archivo en Excel e inténtalo de nuevo."
    )
    # el texto tecnico solo aparece si se pide (tooltip), nunca en el mensaje
    assert "Errno" not in notice.title_label.text() + notice.body_label.text()
    assert notice.toolTip() == "PermissionError: [Errno 13] Permission denied"

    sheet.show_error(None)

    assert notice.isHidden()


def test_success_offers_open_file_show_in_folder_and_done(qtbot, sheet: ExportSheet) -> None:
    sheet.set_state(make_state())
    sheet.open()
    assert sheet.open_file_button.isHidden()
    assert sheet.show_in_folder_button.isHidden()

    sheet.show_success(
        SuccessSummary(
            "3 facturas exportadas",
            "Se guardó lote.xlsx en salidas.",
            "Consecutivos usados: FC 41 a 42 y NC 7.",
        )
    )

    assert sheet.is_success
    assert sheet.title_label.text() == "3 facturas exportadas"
    assert sheet.subtitle_label.text() == "Ya puedes importarlo en World Office."
    assert sheet.success_saved_label.text() == "Se guardó lote.xlsx en salidas."
    assert sheet.success_ranges_label.text() == "Consecutivos usados: FC 41 a 42 y NC 7."
    assert sheet.open_file_button.text() == "Abrir archivo"
    assert sheet.show_in_folder_button.text() == "Mostrar en carpeta"
    assert not sheet.open_file_button.isHidden()
    assert not sheet.show_in_folder_button.isHidden()
    assert sheet.cancel_button.isHidden()
    assert sheet.primary_button.text() == "Listo"
    assert sheet.primary_button.isEnabled()

    with qtbot.waitSignal(sheet.open_file_requested):
        sheet.open_file_button.click()
    with qtbot.waitSignal(sheet.show_in_folder_requested):
        sheet.show_in_folder_button.click()
    with qtbot.waitSignal(sheet.accepted):
        sheet.primary_button.click()
    assert not sheet.isVisible()


def test_notices_are_shown_whole_inside_a_sheet_of_fixed_width(qtbot, sheet: ExportSheet) -> None:
    sheet.set_state(
        make_state(
            skipped_text="3 facturas no están listas y quedan pendientes.",
            collisions=COLLISIONS,
            mismatches=MISMATCHES,
        )
    )
    sheet.show_error(
        ErrorPresentation(
            "No se pudo guardar el archivo",
            "El archivo está en uso o la carpeta no permite escribir.",
            "Cierra el archivo en Excel e inténtalo de nuevo.",
        )
    )

    sheet.open()
    qtbot.waitExposed(sheet)

    assert sheet.width() == SHEET_WIDTH
    for notice in (sheet.collision_notice, sheet.mismatch_notice, sheet.error_notice):
        # nada recortado: cada aviso tiene al menos la altura que pide su texto
        assert notice.height() >= notice.heightForWidth(notice.width())
    action = sheet.collision_notice.action_button
    assert not action.geometry().intersects(sheet.collision_notice.checkbox.geometry())


def test_without_a_ready_export_the_focus_starts_on_the_first_consecutive(qtbot) -> None:
    sheet = ExportSheet()  # sin destino todavia: Exportar espera
    qtbot.addWidget(sheet)
    sheet.set_state(make_state())

    sheet.open()
    qtbot.waitExposed(sheet)

    # nunca en Cancelar: Enter no debe cerrar la hoja por accidente
    assert not sheet.primary_button.isEnabled()
    assert sheet.focusWidget() is sheet.rows[FC].start


def test_tab_walks_the_sheet_in_reading_order(qtbot, sheet: ExportSheet) -> None:
    sheet.set_state(make_state(collisions=COLLISIONS, mismatches=MISMATCHES))
    sheet.mismatch_notice.checkbox.click()
    sheet.collision_notice.checkbox.click()
    sheet.open()
    qtbot.waitExposed(sheet)
    sheet.activateWindow()
    qtbot.waitUntil(lambda: QApplication.focusWidget() is not None)
    sheet.rows[FC].start.setFocus()

    visited = []
    for _ in range(8):
        visited.append(QApplication.focusWidget())
        qtbot.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)

    assert visited == [
        sheet.rows[FC].start,
        sheet.rows[NC].start,
        sheet.collision_notice.action_button,
        sheet.collision_notice.checkbox,
        sheet.mismatch_notice.checkbox,
        sheet.browse_button,
        sheet.cancel_button,
        sheet.primary_button,
    ]
