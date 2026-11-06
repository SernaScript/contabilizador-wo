from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from contabilizador.exports.domain.errors import ExportProblem, ProblemKind
from contabilizador.exports.domain.readiness import (
    DocumentAssessment,
    Readiness,
    assess_document,
    assess_missing,
)
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus

NIT = "900123456"
MAPPED = LineMapping("513515", "CC1")
PRODUCTS = frozenset({"513515", "519560"})
COST_CENTERS = frozenset({"CC1", "CC2"})


def document(
    cufe: str = "c1",
    *,
    kind: DocumentKind = DocumentKind.INVOICE,
    lines: int = 1,
    payable: Decimal | None = None,
) -> ParsedDocument:
    parsed_lines = tuple(
        ParsedLine(f"ITEM {i}", Decimal("1"), Decimal("100"), Decimal("19")) for i in range(lines)
    )
    return ParsedDocument(
        cufe=cufe,
        kind=kind,
        supplier_nit=NIT,
        supplier_name="PROVEEDOR",
        supplier_prefix="FEV",
        supplier_number="0001",
        issue_date=date(2026, 9, 1),
        due_date=None,
        lines=parsed_lines,
        payable_amount=Decimal("119") * lines if payable is None else payable,
        billing_reference_cufe=None,
        source_file=Path(f"{cufe}.xml"),
    )


def assess(
    parsed: ParsedDocument | None = None,
    *,
    mappings: tuple[LineMapping | None, ...] | None = None,
    status: InvoiceStatus = InvoiceStatus.PENDING,
    supplier_configured: bool = True,
) -> DocumentAssessment:
    parsed = parsed or document()
    return assess_document(
        parsed,
        status=status,
        line_mappings=mappings if mappings is not None else (MAPPED,) * len(parsed.lines),
        supplier_configured=supplier_configured,
        product_codes=PRODUCTS,
        cost_center_codes=COST_CENTERS,
    )


def kinds(assessment: DocumentAssessment) -> list[tuple[ProblemKind, int | None, str]]:
    return [(p.kind, p.line_number, p.detail) for p in assessment.problems]


def test_readiness_values_are_the_status_token_names() -> None:
    assert [r.value for r in Readiness] == ["blocked", "incomplete", "mismatch", "ready"]


def test_complete_document_is_ready() -> None:
    result = assess()

    assert result.readiness is Readiness.READY
    assert result.exportable
    assert result.problems == ()
    assert result.primary_problem is None
    assert not result.needs_confirmation
    assert not result.is_stale
    assert result.document_type is DocumentType.FC
    assert result.totals is not None and result.totals.matches


def test_credit_note_is_nc() -> None:
    assert assess(document(kind=DocumentKind.CREDIT_NOTE)).document_type is DocumentType.NC


def test_missing_product_and_cost_center_is_incomplete() -> None:
    result = assess(document(lines=2), mappings=(None, LineMapping("513515", None)))

    assert result.readiness is Readiness.INCOMPLETE
    assert not result.exportable
    assert kinds(result) == [
        (ProblemKind.MISSING_PRODUCT, 1, ""),
        (ProblemKind.MISSING_COST_CENTER, 1, ""),
        (ProblemKind.MISSING_COST_CENTER, 2, ""),
    ]


def test_blank_product_counts_as_missing() -> None:
    result = assess(mappings=(LineMapping("  ", "CC1"),))
    assert kinds(result) == [(ProblemKind.MISSING_PRODUCT, 1, "")]


def test_product_must_exist_in_the_catalog() -> None:
    result = assess(mappings=(LineMapping("999999", "CC1"),))

    assert result.readiness is Readiness.BLOCKED
    assert kinds(result) == [(ProblemKind.UNKNOWN_PRODUCT, 1, "999999")]


def test_cost_center_must_exist_in_the_catalog() -> None:
    result = assess(mappings=(LineMapping("513515", "ZZ"),))

    assert result.readiness is Readiness.BLOCKED
    assert kinds(result) == [(ProblemKind.UNKNOWN_COST_CENTER, 1, "ZZ")]


