"""SupplierWizard: one supplier at a time, with its pending lines as context."""

from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog, QLineEdit

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.rows import ContextLine, SupplierStep, SupplierValues
from contabilizador.ui.pages.suppliers.wizard import SupplierWizard
from contabilizador.ui.widgets import CodeItem
from tests.ui.pages.suppliers.focus import focus_order_after

CATALOG = (
    CodeItem("1001", "Papelería"),
    CodeItem("1002", "Aseo"),
    CodeItem("1003", "Transporte"),
)
LINES = (
    ContextLine("FEV-100", "RESMA PAPEL CARTA 75G", Decimal("30000")),
    ContextLine("FEV-100", "TONER IMPRESORA LASER", Decimal("125000.5")),
)
STEPS = (
    SupplierStep("900123456", "Papelería ABC S.A.S.", LINES),
    SupplierStep("800111222", "Aseo Total Ltda."),
    SupplierStep("700555666", "Beta S.A.", (), ("1002", "1003"), "1003"),
)


def make_wizard(qtbot, steps: tuple[SupplierStep, ...] = STEPS) -> SupplierWizard:
    wizard = SupplierWizard(steps, CATALOG)
    qtbot.addWidget(wizard)
    wizard.show()
    qtbot.waitExposed(wizard)
    return wizard


@pytest.fixture
def wizard(qtbot) -> SupplierWizard:
    return make_wizard(qtbot)


def test_first_step_shows_progress_identity_and_actions(wizard: SupplierWizard) -> None:
    assert wizard.windowTitle() == strings.SUPPLIER_DIALOG_TITLE
    assert wizard.subtitle_label.text() == strings.supplier_dialog_subtitle(1, 3)
    assert wizard.identity.nit_label.text() == "900123456"
    assert wizard.identity.name_label.text() == "Papelería ABC S.A.S."
    assert wizard.primary_button.text() == strings.ACTION_SAVE_AND_NEXT
    assert wizard.skip_button is not None
    assert wizard.skip_button.text() == strings.ACTION_SKIP
    assert wizard.cancel_button.text() == strings.ACTION_CLOSE
    assert wizard.current_index() == 0
    assert wizard.step_count() == 3


def test_nit_and_name_are_labels_not_inputs(wizard: SupplierWizard) -> None:
    assert wizard.identity.findChildren(QLineEdit) == []


def test_context_lists_the_pending_lines_with_money_on_the_right(wizard: SupplierWizard) -> None:
    assert wizard.context.isVisible()
    assert wizard.context.title_label.text() == strings.WIZARD_CONTEXT_TITLE
    assert wizard.context.row_count() == 2
    assert wizard.context.description(0) == "RESMA PAPEL CARTA 75G"
    assert wizard.context.amount_text(0) == "$ 30.000"
    assert wizard.context.amount_text(1) == "$ 125.000,50"


def test_context_is_hidden_when_the_supplier_has_no_pending_lines(
    wizard: SupplierWizard,
) -> None:
    wizard.skip_button.click()  # type: ignore[union-attr]

    assert wizard.current_index() == 1
    assert not wizard.context.isVisible()


def test_save_waits_for_a_product_and_the_hint_says_how_to_get_there(
    wizard: SupplierWizard,
) -> None:
    emitted: list[SupplierValues] = []
    wizard.save_requested.connect(emitted.append)

    # Sin productos marcados no hay estrella en pantalla: la pista pide marcar, no elegir estrella
    hint = "Marca los productos que este proveedor puede traer."
    assert wizard.picker.summary_label.text() == hint
    assert not wizard.primary_button.isEnabled()
    assert wizard.primary_button.toolTip() == strings.SUPPLIER_PRODUCTS_NONE
    wizard.primary_button.click()
    assert emitted == []
    assert wizard.current_index() == 0

    wizard.picker.set_checked("1001", True)

    assert wizard.primary_button.isEnabled()
    assert wizard.primary_button.toolTip() == ""
    assert wizard.picker.summary_label.text() == "Por defecto: 1001 - Papelería."

    wizard.picker.set_checked("1002", True)

    # con mas de un producto marcado ya hay estrellas para elegir cual va primero
    assert wizard.picker.summary_label.text() == (
        "Por defecto: 1001 - Papelería. Cámbialo con la estrella."
    )

    wizard.picker.set_checked("1001", False)
    wizard.picker.set_checked("1002", False)

    assert not wizard.primary_button.isEnabled()
    assert wizard.picker.summary_label.text() == strings.PICKER_NO_DEFAULT_HINT


def test_saving_with_products_that_left_the_catalog_asks_to_remove_them(qtbot) -> None:
    steps = (SupplierStep("700", "Beta", (), ("9999", "1001"), "1001"),)
    wizard = make_wizard(qtbot, steps)
    emitted: list[SupplierValues] = []
    wizard.save_requested.connect(emitted.append)

    wizard.primary_button.click()

    assert emitted == []
    assert wizard.error_note.text() == strings.SUPPLIER_PRODUCTS_MISSING


