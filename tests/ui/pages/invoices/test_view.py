"""Facturas view (presentational): header, toolbar, tree, detail, bulk bar, footer,
overlays and keyboard. It receives data and emits signals; no use case is called."""

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QLabel

from contabilizador.exports.domain.readiness import Readiness
from contabilizador.invoices.application.list_pending_documents import PendingDocuments
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.shared import strings
from contabilizador.ui import fonts, icons
from contabilizador.ui.pages.invoices.delegates import CELL_PADDING, CHEVRON_SIZE
from contabilizador.ui.pages.invoices.model import Column, DocumentTreeModel, Role
from contabilizador.ui.pages.invoices.rows import (
    FIELD_COST_CENTER,
    FIELD_PRODUCT,
    FILTER_KEYS,
    PageSummary,
    build_rows,
    summarize_page,
)
from contabilizador.ui.pages.invoices.view import (
    COLUMN_FLOORS,
    COLUMN_WIDTHS,
    FOLDABLE_COLUMNS,
    SUPPLIER_MIN_WIDTH,
    InvoicesView,
    plan_columns,
)
from contabilizador.ui.theme import PAGE_MARGIN, TOKENS, apply_theme
from contabilizador.ui.widgets.code_combo import CodeCombo, CodeItem
from contabilizador.ui.widgets.status_pill import status_pill_size
from tests.ui.factories import make_pending_document
from tests.ui.pages.invoices.builders import (
    COST_CENTERS,
    PRODUCTS,
    assess,
    incomplete_document,
    make_preview,
    mismatch_document,
    ready_document,
    rows_for,
    unconfigured_document,
)

CATALOG = (
    [CodeItem(c, n) for c, n in PRODUCTS.items()],
    [CodeItem(c, n) for c, n in COST_CENTERS.items()],
)


def _summary(*pending) -> PageSummary:
    preview = make_preview(assess(p) for p in pending)
    return summarize_page(build_rows(PendingDocuments(tuple(pending)), preview), preview)


def _view(qtbot, *pending) -> tuple[InvoicesView, DocumentTreeModel]:
    model = DocumentTreeModel()
    model.set_catalog(*CATALOG, {"900123456": ("P-PAPEL",)})
    model.set_documents(rows_for(*pending))
    view = InvoicesView()
    qtbot.addWidget(view)
    view.resize(1280, 820)
    view.set_model(model)
    view.set_catalog(*CATALOG)
    view.update_summary(_summary(*pending))
    view.show()
    return view, model


def _select(view: InvoicesView, *invoice_ids: int) -> None:
    view.select_invoices(list(invoice_ids))


def _detail_id(view: InvoicesView) -> int | None:
    invoice = view.detail.invoice()
    return invoice.invoice_id if invoice is not None else None


def test_chrome_and_empty_state(qtbot) -> None:
    view, _model = _view(qtbot)

    assert view.title_label.text() == strings.INVOICES_PAGE_TITLE
    # el stepper ya dice para que sirve la pagina: sin subtitulo que se parta en dos lineas
    assert [
        label for label in view.findChildren(QLabel) if label.property("role") == "purpose"
    ] == []
    assert view.stepper.count() == 3
    assert view.stepper.state(0) == "current"
    assert view.import_button.main_button.text() == strings.ACTION_IMPORT
    assert [a.text() for a in view.import_button.menu.actions()] == [
        strings.ACTION_IMPORT_FILES_MENU,
        strings.ACTION_IMPORT_FOLDER_MENU,
    ]
    assert view.chips.keys() == list(FILTER_KEYS)
    assert view.chips.chip("all").text().startswith(strings.FILTER_ALL)
    assert view.chips.chip("unconfigured").text().startswith(strings.FILTER_UNCONFIGURED)
    assert view.empty_state.isVisible()
    assert view.empty_state.action_button.text() == strings.ACTION_CHOOSE_FILES
    assert not view.tree.isVisible()
    assert not view.readiness.isVisible()
    assert not view.banner.isVisible()
    assert not view.bulk_bar.isVisible()

    with qtbot.waitSignal(view.import_files_requested):
        view.import_button.main_button.click()
    with qtbot.waitSignal(view.import_files_requested):
        view.empty_state.action_button.click()
    with qtbot.waitSignal(view.import_folder_requested):
        view.import_button.menu.actions()[1].trigger()


