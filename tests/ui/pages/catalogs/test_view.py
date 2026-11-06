"""CatalogsView: segmented kinds, search, selection-driven actions and its empty states."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared import strings
from contabilizador.ui.pages.catalogs.model import ACTION_COLUMN
from contabilizador.ui.pages.catalogs.rows import CatalogRow
from contabilizador.ui.pages.catalogs.view import CatalogsView
from contabilizador.ui.theme import TOKENS, apply_theme

PRODUCTS = [
    CatalogRow("1001", "Papelería"),
    CatalogRow("20", "Servicios técnicos"),
    CatalogRow("3", "Aseo y cafetería"),
]
COST_CENTERS = [CatalogRow("CC-1", "Administración"), CatalogRow("CC-2", "Ventas")]


def make_view(qtbot, *, rows: bool = True) -> CatalogsView:
    view = CatalogsView()
    qtbot.addWidget(view)
    view.resize(900, 600)
    view.show()
    if rows:
        view.set_rows(CatalogKind.PRODUCT, PRODUCTS)
        view.set_rows(CatalogKind.COST_CENTER, COST_CENTERS)
    return view


def codes(view: CatalogsView) -> list[str]:
    model = view.model
    return [model.index(row, 0).data() for row in range(model.rowCount())]


def wait_for_filter(qtbot, view: CatalogsView, text: str) -> None:
    view.search.setText(text)
    qtbot.waitUntil(lambda: view.model.filter_text() == text, timeout=2000)


# --- cabecera y estructura -------------------------------------------------------


def test_header_names_the_page_and_its_actions(qtbot) -> None:
    view = make_view(qtbot)

    assert view.title_label.text() == strings.CATALOGS_PAGE_TITLE
    assert view.purpose_label.text() == strings.CATALOGS_PAGE_PURPOSE
    assert view.new_button.text() == strings.ACTION_NEW
    assert view.new_button.property("variant") == "primary"
    assert view.import_button.text() == strings.ACTION_IMPORT_EXCEL
    assert view.import_button.property("variant") == "secondary"
    assert view.template_button.text() == strings.ACTION_DOWNLOAD_TEMPLATE
    assert view.template_button.property("variant") == "ghost"
    assert view.search.placeholderText() == strings.CATALOG_SEARCH_PLACEHOLDER


def test_segmented_control_switches_between_kinds_without_tabs(qtbot) -> None:
    view = make_view(qtbot)
    seen: list[CatalogKind] = []
    view.kind_changed.connect(seen.append)

    assert view.segmented.keys() == [CatalogKind.PRODUCT.value, CatalogKind.COST_CENTER.value]
    assert view.segmented.button(CatalogKind.PRODUCT.value).text() == strings.CATALOG_PRODUCTS
    assert view.current_kind() is CatalogKind.PRODUCT
    assert codes(view) == ["3", "20", "1001"]

    qtbot.mouseClick(
        view.segmented.button(CatalogKind.COST_CENTER.value), Qt.MouseButton.LeftButton
    )

    assert seen == [CatalogKind.COST_CENTER]
    assert view.current_kind() is CatalogKind.COST_CENTER
    assert codes(view) == ["CC-1", "CC-2"]
    assert view.count_label.text() == "2 centros de costo"


def test_switching_kind_clears_the_search(qtbot) -> None:
    view = make_view(qtbot)
    wait_for_filter(qtbot, view, "papel")

    view.set_kind(CatalogKind.COST_CENTER)

    assert view.search.text() == ""
    assert view.model.filter_text() == ""
    assert view.state() == "table"


def test_table_is_read_only_and_selects_whole_rows(qtbot) -> None:
    view = make_view(qtbot)

    assert view.state() == "table"
    assert view.table.model() is view.model
    assert view.table.editTriggers() == view.table.EditTrigger.NoEditTriggers
    assert view.table.selectionBehavior() == view.table.SelectionBehavior.SelectRows
    assert view.table.selectionMode() == view.table.SelectionMode.SingleSelection
    assert not view.table.verticalHeader().isVisible()


def test_count_caption_follows_the_filter(qtbot) -> None:
    view = make_view(qtbot)
    assert view.count_label.text() == "3 productos"

    wait_for_filter(qtbot, view, "papeleria")

    assert codes(view) == ["1001"]
    assert view.count_label.text() == "1 de 3 productos"


# --- seleccion y acciones --------------------------------------------------------


def click_cell(qtbot, view: CatalogsView, row: int, column: int) -> None:
    index = view.model.index(row, column)
    qtbot.mouseClick(
        view.table.viewport(), Qt.MouseButton.LeftButton, pos=view.table.visualRect(index).center()
    )


def test_delete_waits_for_a_selection_and_says_why(qtbot) -> None:
    view = make_view(qtbot)

    assert not view.delete_button.isEnabled()
    assert view.delete_button.toolTip() == strings.CATALOG_DELETE_DISABLED_HINT
    assert view.selected_code() is None

    view.select_code("20")

    assert view.selected_code() == "20"
    assert view.delete_button.isEnabled()
    assert view.delete_button.toolTip() == ""


def test_editing_is_an_inline_link_in_every_row_and_not_a_dead_toolbar_button(qtbot) -> None:
    view = make_view(qtbot)

    # un solo patron para editar, el mismo que Proveedores: enlace en la fila, nada en la barra
    assert not hasattr(view, "edit_button")
    assert view.model.columnCount() == 3
    assert view.model.index(0, ACTION_COLUMN).data() == strings.ACTION_EDIT
    assert view.table.itemDelegateForColumn(ACTION_COLUMN) is not None


def test_the_edit_link_asks_to_edit_that_row_even_without_selecting_it_first(qtbot) -> None:
    view = make_view(qtbot)
    edits: list[str] = []
    view.edit_requested.connect(edits.append)

    click_cell(qtbot, view, 1, ACTION_COLUMN)

    assert edits == ["20"]
    assert view.selected_code() == "20"


def test_clicking_the_name_only_selects_and_the_delete_button_announces_the_code(qtbot) -> None:
    view = make_view(qtbot)
    edits: list[str] = []
    deletes: list[str] = []
    view.edit_requested.connect(edits.append)
    view.delete_requested.connect(deletes.append)

    click_cell(qtbot, view, 2, 1)
    qtbot.mouseClick(view.delete_button, Qt.MouseButton.LeftButton)

    assert edits == []
    assert deletes == ["1001"]


def test_double_click_edits_the_row(qtbot) -> None:
    view = make_view(qtbot)
    edits: list[str] = []
    view.edit_requested.connect(edits.append)
    center = view.table.visualRect(view.model.index(0, 1)).center()

    # un doble clic real es un clic seguido del segundo clic con el evento de doble clic
    qtbot.mouseClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=center)
    qtbot.mouseDClick(view.table.viewport(), Qt.MouseButton.LeftButton, pos=center)

    assert edits == ["3"]


def test_the_pointer_becomes_a_hand_over_the_edit_link(qtbot) -> None:
    view = make_view(qtbot)
    link = view.table.visualRect(view.model.index(0, ACTION_COLUMN)).center()
    text = view.table.visualRect(view.model.index(0, 1)).center()

    qtbot.mouseMove(view.table.viewport(), pos=text)
    assert view.table.viewport().cursor().shape() == Qt.CursorShape.ArrowCursor
    qtbot.mouseMove(view.table.viewport(), pos=link)
    qtbot.waitUntil(
        lambda: view.table.viewport().cursor().shape() == Qt.CursorShape.PointingHandCursor,
        timeout=2000,
    )


def test_enter_on_a_row_asks_to_edit_it(qtbot) -> None:
    view = make_view(qtbot)
    edits: list[str] = []
    view.edit_requested.connect(edits.append)
    view.select_code("3")
    view.table.setFocus()

    qtbot.keyClick(view.table, Qt.Key.Key_Return)

    assert edits == ["3"]


def test_delete_key_on_a_row_asks_to_delete_it(qtbot) -> None:
    view = make_view(qtbot)
    deletes: list[str] = []
    view.delete_requested.connect(deletes.append)
    view.select_code("20")
    view.table.setFocus()

    qtbot.keyClick(view.table, Qt.Key.Key_Delete)

    assert deletes == ["20"]


def test_escape_clears_the_selection_like_everywhere_else(qtbot) -> None:
    view = make_view(qtbot)
    view.select_code("20")
    view.table.setFocus()

    qtbot.keyClick(view.table, Qt.Key.Key_Escape)

    assert view.selected_code() is None
    assert not view.delete_button.isEnabled()


def test_delete_key_without_a_selection_does_nothing(qtbot) -> None:
    view = make_view(qtbot)
    deletes: list[str] = []
    view.delete_requested.connect(deletes.append)

    qtbot.keyClick(view.table, Qt.Key.Key_Delete)

    assert deletes == []


def test_clicking_a_row_selects_it(qtbot) -> None:
    view = make_view(qtbot)
    index = view.model.index(1, 0)

    qtbot.mouseClick(
        view.table.viewport(), Qt.MouseButton.LeftButton, pos=view.table.visualRect(index).center()
    )

    assert view.selected_code() == "20"
    assert view.delete_button.isEnabled()


def test_header_buttons_emit_their_requests(qtbot) -> None:
    view = make_view(qtbot)
    emitted: list[str] = []
    view.new_requested.connect(lambda: emitted.append("new"))
    view.import_requested.connect(lambda: emitted.append("import"))
    view.template_requested.connect(lambda: emitted.append("template"))

    for button in (view.new_button, view.import_button, view.template_button):
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert emitted == ["new", "import", "template"]


def test_selection_survives_a_refresh_of_the_same_kind(qtbot) -> None:
    view = make_view(qtbot)
    view.select_code("20")

    view.set_rows(CatalogKind.PRODUCT, [*PRODUCTS, CatalogRow("4", "Nuevo")])

    assert view.selected_code() == "20"
    assert view.delete_button.isEnabled()


def test_selection_is_dropped_when_the_row_disappears(qtbot) -> None:
    view = make_view(qtbot)
    view.select_code("20")

    view.set_rows(CatalogKind.PRODUCT, [CatalogRow("3", "Aseo y cafetería")])

    assert view.selected_code() is None
    assert not view.delete_button.isEnabled()


def test_reveal_code_selects_it_and_clears_a_search_that_hides_it(qtbot) -> None:
    view = make_view(qtbot)
    wait_for_filter(qtbot, view, "papel")

    view.reveal_code("20")

    assert view.search.text() == ""
    assert view.selected_code() == "20"
    assert codes(view) == ["3", "20", "1001"]


# --- busqueda y estados vacios ----------------------------------------------------


def test_no_matches_offers_to_clear_the_search(qtbot) -> None:
    view = make_view(qtbot)

    wait_for_filter(qtbot, view, "zzz")

    assert view.state() == "no_results"
    assert view.no_results.title_label.text() == strings.CATALOG_NO_RESULTS_TITLE
    assert view.no_results.text_label.text() == "Ningún producto coincide con «zzz»."
    assert view.no_results.action_button.text() == strings.ACTION_CLEAR_SEARCH
    assert view.count_label.text() == "0 de 3 productos"

    qtbot.mouseClick(view.no_results.action_button, Qt.MouseButton.LeftButton)
    qtbot.waitUntil(lambda: view.state() == "table", timeout=2000)

    assert view.search.text() == ""


def test_empty_catalog_invites_to_import_or_create(qtbot) -> None:
    view = make_view(qtbot, rows=False)
    view.set_rows(CatalogKind.PRODUCT, [])
    requested: list[str] = []
    view.import_requested.connect(lambda: requested.append("import"))

    assert view.state() == "empty"
    assert view.empty.title_label.text() == "Aún no hay productos"
    assert view.empty.text_label.text() == strings.EMPTY_CATALOG_TEXT
    assert view.empty.action_button.text() == strings.ACTION_IMPORT_EXCEL
    assert view.count_label.isHidden()

    qtbot.mouseClick(view.empty.action_button, Qt.MouseButton.LeftButton)

    assert requested == ["import"]
    view.set_rows(CatalogKind.COST_CENTER, [])
    view.set_kind(CatalogKind.COST_CENTER)
    assert view.state() == "empty"
    assert view.empty.title_label.text() == "Aún no hay centros de costo"


def test_before_the_first_load_nothing_claims_the_catalog_is_empty(qtbot) -> None:
    view = make_view(qtbot, rows=False)

    assert view.state() == "table"
    assert view.count_label.isHidden()

    view.set_rows(CatalogKind.PRODUCT, PRODUCTS)
    view.reset()

    assert view.state() == "table"
    assert view.model.rowCount() == 0


def test_controls_that_need_rows_hide_when_there_is_nothing_to_act_on(qtbot) -> None:
    view = make_view(qtbot)
    controls = (view.search, view.delete_button)
    assert all(control.isVisibleTo(view) for control in controls)

    view.set_rows(CatalogKind.PRODUCT, [])
    assert view.state() == "empty"
    assert not any(control.isVisibleTo(view) for control in controls)
    assert view.segmented.isVisibleTo(view)  # se sigue pudiendo cambiar de catalogo

    view.set_rows(CatalogKind.PRODUCT, PRODUCTS)
    wait_for_filter(qtbot, view, "zzz")
    assert view.state() == "no_results"
    assert all(control.isVisibleTo(view) for control in controls)

    view.set_has_company(False)
    assert not any(control.isVisibleTo(view) for control in controls)


def test_no_results_is_quiet_text_without_a_dashed_drop_zone(qtbot) -> None:
    view = make_view(qtbot)

    wait_for_filter(qtbot, view, "zzz")

    assert view.no_results.property("role") != "empty-state"


def test_without_a_company_the_page_asks_for_one_and_locks_the_actions(qtbot) -> None:
    view = make_view(qtbot)

    view.set_has_company(False)

    assert view.state() == "no_company"
    assert view.no_company.title_label.text() == strings.CATALOG_NO_COMPANY_TITLE
    for button in (view.new_button, view.import_button, view.template_button):
        assert not button.isEnabled()
        assert not button.isVisibleTo(view)  # un boton gris que parece activo confunde: se oculta
    assert not view.delete_button.isEnabled()

    view.set_has_company(True)

    assert view.state() == "table"
    assert view.new_button.isEnabled()
    assert view.new_button.isVisibleTo(view)


def test_busy_locks_every_action_but_keeps_the_rows_visible(qtbot) -> None:
    view = make_view(qtbot)
    view.select_code("20")

    view.set_busy(True)

    for button in (
        view.new_button,
        view.import_button,
        view.template_button,
        view.delete_button,
    ):
        assert not button.isEnabled()
    assert view.state() == "table"

    # con una tarea en curso el enlace de la fila tampoco edita
    edits: list[str] = []
    view.edit_requested.connect(edits.append)
    click_cell(qtbot, view, 1, ACTION_COLUMN)
    assert edits == []

    view.set_busy(False)

    assert view.delete_button.isEnabled()
    assert view.new_button.isEnabled()


def test_focus_search_puts_the_cursor_in_the_search_field(qtbot) -> None:
    view = make_view(qtbot)

    view.focus_search()

    assert view.focusWidget() is view.search


# --- aspecto de los botones deshabilitados ---------------------------------------------


@pytest.fixture
def themed(qapp: QApplication):
    """The real stylesheet, restored afterwards so other tests keep the plain style."""
    previous_sheet = qapp.styleSheet()
    previous_style = qapp.style().objectName()
    apply_theme(qapp)
    yield
    qapp.setStyleSheet(previous_sheet)
    qapp.setStyle(previous_style)


def background_of(button) -> str:
    image = button.grab().toImage()
    return QColor(image.pixelColor(6, button.height() // 2)).name().upper()


def test_disabled_actions_do_not_look_clickable(qtbot, themed) -> None:
    view = make_view(qtbot)
    view.select_code("20")
    enabled = {
        "delete": background_of(view.delete_button),
        "import": background_of(view.import_button),
    }

    view.table.clearSelection()
    view.set_busy(True)

    for name, button in (("delete", view.delete_button), ("import", view.import_button)):
        assert not button.isEnabled()
        assert background_of(button) == TOKENS.disabled_bg, name
    assert enabled["delete"] != TOKENS.disabled_bg
    assert enabled["import"] != TOKENS.disabled_bg
