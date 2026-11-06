"""Item delegates of the document tree: searchable code editor, status pill, type badge."""

from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTreeView

from contabilizador.shared import strings
from contabilizador.ui.pages.invoices.delegates import (
    CELL_PADDING,
    CodeDelegate,
    DocumentDelegate,
    StatusDelegate,
    SupplierDelegate,
    badge_size,
    status_column_width,
)
from contabilizador.ui.pages.invoices.model import Column, DocumentFilterProxy, DocumentTreeModel
from contabilizador.ui.pages.invoices.rows import FIELD_PRODUCT
from contabilizador.ui.theme import STATUS_STYLES, TOKENS
from contabilizador.ui.widgets.code_combo import CodeCombo, CodeItem
from contabilizador.ui.widgets.status_pill import status_pill_size
from tests.ui.pages.invoices.builders import (
    COST_CENTERS,
    PRODUCTS,
    incomplete_document,
    ready_document,
    rows_for,
)


def _tree(qtbot, *documents, catalog: bool = True) -> tuple[QTreeView, DocumentTreeModel]:
    model = DocumentTreeModel()
    if catalog:
        model.set_catalog(
            [CodeItem(c, n) for c, n in PRODUCTS.items()],
            [CodeItem(c, n) for c, n in COST_CENTERS.items()],
            {"900123456": ("P-PAPEL",)},
        )
    model.set_documents(rows_for(*documents))
    proxy = DocumentFilterProxy()
    proxy.setSourceModel(model)
    tree = QTreeView()
    qtbot.addWidget(tree)
    tree.setModel(proxy)
    tree.setItemDelegateForColumn(Column.PRODUCT, CodeDelegate(tree))
    tree.setItemDelegateForColumn(Column.COST_CENTER, CodeDelegate(tree))
    tree.expandAll()
    tree.show()
    return tree, model


def test_code_delegate_opens_a_searchable_combo_with_supplier_products_first(qtbot) -> None:
    tree, _model = _tree(qtbot, ready_document())
    proxy = tree.model()
    invoice = proxy.index(0, 0)
    cell = proxy.index(1, Column.PRODUCT, invoice)

    tree.edit(cell)

    editor = tree.findChild(CodeCombo)
    assert editor is not None
    assert editor.codes() == ["P-PAPEL", "P-SERV"]
    assert editor.is_separator(1)
    assert editor.current_code() == "P-PAPEL"


def test_code_delegate_commits_on_choice_and_closes_the_editor(qtbot) -> None:
    tree, model = _tree(qtbot, incomplete_document())
    proxy = tree.model()
    cell = proxy.index(1, Column.PRODUCT, proxy.index(0, 0))
    tree.edit(cell)
    editor = tree.findChild(CodeCombo)
    assert editor is not None
    assert editor.current_code() is None

    with qtbot.waitSignal(model.line_edited, timeout=2000) as blocker:
        editor.activated.emit(editor.row_for_code("P-SERV"))

    assert blocker.args == [201, FIELD_PRODUCT, "P-SERV"]
    qtbot.waitUntil(lambda: tree.findChild(CodeCombo) is None, timeout=2000)
    assert cell.data(Qt.ItemDataRole.DisplayRole) == "Servicios"


def test_code_delegate_on_an_invoice_row_edits_the_common_value(qtbot) -> None:
    tree, model = _tree(qtbot, incomplete_document())
    proxy = tree.model()
    cell = proxy.index(0, Column.COST_CENTER)
    tree.edit(cell)
    editor = tree.findChild(CodeCombo)
    assert editor is not None
    assert editor.codes() == ["CC-ADM", "CC-VEN"]

    with qtbot.waitSignal(model.document_edited, timeout=2000) as blocker:
        editor.activated.emit(editor.row_for_code("CC-VEN"))

    assert blocker.args == [2, "cost_center", "CC-VEN"]


def test_code_delegate_without_catalog_refuses_to_edit_and_tells_which(qtbot) -> None:
    tree, _model = _tree(qtbot, incomplete_document(), catalog=False)
    proxy = tree.model()
    delegate = tree.itemDelegateForColumn(Column.PRODUCT)
    assert isinstance(delegate, CodeDelegate)

    with qtbot.waitSignal(delegate.catalog_missing, timeout=2000) as blocker:
        tree.edit(proxy.index(0, Column.PRODUCT))

    assert blocker.args == [FIELD_PRODUCT]
    assert tree.findChild(CodeCombo) is None


def _paint(delegate, index: QModelIndex, width: int = 160, height: int = 28) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(TOKENS.paper))
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, width, height)
    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()
    return image


def test_status_delegate_paints_the_pill_for_invoice_rows_only(qtbot) -> None:
    tree, _model = _tree(qtbot, ready_document())
    proxy = tree.model()
    delegate = StatusDelegate(tree)
    invoice_cell = proxy.index(0, Column.STATUS)
    line_cell = proxy.index(0, Column.STATUS, proxy.index(0, 0))

    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 160, 28)
    wanted = status_pill_size("ready", strings.STATUS_READY, tree.font())
    assert delegate.sizeHint(option, invoice_cell).width() >= wanted.width()

    painted = _paint(delegate, invoice_cell)
    assert painted.pixelColor(12, 14).name().upper() == STATUS_STYLES["ready"].bg
    line_painted = _paint(delegate, line_cell)
    assert line_painted.pixelColor(12, 14).name().upper() == TOKENS.paper


