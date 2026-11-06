"""CatalogTableModel: code, name and the row action, natural order and an accent-free filter."""

import pytest
from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import QApplication

from contabilizador.shared import strings
from contabilizador.ui.pages.catalogs.model import ACTION_COLUMN, CatalogTableModel
from contabilizador.ui.pages.catalogs.rows import CatalogRow

ROWS = [
    CatalogRow("20", "Servicios técnicos"),
    CatalogRow("1001", "Papelería"),
    CatalogRow("3", "Aseo y cafetería"),
]


@pytest.fixture
def model(qapp: QApplication) -> CatalogTableModel:
    model = CatalogTableModel()
    model.set_rows(ROWS)
    return model


def cell(model: CatalogTableModel, row: int, column: int, role: int = Qt.ItemDataRole.DisplayRole):
    return model.index(row, column).data(role)


def test_headers_are_code_name_and_an_unlabelled_action_column(model: CatalogTableModel) -> None:
    assert model.columnCount() == 3
    assert ACTION_COLUMN == 2
    headers = [
        model.headerData(column, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
        for column in range(3)
    ]
    assert headers == [strings.COLUMN_CODE, strings.COLUMN_NAME, ""]


def test_headers_align_with_the_cells(model: CatalogTableModel) -> None:
    left = int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    right = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    for column, expected in ((0, left), (1, left), (ACTION_COLUMN, right)):
        header = model.headerData(
            column, Qt.Orientation.Horizontal, Qt.ItemDataRole.TextAlignmentRole
        )
        cell_alignment = model.index(0, column).data(Qt.ItemDataRole.TextAlignmentRole)
        assert header == cell_alignment == expected


def test_every_row_carries_the_edit_link(model: CatalogTableModel) -> None:
    for row in range(model.rowCount()):
        assert cell(model, row, ACTION_COLUMN) == strings.ACTION_EDIT
    assert cell(model, 0, 0) == "3"  # el enlace no cambia las otras celdas


def test_rows_are_ordered_naturally_by_code(model: CatalogTableModel) -> None:
    assert [cell(model, row, 0) for row in range(model.rowCount())] == ["3", "20", "1001"]
    assert cell(model, 2, 1) == "Papelería"


def test_cells_are_read_only_and_selectable(model: CatalogTableModel) -> None:
    flags = model.flags(model.index(0, 0))

    assert flags & Qt.ItemFlag.ItemIsSelectable
    assert flags & Qt.ItemFlag.ItemIsEnabled
    assert not flags & Qt.ItemFlag.ItemIsEditable


def test_tooltip_shows_code_and_name_for_long_names(model: CatalogTableModel) -> None:
    assert cell(model, 2, 1, Qt.ItemDataRole.ToolTipRole) == "1001 - Papelería"


def test_filter_matches_without_accents_and_updates_counts(model: CatalogTableModel) -> None:
    model.set_filter("papeleria")

    assert model.rowCount() == 1
    assert cell(model, 0, 0) == "1001"
    assert model.visible_count() == 1
    assert model.total_count() == 3


def test_clearing_the_filter_restores_every_row(model: CatalogTableModel) -> None:
    model.set_filter("zzz")
    assert model.rowCount() == 0
    assert model.total_count() == 3

    model.set_filter("")

    assert model.rowCount() == 3
    assert model.filter_text() == ""


def test_set_rows_keeps_the_active_filter(model: CatalogTableModel) -> None:
    model.set_filter("aseo")

    model.set_rows([*ROWS, CatalogRow("4", "Aseo industrial")])

    assert [cell(model, row, 0) for row in range(model.rowCount())] == ["3", "4"]


def test_row_lookup_by_code_only_finds_visible_rows(model: CatalogTableModel) -> None:
    assert model.row_of("20") == 1
    model.set_filter("papel")
    assert model.row_of("20") == -1
    assert model.row_of("1001") == 0
    row = model.row_at(0)
    assert row is not None
    assert row.code == "1001"
    assert model.row_at(5) is None


def test_model_is_flat(model: CatalogTableModel) -> None:
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.index(0, 0, QModelIndex()).isValid()
