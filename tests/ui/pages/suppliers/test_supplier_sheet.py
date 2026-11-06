"""SupplierSheet: edit the products of a configured supplier, or delete it."""

import pytest

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.rows import SupplierRow, SupplierValues
from contabilizador.ui.pages.suppliers.sheet import SupplierSheet
from contabilizador.ui.widgets import CodeItem
from tests.ui.pages.suppliers.focus import focus_order_after

CATALOG = (
    CodeItem("1001", "Papelería"),
    CodeItem("1002", "Aseo"),
    CodeItem("1003", "Transporte"),
)
ROW = SupplierRow(
    "900123456",
    "Papelería ABC S.A.S.",
    configured=True,
    product_codes=("1002", "1001"),
    default_product_code="1001",
)


@pytest.fixture
def sheet(qtbot) -> SupplierSheet:
    widget = SupplierSheet(ROW, CATALOG)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_sheet_shows_the_supplier_and_its_current_products(sheet: SupplierSheet) -> None:
    assert sheet.windowTitle() == strings.SUPPLIER_EDIT_TITLE
    assert not sheet.subtitle_label.isVisible()
    assert sheet.identity.nit_label.text() == "900123456"
    assert sheet.identity.name_label.text() == "Papelería ABC S.A.S."
    assert sheet.picker.selected_codes() == ("1002", "1001")
    assert sheet.picker.default_code() == "1001"
    assert sheet.primary_button.text() == strings.ACTION_SAVE
    assert sheet.cancel_button.text() == strings.ACTION_CANCEL


def test_save_emits_the_edited_values_and_locks_the_sheet(sheet: SupplierSheet) -> None:
    emitted: list[SupplierValues] = []
    sheet.save_requested.connect(emitted.append)
    sheet.picker.set_checked("1003", True)
    sheet.picker.set_default_code("1002")

    sheet.primary_button.click()

    assert emitted == [
        SupplierValues("900123456", "Papelería ABC S.A.S.", ("1002", "1001", "1003"), "1002")
    ]
    assert not sheet.primary_button.isEnabled()
    assert not sheet.delete_button.isEnabled()
    assert not sheet.picker.isEnabled()


def test_save_waits_while_no_product_is_checked_and_says_why(sheet: SupplierSheet) -> None:
    emitted: list[SupplierValues] = []
    sheet.save_requested.connect(emitted.append)
    assert sheet.primary_button.isEnabled()

    sheet.picker.set_checked("1002", False)
    sheet.picker.set_checked("1001", False)

    assert not sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == strings.SUPPLIER_PRODUCTS_NONE
    sheet.primary_button.click()
    assert emitted == []

    sheet.picker.set_checked("1003", True)

    assert sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == ""


def test_products_that_left_the_catalog_block_the_save_until_removed(qtbot) -> None:
    row = SupplierRow(
        "700", "Beta", configured=True, product_codes=("9999", "1001"), default_product_code="1001"
    )
    sheet = SupplierSheet(row, CATALOG)
    qtbot.addWidget(sheet)
    sheet.show()
    emitted: list[SupplierValues] = []
    sheet.save_requested.connect(emitted.append)

    sheet.primary_button.click()
    assert emitted == []
    assert sheet.error_note.text() == strings.SUPPLIER_PRODUCTS_MISSING

    sheet.picker.set_checked("9999", False)
    sheet.primary_button.click()
    assert [values.product_codes for values in emitted] == [("1001",)]


def test_delete_button_is_a_destructive_action_that_asks_the_container(
    qtbot, sheet: SupplierSheet
) -> None:
    assert sheet.delete_button.text() == strings.ACTION_DELETE
    assert sheet.delete_button.property("variant") == "danger"

    with qtbot.waitSignal(sheet.delete_requested, timeout=1000) as blocker:
        sheet.delete_button.click()

    assert blocker.args == ["900123456"]
    assert sheet.isVisible()  # el contenedor decide cuando cerrar


def test_mark_failed_shows_the_error_and_unlocks(sheet: SupplierSheet) -> None:
    sheet.primary_button.click()
    sheet.mark_failed("No se pudo guardar el proveedor.")

    assert sheet.error_note.text() == "No se pudo guardar el proveedor."
    assert sheet.primary_button.isEnabled()
    assert sheet.delete_button.isEnabled()
    assert sheet.picker.isEnabled()


def test_catalog_request_is_forwarded(qtbot) -> None:
    sheet = SupplierSheet(ROW, ())
    qtbot.addWidget(sheet)
    sheet.show()

    with qtbot.waitSignal(sheet.catalog_requested, timeout=1000):
        sheet.picker.catalog_button.click()


def test_tab_goes_from_the_list_to_delete_then_cancel_then_save(sheet: SupplierSheet) -> None:
    order = focus_order_after(sheet.picker.list, sheet, 3)

    assert order == [sheet.delete_button, sheet.cancel_button, sheet.primary_button]
