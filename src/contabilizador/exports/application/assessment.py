"""Assessment of a selection of documents.

``ExportBatch`` and ``PreviewExport`` share this helper, so the preview never promises
an export that the export itself would refuse.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from contabilizador.exports.application.ports import (
    CostCenterReader,
    ExportCandidate,
    ExportCandidateSource,
    ProductReader,
    SupplierConfigReader,
)
from contabilizador.exports.domain.errors import ExportProblem, TotalsMismatch
from contabilizador.exports.domain.readiness import (
    DocumentAssessment,
    assess_document,
    assess_missing,
)


@dataclass(frozen=True, slots=True)
class SelectionAssessment:
    """Attributes:
    documents: one assessment per requested CUFE (deduplicated, request order).
    candidates: the documents that were found, in request order.
    cost_center_names: catalog cost center name by code (exported by NAME).
    """

    documents: tuple[DocumentAssessment, ...]
    candidates: tuple[ExportCandidate, ...]
    cost_center_names: Mapping[str, str]

    @property
    def problems(self) -> tuple[ExportProblem, ...]:
        """Every problem, missing documents first (the order ``ExportBlockedError`` uses)."""
        missing = [p for d in self.documents if d.document is None for p in d.problems]
        found = [p for d in self.documents if d.document is not None for p in d.problems]
        return (*missing, *found)

    @property
    def exportable(self) -> tuple[DocumentAssessment, ...]:
        return tuple(d for d in self.documents if d.exportable)

    @property
    def mismatches(self) -> tuple[TotalsMismatch, ...]:
        """Exportable documents whose totals differ: they need explicit confirmation."""
        return tuple(
            TotalsMismatch(d.cufe, d.totals.difference)
            for d in self.exportable
            if d.needs_confirmation and d.totals is not None
        )


def assess_selection(
    company_id: int,
    cufes: Sequence[str],
    *,
    candidates: ExportCandidateSource,
    suppliers: SupplierConfigReader,
    products: ProductReader,
    cost_centers: CostCenterReader,
) -> SelectionAssessment:
    """Assesses every requested CUFE with a constant number of catalog reads."""
    requested = list(dict.fromkeys(cufes))  # sin duplicados, conserva el orden
    found = {c.document.cufe: c for c in candidates.find(company_id, requested)}
    product_codes = frozenset(p.code for p in products.list_by_company(company_id))
    cost_center_names = {c.code: c.name for c in cost_centers.list_by_company(company_id)}
    configured: dict[str, bool] = {}
    documents: list[DocumentAssessment] = []
    for cufe in requested:
        candidate = found.get(cufe)
        if candidate is None:
            documents.append(assess_missing(cufe))
            continue
        nit = candidate.document.supplier_nit
        if nit not in configured:
            configured[nit] = suppliers.get(company_id, nit) is not None
        documents.append(
            assess_document(
                candidate.document,
                status=candidate.status,
                line_mappings=candidate.line_mappings,
                supplier_configured=configured[nit],
                product_codes=product_codes,
                cost_center_codes=cost_center_names,
            )
        )
    return SelectionAssessment(
        documents=tuple(documents),
        candidates=tuple(found[cufe] for cufe in requested if cufe in found),
        cost_center_names=cost_center_names,
    )
