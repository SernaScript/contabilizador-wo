"""SuppliersModel and its search proxy."""

import pytest
from PySide6.QtCore import QModelIndex, Qt

from contabilizador.shared import strings
from contabilizador.ui.pages.suppliers.model import (
    COL_ACTION,
    COL_DEFAULT,
    COL_PENDING,
    COL_PRODUCTS,
    COL_SUPPLIER,
    NIT_ROLE,
    STATUS_ROLE,
    SuppliersFilterProxy,
    SuppliersModel,
)
from contabilizador.ui.pages.suppliers.rows import SupplierRow

ROWS = [
    SupplierRow("900", "Zeta S.A.S.", configured=False, pending_invoices=2),
    SupplierRow("700", "Beta Ltda.", True, ("P-1", "P-2"), "P-1", (), 4),
    SupplierRow("600", "Gamma", True, ("P-9",), "P-9", ("P-9",), 0),
]
NAMES = {"P-1": "Papelería", "P-2": "Aseo"}


@pytest.fixture
def model(qapp) -> SuppliersModel:
    result = SuppliersModel()
    result.set_suppliers(ROWS, NAMES)
    return result


def cell(model: SuppliersModel, row: int, column: int, role: int = Qt.ItemDataRole.DisplayRole):
    return model.index(row, column).data(role)


def test_headers_follow_the_plan_columns(model: SuppliersModel) -> None:
    titles = [
        model.headerData(column, Qt.Orientation.Horizontal) for column in range(model.columnCount())
    ]

    assert titles == [
        strings.COLUMN_SUPPLIER_NAME,
        strings.COLUMN_SUPPLIER_PRODUCTS,
        strings.COLUMN_SUPPLIER_DEFAULT,
        strings.COLUMN_SUPPLIER_PENDING,
        "",
    ]
    assert model.rowCount() == 3
    assert model.rowCount(model.index(0, 0)) == 0  # tabla plana


def test_unconfigured_supplier_says_so_where_the_products_would_be(model: SuppliersModel) -> None:
    assert cell(model, 0, COL_SUPPLIER) == "Zeta S.A.S."
    assert cell(model, 0, COL_SUPPLIER, NIT_ROLE) == "900"
    assert cell(model, 0, COL_PRODUCTS) == strings.SUPPLIERS_UNCONFIGURED_TITLE
    assert cell(model, 0, COL_PRODUCTS, STATUS_ROLE) == "blocked"
    assert cell(model, 0, COL_DEFAULT) == ""
    assert cell(model, 0, COL_PENDING) == "2"
    assert cell(model, 0, COL_ACTION) == strings.ACTION_CONFIGURE


def test_configured_supplier_lists_codes_default_and_edit_action(model: SuppliersModel) -> None:
    assert cell(model, 1, COL_PRODUCTS) == strings.supplier_products_count(2)
    assert cell(model, 1, COL_PRODUCTS, STATUS_ROLE) is None
    assert cell(model, 1, COL_DEFAULT) == "P-1 - Papelería"
    assert cell(model, 1, COL_PENDING) == "4"
    assert cell(model, 1, COL_ACTION) == strings.ACTION_EDIT
    tooltip = cell(model, 1, COL_PRODUCTS, Qt.ItemDataRole.ToolTipRole)
    assert tooltip == "P-1 - Papelería\nP-2 - Aseo"


def test_products_that_left_the_catalog_are_flagged_and_explained(model: SuppliersModel) -> None:
    assert cell(model, 2, COL_PRODUCTS) == strings.SUPPLIER_PRODUCT_MISSING_PILL
    assert cell(model, 2, COL_PRODUCTS, STATUS_ROLE) == "blocked"
    assert cell(model, 2, COL_PRODUCTS, Qt.ItemDataRole.ToolTipRole) == (
        strings.supplier_missing_products_tooltip(["P-9"])
    )
    assert cell(model, 2, COL_DEFAULT) == "P-9"  # sin nombre: ya no esta en el catalogo


def test_pending_column_is_right_aligned(model: SuppliersModel) -> None:
    right = Qt.AlignmentFlag.AlignRight.value
    alignment = cell(model, 1, COL_PENDING, Qt.ItemDataRole.TextAlignmentRole)
    header = model.headerData(
        COL_PENDING, Qt.Orientation.Horizontal, Qt.ItemDataRole.TextAlignmentRole
    )

    assert isinstance(alignment, int)
    assert isinstance(header, int)
    assert alignment & right
    assert header & right


def test_supplier_cell_tooltip_repeats_name_and_nit(model: SuppliersModel) -> None:
    tooltip = cell(model, 1, COL_SUPPLIER, Qt.ItemDataRole.ToolTipRole)

    assert tooltip == f"Beta Ltda.\n{strings.COLUMN_SUPPLIER_NIT} 700"


def test_row_lookup_by_nit(model: SuppliersModel) -> None:
    assert model.row_for_nit("700") == 1
    assert model.row_for_nit("000") == -1
    assert model.supplier_at(1).name == "Beta Ltda."
    assert model.index(1, COL_SUPPLIER).data(NIT_ROLE) == "700"


def test_invalid_index_has_no_data(model: SuppliersModel) -> None:
    assert model.data(QModelIndex()) is None


def test_set_suppliers_resets_the_rows(model: SuppliersModel) -> None:
    model.set_suppliers([ROWS[1]], NAMES)

    assert model.rowCount() == 1
    assert cell(model, 0, COL_SUPPLIER, NIT_ROLE) == "700"


def test_proxy_filters_by_nit_or_name_without_reordering(model: SuppliersModel) -> None:
    proxy = SuppliersFilterProxy()
    proxy.setSourceModel(model)

    assert proxy.rowCount() == 3
    proxy.set_query("BETA")
    assert [proxy.index(row, COL_SUPPLIER).data(NIT_ROLE) for row in range(proxy.rowCount())] == [
        "700"
    ]
    proxy.set_query("6")
    assert [proxy.index(row, COL_SUPPLIER).data(NIT_ROLE) for row in range(proxy.rowCount())] == [
        "600"
    ]
    proxy.set_query("")
    assert [proxy.index(row, COL_SUPPLIER).data(NIT_ROLE) for row in range(proxy.rowCount())] == [
        "900",
        "700",
        "600",
    ]
