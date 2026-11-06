"""SuppliersView: the Proveedores page without any use case behind it."""

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.model import COL_ACTION, COL_DEFAULT, COL_SUPPLIER
from contabilizador.ui.pages.suppliers.rows import SupplierRow
from contabilizador.ui.pages.suppliers.view import ROW_HEIGHT, SuppliersView
from contabilizador.ui.theme import TOKENS

ROWS = [
    SupplierRow("900", "Zeta S.A.S.", configured=False, pending_invoices=2),
    SupplierRow("800", "Alfa Ltda.", configured=False, pending_invoices=1),
    SupplierRow("700", "Beta Ltda.", True, ("P-1", "P-2"), "P-1", (), 4),
]
NAMES = {"P-1": "Papelería", "P-2": "Aseo"}


@pytest.fixture
def view(qtbot) -> SuppliersView:
    widget = SuppliersView()
    qtbot.addWidget(widget)
    widget.resize(900, 600)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


@pytest.fixture
def filled(view: SuppliersView) -> SuppliersView:
    view.set_suppliers(ROWS, NAMES)
    return view


def cell_center(view: SuppliersView, nit: str, column: int) -> QPoint:
    proxy_row = view.visible_nits().index(nit)
    index = view.table.model().index(proxy_row, column)
    return view.table.visualRect(index).center()


def test_page_header_names_the_page_and_its_purpose(view: SuppliersView) -> None:
    assert view.title_label.text() == strings.SUPPLIERS_PAGE_TITLE
    assert view.purpose_label.text() == strings.SUPPLIERS_PAGE_PURPOSE
    assert view.title_label.property("role") == "page-title"


def test_starts_loading_without_controls(view: SuppliersView) -> None:
    assert view.state() == "loading"
    assert view.loading_label.text() == strings.LOADING
    assert not view.search.isVisible()
    assert not view.configure_button.isVisible()


def test_no_company_explains_that_suppliers_belong_to_a_company(view: SuppliersView) -> None:
    view.show_no_company()

    assert view.state() == "no_company"
    assert view.no_company_state.title_label.text() == strings.SUPPLIERS_NO_COMPANY_TITLE
    assert view.no_company_state.text_label.text() == strings.SUPPLIERS_NO_COMPANY_TEXT
    assert not view.search.isVisible()


def test_failure_state_explains_and_offers_to_retry(qtbot, view: SuppliersView) -> None:
    view.show_failure()

    assert view.state() == "error"
    assert view.error_state.title_label.text() == strings.ERROR_GENERIC_TITLE
    assert view.error_state.action_button.text() == strings.ACTION_RETRY
    assert view.retry_button is view.error_state.action_button
    assert not view.search.isVisible()
    with qtbot.waitSignal(view.retry_requested, timeout=1000):
        view.retry_button.click()


def test_empty_list_invites_to_import_invoices(qtbot, view: SuppliersView) -> None:
    view.set_suppliers([], {})

    assert view.state() == "empty"
    assert view.empty_state.title_label.text() == strings.EMPTY_SUPPLIERS_TITLE
    assert view.empty_state.text_label.text() == strings.EMPTY_SUPPLIERS_TEXT
    assert view.empty_state.action_button.text() == strings.ACTION_SUPPLIERS_GO_TO_INVOICES
    assert not view.configure_button.isVisible()
    with qtbot.waitSignal(view.navigate_requested, timeout=1000) as blocker:
        view.empty_state.action_button.click()
    assert blocker.args == ["invoices"]


def test_lists_unconfigured_first_with_the_action_to_configure_them_all(
    qtbot, filled: SuppliersView
) -> None:
    assert filled.state() == "list"
    assert filled.visible_nits() == ["900", "800", "700"]
    assert filled.search.isVisible()
    assert filled.configure_button.isVisible()
    assert filled.configure_button.text() == strings.configure_pending_action(2)
    assert filled.configure_button.property("variant") == "primary"
    with qtbot.waitSignal(filled.configure_all_requested, timeout=1000):
        filled.configure_button.click()


def test_configure_action_uses_the_singular_for_one_supplier(view: SuppliersView) -> None:
    view.set_suppliers([ROWS[0], ROWS[2]], NAMES)

    assert view.configure_button.text() == strings.configure_pending_action(1)


def test_configure_action_disappears_when_everything_is_configured(view: SuppliersView) -> None:
    view.set_suppliers([ROWS[2]], NAMES)

    assert view.state() == "list"
    assert not view.configure_button.isVisible()


def test_search_filters_by_nit_or_name(filled: SuppliersView) -> None:
    filled.set_search_text("beta")
    assert filled.visible_nits() == ["700"]

    filled.set_search_text("90")
    assert filled.visible_nits() == ["900"]

    filled.set_search_text("")
    assert filled.visible_nits() == ["900", "800", "700"]


def test_search_without_results_says_so_and_offers_to_clear(filled: SuppliersView) -> None:
    filled.set_search_text("zzz")

    assert filled.state() == "no_match"
    assert filled.no_match_label.text() == strings.suppliers_no_match("zzz")
    assert filled.clear_search_button.text() == strings.ACTION_CLEAR_SEARCH
    assert filled.search.isVisible()  # se puede seguir escribiendo

    filled.clear_search_button.click()
    assert filled.state() == "list"
    assert filled.search.text() == ""
    assert filled.visible_nits() == ["900", "800", "700"]


def test_typing_in_the_search_field_filters_after_the_debounce(
    qtbot, filled: SuppliersView
) -> None:
    filled.search.set_debounce_ms(0)

    qtbot.keyClicks(filled.search, "alfa")

    qtbot.waitUntil(lambda: filled.visible_nits() == ["800"], timeout=2000)


