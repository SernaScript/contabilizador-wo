"""Line assignments and the mapping memory commit together (one SQLite transaction)."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.application.assign_document_mapping import AssignDocumentMapping
from contabilizador.invoices.application.assign_line_mapping import (
    AssignLineMapping,
    LineAssignment,
)
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.stored import StoredInvoice
from contabilizador.invoices.infrastructure.sqlalchemy_invoice_repository import (
    SqlAlchemyInvoiceRepository,
)
from contabilizador.invoices.infrastructure.sqlalchemy_mapping_memory_repository import (
    SqlAlchemyMappingMemoryRepository,
)
from contabilizador.shared.db import SqlAlchemyUnitOfWork
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.invoices.application.fakes import FakeSupplierConfigs
from tests.invoices.factories import make_document

COMPANY = 1
MAPPING = LineMapping("P-01", "CC-ADM")


class FailingMemory(SqlAlchemyMappingMemoryRepository):
    def remember(self, key: MappingKey, mapping: LineMapping) -> None:
        super().remember(key, mapping)
        raise RuntimeError("fallo al recordar")


def stored_invoice(invoices: SqlAlchemyInvoiceRepository) -> StoredInvoice:
    stored = invoices.get(COMPANY, invoices.add(COMPANY, make_document()))
    assert stored is not None
    return stored


def first_line_key(stored: StoredInvoice) -> MappingKey:
    return mapping_key_for(COMPANY, stored.document.supplier_nit, stored.lines[0].line.description)


def test_assignments_and_memory_commit_together(session_factory: sessionmaker[Session]) -> None:
    invoices = SqlAlchemyInvoiceRepository(session_factory)
    memory = SqlAlchemyMappingMemoryRepository(session_factory)
    stored = stored_invoice(invoices)
    use_case = AssignLineMapping(invoices, memory, SqlAlchemyUnitOfWork(session_factory))

    use_case.execute(COMPANY, [LineAssignment(line.id, MAPPING) for line in stored.lines])

    reloaded = invoices.get(COMPANY, stored.id)
    assert reloaded is not None
    assert [line.assigned for line in reloaded.lines] == [MAPPING, MAPPING]
    assert memory.get(first_line_key(stored)) == MAPPING


def test_failed_memory_write_rolls_back_the_assignment(
    session_factory: sessionmaker[Session],
) -> None:
    invoices = SqlAlchemyInvoiceRepository(session_factory)
    stored = stored_invoice(invoices)
    use_case = AssignLineMapping(
        invoices, FailingMemory(session_factory), SqlAlchemyUnitOfWork(session_factory)
    )

    with pytest.raises(RuntimeError):
        use_case.execute(COMPANY, [LineAssignment(stored.lines[0].id, MAPPING)])

    reloaded = invoices.get(COMPANY, stored.id)
    assert reloaded is not None and reloaded.lines[0].assigned is None
    memory = SqlAlchemyMappingMemoryRepository(session_factory)
    assert memory.get(first_line_key(stored)) is None


def document_use_case(
    session_factory: sessionmaker[Session], memory: SqlAlchemyMappingMemoryRepository
) -> AssignDocumentMapping:
    config = SupplierConfig(COMPANY, "900123456", "COMERCIALIZADORA", ("P-02",), "P-02")
    return AssignDocumentMapping(
        SqlAlchemyInvoiceRepository(session_factory),
        memory,
        FakeSupplierConfigs(config),
        SqlAlchemyUnitOfWork(session_factory),
    )


def test_document_mapping_commits_lines_and_memory_together(
    session_factory: sessionmaker[Session],
) -> None:
    invoices = SqlAlchemyInvoiceRepository(session_factory)
    memory = SqlAlchemyMappingMemoryRepository(session_factory)
    stored = stored_invoice(invoices)

    document_use_case(session_factory, memory).execute(
        COMPANY, [stored.id], cost_center_code="CC-1"
    )

    expected = LineMapping("P-02", "CC-1")
    reloaded = invoices.get(COMPANY, stored.id)
    assert reloaded is not None
    assert [line.assigned for line in reloaded.lines] == [expected, expected]
    assert memory.get(first_line_key(stored)) == expected


def test_failed_document_mapping_changes_nothing(session_factory: sessionmaker[Session]) -> None:
    invoices = SqlAlchemyInvoiceRepository(session_factory)
    stored = stored_invoice(invoices)

    with pytest.raises(RuntimeError):
        document_use_case(session_factory, FailingMemory(session_factory)).execute(
            COMPANY, [stored.id], product_code="P-02"
        )

    reloaded = invoices.get(COMPANY, stored.id)
    assert reloaded is not None
    assert [line.assigned for line in reloaded.lines] == [None, None]