def test_saving_emits_the_values_and_locks_the_sheet_until_the_container_answers(
    wizard: SupplierWizard,
) -> None:
    emitted: list[SupplierValues] = []
    wizard.save_requested.connect(emitted.append)
    wizard.picker.set_checked("1002", True)
    wizard.picker.set_checked("1003", True)
    wizard.picker.set_default_code("1003")

    wizard.primary_button.click()

    assert emitted == [
        SupplierValues("900123456", "Papelería ABC S.A.S.", ("1002", "1003"), "1003")
    ]
    assert not wizard.primary_button.isEnabled()
    assert not wizard.cancel_button.isEnabled()
    assert not wizard.skip_button.isEnabled()  # type: ignore[union-attr]
    assert not wizard.picker.isEnabled()
    assert wizard.current_index() == 0


def test_mark_saved_moves_to_the_next_supplier_with_a_fresh_form(wizard: SupplierWizard) -> None:
    wizard.picker.set_checked("1001", True)
    wizard.primary_button.click()

    wizard.mark_saved()

    assert wizard.current_index() == 1
    assert wizard.subtitle_label.text() == strings.supplier_dialog_subtitle(2, 3)
    assert wizard.identity.nit_label.text() == "800111222"
    assert wizard.picker.selected_codes() == ()
    assert not wizard.primary_button.isEnabled()  # el siguiente proveedor empieza sin productos
    assert wizard.picker.isEnabled()
    assert not wizard.error_note.isVisible()


def test_a_supplier_with_a_previous_configuration_comes_prefilled(wizard: SupplierWizard) -> None:
    wizard.skip_button.click()  # type: ignore[union-attr]
    wizard.skip_button.click()  # type: ignore[union-attr]

    assert wizard.current_index() == 2
    assert wizard.picker.selected_codes() == ("1002", "1003")
    assert wizard.picker.default_code() == "1003"


def test_the_last_step_says_save_and_finishing_accepts_the_dialog(wizard: SupplierWizard) -> None:
    wizard.skip_button.click()  # type: ignore[union-attr]
    wizard.skip_button.click()  # type: ignore[union-attr]
    assert wizard.primary_button.text() == strings.ACTION_SAVE
    emitted: list[SupplierValues] = []
    wizard.save_requested.connect(emitted.append)

    wizard.primary_button.click()
    assert len(emitted) == 1
    wizard.mark_saved()

    assert wizard.result() == QDialog.DialogCode.Accepted


def test_skip_moves_on_without_saving_and_reports_which_supplier(wizard: SupplierWizard) -> None:
    saved: list[SupplierValues] = []
    skipped: list[str] = []
    wizard.save_requested.connect(saved.append)
    wizard.skipped.connect(skipped.append)

    wizard.skip_button.click()  # type: ignore[union-attr]

    assert saved == []
    assert skipped == ["900123456"]
    assert wizard.current_index() == 1


def test_skipping_the_last_supplier_finishes(wizard: SupplierWizard) -> None:
    wizard.skip_button.click()  # type: ignore[union-attr]
    wizard.skip_button.click()  # type: ignore[union-attr]

    wizard.skip_button.click()  # type: ignore[union-attr]

    assert not wizard.isVisible()
    assert wizard.result() == QDialog.DialogCode.Accepted


def test_mark_failed_shows_the_error_and_unlocks(wizard: SupplierWizard) -> None:
    wizard.picker.set_checked("1001", True)
    wizard.primary_button.click()

    wizard.mark_failed("No se pudo guardar. Inténtalo de nuevo.")

    assert wizard.current_index() == 0
    assert wizard.error_note.text() == "No se pudo guardar. Inténtalo de nuevo."
    assert wizard.primary_button.isEnabled()
    assert wizard.picker.isEnabled()


def test_close_rejects_at_any_step(qtbot, wizard: SupplierWizard) -> None:
    wizard.cancel_button.click()

    assert wizard.result() == QDialog.DialogCode.Rejected
    assert not wizard.isVisible()


def test_a_single_supplier_has_no_progress_and_nothing_to_skip(qtbot) -> None:
    wizard = make_wizard(qtbot, (STEPS[0],))

    assert not wizard.subtitle_label.isVisible()
    assert wizard.skip_button is None
    assert wizard.primary_button.text() == strings.ACTION_SAVE


def test_empty_catalog_offers_to_open_the_catalog_without_closing(qtbot) -> None:
    wizard = SupplierWizard(STEPS, ())
    qtbot.addWidget(wizard)
    wizard.show()
    requested: list[int] = []
    wizard.catalog_requested.connect(lambda: requested.append(1))

    wizard.picker.catalog_button.click()

    assert requested == [1]
    assert wizard.isVisible()


def test_wizard_needs_at_least_one_supplier() -> None:
    with pytest.raises(ValueError):
        SupplierWizard((), CATALOG)


def test_tab_follows_the_visual_order_of_the_footer(wizard: SupplierWizard) -> None:
    assert wizard.skip_button is not None

    after_list = focus_order_after(wizard.picker.list, wizard, 3)

    assert after_list == [wizard.skip_button, wizard.cancel_button, wizard.primary_button]


def test_the_context_keeps_one_height_across_steps_so_the_window_does_not_jump(qtbot) -> None:
    many = tuple(ContextLine("FEV-1", f"LINEA {n}", Decimal(n * 1000)) for n in range(1, 8))
    steps = (
        SupplierStep("900", "Con pocas lineas", LINES[:1]),
        SupplierStep("800", "Con muchas lineas", many),
    )
    wizard = make_wizard(qtbot, steps)
    first = wizard.context.table.maximumHeight()

    wizard.skip_button.click()  # type: ignore[union-attr]

    assert wizard.context.row_count() == 7
    assert wizard.context.table.maximumHeight() == first
