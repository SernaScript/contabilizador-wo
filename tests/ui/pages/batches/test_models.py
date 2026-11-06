"""Batch tables: models, status roles and the delegate that paints the pill."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTableView

from contabilizador.shared import strings
from contabilizador.ui.pages.batches.delegates import StatusPillDelegate
from contabilizador.ui.pages.batches.models import (
    STATUS_ROLE,
    BatchDocumentsModel,
    BatchesTableModel,
)
from contabilizador.ui.pages.batches.rows import batch_rows
from contabilizador.ui.theme import STATUS_STYLES, TOKENS
from tests.ui.pages.batches.builders import FC, NC, doc, make_batch

BATCHES = [
    make_batch(3, doc("c", FC, 5750), doc("d", NC, 12, released=True)),
    make_batch(2, doc("b", FC, 5740), doc("e", FC, 5741), voided=True, reused=True),
    make_batch(1, doc("a", FC, 5731)),
]


def cell(model, row: int, column: int, role: int = Qt.ItemDataRole.DisplayRole):
    return model.index(row, column).data(role)


@pytest.fixture
def batches_model(qapp: QApplication) -> BatchesTableModel:
    model = BatchesTableModel()
    model.set_rows(batch_rows(BATCHES))
    return model


@pytest.fixture
def documents_model(qapp: QApplication) -> BatchDocumentsModel:
    model = BatchDocumentsModel()
    model.set_rows(batch_rows(BATCHES)[0].documents)
    return model


# --- lotes ------------------------------------------------------------------------


def test_batches_columns_and_cells(batches_model: BatchesTableModel) -> None:
    headers = [
        batches_model.headerData(c, Qt.Orientation.Horizontal)
        for c in range(batches_model.columnCount())
    ]
    assert headers == [
        strings.COLUMN_BATCH_ID,
        strings.COLUMN_BATCH_DATE,
        strings.COLUMN_BATCH_RANGES,
        strings.COLUMN_BATCH_DOCUMENTS,
        strings.COLUMN_BATCH_STATUS,
    ]
    assert cell(batches_model, 0, 0) == "3"
    assert cell(batches_model, 0, 2) == "FC 5750, NC 12"
    assert cell(batches_model, 0, 3) == "2"
    assert cell(batches_model, 0, 4) == strings.BATCH_STATUS_PARTIAL
    assert cell(batches_model, 2, 4) == strings.BATCH_STATUS_EXPORTED


def test_status_column_exposes_the_pill_to_the_delegate(batches_model: BatchesTableModel) -> None:
    assert cell(batches_model, 0, 4, STATUS_ROLE) == ("incomplete", strings.BATCH_STATUS_PARTIAL)
    assert cell(batches_model, 1, 4, STATUS_ROLE) == (
        "archived",
        strings.BATCH_STATUS_VOIDED_RETURNED,
    )
    assert cell(batches_model, 0, 0, STATUS_ROLE) is None


def test_tooltips_complete_what_the_cells_elide(batches_model: BatchesTableModel) -> None:
    assert cell(batches_model, 0, 4, Qt.ItemDataRole.ToolTipRole) == strings.batch_partial_tooltip(
        1, 2
    )
    assert cell(batches_model, 0, 2, Qt.ItemDataRole.ToolTipRole) == "FC 5750, NC 12"


def test_voided_rows_are_muted_and_counts_align_right(batches_model: BatchesTableModel) -> None:
    muted = cell(batches_model, 1, 0, Qt.ItemDataRole.ForegroundRole)
    assert QColor(muted).name().upper() == TOKENS.slate
    assert cell(batches_model, 0, 0, Qt.ItemDataRole.ForegroundRole) is None
    assert cell(batches_model, 0, 3, Qt.ItemDataRole.TextAlignmentRole) & int(
        Qt.AlignmentFlag.AlignRight
    )


def test_batch_lookup_by_id(batches_model: BatchesTableModel) -> None:
    assert batches_model.row_of(2) == 1
    assert batches_model.row_of(99) == -1
    row = batches_model.row_at(0)
    assert row is not None
    assert row.batch_id == 3
    assert batches_model.row_at(7) is None


# --- facturas del lote ------------------------------------------------------------


def test_document_columns_and_cells(documents_model: BatchDocumentsModel) -> None:
    headers = [
        documents_model.headerData(c, Qt.Orientation.Horizontal)
        for c in range(documents_model.columnCount())
    ]
    assert headers == [
        strings.COLUMN_BATCH_CONSECUTIVE,
        strings.COLUMN_BATCH_DOCUMENT,
        strings.COLUMN_NIT,
        strings.COLUMN_SUPPLIER,
        strings.COLUMN_ISSUE_DATE,
        strings.COLUMN_BATCH_STATUS,
    ]
    assert cell(documents_model, 0, 0) == "FC 5750"
    assert cell(documents_model, 0, 1) == "FEV-C"
    assert cell(documents_model, 0, 2) == "900123456"
    assert cell(documents_model, 0, 3) == "COMERCIALIZADORA EJEMPLO S.A.S."
    assert cell(documents_model, 0, 4) == "31/08/2026"


def test_only_released_documents_show_a_pill_and_cannot_be_selected(
    documents_model: BatchDocumentsModel,
) -> None:
    assert cell(documents_model, 0, 5, STATUS_ROLE) is None
    assert cell(documents_model, 1, 5, STATUS_ROLE) == ("archived", strings.BATCH_DOCUMENT_RELEASED)
    active_flags = documents_model.flags(documents_model.index(0, 0))
    released_flags = documents_model.flags(documents_model.index(1, 0))
    assert active_flags & Qt.ItemFlag.ItemIsSelectable
    assert not released_flags & Qt.ItemFlag.ItemIsSelectable
    assert released_flags & Qt.ItemFlag.ItemIsEnabled


def test_released_documents_are_muted(documents_model: BatchDocumentsModel) -> None:
    assert QColor(cell(documents_model, 1, 0, Qt.ItemDataRole.ForegroundRole)).name().upper() == (
        TOKENS.slate
    )
    assert cell(documents_model, 0, 0, Qt.ItemDataRole.ForegroundRole) is None


def test_document_lookup_by_cufe(documents_model: BatchDocumentsModel) -> None:
    assert documents_model.row_of("d") == 1
    assert documents_model.row_of("zzz") == -1
    row = documents_model.row_at(0)
    assert row is not None
    assert row.cufe == "c"


def test_supplier_tooltip_includes_the_nit(documents_model: BatchDocumentsModel) -> None:
    tip = cell(documents_model, 0, 3, Qt.ItemDataRole.ToolTipRole)
    assert "900123456" in tip
    assert "COMERCIALIZADORA EJEMPLO S.A.S." in tip


# --- delegado de la pastilla --------------------------------------------------------


def test_delegate_paints_the_status_pill_and_sizes_the_column(qtbot, batches_model) -> None:
    table = QTableView()
    qtbot.addWidget(table)
    table.setModel(batches_model)
    delegate = StatusPillDelegate(table)
    table.setItemDelegateForColumn(4, delegate)
    table.resize(900, 300)
    table.show()
    index = batches_model.index(1, 4)

    option = QStyleOptionViewItem()
    option.font = table.font()
    size = delegate.sizeHint(option, index)
    assert size.width() > 120  # texto largo + icono + margenes
    rect = table.visualRect(index)
    image = table.viewport().grab().toImage()
    pill_bg = QColor(STATUS_STYLES["archived"].bg)
    sample = image.pixelColor(rect.left() + 12, rect.center().y())
    assert sample.name() == pill_bg.name()
