"""Document tree model (invoice -> lines) and its recursive filter proxy."""

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtGui import QColor, QIcon

from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.shared import strings
from contabilizador.ui.pages.invoices.model import (
    HEADERS,
    Column,
    DocumentFilterProxy,
    DocumentTreeModel,
    Role,
)
from contabilizador.ui.pages.invoices.rows import FIELD_COST_CENTER, FIELD_PRODUCT
from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets.code_combo import CodeItem
from tests.ui.factories import make_pending_document
from tests.ui.pages.invoices.builders import (
    COST_CENTERS,
    PRODUCTS,
    incomplete_document,
    ready_document,
    rows_for,
    unconfigured_document,
)

PRODUCT_ITEMS = [CodeItem(code, name) for code, name in PRODUCTS.items()]
COST_CENTER_ITEMS = [CodeItem(code, name) for code, name in COST_CENTERS.items()]


def _model(*documents) -> DocumentTreeModel:
    model = DocumentTreeModel()
    model.set_catalog(PRODUCT_ITEMS, COST_CENTER_ITEMS, {"900123456": ("P-PAPEL",)})
    model.set_documents(rows_for(*documents))
    return model


def test_tree_structure_invoices_with_their_lines(qapp) -> None:
    model = _model(ready_document(), incomplete_document())

    assert model.rowCount() == 2
    assert model.columnCount() == len(Column)
    first = model.index(0, 0)
    assert model.rowCount(first) == 2
    assert model.rowCount(model.index(0, 0, first)) == 0
    line = model.index(1, Column.PRODUCT, first)
    assert line.isValid()
    assert model.parent(line) == first
    assert model.parent(first) == QModelIndex()
    assert model.index(5, 0).isValid() is False
    assert [model.headerData(c, Qt.Orientation.Horizontal) for c in Column] == [
        HEADERS[c] for c in Column
    ]
    assert HEADERS[Column.STATUS] == strings.COLUMN_STATUS
    assert model.index_for_invoice(2) == model.index(1, 0)
    assert model.index_for_line(201) == model.index(1, 0, model.index(1, 0))
    assert model.index_for_invoice(99).isValid() is False
    assert model.invoice_at(line).invoice_id == 1
    assert model.invoice_at(first).invoice_id == 1
    line_row = model.line_at(line)
    assert line_row is not None and line_row.line_id == 101
    assert model.line_at(first) is None


def test_display_values_for_invoice_and_line_rows(qapp) -> None:
    model = _model(ready_document())
    invoice = model.index(0, 0)

    root = QModelIndex()

    def cell(column: Column, parent: QModelIndex = root, row: int = 0) -> str:
        return model.index(row, column, parent).data(Qt.ItemDataRole.DisplayRole)

    assert cell(Column.DOCUMENT) == "FEV-001001"
    assert cell(Column.SUPPLIER) == "COMERCIALIZADORA EJEMPLO S.A.S."
    assert cell(Column.ISSUE_DATE) == "31/08/2026"
    assert cell(Column.DUE_DATE) == "30/09/2026"
    assert cell(Column.QUANTITY) == "2 líneas"
    assert cell(Column.TOTAL) == "$ 160.700,33"
    # el nombre manda en la celda; el codigo queda en el tooltip
    assert cell(Column.PRODUCT) == "Papelería"
    assert cell(Column.COST_CENTER) == "Administración"
    assert cell(Column.STATUS) == strings.STATUS_READY

    # la descripcion de la linea va en la columna ancha (Proveedor), no en Documento
    assert cell(Column.DOCUMENT, invoice) == strings.line_label(1)
    assert cell(Column.SUPPLIER, invoice) == "RESMA PAPEL CARTA 75G"
    assert cell(Column.QUANTITY, invoice) == "3"
    assert cell(Column.TOTAL, invoice) == "$ 35.700"
    assert cell(Column.PRODUCT, invoice) == "Papelería"
    assert cell(Column.STATUS, invoice) == ""
    alignment = model.index(0, Column.TOTAL).data(Qt.ItemDataRole.TextAlignmentRole)
    assert alignment & Qt.AlignmentFlag.AlignRight
    tooltip = model.index(0, Column.DOCUMENT, invoice).data(Qt.ItemDataRole.ToolTipRole)
    assert tooltip == "3 a $ 10.000, IVA 19 %"
    assert model.index(0, Column.SUPPLIER).data(Qt.ItemDataRole.ToolTipRole) == (
        strings.supplier_tooltip("COMERCIALIZADORA EJEMPLO S.A.S.", "900123456")
    )
    assert model.index(0, Column.DOCUMENT).data(
        Qt.ItemDataRole.ToolTipRole
    ) == strings.document_tooltip(strings.FLAG_INVOICE, "30/09/2026")


