"""Builders shared by the Facturas page tests (no database)."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from decimal import Decimal
from typing import Any

from contabilizador.exports.application.plan_consecutives import ConsecutivePlan
from contabilizador.exports.application.preview_export import ExportPreview
from contabilizador.exports.domain.errors import TotalsMismatch
from contabilizador.exports.domain.readiness import DocumentAssessment, assess_document
from contabilizador.invoices.application.list_pending_documents import (
    PendingDocument,
    PendingDocuments,
)
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.ui.pages.invoices.rows import InvoiceRow, build_rows
from tests.ui.factories import make_pending_document

PRODUCTS = {"P-PAPEL": "Papelería", "P-SERV": "Servicios"}
COST_CENTERS = {"CC-ADM": "Administración", "CC-VEN": "Ventas"}
MAPPED = (LineMapping("P-PAPEL", "CC-ADM"), LineMapping("P-PAPEL", "CC-ADM"))


def assess(
    pending: PendingDocument,
    *,
    product_codes: Collection[str] = PRODUCTS,
    cost_center_codes: Collection[str] = COST_CENTERS,
) -> DocumentAssessment:
    """Assessment of a pending document with the mappings the screen would show."""
    return assess_document(
        pending.invoice.document,
        status=pending.invoice.status,
        line_mappings=[line.mapping for line in pending.lines],
        supplier_configured=pending.supplier_configured,
        product_codes=product_codes,
        cost_center_codes=cost_center_codes,
    )


def make_preview(assessments: Iterable[DocumentAssessment]) -> ExportPreview:
    documents = tuple(assessments)
    exportable = tuple(d for d in documents if d.exportable)
    return ExportPreview(
        documents=documents,
        plan=ConsecutivePlan(ranges={}, collisions=()),
        exportable_cufes=tuple(d.cufe for d in exportable),
        counts={},
        mismatches=tuple(
            TotalsMismatch(d.cufe, d.totals.difference)
            for d in exportable
            if d.needs_confirmation and d.totals is not None
        ),
    )


def rows_for(*pending: PendingDocument, **assess_kwargs: Collection[str]) -> list[InvoiceRow]:
    """Rows of the given pending documents, assessed with the default catalogs."""
    preview = make_preview(assess(p, **assess_kwargs) for p in pending)
    return build_rows(PendingDocuments(tuple(pending)), preview)


def ready_document(invoice_id: int = 1, cufe: str = "cufe-1", **overrides: Any) -> PendingDocument:
    overrides.setdefault("supplier_number", "001001")
    return make_pending_document(invoice_id=invoice_id, cufe=cufe, mappings=MAPPED, **overrides)


def incomplete_document(
    invoice_id: int = 2, cufe: str = "cufe-2", **overrides: Any
) -> PendingDocument:
    """First line without cost center, second without anything."""
    overrides.setdefault("supplier_number", "001002")
    return make_pending_document(
        invoice_id=invoice_id,
        cufe=cufe,
        mappings=(LineMapping("P-SERV", None), None),
        **overrides,
    )


def unconfigured_document(
    invoice_id: int = 3, cufe: str = "cufe-3", **overrides: Any
) -> PendingDocument:
    overrides.setdefault("supplier_number", "001003")
    return make_pending_document(
        invoice_id=invoice_id,
        cufe=cufe,
        supplier_configured=False,
        mappings=MAPPED,
        supplier_nit="800000001",
        supplier_name="FERRETERIA DEMO",
        **overrides,
    )


def mismatch_document(
    invoice_id: int = 4, cufe: str = "cufe-4", **overrides: Any
) -> PendingDocument:
    overrides.setdefault("supplier_number", "001004")
    return make_pending_document(
        invoice_id=invoice_id,
        cufe=cufe,
        mappings=MAPPED,
        payable_amount=Decimal("999999.00"),
        **overrides,
    )