def test_problems_follow_the_export_order() -> None:
    result = assess(
        document(lines=2),
        mappings=(LineMapping("999999", None), LineMapping("", "ZZ")),
        status=InvoiceStatus.EXPORTED,
        supplier_configured=False,
    )

    assert kinds(result) == [
        (ProblemKind.ALREADY_EXPORTED, None, ""),
        (ProblemKind.UNCONFIGURED_SUPPLIER, None, NIT),
        (ProblemKind.UNKNOWN_PRODUCT, 1, "999999"),
        (ProblemKind.MISSING_COST_CENTER, 1, ""),
        (ProblemKind.MISSING_PRODUCT, 2, ""),
        (ProblemKind.UNKNOWN_COST_CENTER, 2, "ZZ"),
    ]
    assert {p.cufe for p in result.problems} == {"c1"}


def test_totals_mismatch_alone_is_exportable_with_confirmation() -> None:
    result = assess(document(payable=Decimal("150")))

    assert result.readiness is Readiness.MISMATCH
    assert result.exportable
    assert result.needs_confirmation
    assert result.totals is not None and result.totals.difference == Decimal("-31")


def test_missing_values_beat_totals_mismatch() -> None:
    result = assess(document(payable=Decimal("150")), mappings=(None,))
    assert result.readiness is Readiness.INCOMPLETE
    assert not result.needs_confirmation


def test_already_exported_document_is_stale() -> None:
    result = assess(status=InvoiceStatus.EXPORTED, supplier_configured=False)

    assert result.readiness is Readiness.BLOCKED
    assert result.is_stale
    assert result.primary_problem is not None
    assert result.primary_problem.kind is ProblemKind.ALREADY_EXPORTED


def test_missing_document_is_stale_and_blocked() -> None:
    result = assess_missing("gone")

    assert result.cufe == "gone"
    assert result.document is None
    assert result.document_type is None
    assert result.totals is None
    assert result.readiness is Readiness.BLOCKED
    assert not result.exportable
    assert result.is_stale
    assert kinds(result) == [(ProblemKind.DOCUMENT_NOT_FOUND, None, "")]


@pytest.mark.parametrize(
    ("status", "configured", "mappings", "expected"),
    [
        # proveedor sin configurar > codigo inexistente > falta valor
        (InvoiceStatus.PENDING, False, (LineMapping("999999", "ZZ"),), "unconfigured_supplier"),
        (InvoiceStatus.PENDING, True, (None, LineMapping("999999", "CC1")), "unknown_product"),
        (InvoiceStatus.PENDING, True, (None, LineMapping("513515", "ZZ")), "unknown_cost_center"),
        (InvoiceStatus.PENDING, True, (LineMapping("513515", None), None), "missing_product"),
        (InvoiceStatus.PENDING, True, (LineMapping("513515", None), MAPPED), "missing_cost_center"),
    ],
)
def test_primary_problem_follows_the_pill_priority(
    status: InvoiceStatus,
    configured: bool,
    mappings: tuple[LineMapping | None, ...],
    expected: str,
) -> None:
    result = assess(
        document(lines=len(mappings)),
        mappings=mappings,
        status=status,
        supplier_configured=configured,
    )

    assert result.primary_problem is not None
    assert result.primary_problem.kind.value == expected


def test_primary_problem_is_the_first_of_its_kind() -> None:
    result = assess(document(lines=2), mappings=(LineMapping("513515", None), None))

    assert result.primary_problem == ExportProblem(ProblemKind.MISSING_PRODUCT, "c1", 2)


def test_one_mapping_slot_per_line_is_required() -> None:
    with pytest.raises(ValueError):
        assess(document(lines=2), mappings=(MAPPED,))


def test_assessment_cufe_must_match_its_document() -> None:
    with pytest.raises(ValueError):
        DocumentAssessment("other", document("c1"))


def test_assessment_can_be_built_directly_for_views() -> None:
    problem = ExportProblem(ProblemKind.MISSING_COST_CENTER, "c1", 1)

    result = DocumentAssessment("c1", document("c1"), (problem,))

    assert result.readiness is Readiness.INCOMPLETE
    assert result.primary_problem == problem
