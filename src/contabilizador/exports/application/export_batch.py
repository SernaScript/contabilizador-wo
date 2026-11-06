"""Use case: export selected documents to a World Office workbook as a new batch."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from contabilizador.companies.domain.company import Company
from contabilizador.exports.application.assessment import assess_selection
from contabilizador.exports.application.plan_consecutives import PlanConsecutives
from contabilizador.exports.application.ports import (
    BatchRepository,
    Clock,
    CompanyReader,
    ConsecutiveRepository,
    CostCenterReader,
    ExportCandidate,
    ExportCandidateSource,
    InvoiceStatusUpdater,
    ProductReader,
    PurchaseImportExporter,
    SupplierConfigReader,
    UnitOfWork,
)
from contabilizador.exports.domain.batch import Batch, BatchDocument
from contabilizador.exports.domain.document_builder import (
    ExportLineAssignment,
    build_world_office_document,
)
from contabilizador.exports.domain.errors import (
    CompanyNotFoundError,
    ConsecutiveCollisionError,
    ExportBlockedError,
    NothingToExportError,
    TotalsMismatchError,
)
from contabilizador.exports.domain.world_office import DocumentType, WorldOfficeDocument
from contabilizador.invoices.domain.status import InvoiceStatus


@dataclass(frozen=True, slots=True)
class ExportRequest:
    """Attributes:
    start_numbers: first consecutive per type chosen by the user; types left out
        get last used + 1.
    confirm_totals_mismatch / confirm_consecutive_collision: explicit user
        confirmation to export despite those warnings.
    """

    company_id: int
    cufes: Sequence[str]
    destination: Path
    start_numbers: Mapping[DocumentType, int] = field(default_factory=dict)
    confirm_totals_mismatch: bool = False
    confirm_consecutive_collision: bool = False


class ExportBatch:
    def __init__(
        self,
        *,
        companies: CompanyReader,
        candidates: ExportCandidateSource,
        suppliers: SupplierConfigReader,
        products: ProductReader,
        cost_centers: CostCenterReader,
        consecutives: ConsecutiveRepository,
        planner: PlanConsecutives,
        batches: BatchRepository,
        exporter: PurchaseImportExporter,
        invoice_status: InvoiceStatusUpdater,
        clock: Clock,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._companies = companies
        self._candidates = candidates
        self._suppliers = suppliers
        self._products = products
        self._cost_centers = cost_centers
        self._consecutives = consecutives
        self._planner = planner
        self._batches = batches
        self._exporter = exporter
        self._invoice_status = invoice_status
        self._clock = clock
        self._unit_of_work = unit_of_work

    def execute(self, request: ExportRequest) -> Batch:
        company = self._companies.get(request.company_id)
        if company is None:
            raise CompanyNotFoundError(request.company_id)
        cufes = list(dict.fromkeys(request.cufes))  # sin duplicados, conserva el orden
        if not cufes:
            raise NothingToExportError("no documents selected")

        # misma evaluacion que PreviewExport: la vista previa nunca promete de mas
        selection = assess_selection(
            request.company_id,
            cufes,
            candidates=self._candidates,
            suppliers=self._suppliers,
            products=self._products,
            cost_centers=self._cost_centers,
        )
        if selection.problems:
            raise ExportBlockedError(selection.problems)
        if selection.mismatches and not request.confirm_totals_mismatch:
            raise TotalsMismatchError(selection.mismatches)

        # orden cronologico estable: los consecutivos siguen la fecha de emision
        ordered = sorted(selection.candidates, key=lambda c: c.document.issue_date)
        counts = Counter(DocumentType.for_kind(c.document.kind) for c in ordered)
        plan = self._planner.execute(request.company_id, counts, request.start_numbers)
        if plan.collisions and not request.confirm_consecutive_collision:
            raise ConsecutiveCollisionError(plan.collisions)

        next_number = {t: r.first for t, r in plan.ranges.items()}
        documents: list[WorldOfficeDocument] = []
        for candidate in ordered:
            document_type = DocumentType.for_kind(candidate.document.kind)
            documents.append(
                build_world_office_document(
                    company=company,
                    document=candidate.document,
                    number=next_number[document_type],
                    assignments=_assignments(candidate, selection.cost_center_names),
                )
            )
            next_number[document_type] += 1

        # primero el archivo: si falla no se registra lote ni se queman consecutivos
        self._exporter.write(documents, request.destination)
        # lote, consecutivos y estados se confirman juntos o ninguno
        with self._unit_of_work.transaction():
            batch = self._batches.add(
                self._new_batch(company, request.destination, ordered, documents)
            )
            for document_type, consecutive_range in plan.ranges.items():
                last_used = self._consecutives.last_used(request.company_id, document_type) or 0
                self._consecutives.set_last_used(
                    request.company_id, document_type, max(last_used, consecutive_range.last)
                )
            self._invoice_status.set_status(request.company_id, cufes, InvoiceStatus.EXPORTED)
        return batch

    def _new_batch(
        self,
        company: Company,
        destination: Path,
        candidates: list[ExportCandidate],
        documents: list[WorldOfficeDocument],
    ) -> Batch:
        assert company.id is not None
        return Batch(
            id=None,
            company_id=company.id,
            file_path=destination,
            created_at=self._clock(),
            documents=tuple(
                BatchDocument(
                    cufe=candidate.document.cufe,
                    document_type=document.document_type,
                    number=document.number,
                    supplier_nit=candidate.document.supplier_nit,
                    supplier_name=candidate.document.supplier_name,
                    external_prefix=candidate.document.supplier_prefix,
                    external_number=candidate.document.supplier_number,
                    issue_date=candidate.document.issue_date,
                )
                for candidate, document in zip(candidates, documents, strict=True)
            ),
        )


def _assignments(
    candidate: ExportCandidate, cost_center_names: Mapping[str, str]
) -> tuple[ExportLineAssignment, ...]:
    result: list[ExportLineAssignment] = []
    for mapping in candidate.line_mappings:
        # ya validado: cada linea tiene producto y centro de costo existentes
        assert mapping is not None and mapping.cost_center_code is not None
        result.append(
            ExportLineAssignment(mapping.product_code, cost_center_names[mapping.cost_center_code])
        )
    return tuple(result)
