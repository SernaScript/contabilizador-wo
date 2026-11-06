"""Contextual bulk bar: visible with 2+ selected invoices, applies product / cost center."""

from contabilizador.shared import strings
from contabilizador.ui.pages.invoices.bulk_bar import BulkBar
from contabilizador.ui.widgets.code_combo import CodeItem
from tests.ui.pages.invoices.builders import COST_CENTERS, PRODUCTS


def _bar(qtbot) -> BulkBar:
    bar = BulkBar()
    qtbot.addWidget(bar)
    bar.set_catalog(
        [CodeItem(c, n) for c, n in PRODUCTS.items()],
        [CodeItem(c, n) for c, n in COST_CENTERS.items()],
    )
    bar.set_count(3)
    bar.show()
    return bar


def test_bulk_bar_labels_and_disabled_apply_without_a_choice(qtbot) -> None:
    bar = _bar(qtbot)

    assert bar.property("role") == "bulk-bar"
    assert bar.count_label.text() == "3 facturas seleccionadas"
    assert bar.product_combo.itemText(0) == strings.PLACEHOLDER_NO_CHANGE
    assert bar.cost_center_combo.itemText(0) == strings.PLACEHOLDER_NO_CHANGE
    assert bar.product_combo.codes() == ["P-PAPEL", "P-SERV"]
    assert bar.apply_button.text() == strings.ACTION_APPLY
    assert bar.apply_button.property("variant") == "primary"
    assert bar.apply_button.isEnabled() is False
    assert bar.clear_button.text() == strings.ACTION_CLEAR_SELECTION
    assert bar.choices() == (None, None)

    with qtbot.waitSignal(bar.clear_requested):
        bar.clear_button.click()


def test_bulk_bar_applies_the_chosen_values_and_resets(qtbot) -> None:
    bar = _bar(qtbot)

    bar.product_combo.activated.emit(bar.product_combo.row_for_code("P-SERV"))
    assert bar.apply_button.isEnabled() is True
    assert bar.choices() == ("P-SERV", None)

    with qtbot.waitSignal(bar.apply_requested) as blocker:
        bar.apply_button.click()
    assert blocker.args == ["P-SERV", None]

    bar.cost_center_combo.activated.emit(bar.cost_center_combo.row_for_code("CC-VEN"))
    assert bar.choices() == ("P-SERV", "CC-VEN")

    bar.reset()
    assert bar.choices() == (None, None)
    assert bar.apply_button.isEnabled() is False
    bar.set_count(1)
    assert bar.count_label.text() == "1 factura seleccionada"


def test_a_refresh_of_the_catalog_keeps_the_choices_already_made(qtbot) -> None:
    bar = _bar(qtbot)
    bar.product_combo.activated.emit(bar.product_combo.row_for_code("P-SERV"))
    bar.cost_center_combo.activated.emit(bar.cost_center_combo.row_for_code("CC-VEN"))

    # cada refresco de la pagina vuelve a entregar el catalogo
    bar.set_catalog(
        [CodeItem(c, n) for c, n in PRODUCTS.items()],
        [CodeItem(c, n) for c, n in COST_CENTERS.items()],
    )

    assert bar.choices() == ("P-SERV", "CC-VEN")
    assert bar.product_combo.currentText() == "P-SERV - Servicios"
    assert bar.apply_button.isEnabled() is True

    # un codigo que ya no existe en el catalogo no se puede aplicar
    bar.set_catalog(
        [CodeItem("P-PAPEL", PRODUCTS["P-PAPEL"])],
        [CodeItem(c, n) for c, n in COST_CENTERS.items()],
    )
    assert bar.choices() == (None, "CC-VEN")
    assert bar.apply_button.isEnabled() is True