def test_summary_feeds_chips_footer_banner_and_stepper(qtbot) -> None:
    view, _model = _view(
        qtbot, ready_document(), incomplete_document(), unconfigured_document(), mismatch_document()
    )

    assert view.tree.isVisible()
    assert not view.empty_state.isVisible()
    assert view.readiness.isVisible()
    assert view.chips.chip("all").text() == f"{strings.FILTER_ALL} (4)"
    assert view.chips.chip("ready").text() == f"{strings.FILTER_READY} (1)"
    assert view.chips.chip("incomplete").text() == f"{strings.FILTER_INCOMPLETE} (1)"
    assert view.readiness.counts() == {"ready": 1, "mismatch": 1, "incomplete": 1, "blocked": 1}
    # el boton promete lo que sale sin confirmar el descuadre: la lista, no la lista + el descuadre
    assert view.readiness.cta_button.text() == strings.export_cta(1)
    # el chip y la leyenda del pie cuentan lo mismo bajo las mismas palabras
    assert view.chips.chip("incomplete").text() == f"{strings.FILTER_INCOMPLETE} (1)"
    assert view.readiness.segment_label("incomplete").text() == "1 por completar"
    assert view.banner.isVisible()
    assert view.banner.text() == strings.unconfigured_suppliers_banner(1, 1)
    assert view.banner.action_button.text() == strings.configure_pending_action(1)
    assert view.stepper.state(0) == "done"
    assert view.stepper.state(1) == "current"
    assert view.proxy.rowCount() == 4

    with qtbot.waitSignal(view.configure_suppliers_requested):
        view.banner.action_button.click()
    with qtbot.waitSignal(view.export_requested):
        view.readiness.cta_button.click()

    view.update_summary(_summary(ready_document(), mismatch_document()))
    assert view.stepper.state(2) == "current"
    assert not view.banner.isVisible()


def test_selection_drives_bulk_bar_detail_and_footer(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document(), mismatch_document())
    assert view.detail.invoice() is None

    _select(view, 1)
    assert view.selected_invoice_ids() == [1]
    assert view.selected_cufes() == ["cufe-1"]
    assert not view.bulk_bar.isVisible()
    assert _detail_id(view) == 1
    assert view.readiness.cta_button.text() == strings.export_selected_cta(1)
    assert view.readiness.caption_label.text() == strings.selection_caption(1, 1)

    _select(view, 1, 2)
    assert view.bulk_bar.isVisible()
    assert view.bulk_bar.count_label.text() == strings.selected_invoices(2)
    assert view.selected_invoice_ids() == [1, 2]
    # solo la lista cuenta para el CTA (la 2 esta por completar)
    assert view.readiness.cta_button.text() == strings.export_selected_cta(1)
    assert view.readiness.caption_label.text() == strings.selection_caption(2, 1)

    view.bulk_bar.product_combo.activated.emit(view.bulk_bar.product_combo.row_for_code("P-SERV"))
    with qtbot.waitSignal(view.bulk_apply_requested) as blocker:
        view.bulk_bar.apply_button.click()
    assert blocker.args == [[1, 2], "P-SERV", None]
    assert view.bulk_bar.choices() == (None, None)

    view.clear_selection()
    assert view.selected_invoice_ids() == []
    assert not view.bulk_bar.isVisible()
    assert view.readiness.cta_button.text() == strings.export_cta(1)
    assert view.readiness.caption_label.text() == strings.readiness_caption(2, 3)

    # elegir una linea muestra el detalle de su factura
    line = view.proxy.index(0, 0, view.proxy.index(1, 0))
    view.tree.expandAll()
    view.tree.setCurrentIndex(line)
    assert _detail_id(view) == 2
    assert view.selected_invoice_ids() == [2]


def test_the_banner_says_how_many_invoices_the_suppliers_hold_and_counts_its_button(
    qtbot,
) -> None:
    same_supplier = unconfigured_document(invoice_id=5, cufe="cufe-5", supplier_number="001005")
    view, _model = _view(qtbot, unconfigured_document(), same_supplier)

    # un proveedor retiene dos facturas: la consecuencia va en la frase
    assert view.banner.text() == "1 proveedor sin configurar bloquea 2 facturas."
    assert view.banner.action_button.text() == "Configurar proveedor"

    another = make_pending_document(
        invoice_id=6,
        cufe="cufe-6",
        supplier_configured=False,
        mappings=(None, None),
        supplier_nit="900555666",
        supplier_name="OTRO PROVEEDOR",
        supplier_number="001006",
    )
    view.update_summary(_summary(unconfigured_document(), same_supplier, another))
    assert view.banner.text() == "2 proveedores sin configurar bloquean 3 facturas."
    assert view.banner.action_button.text() == "Configurar proveedores"
    # el chip cuenta las mismas facturas que el aviso
    assert view.chips.chip("unconfigured").text() == f"{strings.FILTER_UNCONFIGURED} (3)"


def test_the_footer_does_not_blame_a_supplier_for_a_code_that_left_the_catalog(qtbot) -> None:
    gone = make_pending_document(
        invoice_id=7,
        cufe="cufe-7",
        supplier_number="001007",
        mappings=(LineMapping("P-GONE", "CC-ADM"), LineMapping("P-GONE", "CC-ADM")),
    )
    view, _model = _view(qtbot, ready_document(), unconfigured_document())
    assert view.readiness.segment_label("blocked").text() == "1 con proveedor sin configurar"

    view, _model = _view(qtbot, ready_document(), unconfigured_document(), gone)

    # el proveedor de la 7 esta configurado: lo que la bloquea es el producto que ya no existe
    assert view.readiness.counts() == {"ready": 1, "blocked": 2}
    assert view.readiness.segment_label("blocked").text() == "2 bloqueadas"
    assert view.chips.chip("unconfigured").text() == f"{strings.FILTER_UNCONFIGURED} (1)"

    # la seleccion lleva su propio criterio
    _select(view, 1, 3)
    assert view.readiness.segment_label("blocked").text() == "1 con proveedor sin configurar"
    _select(view, 1, 7)
    assert view.readiness.segment_label("blocked").text() == "1 bloqueada"