def test_a_line_is_named_by_its_number_and_its_description_has_the_wide_column(qapp) -> None:
    model = _model(ready_document())
    invoice = model.index(0, 0)
    label = model.index(0, Column.DOCUMENT, invoice)
    description = model.index(0, Column.SUPPLIER, invoice)

    assert label.data(Qt.ItemDataRole.DisplayRole) == "Línea 1"
    assert label.data(Qt.ItemDataRole.ForegroundRole) == QColor(TOKENS.slate)
    assert model.index(1, Column.DOCUMENT, invoice).data(Qt.ItemDataRole.DisplayRole) == "Línea 2"
    assert description.data(Qt.ItemDataRole.DisplayRole) == "RESMA PAPEL CARTA 75G"
    # la celda puede elidir: el texto completo queda en el tooltip
    assert description.data(Qt.ItemDataRole.ToolTipRole) == "RESMA PAPEL CARTA 75G"
    assert description.data(Qt.ItemDataRole.ForegroundRole) is None


def test_choose_and_various_placeholders(qapp) -> None:
    model = _model(incomplete_document())
    invoice = model.index(0, 0)
    product = model.index(0, Column.PRODUCT)
    cost_center = model.index(0, Column.COST_CENTER)

    assert product.data(Qt.ItemDataRole.DisplayRole) == strings.VARIOUS
    assert product.data(Qt.ItemDataRole.ToolTipRole) == strings.editable_cell_tooltip(
        strings.various_values_tooltip(["P-SERV - Servicios"])
    )
    assert product.data(Qt.ItemDataRole.EditRole) is None
    assert cost_center.data(Qt.ItemDataRole.DisplayRole) == strings.ACTION_CHOOSE
    assert cost_center.data(Qt.ItemDataRole.ForegroundRole) == QColor(TOKENS.incomplete)
    # linea sin producto: tambien invita a elegir
    second_product = model.index(1, Column.PRODUCT, invoice)
    assert second_product.data(Qt.ItemDataRole.DisplayRole) == strings.ACTION_CHOOSE
    assert second_product.data(Qt.ItemDataRole.ForegroundRole) == QColor(TOKENS.incomplete)
    assert model.index(1, Column.STATUS, invoice).data(Qt.ItemDataRole.DisplayRole) == (
        "Falta el producto"
    )


def test_editable_cells_tell_that_a_click_changes_them(qapp) -> None:
    model = _model(ready_document(), incomplete_document())
    invoice = model.index(1, 0)

    # valor comun: el tooltip completa el nombre (la celda puede elidir) y dice que cambia
    filled = model.index(0, Column.COST_CENTER)
    assert filled.data(Qt.ItemDataRole.ToolTipRole) == (
        "CC-ADM - Administración\nHaz clic para cambiar"
    )
    assert strings.HINT_CLICK_TO_CHANGE == "Haz clic para cambiar"
    # vacia: invita a elegir (no "cambiar" algo que no hay)
    empty = model.index(1, Column.COST_CENTER)
    assert empty.data(Qt.ItemDataRole.ToolTipRole) == strings.HINT_CLICK_TO_CHOOSE
    line_empty = model.index(1, Column.PRODUCT, invoice)
    assert line_empty.data(Qt.ItemDataRole.ToolTipRole) == strings.HINT_CLICK_TO_CHOOSE
    # una celda que no se edita no promete nada
    assert model.index(0, Column.TOTAL).data(Qt.ItemDataRole.ToolTipRole) is None


