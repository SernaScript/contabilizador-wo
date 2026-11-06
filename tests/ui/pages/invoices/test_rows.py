"""Row models of the document tree: grouping, readiness from the preview, summaries,
filters and optimistic edits. Pure Python, no Qt."""

from dataclasses import replace
from decimal import Decimal

from contabilizador.exports.domain.errors import ProblemKind
from contabilizador.exports.domain.readiness import Readiness
from contabilizador.invoices.application.list_pending_documents import PendingDocuments
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.suggestion import MappingSource
from contabilizador.shared import strings
from contabilizador.ui.pages.invoices.rows import (
    FIELD_COST_CENTER,
    FIELD_PRODUCT,
    FILTER_KEYS,
    InvoiceRow,
    LineRow,
    SummaryKind,
    build_rows,
    filter_counts,
    flow_step,
    matches_filter,
    summarize_page,
)
from tests.ui.factories import make_pending_document
from tests.ui.pages.invoices.builders import (
    assess,
    incomplete_document,
    make_preview,
    mismatch_document,
    ready_document,
    rows_for,
    unconfigured_document,
)


def test_rows_group_lines_under_the_invoice_with_readiness_from_the_preview() -> None:
    (row,) = rows_for(ready_document())

    assert isinstance(row, InvoiceRow)
    assert row.invoice_id == 1
    assert row.cufe == "cufe-1"
    assert row.kind is DocumentKind.INVOICE
    assert row.document_type == "FC"
    assert row.label == "FEV-001001"
    assert row.supplier_name == "COMERCIALIZADORA EJEMPLO S.A.S."
    assert row.readiness is Readiness.READY
    assert row.exportable is True
    assert row.needs_confirmation is False
    assert row.primary_problem is None
    assert row.pill_status == "ready"
    assert row.pill_text == strings.STATUS_READY
    assert row.total == Decimal("160700.33")
    assert row.totals.matches
    assert len(row.lines) == 2
    first, second = row.lines
    assert isinstance(first, LineRow)
    assert (first.line_id, first.number) == (100, 1)
    assert (second.line_id, second.number) == (101, 2)
    assert first.description == "RESMA PAPEL CARTA 75G"
    assert first.product_code == "P-PAPEL"
    assert first.cost_center_code == "CC-ADM"
    assert first.source is MappingSource.MEMORY
    assert first.is_suggested and not first.is_manual
    # total de la linea con la misma regla que la exportacion: |ext|·(1+iva)
    assert first.total == Decimal("30000.00") * Decimal("1.19")
    assert first.problems == ()


def test_rows_carry_problems_and_pill_text_per_readiness() -> None:
    incomplete, unconfigured, mismatch = rows_for(
        incomplete_document(), unconfigured_document(), mismatch_document()
    )

    assert incomplete.readiness is Readiness.INCOMPLETE
    # prioridad de la pastilla: falta producto antes que falta centro de costo
    assert incomplete.pill_text == "Falta producto"
    assert [p.kind for p in incomplete.problems] == [
        ProblemKind.MISSING_COST_CENTER,
        ProblemKind.MISSING_PRODUCT,
        ProblemKind.MISSING_COST_CENTER,
    ]
    assert [p.kind for p in incomplete.lines[1].problems] == [
        ProblemKind.MISSING_PRODUCT,
        ProblemKind.MISSING_COST_CENTER,
    ]
    assert incomplete.lines[1].primary_problem is not None
    assert incomplete.lines[1].primary_problem.kind is ProblemKind.MISSING_PRODUCT
    assert incomplete.lines[1].source is MappingSource.NONE
    assert incomplete.exportable is False

    assert unconfigured.readiness is Readiness.BLOCKED
    assert unconfigured.pill_text == strings.FLAG_UNCONFIGURED_SUPPLIER
    assert unconfigured.supplier_configured is False
    assert unconfigured.document_problems[0].kind is ProblemKind.UNCONFIGURED_SUPPLIER

    assert mismatch.readiness is Readiness.MISMATCH
    assert mismatch.exportable is True
    assert mismatch.needs_confirmation is True
    assert mismatch.pill_text == strings.STATUS_MISMATCH
    assert not mismatch.totals.matches


