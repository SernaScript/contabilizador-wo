"""Detail panel: supplier, CUFE, dates, totals, problems checklist with direct actions."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.shared import strings
from contabilizador.ui.formatting import short_cufe
from contabilizador.ui.pages.invoices.detail_panel import DetailPanel
from contabilizador.ui.pages.invoices.rows import FIELD_COST_CENTER, FIELD_PRODUCT, InvoiceRow
from tests.ui.factories import make_pending_document
from tests.ui.pages.invoices.builders import (
    MAPPED,
    incomplete_document,
    mismatch_document,
    ready_document,
    rows_for,
    unconfigured_document,
)


def _panel(qtbot, row: InvoiceRow | None) -> DetailPanel:
    panel = DetailPanel()
    qtbot.addWidget(panel)
    panel.show()
    panel.show_invoice(row)
    return panel


def test_empty_panel_invites_to_select(qtbot) -> None:
    panel = _panel(qtbot, None)

    assert panel.property("role") == "detail"
    assert panel.invoice() is None
    assert panel.empty_label.text() == strings.DETAIL_EMPTY
    assert panel.empty_label.isVisibleTo(panel)
    assert not panel.content.isVisibleTo(panel)


def test_ready_invoice_shows_identity_totals_and_all_clear(qtbot) -> None:
    (row,) = rows_for(ready_document())
    panel = _panel(qtbot, row)

    assert panel.invoice() is row
    assert panel.content.isVisibleTo(panel)
    # el proveedor ya tiene su bloque: el titulo es solo el documento
    assert panel.title_label.text() == "FEV-001001"
    assert row.supplier_name not in panel.title_label.text()
    assert panel.pill.status == "ready"
    assert panel.pill.text == strings.STATUS_READY
    assert panel.supplier_name_label.text() == row.supplier_name
    assert panel.supplier_nit_label.text() == "900123456"
    # el estado del proveedor es una pastilla (icono + texto), no una nota gris
    assert panel.supplier_pill.status == "ready"
    assert panel.supplier_pill.text == strings.DETAIL_SUPPLIER_CONFIGURED
    assert not panel.configure_button.isVisibleTo(panel)
    assert panel.cufe_label.text() == short_cufe("cufe-1")
    assert panel.cufe_label.toolTip() == "cufe-1"
    assert panel.issue_label.text() == "31/08/2026"
    assert panel.due_label.text() == "30/09/2026"
    assert panel.lines_label.text() == "2 líneas"
    assert panel.total_xml_label.text() == "$ 160.700,33"
    assert panel.total_computed_label.text() == "$ 160.700,33"
    assert panel.difference_label.text() == "$ 0"
    assert panel.difference_label.property("status") is None
    assert not panel.original_label.isVisibleTo(panel)
    assert not panel.mismatch_note.isVisibleTo(panel)
    assert not panel.restore_button.isVisibleTo(panel)
    rows = panel.problem_rows()
    assert [r.label.text() for r in rows] == [strings.DETAIL_NO_PROBLEMS]
    assert rows[0].button is None

    with qtbot.waitSignal(panel.copy_cufe_requested) as blocker:
        panel.copy_button.click()
    assert blocker.args == ["cufe-1"]
    with qtbot.waitSignal(panel.show_in_folder_requested) as blocker:
        panel.show_xml_button.click()
    assert blocker.args == [Path("facturas") / "invoice_plain.xml"]


def test_unconfigured_supplier_offers_to_configure(qtbot) -> None:
    (row,) = rows_for(unconfigured_document())
    panel = _panel(qtbot, row)

    assert panel.pill.status == "blocked"
    assert panel.supplier_pill.status == "blocked"
    assert panel.supplier_pill.text == strings.DETAIL_SUPPLIER_UNCONFIGURED
    assert panel.configure_button.isVisibleTo(panel)
    rows = panel.problem_rows()
    assert rows[0].label.text() == strings.problem_message(
        "unconfigured_supplier", None, "800000001"
    )
    assert rows[0].button is not None
    assert rows[0].button.text() == strings.ACTION_CONFIGURE_SUPPLIER

    with qtbot.waitSignal(panel.configure_supplier_requested) as blocker:
        rows[0].button.click()
    assert blocker.args == ["800000001", "FERRETERIA DEMO"]
    with qtbot.waitSignal(panel.configure_supplier_requested) as blocker:
        panel.configure_button.click()
    assert blocker.args == ["800000001", "FERRETERIA DEMO"]


def test_missing_values_link_to_the_line_editor(qtbot) -> None:
    (row,) = rows_for(incomplete_document())
    panel = _panel(qtbot, row)

    rows = panel.problem_rows()
    assert [r.label.text() for r in rows] == [
        strings.problem_message("missing_cost_center", 1, ""),
        strings.problem_message("missing_product", 2, ""),
        strings.problem_message("missing_cost_center", 2, ""),
    ]
    assert all(r.button is not None and r.button.text() == strings.ACTION_CHOOSE for r in rows)

    first, second = rows[0].button, rows[1].button
    assert first is not None and second is not None
    with qtbot.waitSignal(panel.edit_line_requested) as blocker:
        first.click()
    assert blocker.args == [200, FIELD_COST_CENTER]
    with qtbot.waitSignal(panel.edit_line_requested) as blocker:
        second.click()
    assert blocker.args == [201, FIELD_PRODUCT]


def test_unknown_code_offers_to_choose_another_and_stale_offers_refresh(qtbot) -> None:
    (unknown,) = rows_for(ready_document(), product_codes={"OTRO"})
    panel = _panel(qtbot, unknown)
    rows = panel.problem_rows()
    assert rows[0].label.text() == strings.problem_message("unknown_product", 1, "P-PAPEL")
    assert rows[0].button is not None and rows[0].button.text() == strings.ACTION_CHOOSE_ANOTHER
    with qtbot.waitSignal(panel.edit_line_requested) as blocker:
        rows[0].button.click()
    assert blocker.args == [100, FIELD_PRODUCT]

    from contabilizador.invoices.application.list_pending_documents import PendingDocuments
    from contabilizador.ui.pages.invoices.rows import build_rows
    from tests.ui.pages.invoices.builders import make_preview

    (stale,) = build_rows(PendingDocuments((ready_document(),)), make_preview([]))
    panel.show_invoice(stale)
    rows = panel.problem_rows()
    assert rows[0].button is not None and rows[0].button.text() == strings.ACTION_REFRESH
    with qtbot.waitSignal(panel.refresh_requested):
        rows[0].button.click()


def test_mismatch_shows_difference_and_confirmation_note(qtbot) -> None:
    (row,) = rows_for(mismatch_document())
    panel = _panel(qtbot, row)

    assert panel.pill.status == "mismatch"
    assert panel.total_xml_label.text() == "$ 999.999"
    assert panel.difference_label.text() == "-$ 839.298,67"
    assert panel.difference_label.property("status") == "mismatch"
    assert panel.mismatch_note.isVisibleTo(panel)
    assert panel.mismatch_note.text() == strings.DETAIL_MISMATCH_NOTE
    # arriba, donde se mira primero, el listado no dice "todo listo" de una factura descuadrada
    [problem] = panel.problem_rows()
    assert problem.label.text() == strings.FLAG_TOTALS_MISMATCH
    assert problem.button is None


def test_credit_note_reports_the_original_and_manual_lines_can_be_restored(qtbot) -> None:
    pending = make_pending_document(
        invoice_id=7,
        cufe="cude-7",
        kind=DocumentKind.CREDIT_NOTE,
        supplier_prefix="NC",
        supplier_number="125",
        billing_reference_cufe="cufe-1",
        mappings=(LineMapping("P-PAPEL", "CC-ADM"), LineMapping("P-PAPEL", "CC-ADM")),
    )
    (row,) = rows_for(replace(pending, original_found=False))
    row = row.with_line_value(700, FIELD_PRODUCT, "P-SERV")
    panel = _panel(qtbot, row)

    assert panel.original_label.isVisibleTo(panel)
    assert panel.original_label.text() == strings.DETAIL_ORIGINAL_MISSING
    assert panel.restore_button.isVisibleTo(panel)
    with qtbot.waitSignal(panel.restore_suggestion_requested) as blocker:
        panel.restore_button.click()
    assert blocker.args == [[700]]

    (found,) = rows_for(replace(pending, original_found=True))
    panel.show_invoice(found)
    assert panel.original_label.text() == strings.DETAIL_ORIGINAL_FOUND
    assert not panel.restore_button.isVisibleTo(panel)


def test_sub_cent_rounding_shows_zero_and_small_differences_keep_their_sign(qtbot) -> None:
    (rounding,) = rows_for(
        make_pending_document(mappings=MAPPED, payable_amount=Decimal("160700.334"))
    )
    panel = _panel(qtbot, rounding)
    assert panel.difference_label.text() == "$ 0"
    assert panel.difference_label.property("status") is None

    (half,) = rows_for(make_pending_document(mappings=MAPPED, payable_amount=Decimal("160700.83")))
    panel.show_invoice(half)
    assert panel.difference_label.text() == "-$ 0,50"
    assert panel.difference_label.property("status") is None  # dentro de la tolerancia


def _top(widget: QWidget, panel: DetailPanel) -> int:
    QApplication.processEvents()
    layout = panel.content.layout()
    if layout is not None:
        layout.activate()
    return widget.mapTo(panel.content, QPoint(0, 0)).y()


def test_what_can_be_fixed_comes_first_then_the_reference_data_in_reading_order(qtbot) -> None:
    (row,) = rows_for(incomplete_document())
    panel = _panel(qtbot, row)

    order = [
        panel.title_label,
        panel.lines_label,
        panel.pill,
        panel.problems_title,
        panel.problems_box,
        panel.supplier_name_label,
        panel.issue_label,
        panel.due_label,
        panel.total_xml_label,
        panel.difference_label,
        # el CUFE solo sirve para copiarlo: va despues de lo que se lee
        panel.cufe_label,
        panel.show_xml_button,
    ]
    tops = [_top(widget, panel) for widget in order]

    assert tops == sorted(tops)
    assert len(set(tops)) == len(tops)


def test_the_line_count_is_a_caption_under_the_title_not_a_date(qtbot) -> None:
    (row,) = rows_for(ready_document())
    panel = _panel(qtbot, row)

    assert panel.lines_label.text() == strings.lines_count(2)
    assert panel.lines_label.property("role") == "caption"
    # la unidad aparece una vez: ya no hay una fila "Líneas" con "2 líneas" dentro de Fechas
    assert "Líneas" not in {
        label.text()
        for label in panel.findChildren(QLabel)
        if label.property("role") == "label" and label.isVisibleTo(panel)
    }
    assert _top(panel.lines_label, panel) > _top(panel.title_label, panel)
    assert _top(panel.lines_label, panel) < _top(panel.pill, panel)


def test_restore_suggestion_sits_with_the_assignment_and_only_for_a_manual_one(qtbot) -> None:
    pending = make_pending_document(
        invoice_id=7,
        cufe="cufe-7",
        mappings=(LineMapping("P-PAPEL", None), LineMapping("P-PAPEL", "CC-ADM")),
    )
    (row,) = rows_for(pending)
    panel = _panel(qtbot, row)

    # sin asignacion a mano no hay nada que restablecer: ni el boton ni su bloque
    assert not panel.restore_button.isVisibleTo(panel)
    assert not panel.assignment_title.isVisibleTo(panel)

    panel.show_invoice(row.with_line_value(700, FIELD_PRODUCT, "P-SERV"))

    assert panel.restore_button.isVisibleTo(panel)
    assert panel.assignment_title.text() == strings.DETAIL_ASSIGNMENT
    assert panel.assignment_label.text() == strings.PROVENANCE_MANUAL
    # no es un pendiente: baja a su propio bloque, despues de los totales y antes del CUFE
    assert _top(panel.problems_box, panel) < _top(panel.supplier_name_label, panel)
    assert _top(panel.difference_label, panel) < _top(panel.assignment_title, panel)
    assert _top(panel.assignment_title, panel) < _top(panel.assignment_label, panel)
    assert _top(panel.assignment_label, panel) < _top(panel.restore_button, panel)
    assert _top(panel.restore_button, panel) < _top(panel.cufe_label, panel)


def test_the_totals_that_explain_a_mismatch_are_on_the_first_screen(qtbot) -> None:
    (row,) = rows_for(mismatch_document())
    panel = _panel(qtbot, row)
    panel.resize(280, 470)  # el panel del layout de 1280 x 820
    QApplication.processEvents()

    bottom = _top(panel.difference_label, panel) + panel.difference_label.height()

    # sin bajar con la barra: la diferencia es lo que explica el descuadre
    assert bottom < panel.scroll_area.viewport().height()
    assert _top(panel.total_xml_label, panel) < _top(panel.cufe_label, panel)


def test_the_panel_needs_no_scrolling_to_reach_the_problems(qtbot) -> None:
    (row,) = rows_for(incomplete_document())
    panel = _panel(qtbot, row)
    panel.resize(320, 520)
    QApplication.processEvents()

    problems_bottom = _top(panel.problems_box, panel) + panel.problems_box.height()

    # los pendientes caben en la primera pantalla del panel, sin bajar con la barra
    assert panel.problems_box.height() > 0
    assert problems_bottom < panel.scroll_area.viewport().height()
