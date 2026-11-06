from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.application.assign_line_mapping import (
    AssignLineMapping,
    LineAssignment,
)
from contabilizador.invoices.application.errors import ImportCancelledError
from contabilizador.invoices.application.import_invoice_files import ImportInvoiceFiles
from contabilizador.invoices.application.list_pending_documents import ListPendingDocuments
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.suggestion import MappingSource
from contabilizador.invoices.infrastructure.dian_xml_parser import LxmlDianParser
from contabilizador.invoices.infrastructure.file_document_source import FileDocumentSource
from contabilizador.invoices.infrastructure.sqlalchemy_invoice_repository import (
    SqlAlchemyInvoiceRepository,
)
from contabilizador.invoices.infrastructure.sqlalchemy_mapping_memory_repository import (
    SqlAlchemyMappingMemoryRepository,
)
from contabilizador.shared.db import SqlAlchemyUnitOfWork
from tests.invoices.application.fakes import FakeSupplierConfigs

COMPANY = 1


def test_import_fixtures_folder_end_to_end(
    session_factory: sessionmaker[Session], xml_fixtures_dir: Path
) -> None:
    invoices = SqlAlchemyInvoiceRepository(session_factory)
    memory = SqlAlchemyMappingMemoryRepository(session_factory)
    importer = ImportInvoiceFiles(
        FileDocumentSource(LxmlDianParser()), invoices, SqlAlchemyUnitOfWork(session_factory)
    )

    first = importer.execute(COMPANY, [xml_fixtures_dir])
    # 6 XML válidos; el zip repite invoice_plain y credit_note
    assert len(first.imported) == 6
    assert sorted(d.supplier_number for d in first.duplicates) == ["1001", "125"]
    assert [Path(s.source).name for s in first.ignored] == ["application_response.xml"]
    assert first.failed == ()
    # La nota crédito referencia invoice_plain, importada en el mismo lote
    assert first.credit_notes_without_original == ()

    second = importer.execute(COMPANY, [xml_fixtures_dir])
    assert second.imported == ()
    assert len(second.duplicates) == 8

    pending = ListPendingDocuments(invoices, memory, FakeSupplierConfigs()).execute(COMPANY)
    assert len(pending.documents) == 6
    assert all(doc.totals.matches for doc in pending.documents)
    assert {s.nit for s in pending.unconfigured_suppliers} == {
        "900123456",
        "1017000111",
        "800987654",
    }

    # Asignar manualmente la resma la recuerda para la nota crédito del mismo ítem
    resma = next(doc for doc in pending.documents if doc.invoice.document.supplier_number == "1001")
    AssignLineMapping(invoices, memory, SqlAlchemyUnitOfWork(session_factory)).execute(
        COMPANY, [LineAssignment(resma.lines[0].stored.id, LineMapping("P-PAPEL", "CC-ADM"))]
    )
    refreshed = ListPendingDocuments(invoices, memory, FakeSupplierConfigs()).execute(COMPANY)
    credit_note = next(d for d in refreshed.documents if d.invoice.document.is_credit_note)
    (line,) = credit_note.lines
    assert line.suggestion.source is MappingSource.MEMORY
    assert line.mapping == LineMapping("P-PAPEL", "CC-ADM")


def test_cancelled_import_stores_nothing(
    session_factory: sessionmaker[Session], xml_fixtures_dir: Path
) -> None:
    invoices = SqlAlchemyInvoiceRepository(session_factory)
    importer = ImportInvoiceFiles(
        FileDocumentSource(LxmlDianParser()), invoices, SqlAlchemyUnitOfWork(session_factory)
    )
    progress: list[tuple[int, int]] = []

    with pytest.raises(ImportCancelledError):
        importer.execute(
            COMPANY,
            [xml_fixtures_dir],
            on_progress=lambda done, total: progress.append((done, total)),
            is_cancelled=lambda: len(progress) > 3,
        )

    # 6 XML + 2 dentro del zip + la respuesta de aplicacion = 9 pasos
    assert progress[0] == (0, 9)
    assert invoices.list_by_status(COMPANY, list(InvoiceStatus)) == []