def test_activating_a_row_requests_its_edit(qtbot, filled: SuppliersView) -> None:
    index = filled.table.model().index(2, COL_SUPPLIER)

    with qtbot.waitSignal(filled.edit_requested, timeout=1000) as blocker:
        filled.table.activated.emit(index)

    assert blocker.args == ["700"]


def test_double_clicking_a_row_requests_its_edit(qtbot, filled: SuppliersView) -> None:
    position = cell_center(filled, "800", COL_SUPPLIER)
    # Como un usuario: el primer clic selecciona la fila y el doble clic la abre
    qtbot.mouseClick(filled.table.viewport(), Qt.MouseButton.LeftButton, pos=position)

    with qtbot.waitSignal(filled.edit_requested, timeout=1000) as blocker:
        qtbot.mouseDClick(filled.table.viewport(), Qt.MouseButton.LeftButton, pos=position)

    assert blocker.args == ["800"]


def test_clicking_the_action_cell_requests_the_edit_in_one_click(
    qtbot, filled: SuppliersView
) -> None:
    with qtbot.waitSignal(filled.edit_requested, timeout=1000) as blocker:
        qtbot.mouseClick(
            filled.table.viewport(),
            Qt.MouseButton.LeftButton,
            pos=cell_center(filled, "700", COL_ACTION),
        )

    assert blocker.args == ["700"]


def test_clicking_any_other_cell_only_selects_the_row(qtbot, filled: SuppliersView) -> None:
    requested: list[str] = []
    filled.edit_requested.connect(requested.append)

    qtbot.mouseClick(
        filled.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=cell_center(filled, "800", COL_SUPPLIER),
    )

    assert requested == []
    assert filled.selected_nit() == "800"


def test_delete_key_asks_to_delete_only_configured_suppliers(qtbot, filled: SuppliersView) -> None:
    deleted: list[str] = []
    filled.delete_requested.connect(deleted.append)

    filled.select_nit("900")
    qtbot.keyClick(filled.table, Qt.Key.Key_Delete)
    assert deleted == []

    filled.select_nit("700")
    qtbot.keyClick(filled.table, Qt.Key.Key_Delete)
    assert deleted == ["700"]


def test_context_menu_depends_on_whether_the_supplier_is_configured(
    qtbot, filled: SuppliersView
) -> None:
    configured = filled.context_menu("700")
    waiting = filled.context_menu("900")

    assert [a.text() for a in configured.actions()] == [
        strings.ACTION_EDIT,
        strings.ACTION_DELETE,
    ]
    assert [a.text() for a in waiting.actions()] == [strings.ACTION_CONFIGURE]

    edit, delete = _actions(configured)
    with qtbot.waitSignal(filled.edit_requested, timeout=1000) as edited:
        edit.trigger()
    with qtbot.waitSignal(filled.delete_requested, timeout=1000) as deleted:
        delete.trigger()
    assert edited.args == ["700"]
    assert deleted.args == ["700"]


def _actions(menu) -> list[QAction]:
    return list(menu.actions())


def test_refresh_keeps_the_selected_supplier(filled: SuppliersView) -> None:
    filled.select_nit("700")

    filled.set_suppliers([ROWS[1], ROWS[0], ROWS[2]], NAMES)

    assert filled.selected_nit() == "700"


def test_refresh_keeps_the_search(filled: SuppliersView) -> None:
    filled.set_search_text("beta")

    filled.set_suppliers(ROWS, NAMES)

    assert filled.visible_nits() == ["700"]


def test_focus_search_puts_the_cursor_in_the_search_field(view: SuppliersView) -> None:
    view.set_suppliers(ROWS, NAMES)

    view.focus_search()

    assert view.search.hasFocus()


def test_keyboard_focus_marks_the_current_row_with_a_blue_bar(qtbot, filled: SuppliersView) -> None:
    filled.select_nit("800")
    filled.table.setFocus()
    qtbot.waitUntil(filled.table.hasFocus, timeout=2000)

    image = filled.table.viewport().grab().toImage()
    row_rect = filled.table.visualRect(filled.table.currentIndex())
    other_rect = filled.table.visualRect(filled.table.model().index(0, 0))

    assert image.pixelColor(1, row_rect.center().y()).name().upper() == TOKENS.blue
    assert image.pixelColor(1, other_rect.center().y()).name().upper() != TOKENS.blue


def test_wide_windows_give_the_extra_room_to_the_default_product(
    qtbot, filled: SuppliersView
) -> None:
    filled.resize(1500, 700)
    qtbot.waitUntil(lambda: filled.table.columnWidth(COL_DEFAULT) > 146, timeout=2000)
    wide = filled.table.columnWidth(COL_DEFAULT)

    # La pagina de 1024 px ocupa unos 760 sin la barra lateral: ahi no sobra nada
    filled.resize(760, 700)
    qtbot.waitUntil(lambda: filled.table.columnWidth(COL_DEFAULT) < wide, timeout=2000)

    assert filled.table.columnWidth(COL_DEFAULT) == 146  # nunca por debajo del minimo


def test_the_table_is_as_tall_as_its_rows_so_short_lists_do_not_leave_an_empty_box(
    filled: SuppliersView,
) -> None:
    table = filled.table
    chrome = table.horizontalHeader().height() + 2 * table.frameWidth()

    assert table.maximumHeight() == chrome + 3 * ROW_HEIGHT

    filled.set_search_text("beta")
    assert table.maximumHeight() == chrome + 1 * ROW_HEIGHT