def test_document_delegate_paints_the_type_badge_before_the_label(qtbot) -> None:
    tree, _model = _tree(qtbot, ready_document())
    proxy = tree.model()
    delegate = DocumentDelegate(tree)
    invoice_cell = proxy.index(0, Column.DOCUMENT)
    line_cell = proxy.index(0, Column.DOCUMENT, proxy.index(0, 0))

    badge = badge_size("FC", tree.font())
    assert badge.width() > 0
    # se muestrea el relleno del badge (antes de las letras), no el trazo del texto
    painted = _paint(delegate, invoice_cell)
    assert painted.pixelColor(CELL_PADDING, 14).name().upper() == STATUS_STYLES["archived"].bg
    line_painted = _paint(delegate, line_cell)
    assert line_painted.pixelColor(CELL_PADDING, 14).name().upper() == TOKENS.paper
    assert delegate.sizeHint(QStyleOptionViewItem(), invoice_cell).width() > badge.width()


def _line_tree(qtbot, *documents) -> tuple[QTreeView, DocumentTreeModel]:
    """Tree with the delegates and widths the page uses, every invoice expanded."""
    tree, model = _tree(qtbot, *documents)
    tree.setItemDelegateForColumn(Column.DOCUMENT, DocumentDelegate(tree))
    tree.setItemDelegateForColumn(Column.SUPPLIER, SupplierDelegate(tree))
    tree.resize(700, 300)
    tree.setColumnWidth(Column.DOCUMENT, 140)
    tree.setColumnWidth(Column.SUPPLIER, 140)
    tree.expandAll()
    QApplication.processEvents()
    return tree, model


def _ink(image: QImage, rect: QRect) -> int:
    """Pixels of the middle of ``rect`` that are not the row background (the text is
    centered; the edges can hold the row border when a theme is active)."""
    inner = rect.adjusted(2, 5, -2, -5)
    background = image.pixelColor(inner.left(), inner.top()).name()
    return sum(
        1
        for x in range(inner.left(), inner.right() + 1)
        for y in range(inner.top(), inner.bottom() + 1)
        if image.pixelColor(x, y).name() != background
    )


def test_a_line_reads_across_documento_and_proveedor(qtbot) -> None:
    tree, _model = _line_tree(qtbot, ready_document())
    proxy = tree.model()
    line = proxy.index(0, 0, proxy.index(0, 0))  # "RESMA PAPEL CARTA 75G", 21 caracteres
    document = tree.visualRect(line.siblingAtColumn(Column.DOCUMENT))
    supplier = tree.visualRect(line.siblingAtColumn(Column.SUPPLIER))

    image = tree.viewport().grab().toImage()

    # "Línea 1" y la primera parte de la descripcion caben en Documento; el resto sigue en
    # Proveedor, que en una linea no tiene nada propio que mostrar
    assert _ink(image, document) > 0
    assert _ink(image, supplier) > 0


def test_a_line_keeps_its_text_when_only_the_supplier_cell_is_repainted(qtbot) -> None:
    tree, _model = _line_tree(qtbot, ready_document())
    proxy = tree.model()
    line = proxy.index(0, 0, proxy.index(0, 0))
    supplier = tree.visualRect(line.siblingAtColumn(Column.SUPPLIER))

    # pasar el puntero de una celda a otra repinta una sola: el texto no queda a medias
    partial = tree.viewport().grab(supplier).toImage()

    assert _ink(partial, partial.rect()) > 0


def test_a_short_description_leaves_the_supplier_cell_empty(qtbot) -> None:
    tree, _model = _line_tree(qtbot, ready_document())
    tree.setColumnWidth(Column.DOCUMENT, 400)
    QApplication.processEvents()
    proxy = tree.model()
    line = proxy.index(0, 0, proxy.index(0, 0))
    supplier = tree.visualRect(line.siblingAtColumn(Column.SUPPLIER))

    image = tree.viewport().grab().toImage()

    assert _ink(image, supplier) == 0


def test_invoice_rows_keep_the_supplier_name_in_its_own_cell(qtbot) -> None:
    tree, _model = _line_tree(qtbot, ready_document())
    proxy = tree.model()
    supplier = tree.visualRect(proxy.index(0, Column.SUPPLIER))

    image = tree.viewport().grab().toImage()

    assert _ink(image, supplier) > 0


def test_the_status_column_is_wide_enough_for_the_longest_pill(qtbot) -> None:
    tree, _model = _tree(qtbot, ready_document())
    longest = max(
        status_pill_size("blocked", text, tree.font()).width()
        for text in strings.PILL_LABELS.values()
    )

    assert status_column_width(tree.font()) == longest + 2 * CELL_PADDING
