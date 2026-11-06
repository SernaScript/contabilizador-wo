"""Export readiness of a document.

The single rule behind the status pills, the readiness footer, the export preview and
the export itself: a document is exportable when it has no problems; a totals mismatch
is still exportable but needs explicit confirmation.
"""

from __future__ import annotations

from collections.abc import Container, Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum

from contabilizador.exports.domain.errors import ExportProblem, ProblemKind
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.totals import TotalsCheck, check_document_totals


class Readiness(StrEnum):
    """Status of a document for the export. Values match the UI status token names."""

    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"
    MISMATCH = "mismatch"
    READY = "ready"


# La lista mostrada ya no corresponde a la base de datos: hay que refrescar
STALE_PROBLEMS = frozenset({ProblemKind.ALREADY_EXPORTED, ProblemKind.DOCUMENT_NOT_FOUND})
# Faltan valores que el usuario puede completar; cualquier otro problema bloquea
INCOMPLETE_PROBLEMS = frozenset({ProblemKind.MISSING_PRODUCT, ProblemKind.MISSING_COST_CENTER})
# Prioridad de la etiqueta de estado: desactualizado > bloqueado > incompleto
PROBLEM_PRIORITY: tuple[ProblemKind, ...] = (
    ProblemKind.ALREADY_EXPORTED,
    ProblemKind.DOCUMENT_NOT_FOUND,
    ProblemKind.UNCONFIGURED_SUPPLIER,
    ProblemKind.UNKNOWN_PRODUCT,
    ProblemKind.UNKNOWN_COST_CENTER,
    ProblemKind.MISSING_PRODUCT,
    ProblemKind.MISSING_COST_CENTER,
)


def _priority(problem: ExportProblem) -> int:
    kind = problem.kind
    return PROBLEM_PRIORITY.index(kind) if kind in PROBLEM_PRIORITY else len(PROBLEM_PRIORITY)


@dataclass(frozen=True, slots=True)
class DocumentAssessment:
    """Whether one requested document can be exported, and why not.

    Attributes:
        cufe: requested CUFE.
        document: the stored document; ``None`` when it was not found.
        problems: every problem, in export order (empty = exportable).
    """

    cufe: str
    document: ParsedDocument | None
    problems: tuple[ExportProblem, ...] = ()

    def __post_init__(self) -> None:
        if self.document is not None and self.document.cufe != self.cufe:
            raise ValueError("assessment cufe must match its document")

    @property
    def document_type(self) -> DocumentType | None:
        """FC / NC; ``None`` when the document was not found."""
        return DocumentType.for_kind(self.document.kind) if self.document else None

    @property
    def totals(self) -> TotalsCheck | None:
        return check_document_totals(self.document) if self.document else None

    @property
    def exportable(self) -> bool:
        """No problems. A totals mismatch is exportable after confirmation."""
        return self.document is not None and not self.problems

    @property
    def readiness(self) -> Readiness:
        kinds = {problem.kind for problem in self.problems}
        if self.document is None or kinds - INCOMPLETE_PROBLEMS:
            return Readiness.BLOCKED
        if kinds:
            return Readiness.INCOMPLETE
        totals = self.totals
        if totals is not None and not totals.matches:
            return Readiness.MISMATCH
        return Readiness.READY

    @property
    def primary_problem(self) -> ExportProblem | None:
        """The problem the status pill shows (first one of the highest priority)."""
        return min(self.problems, key=_priority, default=None)

    @property
    def needs_confirmation(self) -> bool:
        return self.readiness is Readiness.MISMATCH

    @property
    def is_stale(self) -> bool:
        """Already exported or gone: the caller should refresh its list."""
        return any(problem.kind in STALE_PROBLEMS for problem in self.problems)


def assess_document(
    document: ParsedDocument,
    *,
    status: InvoiceStatus,
    line_mappings: Sequence[LineMapping | None],
    supplier_configured: bool,
    product_codes: Container[str],
    cost_center_codes: Container[str],
) -> DocumentAssessment:
    """Problems of a stored document in export order: already exported, unconfigured
    supplier, then per line (1-based) its product and its cost center.

    ``line_mappings`` is the effective mapping of each line (parallel to its lines).
    """
    if len(line_mappings) != len(document.lines):
        raise ValueError("one mapping slot is required per document line")
    cufe = document.cufe
    problems: list[ExportProblem] = []
    if status is InvoiceStatus.EXPORTED:
        problems.append(ExportProblem(ProblemKind.ALREADY_EXPORTED, cufe))
    if not supplier_configured:
        problems.append(
            ExportProblem(ProblemKind.UNCONFIGURED_SUPPLIER, cufe, detail=document.supplier_nit)
        )
    for line_number, mapping in enumerate(line_mappings, start=1):
        problems.extend(
            _line_problems(cufe, line_number, mapping, product_codes, cost_center_codes)
        )
    return DocumentAssessment(cufe, document, tuple(problems))


def assess_missing(cufe: str) -> DocumentAssessment:
    """Assessment of a requested CUFE that is not stored for the company."""
    return DocumentAssessment(cufe, None, (ExportProblem(ProblemKind.DOCUMENT_NOT_FOUND, cufe),))


def _line_problems(
    cufe: str,
    line_number: int,
    mapping: LineMapping | None,
    product_codes: Container[str],
    cost_center_codes: Container[str],
) -> Iterator[ExportProblem]:
    product_code = mapping.product_code if mapping else ""
    if not product_code.strip():
        yield ExportProblem(ProblemKind.MISSING_PRODUCT, cufe, line_number)
    elif product_code not in product_codes:
        yield ExportProblem(ProblemKind.UNKNOWN_PRODUCT, cufe, line_number, detail=product_code)
    cost_center_code = mapping.cost_center_code if mapping else None
    if not cost_center_code:
        yield ExportProblem(ProblemKind.MISSING_COST_CENTER, cufe, line_number)
    elif cost_center_code not in cost_center_codes:
        yield ExportProblem(
            ProblemKind.UNKNOWN_COST_CENTER, cufe, line_number, detail=cost_center_code
        )
