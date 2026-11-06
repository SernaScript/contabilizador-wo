"""Rows of the document tree: one invoice with its lines. Pure Python, no Qt.

Readiness, problems and the exportable flag come straight from the export preview
(``DocumentAssessment``); this module never re-implements those rules. It only shapes
them for display: pill text, common value of a column ("Varios" / "Elegir…"), filters,
search text and the optimistic copy of an edit while the use case runs.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from contabilizador.exports.application.preview_export import ExportPreview
from contabilizador.exports.domain.errors import ExportProblem
from contabilizador.exports.domain.readiness import (
    PROBLEM_PRIORITY,
    DocumentAssessment,
    Readiness,
    assess_missing,
)
from contabilizador.invoices.application.list_pending_documents import (
    PendingDocument,
    PendingDocuments,
    PendingLine,
)
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.suggestion import MappingSource
from contabilizador.invoices.domain.totals import TotalsCheck, line_total_with_tax
from contabilizador.shared import strings
from contabilizador.ui.formatting import document_label, format_difference

FIELD_PRODUCT = "product"
FIELD_COST_CENTER = "cost_center"
FIELDS = (FIELD_PRODUCT, FIELD_COST_CENTER)

FILTER_ALL = "all"
FILTER_READY = "ready"
FILTER_INCOMPLETE = "incomplete"
FILTER_UNCONFIGURED = "unconfigured"
FILTER_MISMATCH = "mismatch"
FILTER_SUGGESTED = "suggested"
FILTER_KEYS = (
    FILTER_ALL,
    FILTER_READY,
    FILTER_INCOMPLETE,
    FILTER_UNCONFIGURED,
    FILTER_MISMATCH,
    FILTER_SUGGESTED,
)

SUGGESTED_SOURCES = frozenset({MappingSource.MEMORY, MappingSource.SUPPLIER_DEFAULT})


def difference_text(totals: TotalsCheck) -> str:
    """Signed difference; ``format_difference`` rounds to cents, so a sub-cent rounding
    reads "$ 0", not "+$ 0"."""
    return format_difference(totals.difference)


def _priority(problem: ExportProblem) -> int:
    kind = problem.kind
    return PROBLEM_PRIORITY.index(kind) if kind in PROBLEM_PRIORITY else len(PROBLEM_PRIORITY)


class SummaryKind(StrEnum):
    """What an invoice row shows for a column its lines own."""

    EMPTY = "empty"  # ninguna linea tiene valor: "Elegir…"
    VALUE = "value"  # todas las lineas comparten el valor
    VARIOUS = "various"  # valores distintos o solo algunas lineas con valor: "Varios"


@dataclass(frozen=True, slots=True)
class CellSummary:
    kind: SummaryKind
    value: str | None
    values: tuple[str, ...]


def summarize(values: Iterable[str | None]) -> CellSummary:
    items = list(values)
    distinct = tuple(dict.fromkeys(value for value in items if value))
    if not distinct:
        return CellSummary(SummaryKind.EMPTY, None, ())
    if len(distinct) == 1 and all(items):
        return CellSummary(SummaryKind.VALUE, distinct[0], distinct)
    return CellSummary(SummaryKind.VARIOUS, None, distinct)


@dataclass(frozen=True, slots=True)
class LineRow:
    """One document line with its effective mapping and where it came from."""

    line_id: int
    number: int  # 1-based, matches ExportProblem.line_number
    description: str
    quantity: Decimal
    unit_value: Decimal
    tax_percent: Decimal
    total: Decimal
    product_code: str | None
    cost_center_code: str | None
    source: MappingSource
    problems: tuple[ExportProblem, ...] = ()

    @property
    def is_suggested(self) -> bool:
        return self.source in SUGGESTED_SOURCES

    @property
    def is_manual(self) -> bool:
        return self.source is MappingSource.ASSIGNED

    @property
    def mapping(self) -> LineMapping | None:
        if not self.product_code and not self.cost_center_code:
            return None
        return LineMapping(self.product_code or "", self.cost_center_code or None)

    @property
    def primary_problem(self) -> ExportProblem | None:
        return min(self.problems, key=_priority, default=None)

    @property
    def search_text(self) -> str:
        return self.description.casefold()

    def value(self, field: str) -> str | None:
        return self.product_code if field == FIELD_PRODUCT else self.cost_center_code

    def with_value(self, field: str, code: str) -> LineRow:
        """Optimistic copy of an edit: the value changes and the line becomes manual."""
        if field == FIELD_PRODUCT:
            return replace(self, product_code=code, source=MappingSource.ASSIGNED)
        return replace(self, cost_center_code=code, source=MappingSource.ASSIGNED)


@dataclass(frozen=True, slots=True)
class InvoiceRow:
    invoice_id: int
    cufe: str
    kind: DocumentKind
    document_type: str  # "FC" | "NC"
    supplier_nit: str
    supplier_name: str
    prefix: str
    number: str
    label: str  # "FEV-001001"
    issue_date: date
    due_date: date
    total: Decimal
    totals: TotalsCheck
    supplier_configured: bool
    original_found: bool | None
    readiness: Readiness
    exportable: bool
    primary_problem: ExportProblem | None
    problems: tuple[ExportProblem, ...]
    lines: tuple[LineRow, ...]
    source_file: Path

    @property
    def needs_confirmation(self) -> bool:
        return self.readiness is Readiness.MISMATCH

    @property
    def pill_status(self) -> str:
        return self.readiness.value

    @property
    def pill_text(self) -> str:
        kind = self.primary_problem.kind.value if self.primary_problem else None
        return strings.readiness_pill_text(self.pill_status, kind)

    @property
    def document_problems(self) -> tuple[ExportProblem, ...]:
        return tuple(problem for problem in self.problems if problem.line_number is None)

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def product_summary(self) -> CellSummary:
        return self.summary(FIELD_PRODUCT)

    @property
    def cost_center_summary(self) -> CellSummary:
        return self.summary(FIELD_COST_CENTER)

    def summary(self, field: str) -> CellSummary:
        return summarize(line.value(field) for line in self.lines)

    @property
    def has_suggestions(self) -> bool:
        return any(line.is_suggested for line in self.lines)

    @property
    def has_manual(self) -> bool:
        return any(line.is_manual for line in self.lines)

    @property
    def search_text(self) -> str:
        return " ".join((self.supplier_name, self.supplier_nit, self.label)).casefold()

    def line(self, line_id: int) -> LineRow | None:
        return next((line for line in self.lines if line.line_id == line_id), None)

    def with_line_value(self, line_id: int, field: str, code: str) -> InvoiceRow:
        lines = tuple(
            line.with_value(field, code) if line.line_id == line_id else line for line in self.lines
        )
        return replace(self, lines=lines)

    def with_all_lines(self, field: str, code: str) -> InvoiceRow:
        return replace(self, lines=tuple(line.with_value(field, code) for line in self.lines))


def _line_row(pending: PendingLine, number: int, problems: Sequence[ExportProblem]) -> LineRow:
    parsed = pending.stored.line
    mapping = pending.mapping
    return LineRow(
        line_id=pending.stored.id,
        number=number,
        description=parsed.description,
        quantity=parsed.quantity,
        unit_value=parsed.unit_value,
        tax_percent=parsed.tax_percent,
        total=line_total_with_tax(parsed),
        product_code=(mapping.product_code or None) if mapping else None,
        cost_center_code=(mapping.cost_center_code or None) if mapping else None,
        source=pending.suggestion.source,
        problems=tuple(problem for problem in problems if problem.line_number == number),
    )


def _invoice_row(pending: PendingDocument, assessment: DocumentAssessment) -> InvoiceRow:
    invoice = pending.invoice
    document = invoice.document
    return InvoiceRow(
        invoice_id=invoice.id,
        cufe=document.cufe,
        kind=document.kind,
        document_type="NC" if document.is_credit_note else "FC",
        supplier_nit=document.supplier_nit,
        supplier_name=document.supplier_name,
        prefix=document.supplier_prefix,
        number=document.supplier_number,
        label=document_label(document.supplier_prefix, document.supplier_number),
        issue_date=document.issue_date,
        due_date=document.effective_due_date,
        total=document.payable_amount,
        totals=invoice.totals,
        supplier_configured=pending.supplier_configured,
        original_found=pending.original_found,
        readiness=assessment.readiness,
        exportable=assessment.exportable,
        primary_problem=assessment.primary_problem,
        problems=assessment.problems,
        lines=tuple(
            _line_row(line, number, assessment.problems)
            for number, line in enumerate(pending.lines, start=1)
        ),
        source_file=document.source_file,
    )


def build_rows(pending: PendingDocuments, preview: ExportPreview) -> list[InvoiceRow]:
    """One row per pending document, assessed by the preview (missing = not found)."""
    assessments = preview.by_cufe
    rows: list[InvoiceRow] = []
    for document in pending.documents:
        cufe = document.invoice.document.cufe
        assessment = assessments.get(cufe) or assess_missing(cufe)
        rows.append(_invoice_row(document, assessment))
    return rows


# --- filtros y busqueda ------------------------------------------------------


def matches_filter(row: InvoiceRow, key: str) -> bool:
    """Chips that share a name with a footer bucket (listas, por completar, descuadre) are
    that bucket: one readiness per invoice, so chip and legend always show the same number.
    "Proveedor sin configurar" is a cause, not a bucket, and counts every invoice of those
    suppliers."""
    match key:
        case "ready":
            return row.readiness is Readiness.READY
        case "incomplete":
            return row.readiness is Readiness.INCOMPLETE
        case "unconfigured":
            return not row.supplier_configured
        case "mismatch":
            return row.readiness is Readiness.MISMATCH
        case "suggested":
            return row.has_suggestions
        case _:
            return True


def filter_counts(rows: Sequence[InvoiceRow]) -> dict[str, int]:
    return {key: sum(1 for row in rows if matches_filter(row, key)) for key in FILTER_KEYS}


def flow_step(rows: Collection[InvoiceRow]) -> int:
    """Stepper state: 0 import (nothing yet), 1 complete, 2 export (all exportable)."""
    if not rows:
        return 0
    return 2 if all(row.exportable for row in rows) else 1


@dataclass(frozen=True, slots=True)
class PageSummary:
    """Numbers the page shows around the tree (footer, chips, banner, badge, stepper)."""

    total: int
    readiness_counts: dict[Readiness, int]
    filter_counts: dict[str, int]
    unconfigured: tuple[tuple[str, str], ...]
    attention: int
    exportable_cufes: tuple[str, ...]
    flow_step: int

    @property
    def mismatch_count(self) -> int:
        return self.readiness_counts[Readiness.MISMATCH]


def summarize_page(rows: Sequence[InvoiceRow], preview: ExportPreview) -> PageSummary:
    counts = {readiness: 0 for readiness in Readiness}
    for row in rows:
        counts[row.readiness] += 1
    unconfigured: dict[str, str] = {}
    for row in rows:
        if not row.supplier_configured and row.supplier_nit not in unconfigured:
            unconfigured[row.supplier_nit] = row.supplier_name
    return PageSummary(
        total=len(rows),
        readiness_counts=counts,
        filter_counts=filter_counts(rows),
        unconfigured=tuple(unconfigured.items()),
        attention=counts[Readiness.INCOMPLETE] + counts[Readiness.BLOCKED],
        exportable_cufes=tuple(preview.exportable_cufes),
        flow_step=flow_step(rows),
    )