def test_the_empty_role_marks_the_editable_cells_that_invite_to_choose(qapp) -> None:
    model = _model(ready_document(), incomplete_document())
    invoice = model.index(1, 0)

    assert model.index(1, Column.COST_CENTER).data(Role.IS_EMPTY) is True
    assert model.index(1, Column.PRODUCT, invoice).data(Role.IS_EMPTY) is True
    # "Varios" y los valores comunes no estan vacios; las demas columnas tampoco
    assert model.index(1, Column.PRODUCT).data(Role.IS_EMPTY) is False
    assert model.index(0, Column.COST_CENTER).data(Role.IS_EMPTY) is False
    assert model.index(0, Column.TOTAL).data(Role.IS_EMPTY) is False
    assert model.index(0, Column.COST_CENTER, model.index(0, 0)).data(Role.IS_EMPTY) is False


def test_roles_provenance_and_status(qapp) -> None:
    model = _model(ready_document(), unconfigured_document())
    invoice = model.index(0, 0)
    line_product = model.index(0, Column.PRODUCT, invoice)

    assert invoice.data(Role.IS_INVOICE) is True
    assert invoice.data(Role.INVOICE_ID) == 1
    assert invoice.data(Role.CUFE) == "cufe-1"
    assert invoice.data(Role.STATUS) == "ready"
    assert invoice.data(Role.PILL_TEXT) == strings.STATUS_READY
    assert invoice.data(Role.EXPORTABLE) is True
    assert invoice.data(Role.DOCUMENT_TYPE) == "FC"
    assert line_product.data(Role.IS_INVOICE) is False
    assert line_product.data(Role.LINE_ID) == 100
    assert line_product.data(Role.INVOICE_ID) == 1
    assert line_product.data(Role.SOURCE) == "memory"
    icon = line_product.data(Qt.ItemDataRole.DecorationRole)
    assert isinstance(icon, QIcon) and not icon.isNull()
    assert line_product.data(Qt.ItemDataRole.ToolTipRole) == (
        "P-PAPEL - Papelería\n" + strings.PROVENANCE_MEMORY + "\nHaz clic para cambiar"
    )

    blocked = model.index(1, 0)
    assert blocked.data(Role.STATUS) == "blocked"
    assert blocked.data(Role.PILL_TEXT) == strings.FLAG_UNCONFIGURED_SUPPLIER
    assert blocked.data(Role.EXPORTABLE) is False
    status_tip = model.index(1, Column.STATUS).data(Qt.ItemDataRole.ToolTipRole)
    assert status_tip == strings.problem_message("unconfigured_supplier", None, "800000001")


def test_only_product_and_cost_center_are_editable(qapp) -> None:
    model = _model(ready_document())
    invoice = model.index(0, 0)

    for column in Column:
        editable = bool(model.flags(model.index(0, column)) & Qt.ItemFlag.ItemIsEditable)
        assert editable == (column in (Column.PRODUCT, Column.COST_CENTER)), column
        line_editable = bool(
            model.flags(model.index(0, column, invoice)) & Qt.ItemFlag.ItemIsEditable
        )
        assert line_editable == editable, column


def test_set_data_on_a_line_emits_line_edited_and_updates_optimistically(qapp, qtbot) -> None:
    model = _model(incomplete_document())
    invoice = model.index(0, 0)
    cell = model.index(1, Column.PRODUCT, invoice)

    with qtbot.waitSignal(model.line_edited) as blocker:
        assert model.setData(cell, "P-PAPEL", Qt.ItemDataRole.EditRole) is True
    assert blocker.args == [201, FIELD_PRODUCT, "P-PAPEL"]
    assert cell.data(Qt.ItemDataRole.DisplayRole) == "Papelería"
    assert cell.data(Role.SOURCE) == "assigned"
    assert cell.data(Qt.ItemDataRole.DecorationRole) is None
    assert model.rows()[0].lines[1].product_code == "P-PAPEL"

    seen: list[object] = []
    model.line_edited.connect(lambda *args: seen.append(args))
    assert model.setData(cell, "P-PAPEL", Qt.ItemDataRole.EditRole) is True  # sin cambio
    assert model.setData(cell, "", Qt.ItemDataRole.EditRole) is False
    assert model.setData(cell, None, Qt.ItemDataRole.EditRole) is False
    assert seen == []


