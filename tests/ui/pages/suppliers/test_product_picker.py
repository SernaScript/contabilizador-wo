"""ProductPicker: searchable checklist with a star for the default product."""

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QToolTip, QVBoxLayout

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.product_picker import ProductPicker
from contabilizador.ui.widgets import CodeItem

CATALOG = (
    CodeItem("1001", "Papelería"),
    CodeItem("1002", "Aseo y cafetería"),
    CodeItem("1003", "Transporte"),
    CodeItem("1004", "Mensajería"),
)


@pytest.fixture
def picker(qtbot) -> ProductPicker:
    widget = ProductPicker()
    qtbot.addWidget(widget)
    widget.resize(440, 420)
    widget.set_products(CATALOG)
    return widget


@pytest.fixture
def shown(qtbot, picker: ProductPicker) -> ProductPicker:
    picker.show()
    qtbot.waitExposed(picker)
    return picker


def test_lists_the_whole_catalog_unchecked(picker: ProductPicker) -> None:
    assert picker.visible_codes() == ["1001", "1002", "1003", "1004"]
    assert picker.selected_codes() == ()
    assert picker.default_code() is None
    assert picker.count_label.text() == strings.picker_selected_count(0)
    assert picker.summary_label.text() == strings.PICKER_NO_DEFAULT_HINT


def test_selection_goes_first_in_the_given_order_and_keeps_the_default(
    picker: ProductPicker,
) -> None:
    picker.set_selection(["1003", "1001"], "1001")

    assert picker.visible_codes() == ["1003", "1001", "1002", "1004"]
    assert picker.selected_codes() == ("1003", "1001")
    assert picker.default_code() == "1001"
    assert picker.count_label.text() == strings.picker_selected_count(2)
    assert picker.summary_label.text() == strings.picker_default_summary(
        "1001 - Papelería", can_change=True
    )


def test_a_default_outside_the_selection_falls_back_to_the_first_selected(
    picker: ProductPicker,
) -> None:
    picker.set_selection(["1003", "1001"], "1004")

    assert picker.default_code() == "1003"


def test_checking_the_first_product_makes_it_the_default(picker: ProductPicker) -> None:
    picker.set_checked("1002", True)
    picker.set_checked("1004", True)

    assert picker.selected_codes() == ("1002", "1004")
    assert picker.default_code() == "1002"


def test_unchecking_the_default_moves_it_to_the_first_remaining(picker: ProductPicker) -> None:
    picker.set_selection(["1001", "1002", "1003"], "1001")

    picker.set_checked("1001", False)

    assert picker.selected_codes() == ("1002", "1003")
    assert picker.default_code() == "1002"


def test_unchecking_everything_clears_the_default(picker: ProductPicker) -> None:
    picker.set_selection(["1001"], "1001")

    picker.set_checked("1001", False)

    assert picker.selected_codes() == ()
    assert picker.default_code() is None
    assert picker.summary_label.text() == strings.PICKER_NO_DEFAULT_HINT


def test_choosing_a_default_also_checks_the_product(picker: ProductPicker) -> None:
    picker.set_selection(["1001"], "1001")

    picker.set_default_code("1004")

    assert picker.selected_codes() == ("1001", "1004")
    assert picker.default_code() == "1004"


def test_user_changes_emit_selection_changed_but_programmatic_loads_do_not(
    qtbot, picker: ProductPicker
) -> None:
    emitted: list[int] = []
    picker.selection_changed.connect(lambda: emitted.append(1))

    picker.set_selection(["1001"], "1001")
    picker.set_products(CATALOG)
    assert emitted == []

    picker.set_checked("1002", True)
    picker.set_default_code("1002")
    assert len(emitted) == 2


def test_catalog_reload_keeps_the_selection(picker: ProductPicker) -> None:
    picker.set_selection(["1002"], "1002")

    picker.set_products([*CATALOG, CodeItem("1005", "Nueva")])

    assert picker.selected_codes() == ("1002",)
    assert picker.default_code() == "1002"
    assert "1005" in picker.visible_codes()


def test_search_ignores_case_and_accents_and_matches_code_or_name(picker: ProductPicker) -> None:
    picker.search.setText("CAFETERIA")
    assert picker.visible_codes() == ["1002"]

    picker.search.setText("1003")
    assert picker.visible_codes() == ["1003"]

    picker.search.setText("")
    assert len(picker.visible_codes()) == 4


def test_search_without_results_says_so_and_clearing_restores_the_list(
    shown: ProductPicker,
) -> None:
    shown.search.setText("zzz")

    assert shown.visible_codes() == []
    assert shown.no_match_label.isVisible()
    assert shown.no_match_label.text() == strings.picker_no_match("zzz")
    assert not shown.list.isVisible()

    shown.search.setText("")
    assert shown.list.isVisible()
    assert not shown.no_match_label.isVisible()


def test_filtering_does_not_lose_checked_products(picker: ProductPicker) -> None:
    picker.set_selection(["1001"], "1001")

    picker.search.setText("transporte")
    picker.set_checked("1003", True)
    picker.search.setText("")

    assert picker.selected_codes() == ("1001", "1003")


def test_products_missing_from_the_catalog_are_listed_checked_and_removable(
    picker: ProductPicker,
) -> None:
    picker.set_selection(["9999", "1001"], "1001")

    assert picker.visible_codes()[:2] == ["9999", "1001"]
    assert picker.selected_codes() == ("9999", "1001")
    assert picker.missing_codes() == ("9999",)

    picker.search.setText("transporte")
    assert "9999" in picker.visible_codes()  # siempre visible: hay que quitarlo

    picker.set_checked("9999", False)
    assert picker.missing_codes() == ()
    assert "9999" not in picker.visible_codes()
    assert picker.selected_codes() == ("1001",)


