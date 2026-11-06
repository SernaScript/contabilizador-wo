"""The documents screen refresh (pending list + export preview) runs a constant number of
SQL statements: it must not grow with the number of invoices or lines."""

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine

# Registrar todas las tablas en el metadata compartido
import contabilizador.catalog.infrastructure.orm
import contabilizador.exports.infrastructure.orm
import contabilizador.invoices.infrastructure.orm
import contabilizador.suppliers.infrastructure.orm  # noqa: F401
from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.catalog.infrastructure.repository import (
    SqlAlchemyCostCenterRepository,
    SqlAlchemyProductRepository,
)
from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository
from contabilizador.exports.application.plan_consecutives import PlanConsecutives
from contabilizador.exports.application.preview_export import PreviewExport
from contabilizador.exports.infrastructure.invoice_candidate_source import (
    InvoiceExportCandidateSource,
)
from contabilizador.exports.infrastructure.repositories import (
    SqlAlchemyBatchRepository,
    SqlAlchemyConsecutiveRepository,
)
from contabilizador.invoices.application.list_pending_documents import ListPendingDocuments
from contabilizador.invoices.domain.document import DocumentKind, ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.infrastructure.sqlalchemy_invoice_repository import (
    SqlAlchemyInvoiceRepository,
)
from contabilizador.invoices.infrastructure.sqlalchemy_mapping_memory_repository import (
    SqlAlchemyMappingMemoryRepository,
)
from contabilizador.shared.db import Base, create_engine_for, create_session_factory
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.suppliers.infrastructure.repository import SqlAlchemySupplierConfigRepository
from tests.invoices.factories import make_document
from tests.invoices.query_counter import count_queries

NIT = "900123456"
MAPPED = LineMapping("P-1", "CC-1")


@dataclass
class Screen:
    engine: Engine
    company_id: int
    invoices: SqlAlchemyInvoiceRepository
    memory: SqlAlchemyMappingMemoryRepository
    list_pending: ListPendingDocuments
    preview: PreviewExport


def build_screen(db_path: Path) -> Screen:
    engine = create_engine_for(db_path)
    Base.metadata.create_all(engine)
    sessions = create_session_factory(engine)
    companies = SqlAlchemyCompanyRepository(sessions)
    company = companies.save(Company(None, "WEARE DEV S.A.S", "1017", "Principal", "Und."))
    assert company.id is not None
    products = SqlAlchemyProductRepository(sessions)
    products.save(Product(company.id, "P-1", "Papeleria"))
    cost_centers = SqlAlchemyCostCenterRepository(sessions)
    cost_centers.save(CostCenter(company.id, "CC-1", "Administracion"))
    suppliers = SqlAlchemySupplierConfigRepository(sessions)
    suppliers.save(SupplierConfig(company.id, NIT, "PROVEEDOR", ("P-1",), "P-1"))
    invoices = SqlAlchemyInvoiceRepository(sessions)
    memory = SqlAlchemyMappingMemoryRepository(sessions)
    batches = SqlAlchemyBatchRepository(sessions)
    consecutives = SqlAlchemyConsecutiveRepository(sessions)
    return Screen(
        engine=engine,
        company_id=company.id,
        invoices=invoices,
        memory=memory,
        list_pending=ListPendingDocuments(invoices, memory, suppliers),
        preview=PreviewExport(
            companies=companies,
            candidates=InvoiceExportCandidateSource(invoices, memory, suppliers),
            suppliers=suppliers,
            products=products,
            cost_centers=cost_centers,
            planner=PlanConsecutives(consecutives=consecutives, batches=batches),
        ),
    )


def seed(screen: Screen, *, invoices: int, lines: int) -> None:
    """Every line mapped: the first one by hand, the others through the memory."""
    for number in range(invoices):
        _add(screen, f"fc-{number}", DocumentKind.INVOICE, lines)
    # nota credito cuya factura original no esta en la lista de pendientes
    _add(screen, "nc", DocumentKind.CREDIT_NOTE, 1, reference="original-ausente")


def _add(
    screen: Screen, cufe: str, kind: DocumentKind, lines: int, reference: str | None = None
) -> None:
    parsed_lines = tuple(
        ParsedLine(f"ITEM {cufe} {n}", Decimal(1), Decimal(100), Decimal(19)) for n in range(lines)
    )
    document = make_document(
        cufe=cufe,
        kind=kind,
        lines=parsed_lines,
        payable_amount=Decimal(119) * lines,
        billing_reference_cufe=reference,
    )
    stored = screen.invoices.get(
        screen.company_id, screen.invoices.add(screen.company_id, document)
    )
    assert stored is not None
    screen.invoices.assign_line(stored.lines[0].id, MAPPED)
    for line in parsed_lines[1:]:
        screen.memory.remember(mapping_key_for(screen.company_id, NIT, line.description), MAPPED)


def refresh_queries(screen: Screen) -> tuple[int, int]:
    with count_queries(screen.engine) as listing:
        pending = screen.list_pending.execute(screen.company_id)
    cufes = [document.invoice.document.cufe for document in pending.documents]
    with count_queries(screen.engine) as preview:
        result = screen.preview.execute(screen.company_id, cufes)
    assert set(result.exportable_cufes) == set(cufes)
    return listing.count, preview.count


def test_refresh_query_count_does_not_grow_with_invoices_or_lines(tmp_path: Path) -> None:
    small = build_screen(tmp_path / "small.db")
    seed(small, invoices=1, lines=2)
    large = build_screen(tmp_path / "large.db")
    seed(large, invoices=15, lines=4)

    assert refresh_queries(large) == refresh_queries(small)

    small.engine.dispose()
    large.engine.dispose()