def test_set_data_on_an_invoice_applies_to_every_line(qapp, qtbot) -> None:
    model = _model(incomplete_document())
    invoice = model.index(0, 0)
    cell = model.index(0, Column.COST_CENTER)
    changes: list[tuple[int, int]] = []
    model.dataChanged.connect(
        lambda top, bottom, _roles=None: changes.append((top.row(), bottom.row()))
    )

    with qtbot.waitSignal(model.document_edited) as blocker:
        assert model.setData(cell, "CC-VEN", Qt.ItemDataRole.EditRole) is True

    assert blocker.args == [2, FIELD_COST_CENTER, "CC-VEN"]
    assert cell.data(Qt.ItemDataRole.DisplayRole) == "Ventas"
    lines = model.rows()[0].lines
    assert [line.cost_center_code for line in lines] == ["CC-VEN", "CC-VEN"]
    assert model.index(1, Column.COST_CENTER, invoice).data(Qt.ItemDataRole.DisplayRole) == "Ventas"
    assert changes  # la fila y sus lineas se repintan


def test_set_documents_keeps_structure_in_place_or_resets(qapp, qtbot) -> None:
    model = _model(ready_document(), incomplete_document())
    resets: list[str] = []
    model.modelReset.connect(lambda: resets.append("reset"))
    changes: list[str] = []
    model.dataChanged.connect(lambda *_: changes.append("changed"))

    # mismos ids: actualizacion en sitio (no se pierde expansion ni seleccion en la vista)
    same = rows_for(
        make_pending_document(
            invoice_id=1,
            cufe="cufe-1",
            mappings=(LineMapping("P-SERV", "CC-VEN"), LineMapping("P-SERV", "CC-VEN")),
        ),
        incomplete_document(),
    )
    assert model.set_documents(same) is False
    assert resets == []
    assert changes
    assert model.index(0, Column.PRODUCT).data(Qt.ItemDataRole.DisplayRole) == "Servicios"

    # otra estructura: reset completo
    assert model.set_documents(rows_for(incomplete_document())) is True
    assert resets == ["reset"]
    assert model.rowCount() == 1
    assert model.set_documents([]) is True
    assert model.rowCount() == 0


def test_editor_items_put_supplier_products_first(qapp) -> None:
    model = _model(ready_document())
    invoice = model.index(0, 0)

    preferred, rest = model.index(0, Column.PRODUCT).data(Role.EDITOR_ITEMS)
    assert [item.code for item in preferred] == ["P-PAPEL"]
    assert [item.code for item in rest] == ["P-SERV"]
    preferred, rest = model.index(1, Column.PRODUCT, invoice).data(Role.EDITOR_ITEMS)
    assert [item.code for item in preferred] == ["P-PAPEL"]
    preferred, rest = model.index(0, Column.COST_CENTER).data(Role.EDITOR_ITEMS)
    assert preferred == []
    assert [item.code for item in rest] == ["CC-ADM", "CC-VEN"]
    assert model.index(0, Column.TOTAL).data(Role.EDITOR_ITEMS) is None
    assert model.index(0, Column.PRODUCT).data(Role.FIELD) == FIELD_PRODUCT
    assert model.index(0, Column.COST_CENTER).data(Role.FIELD) == FIELD_COST_CENTER


def test_set_catalog_refreshes_names(qapp) -> None:
    model = DocumentTreeModel()
    model.set_documents(rows_for(ready_document()))
    cell = model.index(0, Column.PRODUCT)
    assert cell.data(Qt.ItemDataRole.DisplayRole) == "P-PAPEL"

    model.set_catalog(PRODUCT_ITEMS, COST_CENTER_ITEMS, {})

    assert cell.data(Qt.ItemDataRole.DisplayRole) == "Papelería"
    assert model.product_name("P-PAPEL") == "Papelería"
    assert model.has_products() and model.has_cost_centers()


# --- proxy ----------------------------------------------------------------------


def _proxy(*documents) -> tuple[DocumentTreeModel, DocumentFilterProxy]:
    model = _model(*documents)
    proxy = DocumentFilterProxy()
    proxy.setSourceModel(model)
    return model, proxy