def test_the_footer_describes_the_selection_not_the_whole_list(qtbot) -> None:
    view, _model = _view(
        qtbot,
        ready_document(),
        incomplete_document(),
        unconfigured_document(),
        mismatch_document(),
    )
    footer = view.readiness
    everything = {"ready": 1, "mismatch": 1, "incomplete": 1, "blocked": 1}
    assert footer.bar.counts() == everything

    # una lista seleccionada: ni la barra, ni la leyenda, ni la linea de abajo hablan de las otras
    _select(view, 1)
    assert footer.bar.counts() == {"ready": 1, "mismatch": 0, "incomplete": 0, "blocked": 0}
    assert footer.segment_label("ready").text() == "1 lista"
    assert not footer.legend_item("mismatch").isVisibleTo(footer)
    assert not footer.legend_item("incomplete").isVisibleTo(footer)
    assert not footer.legend_item("blocked").isVisibleTo(footer)
    assert not footer.secondary_label.isVisibleTo(footer)
    assert footer.cta_button.text() == strings.export_selected_cta(1)

    # con un descuadre en la seleccion la linea de abajo vuelve, y el boton no lo cuenta
    _select(view, 1, 4)
    assert footer.bar.counts() == {"ready": 1, "mismatch": 1, "incomplete": 0, "blocked": 0}
    assert footer.secondary_label.text() == strings.mismatch_needs_confirmation(1)
    assert footer.caption_label.text() == strings.selection_caption(2, 2)
    assert footer.cta_button.text() == strings.export_selected_cta(1)

    # solo facturas que no salen: el boton exporta todo lo listo y el pie sigue siendo global
    _select(view, 2, 3)
    assert footer.bar.counts() == everything
    assert footer.cta_button.text() == strings.export_cta(1)

    view.clear_selection()
    assert footer.bar.counts() == everything
    assert footer.secondary_label.text() == strings.mismatch_needs_confirmation(1)


def test_chips_and_search_filter_the_tree(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document(), unconfigured_document())
    view.search.set_debounce_ms(10)

    view.chips.chip("incomplete").click()
    assert view.proxy.filter_key() == "incomplete"
    assert view.proxy.rowCount() == 1
    assert not view.no_results_label.isVisible()

    view.chips.chip("all").click()
    with qtbot.waitSignal(view.search.search_changed, timeout=2000):
        qtbot.keyClicks(view.search, "ferreteria")
    assert view.proxy.rowCount() == 1
    assert view.proxy.index(0, 0).data(Qt.ItemDataRole.DisplayRole) == "FEV-001003"

    with qtbot.waitSignal(view.search.search_changed, timeout=2000):
        qtbot.keyClicks(view.search, "zzz")
    assert view.proxy.rowCount() == 0
    assert view.no_results_label.isVisible()

    view.set_filter("ready")
    assert view.chips.current() == "ready"
    assert view.proxy.filter_key() == "ready"


def test_expansion_and_selection_survive_a_reset(qtbot) -> None:
    view, model = _view(qtbot, ready_document(), incomplete_document())
    view.tree.expand(view.proxy.index(0, 0))
    _select(view, 2)
    assert view.expanded_invoice_ids() == {1}

    model.set_documents(rows_for(ready_document(), incomplete_document(), unconfigured_document()))

    assert view.proxy.rowCount() == 3
    assert view.tree.isExpanded(view.proxy.index(0, 0))
    assert not view.tree.isExpanded(view.proxy.index(1, 0))
    assert view.selected_invoice_ids() == [2]
    assert _detail_id(view) == 2

    model.set_documents(rows_for(unconfigured_document()))
    assert view.selected_invoice_ids() == []
    assert view.detail.invoice() is None


def test_in_place_update_refreshes_the_detail(qtbot) -> None:
    view, model = _view(qtbot, incomplete_document())
    _select(view, 2)
    assert view.detail.pill.status == "incomplete"

    # misma estructura (ids iguales): actualizacion en sitio, el detalle se refresca
    (row,) = rows_for(ready_document(invoice_id=2, cufe="cufe-2", supplier_number="001002"))
    assert model.set_documents([row]) is False

    assert view.detail.pill.status == "ready"
    assert view.selected_invoice_ids() == [2]


