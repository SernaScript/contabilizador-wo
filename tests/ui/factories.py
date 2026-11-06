"""Builders of pending documents for UI tests (no database)."""

from decimal import Decimal

from contabilizador.invoices.application.list_pending_documents import (
    PendingDocument,
    PendingDocuments,
    PendingLine,
)
from contabilizador.invoices.domain.document import ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from contabilizador.invoices.domain.suggestion import MappingSource, MappingSuggestion
from tests.invoices.factories import make_document

COMPANY = 1
# Σ qty·valor·(1+iva) de las dos lineas de make_document (3·10000·1.19 + 125000.33)
MATCHING_PAYABLE = Decimal("160700.33")


def make_pending_document(
    *,
    invoice_id: int = 1,
    cufe: str = "cufe-1",
    supplier_configured: bool = True,
    mappings: tuple[LineMapping | None, ...] | None = None,
    payable_amount: Decimal | None = None,
    **overrides: object,
) -> PendingDocument:
    """Two-line document (see ``make_document``); ``mappings`` is parallel to its lines."""
    overrides["payable_amount"] = MATCHING_PAYABLE if payable_amount is None else payable_amount
    document = make_document(cufe=cufe, **overrides)
    chosen = mappings if mappings is not None else (None,) * len(document.lines)
    stored_lines = tuple(
        StoredLine(id=invoice_id * 100 + position, position=position, line=line, assigned=None)
        for position, line in enumerate(document.lines)
    )
    stored = StoredInvoice(
        id=invoice_id,
        company_id=COMPANY,
        status=InvoiceStatus.PENDING,
        document=document,
        lines=stored_lines,
    )
    pending_lines = tuple(
        PendingLine(
            line,
            MappingSuggestion(
                mapping, MappingSource.MEMORY if mapping is not None else MappingSource.NONE
            ),
        )
        for line, mapping in zip(stored_lines, chosen, strict=True)
    )
    return PendingDocument(stored, supplier_configured, pending_lines)


def make_pending_documents(*documents: PendingDocument) -> PendingDocuments:
    return PendingDocuments(tuple(documents))


def line(description: str, quantity: str, amount: str, tax: str = "19.00") -> ParsedLine:
    return ParsedLine(description, Decimal(quantity), Decimal(amount), Decimal(tax))