def test_a_missing_product_never_becomes_the_default(picker: ProductPicker) -> None:
    picker.set_selection(["9999", "1001"], "9999")

    assert picker.default_code() == "1001"


def test_empty_catalog_shows_the_hint_and_asks_to_open_the_catalog(
    qtbot, shown: ProductPicker
) -> None:
    shown.set_products([])

    assert shown.empty_label.isVisible()
    assert shown.empty_label.text() == strings.NO_PRODUCTS_HINT
    assert not shown.search.isVisible()
    assert shown.catalog_button.text() == strings.ACTION_PICKER_GO_TO_CATALOGS
    with qtbot.waitSignal(shown.catalog_requested, timeout=1000):
        shown.catalog_button.click()

    shown.set_products(CATALOG)
    assert shown.list.isVisible()
    assert shown.search.isVisible()
    assert not shown.empty_label.isVisible()


def test_clicking_a_row_toggles_it(qtbot, shown: ProductPicker) -> None:
    qtbot.mouseClick(
        shown.list.viewport(), Qt.MouseButton.LeftButton, pos=shown.row_rect("1002").center()
    )
    assert shown.selected_codes() == ("1002",)
    assert shown.default_code() == "1002"

    qtbot.mouseClick(
        shown.list.viewport(), Qt.MouseButton.LeftButton, pos=shown.row_rect("1002").center()
    )
    assert shown.selected_codes() == ()


def test_clicking_the_star_of_a_checked_row_sets_the_default(qtbot, shown: ProductPicker) -> None:
    shown.set_selection(["1001", "1003"], "1001")

    qtbot.mouseClick(
        shown.list.viewport(), Qt.MouseButton.LeftButton, pos=shown.star_rect("1003").center()
    )

    assert shown.default_code() == "1003"
    assert shown.selected_codes() == ("1001", "1003")  # la estrella no desmarca


def test_unchecked_rows_have_no_star_and_a_click_on_their_right_edge_checks_them(
    qtbot, shown: ProductPicker
) -> None:
    assert shown.star_rect("1002").isNull()

    rect = shown.row_rect("1002")
    qtbot.mouseClick(
        shown.list.viewport(),
        Qt.MouseButton.LeftButton,
        pos=QPoint(rect.right() - 20, rect.center().y()),
    )

    assert shown.selected_codes() == ("1002",)


def test_space_toggles_the_current_row(qtbot, shown: ProductPicker) -> None:
    shown.list.setCurrentIndex(shown.index_for("1003"))

    qtbot.keyClick(shown.list, Qt.Key.Key_Space)
    assert shown.selected_codes() == ("1003",)

    qtbot.keyClick(shown.list, Qt.Key.Key_Space)
    assert shown.selected_codes() == ()


def test_default_shortcut_marks_the_current_row(qtbot, shown: ProductPicker) -> None:
    shown.set_selection(["1001"], "1001")
    shown.list.setCurrentIndex(shown.index_for("1004"))

    shown.set_current_as_default()

    assert shown.default_code() == "1004"
    assert shown.selected_codes() == ("1001", "1004")


def test_return_in_the_search_field_moves_to_the_list_instead_of_submitting(
    qtbot,
) -> None:
    dialog = QDialog()
    qtbot.addWidget(dialog)
    layout = QVBoxLayout(dialog)
    picker = ProductPicker()
    picker.set_products(CATALOG)
    layout.addWidget(picker)
    submit = QPushButton("Guardar")
    submit.setDefault(True)
    clicks: list[int] = []
    submit.clicked.connect(lambda: clicks.append(1))
    layout.addWidget(submit)
    dialog.show()
    qtbot.waitExposed(dialog)

    picker.search.setFocus()
    picker.search.setText("transporte")
    qtbot.keyClick(picker.search, Qt.Key.Key_Return)

    assert clicks == []
    assert picker.current_code() == "1003"


def test_star_tooltip_mentions_the_shortcut(picker: ProductPicker) -> None:
    assert strings.PICKER_STAR_SET in picker.star_tooltip(is_default=False)
    assert picker.star_tooltip(is_default=True) == strings.PICKER_STAR_IS_DEFAULT


def test_rows_expose_the_full_label_as_display_text(picker: ProductPicker) -> None:
    index = picker.index_for("1001")

    assert index.data(Qt.ItemDataRole.DisplayRole) == "1001 - Papelería"


def test_a_new_search_moves_to_its_first_match_when_entering_the_list(
    qtbot, shown: ProductPicker
) -> None:
    shown.list.setCurrentIndex(shown.index_for("1004"))

    shown.search.setText("a")
    qtbot.keyClick(shown.search, Qt.Key.Key_Return)

    assert shown.current_code() == shown.visible_codes()[0]


def test_hovering_the_star_shows_its_tooltip(qtbot, shown: ProductPicker) -> None:
    shown.set_selection(["1001", "1002"], "1001")
    viewport = shown.list.viewport()
    position = shown.star_rect("1002").center()
    event = QHelpEvent(QEvent.Type.ToolTip, position, viewport.mapToGlobal(position))

    QApplication.sendEvent(viewport, event)

    assert QToolTip.text() == shown.star_tooltip(is_default=False)
    QToolTip.hideText()

    position = shown.star_rect("1001").center()
    QApplication.sendEvent(
        viewport, QHelpEvent(QEvent.Type.ToolTip, position, viewport.mapToGlobal(position))
    )
    assert QToolTip.text() == strings.PICKER_STAR_IS_DEFAULT
    QToolTip.hideText()