def test_space_toggles_expansion_and_escape_clears_selection(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    first = view.proxy.index(0, 0)
    view.tree.setFocus()
    view.tree.setCurrentIndex(first)
    assert view.selected_invoice_ids() == [1]

    qtbot.keyClick(view.tree, Qt.Key.Key_Space)
    assert view.tree.isExpanded(first)
    qtbot.keyClick(view.tree, Qt.Key.Key_Space)
    assert not view.tree.isExpanded(first)

    qtbot.keyClick(view.tree, Qt.Key.Key_Escape)
    assert view.selected_invoice_ids() == []

    view.expand_button.click()
    assert view.tree.isExpanded(first)
    view.collapse_button.click()
    assert not view.tree.isExpanded(first)


def test_drag_shows_the_overlay_and_drop_emits_paths(qtbot, tmp_path: Path) -> None:
    view, _model = _view(qtbot)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "f.xml")), QUrl("https://x.y/z.xml")])
    actions = Qt.DropAction.CopyAction
    buttons = Qt.MouseButton.NoButton
    modifiers = Qt.KeyboardModifier.NoModifier

    enter = QDragEnterEvent(QPoint(10, 10), actions, mime, buttons, modifiers)
    QApplication.sendEvent(view, enter)
    assert enter.isAccepted()
    assert view.drop_overlay.is_active
    assert view.empty_state.property("active") == "true"

    QApplication.sendEvent(view, QDragLeaveEvent())
    assert not view.drop_overlay.is_active
    assert view.empty_state.property("active") == "false"

    QApplication.sendEvent(view, enter)
    with qtbot.waitSignal(view.paths_dropped) as blocker:
        QApplication.sendEvent(view, QDropEvent(QPointF(10, 10), actions, mime, buttons, modifiers))
    assert blocker.args == [[tmp_path / "f.xml"]]
    assert not view.drop_overlay.is_active

    # el evento no es dueño del QMimeData: debe seguir vivo mientras se procesa
    without_files = QMimeData()
    plain = QDragEnterEvent(QPoint(1, 1), actions, without_files, buttons, modifiers)
    QApplication.sendEvent(view, plain)
    assert not plain.isAccepted()


def test_context_menu_actions_emit_signals(qtbot) -> None:
    view, model = _view(qtbot, incomplete_document())
    invoice = view.proxy.index(0, 0)
    view.tree.expandAll()
    line = view.proxy.index(0, 0, invoice)

    menu = view.context_menu_for(invoice)
    assert menu is not None
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert texts == [
        strings.ACTION_COPY_CUFE,
        strings.ACTION_SHOW_XML,
        strings.ACTION_RESTORE_SUGGESTION,
    ]
    restore = menu.actions()[-1]
    assert restore.isEnabled() is False  # nada asignado a mano

    with qtbot.waitSignal(view.copy_cufe_requested) as blocker:
        menu.actions()[0].trigger()
    assert blocker.args == ["cufe-2"]
    with qtbot.waitSignal(view.show_in_folder_requested) as blocker:
        menu.actions()[1].trigger()
    assert blocker.args == [Path("facturas") / "invoice_plain.xml"]

    # la linea 1 ya tiene P-SERV: asignar otro producto la vuelve manual
    model.setData(view.proxy.mapToSource(view.proxy.index(0, Column.PRODUCT, invoice)), "P-PAPEL")
    menu = view.context_menu_for(line)
    assert menu is not None
    restore = next(a for a in menu.actions() if a.text() == strings.ACTION_RESTORE_SUGGESTION)
    assert restore.isEnabled()
    with qtbot.waitSignal(view.restore_suggestion_requested) as blocker:
        restore.trigger()
    assert blocker.args == [[200]]
    assert view.context_menu_for(view.proxy.index(5, 0)) is None


