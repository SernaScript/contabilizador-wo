from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.companies.domain.company import Company
from contabilizador.exports.application.export_batch import ExportBatch, ExportRequest
from contabilizador.exports.application.manage_batches import ListBatches, VoidBatch
from contabilizador.exports.application.plan_consecutives import PlanConsecutives
from contabilizador.exports.application.ports import ExportCandidate
from contabilizador.exports.domain.world_office import (
    HEADER_SHEET_NAME,
    LINE_SHEET_NAME,
    DocumentType,
)
from contabilizador.exports.infrastructure.repositories import (
    SqlAlchemyBatchRepository,
    SqlAlchemyConsecutiveRepository,
)
from contabilizador.exports.infrastructure.workbook_writer import WorldOfficeWorkbookWriter
from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.shared.db import (
    Base,
    SqlAlchemyUnitOfWork,
    create_engine_for,
    create_session_factory,
)
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.exports.application.fakes import (
    FakeCandidates,
    FakeClock,
    FakeCompanies,
    FakeCostCenters,
    FakeInvoiceStatus,
    FakeProducts,
    FakeSuppliers,
)

COMPANY = Company(
    id=1,
    name="WEARE DEV S.A.S",
    internal_third_party_id="1037663527",
    warehouse="Principal",
    unit="Und.",
)


def credit_note() -> ExportCandidate:
    # valores de credit_note.xml (ver tests/fixtures/README.md)
    document = ParsedDocument(
        cufe="cude-nc-125",
        kind=DocumentKind.CREDIT_NOTE,
        supplier_nit="900123456",
        supplier_name="COMERCIALIZADORA EJEMPLO S.A.S.",
        supplier_prefix="NC",
        supplier_number="125",
        issue_date=date(2026, 9, 5),
        due_date=None,
        lines=(
            ParsedLine("RESMA PAPEL CARTA 75G", Decimal("1"), Decimal("10000.00"), Decimal("19")),
        ),
        payable_amount=Decimal("11900.00"),
        billing_reference_cufe="cufe-fev-1001",
        source_file=Path("credit_note.xml"),
    )
    return ExportCandidate(
        document=document,
        status=InvoiceStatus.PENDING,
        line_mappings=(LineMapping("513515", "CC1"),),
    )


def test_export_and_void_against_sqlite_and_xlsx(tmp_path: Path) -> None:
    engine = create_engine_for(tmp_path / "data" / "app.db")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    batches = SqlAlchemyBatchRepository(session_factory)
    consecutives = SqlAlchemyConsecutiveRepository(session_factory)
    invoice_status = FakeInvoiceStatus()
    unit_of_work = SqlAlchemyUnitOfWork(session_factory)
    export = ExportBatch(
        companies=FakeCompanies(COMPANY),
        candidates=FakeCandidates(1, credit_note()),
        suppliers=FakeSuppliers(
            SupplierConfig(1, "900123456", "COMERCIALIZADORA", ("513515",), "513515")
        ),
        products=FakeProducts(Product(1, "513515", "PAPELERIA")),
        cost_centers=FakeCostCenters(CostCenter(1, "CC1", "GERENCIA GENERAL")),
        consecutives=consecutives,
        planner=PlanConsecutives(consecutives=consecutives, batches=batches),
        batches=batches,
        exporter=WorldOfficeWorkbookWriter(),
        invoice_status=invoice_status,
        clock=FakeClock(),
        unit_of_work=unit_of_work,
    )
    destination = tmp_path / "salidas" / "lote septiembre.xlsx"

    batch = export.execute(
        ExportRequest(
            company_id=1,
            cufes=["cude-nc-125"],
            destination=destination,
            start_numbers={DocumentType.NC: 40},
        )
    )

    workbook = openpyxl.load_workbook(destination)
    header = next(workbook[HEADER_SHEET_NAME].iter_rows(min_row=2, values_only=True))
    line = next(workbook[LINE_SHEET_NAME].iter_rows(min_row=2, values_only=True))
    assert header == (
        "WEARE DEV S.A.S",
        "NC",
        "NC",
        40,
        "05/09/2026",
        "1037663527",
        "900123456",
        "NC",
        "125",
        "RESMA PAPEL CARTA 75G",
        "Credito",
        0,
        0,
        "05/09/2026",
    )
    assert line == (
        "WEARE DEV S.A.S",
        "NC",
        "NC",
        40,
        "513515",
        "Principal",
        "Und.",
        1,
        0.19,
        10000,
        0,
        "05/09/2026",
        "RESMA PAPEL CARTA 75G",
        "GERENCIA GENERAL",
    )
    assert consecutives.last_used(1, DocumentType.NC) == 40

    VoidBatch(
        batches=batches,
        consecutives=consecutives,
        invoice_status=invoice_status,
        unit_of_work=unit_of_work,
    ).execute(batch.id or 0)

    assert consecutives.last_used(1, DocumentType.NC) == 39
    [history] = ListBatches(batches=batches).execute(1)
    assert history.is_voided
    assert history.numbers_reused
    assert [d.cufe for d in history.released_documents] == ["cude-nc-125"]


class FailingInvoiceStatus(FakeInvoiceStatus):
    def set_status(self, company_id: int, cufes: list[str], status: InvoiceStatus) -> None:
        raise RuntimeError("database is locked")


def test_failed_status_update_rolls_back_batch_and_consecutives(tmp_path: Path) -> None:
    engine = create_engine_for(tmp_path / "app.db")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    batches = SqlAlchemyBatchRepository(session_factory)
    consecutives = SqlAlchemyConsecutiveRepository(session_factory)
    consecutives.set_last_used(1, DocumentType.NC, 7)
    export = ExportBatch(
        companies=FakeCompanies(COMPANY),
        candidates=FakeCandidates(1, credit_note()),
        suppliers=FakeSuppliers(
            SupplierConfig(1, "900123456", "COMERCIALIZADORA", ("513515",), "513515")
        ),
        products=FakeProducts(Product(1, "513515", "PAPELERIA")),
        cost_centers=FakeCostCenters(CostCenter(1, "CC1", "GERENCIA GENERAL")),
        consecutives=consecutives,
        planner=PlanConsecutives(consecutives=consecutives, batches=batches),
        batches=batches,
        exporter=WorldOfficeWorkbookWriter(),
        invoice_status=FailingInvoiceStatus(),
        clock=FakeClock(),
        unit_of_work=SqlAlchemyUnitOfWork(session_factory),
    )

    with pytest.raises(RuntimeError):
        export.execute(
            ExportRequest(company_id=1, cufes=["cude-nc-125"], destination=tmp_path / "x.xlsx")
        )

    assert batches.list_by_company(1) == []
    assert consecutives.last_used(1, DocumentType.NC) == 7
    engine.dispose()
