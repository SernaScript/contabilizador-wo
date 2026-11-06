from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from contabilizador.companies.domain.company import Company
from contabilizador.exports.domain.document_builder import (
    ExportLineAssignment,
    build_world_office_document,
    totals_difference,
    totals_match,
)
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.header_note import HEADER_NOTE_MAX_LENGTH, build_header_note
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine

COMPANY = Company(
    id=1,
    name="WEARE DEV S.A.S",
    internal_third_party_id="1037663527",
    warehouse="Principal",
    unit="Und.",
)


def make_document(
    *,
    kind: DocumentKind = DocumentKind.INVOICE,
    due_date: date | None = date(2026, 9, 30),
    lines: tuple[ParsedLine, ...] | None = None,
    payable: Decimal = Decimal("184450.00"),
    prefix: str = "FEV",
) -> ParsedDocument:
    return ParsedDocument(
        cufe="cufe-1",
        kind=kind,
        supplier_nit="900123456",
        supplier_name="COMERCIALIZADORA EJEMPLO S.A.S.",
        supplier_prefix=prefix,
        supplier_number="01001",
        issue_date=date(2026, 8, 31),
        due_date=due_date,
        lines=lines
        or (
            ParsedLine("RESMA PAPEL CARTA 75G", Decimal("3"), Decimal("30000.00"), Decimal("19")),
            ParsedLine("TONER IMPRESORA LASER", Decimal("1"), Decimal("125000.00"), Decimal("19")),
        ),
        payable_amount=payable,
        billing_reference_cufe=None,
        source_file=Path("invoice_plain.xml"),
    )


ASSIGNMENTS = (
    ExportLineAssignment(product_code="513515", cost_center_name="GERENCIA GENERAL"),
    ExportLineAssignment(product_code="519560", cost_center_name="Administracion"),
)


def test_header_note_uses_the_shared_invoices_rule() -> None:
    # una sola regla de nota (invoices/domain/header_note.py) para pantalla y exportacion
    lines = (
        ParsedLine("X" * 300, Decimal("1"), Decimal("1"), Decimal("0")),
        ParsedLine("Y" * 300, Decimal("1"), Decimal("1"), Decimal("0")),
    )
    document = make_document(lines=lines)

    built = build_world_office_document(
        company=COMPANY, document=document, number=1, assignments=ASSIGNMENTS
    )

    assert built.note == build_header_note(line.description for line in lines)
    assert len(built.note) == HEADER_NOTE_MAX_LENGTH


def test_builds_invoice_as_fc_with_company_defaults() -> None:
    document = build_world_office_document(
        company=COMPANY, document=make_document(), number=9420378244, assignments=ASSIGNMENTS
    )

    assert document.document_type is DocumentType.FC
    assert document.prefix == "FC"
    assert document.number == 9420378244
    assert document.company_name == "WEARE DEV S.A.S"
    assert document.internal_third_party == "1037663527"
    assert document.external_third_party == "900123456"
    assert document.external_prefix == "FEV"
    assert document.external_number == "01001"
    assert document.payment_form == "Credito"
    assert document.date == document.issue_date == date(2026, 8, 31)
    assert document.note == "RESMA PAPEL CARTA 75G & TONER IMPRESORA LASER"
    assert (document.verified, document.voided) == (0, 0)


def test_builds_lines_with_unit_value_tax_rate_and_assignment() -> None:
    document = build_world_office_document(
        company=COMPANY, document=make_document(), number=1, assignments=ASSIGNMENTS
    )

    first, second = document.lines
    assert first.product_code == "513515"
    assert first.cost_center_name == "GERENCIA GENERAL"
    assert first.warehouse == "Principal"
    assert first.unit == "Und."
    assert first.quantity == Decimal("3")
    assert first.unit_value == Decimal("10000")
    assert first.tax_rate == Decimal("0.19")
    assert first.discount == 0
    assert first.due_date == date(2026, 9, 30)
    assert first.detail_note == "RESMA PAPEL CARTA 75G"
    assert second.product_code == "519560"
    assert second.cost_center_name == "Administracion"


def test_due_date_falls_back_to_issue_date() -> None:
    document = build_world_office_document(
        company=COMPANY, document=make_document(due_date=None), number=1, assignments=ASSIGNMENTS
    )
    assert {line.due_date for line in document.lines} == {date(2026, 8, 31)}


def test_credit_note_is_nc_with_positive_values() -> None:
    credit_note = make_document(
        kind=DocumentKind.CREDIT_NOTE,
        lines=(ParsedLine("RESMA", Decimal("1"), Decimal("-10000.00"), Decimal("19")),),
        prefix="",
    )
    document = build_world_office_document(
        company=COMPANY, document=credit_note, number=5, assignments=ASSIGNMENTS[:1]
    )
    assert document.document_type is DocumentType.NC
    assert document.prefix == "NC"
    assert document.external_prefix == ""
    assert document.lines[0].unit_value == Decimal("10000")


def test_assignments_must_match_lines() -> None:
    with pytest.raises(ValueError):
        build_world_office_document(
            company=COMPANY, document=make_document(), number=1, assignments=ASSIGNMENTS[:1]
        )


def test_totals_difference_is_zero_when_lines_match_payable() -> None:
    assert totals_difference(make_document()) == Decimal("0")


def test_totals_difference_reports_gap_against_payable() -> None:
    assert totals_difference(make_document(payable=Decimal("184400.00"))) == Decimal("50")


@pytest.mark.parametrize(
    ("payable", "matches"), [(Decimal("11900.00"), True), (Decimal("12000.00"), False)]
)
def test_grid_and_export_agree_on_negative_credit_notes(payable: Decimal, matches: bool) -> None:
    # una sola regla de totales: la grilla (StoredInvoice) y la exportacion no discrepan
    credit_note = make_document(
        kind=DocumentKind.CREDIT_NOTE,
        lines=(ParsedLine("RESMA", Decimal("1"), Decimal("-10000.00"), Decimal("19")),),
        payable=payable,
    )
    stored = StoredInvoice(
        id=1,
        company_id=1,
        status=InvoiceStatus.PENDING,
        document=credit_note,
        lines=(StoredLine(id=1, position=0, line=credit_note.lines[0], assigned=None),),
    )

    assert stored.totals.matches is totals_match(credit_note) is matches
    assert stored.totals.difference == totals_difference(credit_note)
