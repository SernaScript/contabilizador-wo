"""Maps a parsed DIAN document plus its line assignments to a World Office document."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from contabilizador.companies.domain.company import Company
from contabilizador.exports.domain.world_office import (
    DocumentType,
    WorldOfficeDocument,
    WorldOfficeLine,
)
from contabilizador.invoices.domain.document import ParsedDocument, ParsedLine
from contabilizador.invoices.domain.header_note import build_header_note
from contabilizador.invoices.domain.totals import check_document_totals


@dataclass(frozen=True, slots=True)
class ExportLineAssignment:
    """Product and cost center (already resolved to its NAME) for one parsed line.

    Not to be confused with ``invoices.application.assign_line_mapping.LineAssignment``
    (line id + codes chosen by the user)."""

    product_code: str
    cost_center_name: str


def totals_difference(document: ParsedDocument) -> Decimal:
    """Σ qty·valor·(1+iva) minus the XML payable amount (both taken as positive).

    Delegates to the single totals rule of the invoices module."""
    return check_document_totals(document).difference


def totals_match(document: ParsedDocument) -> bool:
    return check_document_totals(document).matches


def _build_line(
    company: Company, document: ParsedDocument, line: ParsedLine, assignment: ExportLineAssignment
) -> WorldOfficeLine:
    return WorldOfficeLine(
        product_code=assignment.product_code,
        warehouse=company.warehouse,
        unit=company.unit,
        quantity=line.quantity,
        tax_rate=line.tax_rate,
        # notas credito tambien van con valores positivos
        unit_value=abs(line.unit_value),
        discount=Decimal(0),
        due_date=document.effective_due_date,
        detail_note=line.description,
        cost_center_name=assignment.cost_center_name,
    )


def build_world_office_document(
    *,
    company: Company,
    document: ParsedDocument,
    number: int,
    assignments: Sequence[ExportLineAssignment],
) -> WorldOfficeDocument:
    """``assignments`` is parallel to ``document.lines`` (same length and order)."""
    if len(assignments) != len(document.lines):
        raise ValueError("one assignment is required per document line")
    return WorldOfficeDocument(
        company_name=company.name,
        document_type=DocumentType.for_kind(document.kind),
        number=number,
        date=document.issue_date,
        internal_third_party=company.internal_third_party_id,
        external_third_party=document.supplier_nit,
        external_prefix=document.supplier_prefix,
        external_number=document.supplier_number,
        note=build_header_note(line.description for line in document.lines),
        payment_form=company.payment_form,
        issue_date=document.issue_date,
        lines=tuple(
            _build_line(company, document, line, assignment)
            for line, assignment in zip(document.lines, assignments, strict=True)
        ),
    )