def test_unknown_product_blocks_and_missing_assessment_means_not_found() -> None:
    pending = ready_document()
    blocked = rows_for(pending, product_codes={"OTRO"})[0]
    assert blocked.readiness is Readiness.BLOCKED
    assert blocked.pill_text == "Producto inexistente"

    (stale,) = build_rows(PendingDocuments((pending,)), make_preview([]))
    assert stale.readiness is Readiness.BLOCKED
    assert stale.pill_text == "No encontrada"
    assert stale.exportable is False


def test_credit_note_rows_keep_the_original_flag_and_type() -> None:
    pending = make_pending_document(
        invoice_id=7,
        cufe="cude-7",
        kind=DocumentKind.CREDIT_NOTE,
        supplier_prefix="NC",
        supplier_number="125",
        billing_reference_cufe="cufe-1",
        mappings=(LineMapping("P-PAPEL", "CC-ADM"), LineMapping("P-PAPEL", "CC-ADM")),
    )
    pending = replace(pending, original_found=False)

    (row,) = rows_for(pending)

    assert row.kind is DocumentKind.CREDIT_NOTE
    assert row.document_type == "NC"
    assert row.label == "NC-125"
    assert row.original_found is False


def test_cell_summaries_common_value_various_and_empty() -> None:
    (common,) = rows_for(ready_document())
    assert common.product_summary.kind is SummaryKind.VALUE
    assert common.product_summary.value == "P-PAPEL"
    assert common.cost_center_summary.value == "CC-ADM"

    (mixed,) = rows_for(incomplete_document())
    assert mixed.product_summary.kind is SummaryKind.VARIOUS
    assert mixed.product_summary.values == ("P-SERV",)
    assert mixed.cost_center_summary.kind is SummaryKind.EMPTY
    assert mixed.cost_center_summary.value is None

    (various,) = rows_for(
        make_pending_document(
            mappings=(LineMapping("P-SERV", "CC-ADM"), LineMapping("P-PAPEL", "CC-ADM"))
        )
    )
    assert various.product_summary.kind is SummaryKind.VARIOUS
    assert various.product_summary.values == ("P-SERV", "P-PAPEL")


def test_filters_and_counts() -> None:
    rows = rows_for(
        ready_document(), incomplete_document(), unconfigured_document(), mismatch_document()
    )
    assert FILTER_KEYS == ("all", "ready", "incomplete", "unconfigured", "mismatch", "suggested")
    assert all(matches_filter(row, "all") for row in rows)
    assert [matches_filter(row, "ready") for row in rows] == [True, False, False, False]
    assert [matches_filter(row, "incomplete") for row in rows] == [False, True, False, False]
    assert [matches_filter(row, "unconfigured") for row in rows] == [False, False, True, False]
    assert [matches_filter(row, "mismatch") for row in rows] == [False, False, False, True]
    # sugeridas: alguna linea toma su valor de la memoria o del proveedor
    assert [matches_filter(row, "suggested") for row in rows] == [True, True, True, True]
    assert filter_counts(rows) == {
        "all": 4,
        "ready": 1,
        "incomplete": 1,
        "unconfigured": 1,
        "mismatch": 1,
        "suggested": 4,
    }
    # un producto inexistente bloquea: el pie la cuenta como bloqueada, no como por completar
    blocked = rows_for(ready_document(), product_codes={"OTRO"})[0]
    assert blocked.readiness is Readiness.BLOCKED
    assert matches_filter(blocked, "incomplete") is False