def _visible(proxy: DocumentFilterProxy) -> dict[str, list[str]]:
    shown: dict[str, list[str]] = {}
    for row in range(proxy.rowCount()):
        invoice = proxy.index(row, 0)
        shown[invoice.data(Qt.ItemDataRole.DisplayRole)] = [
            proxy.index(line, Column.SUPPLIER, invoice).data(Qt.ItemDataRole.DisplayRole)
            for line in range(proxy.rowCount(invoice))
        ]
    return shown


def test_proxy_filters_invoices_by_chip_and_keeps_their_lines(qapp) -> None:
    _, proxy = _proxy(ready_document(), incomplete_document(), unconfigured_document())
    assert proxy.filter_key() == "all"
    assert len(_visible(proxy)) == 3

    proxy.set_filter("incomplete")

    shown = _visible(proxy)
    assert list(shown) == ["FEV-001002"]
    assert shown["FEV-001002"] == ["RESMA PAPEL CARTA 75G", "TONER IMPRESORA LASER"]
    assert proxy.mapToSource(proxy.index(0, 0)).data(Role.INVOICE_ID) == 2


def test_proxy_search_matches_supplier_or_a_line_description(qapp) -> None:
    _, proxy = _proxy(
        ready_document(),
        make_pending_document(
            invoice_id=5,
            cufe="cufe-5",
            supplier_name="PAPELERIA CENTRAL",
            supplier_nit="811000222",
            supplier_number="001005",
            mappings=(None, None),
        ),
    )

    proxy.set_search("central")
    shown = _visible(proxy)
    assert list(shown) == ["FEV-001005"]
    assert len(shown["FEV-001005"]) == 2  # la factura coincide: todas sus lineas se ven

    proxy.set_search("toner")
    shown = _visible(proxy)
    assert len(shown) == 2
    assert all(lines == ["TONER IMPRESORA LASER"] for lines in shown.values())

    proxy.set_search("811000222")
    assert len(_visible(proxy)) == 1
    proxy.set_search("")
    assert len(_visible(proxy)) == 2
    assert proxy.search_text() == ""


def test_proxy_does_not_refilter_while_editing(qapp) -> None:
    model, proxy = _proxy(incomplete_document())
    proxy.set_filter("incomplete")
    assert proxy.rowCount() == 1
    assert proxy.dynamicSortFilter() is False

    # la fila deja de estar "por completar" tras la edicion, pero sigue visible
    model.set_documents(
        rows_for(
            make_pending_document(
                invoice_id=2,
                cufe="cufe-2",
                mappings=(LineMapping("P-SERV", "CC-ADM"), LineMapping("P-SERV", "CC-ADM")),
            )
        )
    )
    assert proxy.rowCount() == 1

    proxy.refilter()
    assert proxy.rowCount() == 0


def test_tooltips_carry_the_full_text_of_elided_cells(qapp) -> None:
    model = _model(ready_document())
    invoice = model.index(0, 0)

    assert model.index(0, Column.PRODUCT).data(Qt.ItemDataRole.ToolTipRole) == (
        "P-PAPEL - Papelería\n" + strings.HINT_CLICK_TO_CHANGE
    )
    assert model.index(0, Column.COST_CENTER).data(Qt.ItemDataRole.ToolTipRole) == (
        "CC-ADM - Administración\n" + strings.HINT_CLICK_TO_CHANGE
    )
    assert model.index(0, Column.SUPPLIER).data(Qt.ItemDataRole.ToolTipRole) == (
        "COMERCIALIZADORA EJEMPLO S.A.S.\nNIT 900123456"
    )
    line = model.index(0, Column.COST_CENTER, invoice)
    assert line.data(Qt.ItemDataRole.ToolTipRole) == (
        f"CC-ADM - Administración\n{strings.PROVENANCE_MEMORY}\n{strings.HINT_CLICK_TO_CHANGE}"
    )
    credit_note = model.index(0, Column.DOCUMENT)
    assert credit_note.data(Qt.ItemDataRole.ToolTipRole).startswith(strings.FLAG_INVOICE)
