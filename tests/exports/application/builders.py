"""Builders and wiring shared by the export use case tests (fakes only, no database)."""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.companies.domain.company import Company
from contabilizador.exports.application.export_batch import ExportBatch, ExportRequest
from contabilizador.exports.application.manage_batches import ReleaseDocuments, VoidBatch
from contabilizador.exports.application.plan_consecutives import PlanConsecutives
from contabilizador.exports.application.ports import ExportCandidate
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.exports.application.fakes import (
    FakeBatches,
    FakeCandidates,
    FakeClock,
    FakeCompanies,
    FakeConsecutives,
    FakeCostCenters,
    FakeExporter,
    FakeInvoiceStatus,
    FakeProducts,
    FakeSuppliers,
    FakeUnitOfWork,
)

FC = DocumentType.FC
NC = DocumentType.NC
COMPANY_ID = 1
NIT = "900123456"
COMPANY = Company(
    id=COMPANY_ID,
    name="WEARE DEV S.A.S",
    internal_third_party_id="1037663527",
    warehouse="Principal",
    unit="Und.",
)
MAPPED = LineMapping(product_code="513515", cost_center_code="CC1")


def parsed(
    cufe: str,
    *,
    kind: DocumentKind = DocumentKind.INVOICE,
    nit: str = NIT,
    issue_date: date = date(2026, 8, 31),
    payable: Decimal = Decimal("119.00"),
) -> ParsedDocument:
    return ParsedDocument(
        cufe=cufe,
        kind=kind,
        supplier_nit=nit,
        supplier_name="PROVEEDOR",
        supplier_prefix="FEV",
        supplier_number=f"0{cufe}",
        issue_date=issue_date,
        due_date=None,
        lines=(ParsedLine(f"ITEM {cufe}", Decimal("1"), Decimal("100"), Decimal("19")),),
        payable_amount=payable,
        billing_reference_cufe=None,
        source_file=Path(f"{cufe}.xml"),
    )


def candidate(
    cufe: str,
    *,
    mapping: LineMapping | None = MAPPED,
    status: InvoiceStatus = InvoiceStatus.PENDING,
    **kwargs: object,
) -> ExportCandidate:
    return ExportCandidate(
        document=parsed(cufe, **kwargs),  # type: ignore[arg-type]
        status=status,
        line_mappings=(mapping,),
    )


@dataclass
class Harness:
    candidates: FakeCandidates
    companies: FakeCompanies = field(default_factory=lambda: FakeCompanies(COMPANY))
    suppliers: FakeSuppliers = field(
        default_factory=lambda: FakeSuppliers(
            SupplierConfig(COMPANY_ID, NIT, "PROVEEDOR", ("513515",), "513515")
        )
    )
    products: FakeProducts = field(
        default_factory=lambda: FakeProducts(Product(COMPANY_ID, "513515", "PAPELERIA"))
    )
    cost_centers: FakeCostCenters = field(
        default_factory=lambda: FakeCostCenters(CostCenter(COMPANY_ID, "CC1", "GERENCIA GENERAL"))
    )
    invoice_status: FakeInvoiceStatus = field(default_factory=FakeInvoiceStatus)
    consecutives: FakeConsecutives = field(default_factory=FakeConsecutives)
    batches: FakeBatches = field(default_factory=FakeBatches)
    exporter: FakeExporter = field(default_factory=FakeExporter)
    clock: FakeClock = field(default_factory=FakeClock)
    unit_of_work: FakeUnitOfWork = field(default_factory=FakeUnitOfWork)

    def __post_init__(self) -> None:
        # los fakes reportan sus escrituras para verificar la transaccion
        for repository in (self.batches, self.consecutives, self.invoice_status):
            repository.unit_of_work = self.unit_of_work

    @property
    def planner(self) -> PlanConsecutives:
        return PlanConsecutives(consecutives=self.consecutives, batches=self.batches)

    @property
    def export(self) -> ExportBatch:
        return ExportBatch(
            companies=self.companies,
            candidates=self.candidates,
            suppliers=self.suppliers,
            products=self.products,
            cost_centers=self.cost_centers,
            consecutives=self.consecutives,
            planner=self.planner,
            batches=self.batches,
            exporter=self.exporter,
            invoice_status=self.invoice_status,
            clock=self.clock,
            unit_of_work=self.unit_of_work,
        )

    @property
    def void(self) -> VoidBatch:
        return VoidBatch(
            batches=self.batches,
            consecutives=self.consecutives,
            invoice_status=self.invoice_status,
            unit_of_work=self.unit_of_work,
        )

    @property
    def release(self) -> ReleaseDocuments:
        return ReleaseDocuments(
            batches=self.batches,
            invoice_status=self.invoice_status,
            unit_of_work=self.unit_of_work,
        )


def harness(*candidates: ExportCandidate) -> Harness:
    return Harness(candidates=FakeCandidates(COMPANY_ID, *candidates))


def request(*cufes: str, **kwargs: object) -> ExportRequest:
    return ExportRequest(
        company_id=COMPANY_ID,
        cufes=cufes,
        destination=Path("out") / "lote.xlsx",
        **kwargs,  # type: ignore[arg-type]
    )
