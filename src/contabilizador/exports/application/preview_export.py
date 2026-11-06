"""Use case: what an export of a selection would do, without writing anything.

Feeds the status pills, the readiness footer and the export sheet. It shares the
assessment with ``ExportBatch``, so its exportable subset is exactly what the export
accepts.
"""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contabilizador.exports.application.assessment import assess_selection
from contabilizador.exports.application.plan_consecutives import ConsecutivePlan, PlanConsecutives
from contabilizador.exports.application.ports import (
    CompanyReader,
    CostCenterReader,
    ExportCandidateSource,
    ProductReader,
    SupplierConfigReader,
)
from contabilizador.exports.domain.errors import CompanyNotFoundError, TotalsMismatch
from contabilizador.exports.domain.readiness import DocumentAssessment, Readiness
from contabilizador.exports.domain.world_office import DocumentType


@dataclass(frozen=True, slots=True)
class ExportPreview:
    """Attributes:
    documents: one assessment per requested CUFE (deduplicated, request order),
        including the ones that were not found.
    plan: consecutive ranges and collisions for the exportable subset.
    exportable_cufes: documents an export would accept (request order); a totals
        mismatch among them needs ``confirm_totals_mismatch``.
    counts: exportable documents per type.
    mismatches: exportable documents whose totals differ from the XML.
    """

    documents: tuple[DocumentAssessment, ...]
    plan: ConsecutivePlan
    exportable_cufes: tuple[str, ...]
    counts: Mapping[DocumentType, int]
    mismatches: tuple[TotalsMismatch, ...]

    def assessment(self, cufe: str) -> DocumentAssessment | None:
        return next((d for d in self.documents if d.cufe == cufe), None)

    @property
    def by_cufe(self) -> dict[str, DocumentAssessment]:
        """Assessments by CUFE, in request order (for bulk lookups)."""
        return {d.cufe: d for d in self.documents}

    @property
    def readiness_counts(self) -> dict[Readiness, int]:
        """Documents per state, every state present (feeds the readiness bar)."""
        counts = Counter(d.readiness for d in self.documents)
        return {readiness: counts[readiness] for readiness in Readiness}

    @property
    def needs_refresh(self) -> bool:
        """Some document was exported or removed since the caller listed it."""
        return any(d.is_stale for d in self.documents)


class PreviewExport:
    def __init__(
        self,
        *,
        companies: CompanyReader,
        candidates: ExportCandidateSource,
        suppliers: SupplierConfigReader,
        products: ProductReader,
        cost_centers: CostCenterReader,
        planner: PlanConsecutives,
    ) -> None:
        self._companies = companies
        self._candidates = candidates
        self._suppliers = suppliers
        self._products = products
        self._cost_centers = cost_centers
        self._planner = planner

    def execute(
        self,
        company_id: int,
        cufes: Sequence[str],
        start_numbers: Mapping[DocumentType, int] | None = None,
    ) -> ExportPreview:
        """Read only: writes no file, batch, consecutive nor status.

        ``start_numbers``: first consecutive per type; types left out get last + 1.

        Raises:
            CompanyNotFoundError: the company does not exist (the export would fail too).
        """
        if self._companies.get(company_id) is None:
            raise CompanyNotFoundError(company_id)
        if not cufes:
            return ExportPreview((), ConsecutivePlan(ranges={}, collisions=()), (), {}, ())
        selection = assess_selection(
            company_id,
            cufes,
            candidates=self._candidates,
            suppliers=self._suppliers,
            products=self._products,
            cost_centers=self._cost_centers,
        )
        exportable = selection.exportable
        counts = dict(Counter(d.document_type for d in exportable if d.document_type))
        return ExportPreview(
            documents=selection.documents,
            plan=self._planner.execute(company_id, counts, start_numbers),
            exportable_cufes=tuple(d.cufe for d in exportable),
            counts=counts,
            mismatches=selection.mismatches,
        )