def test_edit_line_opens_the_editor_on_the_right_cell(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    assert not view.tree.isExpanded(view.proxy.index(1, 0))

    view.edit_line(201, FIELD_COST_CENTER)

    assert view.tree.isExpanded(view.proxy.index(1, 0))
    current = view.tree.currentIndex()
    assert current.column() == Column.COST_CENTER
    assert view.proxy.mapToSource(current).data(Qt.ItemDataRole.EditRole) is None
    editor = view.tree.findChild(CodeCombo)
    assert editor is not None
    assert editor.codes() == ["CC-ADM", "CC-VEN"]
    view.edit_line(999, FIELD_PRODUCT)  # inexistente: no rompe


def test_edit_line_opens_the_editor_of_a_line_the_search_hides(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    with qtbot.waitSignal(view.search.search_changed, timeout=2000):
        qtbot.keyClicks(view.search, "toner")
    # la busqueda deja ver la linea del toner (201) y esconde la de la resma (200)
    assert view.proxy.search_text() == "toner"

    view.edit_line(200, FIELD_PRODUCT)

    # el editor se abre al primer clic: la busqueda se limpia de inmediato, sin esperar
    assert view.search.text() == ""
    assert view.proxy.search_text() == ""
    current = view.tree.currentIndex()
    assert current.column() == Column.PRODUCT
    assert view.proxy.mapToSource(current).data(Role.LINE_ID) == 200
    assert view.tree.findChild(CodeCombo) is not None


def test_detail_panel_signals_bubble_up_and_visibility_toggles(qtbot) -> None:
    view, _model = _view(qtbot, unconfigured_document())
    _select(view, 3)
    assert view.detail.isVisible()

    with qtbot.waitSignal(view.configure_supplier_requested) as blocker:
        view.detail.configure_button.click()
    assert blocker.args == ["800000001", "FERRETERIA DEMO"]
    with qtbot.waitSignal(view.detail_visibility_changed) as blocker:
        view.detail_button.click()
    assert blocker.args == [False]
    assert not view.detail.isVisible()
    assert view.is_detail_visible() is False
    view.set_detail_visible(True)
    assert view.detail.isVisible()

    with qtbot.waitSignal(view.refresh_requested):
        view.detail.refresh_requested.emit()
    with qtbot.waitSignal(view.edit_line_requested) as blocker:
        view.detail.edit_line_requested.emit(300, FIELD_PRODUCT)
    assert blocker.args == [300, FIELD_PRODUCT]


def test_stepper_clicks_import_filter_and_export(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())

    with qtbot.waitSignal(view.import_files_requested):
        view.stepper.button(0).click()
    view.stepper.button(1).click()
    assert view.chips.current() == "incomplete"
    assert view.proxy.filter_key() == "incomplete"
    with qtbot.waitSignal(view.export_requested):
        view.stepper.button(2).click()


def test_busy_overlay_locks_import_and_cancels(qtbot) -> None:
    view, _model = _view(qtbot, ready_document())

    view.set_busy(strings.IMPORT_PROGRESS, cancellable=True)
    assert view.busy_overlay.is_running
    assert view.busy_overlay.message_label.text() == strings.IMPORT_PROGRESS
    assert view.import_button.isEnabled() is False
    view.set_progress(3, 10)
    assert view.busy_overlay.progress_label.text() == strings.busy_progress(3, 10)
    with qtbot.waitSignal(view.cancel_requested):
        view.busy_overlay.cancel_button.click()

    view.set_idle()
    assert not view.busy_overlay.is_running
    assert view.import_button.isEnabled() is True


def test_focus_search_and_readiness_enum_counts(qtbot) -> None:
    view, _model = _view(qtbot, ready_document())
    view.focus_search()
    assert view.focusWidget() is view.search
    summary = _summary(ready_document())
    assert set(summary.readiness_counts) == set(Readiness)
    assert view.readiness.counts() == {"ready": 1}
    assert FIELD_PRODUCT != FIELD_COST_CENTER


@pytest.fixture
def plex(qapp):
    """The bundled font, as the app runs; restored afterwards (widths depend on the font)."""
    previous = qapp.font()
    fonts.apply_app_font(qapp)
    yield
    qapp.setFont(previous)


def _longest_pill_cell(view: InvoicesView) -> int:
    widest = max(
        status_pill_size("blocked", text, view.tree.font()).width()
        for text in strings.PILL_LABELS.values()
    )
    return widest + 2 * CELL_PADDING


def test_the_status_column_shows_the_longest_pill_whole(qtbot, plex) -> None:
    view, _model = _view(qtbot, ready_document())

    assert view.tree.columnWidth(Column.STATUS) >= _longest_pill_cell(view)
    assert view.tree.columnWidth(Column.STATUS) >= COLUMN_WIDTHS[Column.STATUS]
    assert view.column_widths()[Column.STATUS] == view.tree.columnWidth(Column.STATUS)


def test_columns_fold_in_order_and_the_supplier_keeps_its_room(qtbot, plex) -> None:
    view, _model = _view(qtbot, ready_document())
    view.set_detail_visible(False)
    assert SUPPLIER_MIN_WIDTH == 140

    previous_hidden = -1
    for width in range(1400, 520, -40):
        view.resize(width, 820)
        QApplication.processEvents()
        hidden = [column for column in FOLDABLE_COLUMNS if view.tree.isColumnHidden(column)]
        # se pliega siempre en el mismo orden y nunca de mas
        assert hidden == list(FOLDABLE_COLUMNS[: len(hidden)])
        assert len(hidden) >= previous_hidden
        previous_hidden = len(hidden)
        supplier = view.tree.columnWidth(Column.SUPPLIER)
        assert supplier >= SUPPLIER_MIN_WIDTH or len(hidden) == len(FOLDABLE_COLUMNS), width
    assert previous_hidden > 0

    view.resize(1500, 820)
    QApplication.processEvents()
    assert not any(view.tree.isColumnHidden(column) for column in FOLDABLE_COLUMNS)


def test_the_total_is_never_one_of_the_columns_that_fold() -> None:
    # el importe es lo primero que se lee despues del estado: se estrecha lo demas antes que el
    assert Column.TOTAL not in FOLDABLE_COLUMNS
    assert FOLDABLE_COLUMNS == (Column.QUANTITY, Column.DUE_DATE, Column.ISSUE_DATE)


def test_a_1280_window_reads_the_pill_and_the_supplier_and_folds_vencimiento(qtbot, plex) -> None:
    view, _model = _view(qtbot, ready_document())
    view.set_detail_visible(False)
    view.resize(1048, 820)  # 1280 menos la barra lateral de 232
    QApplication.processEvents()

    assert view.tree.isColumnHidden(Column.QUANTITY)
    assert view.tree.isColumnHidden(Column.DUE_DATE)  # vive en el panel de detalle
    assert not view.tree.isColumnHidden(Column.ISSUE_DATE)
    assert not view.tree.isColumnHidden(Column.TOTAL)
    assert view.tree.columnWidth(Column.SUPPLIER) >= SUPPLIER_MIN_WIDTH
    assert view.tree.columnWidth(Column.STATUS) >= _longest_pill_cell(view)


def _preferred(status: int = 193) -> dict[Column, int]:
    return {**COLUMN_WIDTHS, Column.STATUS: status}


def _supplier_room(available: int, plan) -> int:
    shown = sum(width for column, width in plan.widths.items() if column not in plan.hidden)
    return available - shown


def test_the_plan_keeps_every_column_whole_when_it_fits() -> None:
    plan = plan_columns(1400, _preferred())

    assert plan.hidden == ()
    assert plan.widths == _preferred()


def test_the_plan_folds_the_least_useful_columns_first() -> None:
    assert plan_columns(1040, _preferred()).hidden == (Column.QUANTITY,)
    assert plan_columns(1000, _preferred()).hidden == (Column.QUANTITY, Column.DUE_DATE)
    # nada se estrecha mientras plegar baste
    assert plan_columns(1000, _preferred()).widths == _preferred()


def test_the_plan_squeezes_what_is_left_and_keeps_the_total_and_the_supplier() -> None:
    for available in range(900, 640, -10):
        plan = plan_columns(available, _preferred())

        assert Column.TOTAL not in plan.hidden, available
        for column, floor in COLUMN_FLOORS.items():
            assert plan.widths[column] >= floor, (available, column)
        # el proveedor es lo que sobra: lo ultimo que se cede
        assert _supplier_room(available, plan) >= min(
            SUPPLIER_MIN_WIDTH, available - sum(COLUMN_FLOORS.values()) - 138
        ), available

    # con 700 px (1024 sin panel o 1280 con panel) caben todas las columnas utiles
    plan = plan_columns(700, _preferred())
    assert set(plan.hidden) == set(FOLDABLE_COLUMNS)
    assert _supplier_room(700, plan) >= 128  # unas 15 letras del nombre


def test_the_plan_squeezes_product_and_cost_center_before_the_status() -> None:
    # plegado todo lo plegable falta poco: solo ceden los nombres editables
    plan = plan_columns(780, _preferred())

    assert plan.widths[Column.STATUS] == 193
    assert plan.widths[Column.PRODUCT] < COLUMN_WIDTHS[Column.PRODUCT]
    assert plan.widths[Column.COST_CENTER] < COLUMN_WIDTHS[Column.COST_CENTER]
    assert plan.widths[Column.PRODUCT] >= COLUMN_FLOORS[Column.PRODUCT]

    tighter = plan_columns(700, _preferred())
    assert tighter.widths[Column.PRODUCT] == COLUMN_FLOORS[Column.PRODUCT]
    assert tighter.widths[Column.COST_CENTER] == COLUMN_FLOORS[Column.COST_CENTER]
    assert COLUMN_FLOORS[Column.STATUS] <= tighter.widths[Column.STATUS] < 193


def test_the_plan_gives_up_gracefully_when_even_the_floors_do_not_fit() -> None:
    plan = plan_columns(400, _preferred())

    # todo en su minimo y el resto se desplaza: nunca un ancho por debajo del minimo
    assert set(plan.hidden) == set(FOLDABLE_COLUMNS)
    for column, floor in COLUMN_FLOORS.items():
        assert plan.widths[column] == floor


@pytest.mark.parametrize(("width", "detail"), [(792, False), (1048, True), (1048, False)])
def test_the_total_and_the_supplier_stay_readable_at_1024_and_1280_with_the_panel(
    qtbot, plex, width: int, detail: bool
) -> None:
    view, _model = _view(qtbot, ready_document())
    view.set_detail_visible(detail)
    view.resize(width, 820)  # la ventana de 1024 o 1280 menos la barra lateral de 232
    QApplication.processEvents()

    header = view.tree.header()
    viewport = view.tree.viewport().width()
    for column in (
        Column.DOCUMENT,
        Column.SUPPLIER,
        Column.TOTAL,
        Column.PRODUCT,
        Column.COST_CENTER,
        Column.STATUS,
    ):
        assert not view.tree.isColumnHidden(column), column.name
        right = header.sectionViewportPosition(column) + header.sectionSize(column)
        assert right <= viewport, column.name
    assert view.tree.columnWidth(Column.SUPPLIER) >= 128  # unas 15 letras del nombre
    # el estado se lee entero salvo la pastilla mas larga, que se elide: su texto va en el tooltip
    assert view.tree.columnWidth(Column.STATUS) >= COLUMN_FLOORS[Column.STATUS]


def test_the_columns_refit_when_the_scrollbar_takes_its_room(qtbot, plex, themed) -> None:
    view, model = _view(qtbot, ready_document())
    view.set_detail_visible(False)
    view.resize(792, 700)  # 1024 menos la barra lateral
    QApplication.processEvents()
    assert not view.tree.verticalScrollBar().isVisible()
    status_before = view.tree.columnWidth(Column.STATUS)

    # llegan filas de sobra: aparece la barra sin que cambie el tamano del arbol
    documents = [
        ready_document(invoice_id=number, cufe=f"cufe-{number}", supplier_number=f"{number:06d}")
        for number in range(1, 41)
    ]
    model.set_documents(rows_for(*documents))
    qtbot.waitUntil(lambda: view.tree.verticalScrollBar().isVisible(), timeout=2000)
    QApplication.processEvents()

    # lo que la barra le quita al arbol se descuenta de las columnas que ceden, no del proveedor
    assert view.tree.columnWidth(Column.STATUS) < status_before
    assert view.tree.columnWidth(Column.SUPPLIER) >= SUPPLIER_MIN_WIDTH


# --- barra de herramientas ---------------------------------------------------------------


def test_toolbar_icons_say_what_they_do_and_the_panel_toggle_follows_its_state(qtbot) -> None:
    view, _model = _view(qtbot, ready_document())

    assert view.expand_button.toolTip() == strings.ACTION_EXPAND_ALL
    assert view.collapse_button.toolTip() == strings.ACTION_COLLAPSE_ALL
    assert view.detail_button.toolTip() == strings.ACTION_TOGGLE_DETAIL
    assert view.expand_button.icon().cacheKey() == icons.icon("expand_all").cacheKey()
    assert view.collapse_button.icon().cacheKey() == icons.icon("collapse_all").cacheKey()

    view.set_detail_visible(True)
    assert view.detail_button.icon().cacheKey() == icons.icon("panel_close").cacheKey()
    view.set_detail_visible(False)
    assert view.detail_button.icon().cacheKey() == icons.icon("panel_open").cacheKey()


def test_the_tree_buttons_are_a_group_and_the_panel_toggle_sits_at_the_right_edge(qtbot) -> None:
    view, _model = _view(qtbot, ready_document())
    QApplication.processEvents()
    expand, collapse, toggle = view.expand_button, view.collapse_button, view.detail_button

    assert collapse.geometry().left() - expand.geometry().right() - 1 == 4
    assert toggle.geometry().left() > collapse.geometry().right() + 4  # grupo aparte
    assert toggle.mapTo(view, QPoint(toggle.width(), 0)).x() == view.width() - PAGE_MARGIN


# --- el arbol ----------------------------------------------------------------------------


@pytest.fixture
def themed(qapp: QApplication):
    """The real stylesheet, restored afterwards so other tests keep the plain style."""
    previous_sheet = qapp.styleSheet()
    previous_style = qapp.style().objectName()
    apply_theme(qapp)
    yield
    qapp.setStyleSheet(previous_sheet)
    qapp.setStyle(previous_style)


def _gutter_ink(view: InvoicesView, index) -> int:
    """Pixels of the branch gutter (left of the row) that are not row background."""
    image = view.tree.viewport().grab().toImage()
    rect = view.tree.visualRect(index)
    background = image.pixelColor(2, rect.top() + 2).name()
    return sum(
        1
        for x in range(0, rect.left())
        for y in range(rect.top(), rect.bottom() + 1)
        if image.pixelColor(x, y).name() != background
    )


def test_invoice_rows_show_a_chevron_and_line_rows_do_not(qtbot, themed) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    view.tree.expand(view.proxy.index(0, 0))
    QApplication.processEvents()
    closed = view.proxy.index(1, 0)
    opened = view.proxy.index(0, 0)
    line = view.proxy.index(0, 0, opened)

    assert _gutter_ink(view, closed) > 10  # chevron hacia la derecha
    assert _gutter_ink(view, opened) > 10  # chevron hacia abajo
    assert _gutter_ink(view, line) == 0  # las lineas no se abren: el hueco queda limpio


# --- celdas editables ----------------------------------------------------------------------


def _cell_ink(view: InvoicesView, index, *, glyph_only: bool = True) -> int:
    """Pixels of the chevron slot (12 px at the right edge of the cell) that are not the
    cell background."""
    QApplication.processEvents()
    image = view.tree.viewport().grab().toImage()
    cell = view.tree.visualRect(index)
    slot = QRect(cell.right() - CELL_PADDING - CHEVRON_SIZE + 1, cell.top() + 3, CHEVRON_SIZE, 20)
    background = image.pixelColor(slot.left() - 14, slot.top()).name()
    return sum(
        1
        for x in range(slot.left(), slot.right() + 1)
        for y in range(slot.top(), slot.bottom() + 1)
        if image.pixelColor(x, y).name() != background
    )


def _cell(view: InvoicesView, row: int, column: int, parent=None):
    return (
        view.proxy.index(row, column, parent)
        if parent is not None
        else view.proxy.index(row, column)
    )


def test_a_filled_cell_is_quiet_until_the_pointer_or_the_keyboard_reaches_its_row(
    qtbot, themed
) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    first_product = _cell(view, 0, Column.PRODUCT)
    second_product = _cell(view, 1, Column.PRODUCT)
    assert _cell_ink(view, first_product) == 0

    # el puntero sobre cualquier celda de la fila (aqui el documento) muestra los chevrons
    qtbot.mouseMove(view.tree.viewport(), pos=view.tree.visualRect(_cell(view, 0, 0)).center())
    qtbot.waitUntil(lambda: view.tree.is_row_active(first_product), timeout=2000)
    assert _cell_ink(view, first_product) > 10
    assert _cell_ink(view, _cell(view, 0, Column.COST_CENTER)) > 10
    assert _cell_ink(view, _cell(view, 0, Column.STATUS)) == 0  # solo las celdas editables

    # al salir del arbol vuelve a callar
    QApplication.sendEvent(view.tree.viewport(), QEvent(QEvent.Type.Leave))
    qtbot.waitUntil(lambda: not view.tree.is_row_active(first_product), timeout=2000)
    assert _cell_ink(view, first_product) == 0

    # la fila actual (teclado) lleva los chevrons aunque el puntero este lejos
    view.tree.setCurrentIndex(second_product)
    assert view.tree.is_row_active(second_product)
    assert _cell_ink(view, second_product) > 10
    assert _cell_ink(view, first_product) == 0


def test_an_empty_cell_always_shows_its_chevron(qtbot, themed) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    empty = _cell(view, 1, Column.COST_CENTER)  # "Elegir…" en ambar
    filled = _cell(view, 1, Column.PRODUCT)  # la factura mezcla productos: "Varios"

    assert empty.data(Qt.ItemDataRole.DisplayRole) == strings.ACTION_CHOOSE
    assert not view.tree.is_row_active(empty)
    assert _cell_ink(view, empty) > 10
    assert _cell_ink(view, _cell(view, 0, Column.PRODUCT)) == 0  # el valor lleno calla
    assert filled.data(Qt.ItemDataRole.DisplayRole) == strings.VARIOUS


def test_the_chevron_blends_into_a_selected_row(qtbot, themed) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    _select(view, 1)
    cell = _cell(view, 0, Column.COST_CENTER)
    QApplication.processEvents()
    image = view.tree.viewport().grab().toImage()
    rect = view.tree.visualRect(cell)

    # el velo del chevron tiene el color de la fila: no queda un rectangulo a la vista
    left_of_fade = image.pixelColor(rect.right() - 60, rect.top() + 3).name()
    under_fade = image.pixelColor(rect.right() - CELL_PADDING - 2, rect.top() + 3).name()
    assert left_of_fade == under_fade == TOKENS.blue_tint.lower()


def test_the_pointer_is_a_hand_over_the_editable_cells_only(qtbot) -> None:
    view, _model = _view(qtbot, ready_document())
    viewport = view.tree.viewport()

    qtbot.mouseMove(viewport, pos=view.tree.visualRect(_cell(view, 0, 0)).center())
    assert viewport.cursor().shape() == Qt.CursorShape.ArrowCursor
    qtbot.mouseMove(viewport, pos=view.tree.visualRect(_cell(view, 0, Column.PRODUCT)).center())
    qtbot.waitUntil(
        lambda: viewport.cursor().shape() == Qt.CursorShape.PointingHandCursor, timeout=2000
    )
    qtbot.mouseMove(viewport, pos=view.tree.visualRect(_cell(view, 0, Column.COST_CENTER)).center())
    assert viewport.cursor().shape() == Qt.CursorShape.PointingHandCursor
    qtbot.mouseMove(viewport, pos=view.tree.visualRect(_cell(view, 0, Column.TOTAL)).center())
    qtbot.waitUntil(lambda: viewport.cursor().shape() == Qt.CursorShape.ArrowCursor, timeout=2000)


def test_a_click_on_an_editable_cell_opens_its_editor_like_the_hand_says(qtbot) -> None:
    view, _model = _view(qtbot, ready_document(), incomplete_document())
    viewport = view.tree.viewport()
    product = view.tree.visualRect(_cell(view, 0, Column.PRODUCT)).center()

    # otra celda: solo selecciona la fila
    qtbot.mouseClick(
        viewport, Qt.MouseButton.LeftButton, pos=view.tree.visualRect(_cell(view, 0, 0)).center()
    )
    assert view.tree.findChild(CodeCombo) is None
    assert view.selected_invoice_ids() == [1]

    # con Ctrl o Mayus. se esta eligiendo filas, no editando
    qtbot.mouseClick(
        viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, product
    )
    assert view.tree.findChild(CodeCombo) is None

    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=product)
    editor = view.tree.findChild(CodeCombo)
    assert editor is not None
    assert editor.current_code() == "P-PAPEL"


def test_a_click_on_an_empty_catalog_cell_says_why_nothing_opens(qtbot) -> None:
    model = DocumentTreeModel()
    model.set_documents(rows_for(incomplete_document()))  # sin catalogo
    view = InvoicesView()
    qtbot.addWidget(view)
    view.resize(1280, 820)
    view.set_model(model)
    view.update_summary(_summary(incomplete_document()))
    view.show()

    with qtbot.waitSignal(view.catalog_missing, timeout=2000) as blocker:
        qtbot.mouseClick(
            view.tree.viewport(),
            Qt.MouseButton.LeftButton,
            pos=view.tree.visualRect(_cell(view, 0, Column.COST_CENTER)).center(),
        )
    assert blocker.args == [FIELD_COST_CENTER]
    assert view.tree.findChild(CodeCombo) is None