def test_the_chips_count_what_the_footer_legend_counts() -> None:
    """The same words carry the same number: "Por completar" and "Descuadre" in the chips
    are the footer buckets, whatever else an invoice also has."""
    unconfigured_with_gaps = make_pending_document(
        invoice_id=6,
        cufe="cufe-6",
        supplier_configured=False,
        mappings=(None, None),
        supplier_nit="800000001",
        supplier_name="FERRETERIA DEMO",
        supplier_number="001006",
    )
    incomplete_and_off = incomplete_document(
        invoice_id=7, cufe="cufe-7", supplier_number="001007", payable_amount=Decimal("999999.00")
    )
    pending = (
        ready_document(),
        incomplete_document(),
        unconfigured_document(),
        mismatch_document(),
        unconfigured_with_gaps,
        incomplete_and_off,
    )
    preview = make_preview(assess(p) for p in pending)
    rows = build_rows(PendingDocuments(pending), preview)
    summary = summarize_page(rows, preview)
    counts = summary.readiness_counts

    # el proveedor sin configurar con lineas vacias es bloqueada, no por completar
    assert matches_filter(rows[4], "incomplete") is False
    assert matches_filter(rows[4], "unconfigured") is True
    # una por completar que ademas tiene descuadre sigue siendo por completar
    assert matches_filter(rows[5], "incomplete") is True
    assert matches_filter(rows[5], "mismatch") is False

    assert counts[Readiness.INCOMPLETE] == 2
    assert counts[Readiness.MISMATCH] == 1
    assert summary.filter_counts["ready"] == counts[Readiness.READY]
    assert summary.filter_counts["incomplete"] == counts[Readiness.INCOMPLETE]
    assert summary.filter_counts["mismatch"] == counts[Readiness.MISMATCH]
    # la causa concreta sigue siendo un filtro propio: cuenta las facturas de esos proveedores
    assert summary.filter_counts["unconfigured"] == 2


def test_search_text_covers_supplier_nit_number_and_descriptions() -> None:
    (row,) = rows_for(ready_document())

    assert "comercializadora" in row.search_text
    assert "900123456" in row.search_text
    assert "fev-001001" in row.search_text
    assert "001001" in row.search_text
    assert "resma papel" in row.lines[0].search_text
    assert "resma" not in row.search_text


def test_optimistic_edits_mark_lines_as_manual() -> None:
    (row,) = rows_for(incomplete_document())

    edited = row.with_line_value(201, FIELD_PRODUCT, "P-PAPEL")
    assert edited.lines[1].product_code == "P-PAPEL"
    assert edited.lines[1].cost_center_code is None
    assert edited.lines[1].source is MappingSource.ASSIGNED
    assert edited.lines[0] == row.lines[0]
    assert edited.lines[1].mapping == LineMapping("P-PAPEL", None)

    whole = row.with_all_lines(FIELD_COST_CENTER, "CC-VEN")
    assert [line.cost_center_code for line in whole.lines] == ["CC-VEN", "CC-VEN"]
    assert [line.product_code for line in whole.lines] == ["P-SERV", None]
    assert whole.lines[1].mapping == LineMapping("", "CC-VEN")
    assert row.line(201) is row.lines[1]
    assert row.line(999) is None


def test_flow_step_and_page_summary() -> None:
    assert flow_step([]) == 0
    assert flow_step(rows_for(ready_document(), incomplete_document())) == 1
    assert flow_step(rows_for(ready_document(), mismatch_document())) == 2

    pending = (ready_document(), incomplete_document(), unconfigured_document())
    preview = make_preview(assess(p) for p in pending)
    rows = build_rows(PendingDocuments(pending), preview)
    summary = summarize_page(rows, preview)

    assert summary.total == 3
    assert summary.readiness_counts == {
        Readiness.BLOCKED: 1,
        Readiness.INCOMPLETE: 1,
        Readiness.MISMATCH: 0,
        Readiness.READY: 1,
    }
    assert summary.filter_counts["incomplete"] == 1
    assert summary.unconfigured == (("800000001", "FERRETERIA DEMO"),)
    assert summary.attention == 2
    assert summary.exportable_cufes == ("cufe-1",)
    assert summary.flow_step == 1
