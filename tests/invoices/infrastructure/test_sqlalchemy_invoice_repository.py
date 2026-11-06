from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.infrastructure.sqlalchemy_invoice_repository import (
    SqlAlchemyInvoiceRepository,
)
from contabilizador.shared.db import SqlAlchemyUnitOfWork
from tests.invoices.factories import make_document
from tests.invoices.query_counter import count_queries


@pytest.fixture
def repo(session_factory: sessionmaker[Session]) -> SqlAlchemyInvoiceRepository:
    return SqlAlchemyInvoiceRepository(session_factory)


def test_add_and_exists(repo: SqlAlchemyInvoiceRepository) -> None:
    assert not repo.exists(1, "cufe-1")
    invoice_id = repo.add(1, make_document())
    assert invoice_id > 0
    assert repo.exists(1, "cufe-1")
    # Mismo CUFE en otra empresa es otro documento
    assert not repo.exists(2, "cufe-1")


def test_round_trip_preserves_document_exactly(repo: SqlAlchemyInvoiceRepository) -> None:
    document = make_document()
    invoice_id = repo.add(1, document)
    stored = repo.get(1, invoice_id)
    assert stored is not None
    assert stored.status is InvoiceStatus.PENDING
    assert stored.company_id == 1
    assert stored.document == document
    # Decimales exactos (sin pasar por float)
    assert str(stored.document.lines[1].line_extension_amount) == "125000.33"
    assert stored.document.supplier_number == "001001"
    assert [line.position for line in stored.lines] == [0, 1]
    assert all(line.assigned is None for line in stored.lines)


def test_round_trip_credit_note_without_due_date(repo: SqlAlchemyInvoiceRepository) -> None:
    document = make_document(
        cufe="cude-1",
        kind=DocumentKind.CREDIT_NOTE,
        due_date=None,
        billing_reference_cufe="cufe-1",
        supplier_prefix="",
    )
    stored = repo.get(1, repo.add(1, document))
    assert stored is not None
    assert stored.document == document
    assert stored.document.effective_due_date == date(2026, 8, 31)


def test_unique_company_cufe(repo: SqlAlchemyInvoiceRepository) -> None:
    repo.add(1, make_document())
    repo.add(2, make_document())
    with pytest.raises(IntegrityError):
        repo.add(1, make_document())


def test_get_from_other_company_returns_none(repo: SqlAlchemyInvoiceRepository) -> None:
    invoice_id = repo.add(1, make_document())
    assert repo.get(2, invoice_id) is None
    assert repo.get(1, 9999) is None


def test_get_by_cufe(repo: SqlAlchemyInvoiceRepository) -> None:
    repo.add(1, make_document())
    stored = repo.get_by_cufe(1, "cufe-1")
    assert stored is not None and stored.document.cufe == "cufe-1"
    assert repo.get_by_cufe(2, "cufe-1") is None


def test_set_status_and_list_by_status(repo: SqlAlchemyInvoiceRepository) -> None:
    repo.add(1, make_document(cufe="a", issue_date=date(2026, 9, 2)))
    repo.add(1, make_document(cufe="b", issue_date=date(2026, 9, 1)))
    repo.add(1, make_document(cufe="c"))
    repo.add(2, make_document(cufe="a"))
    repo.set_status(1, ["a", "c"], InvoiceStatus.EXPORTED)
    pending = repo.list_by_status(1, [InvoiceStatus.PENDING])
    assert [s.document.cufe for s in pending] == ["b"]
    exported = repo.list_by_status(1, [InvoiceStatus.EXPORTED])
    assert {s.document.cufe for s in exported} == {"a", "c"}
    assert repo.list_by_status(2, [InvoiceStatus.PENDING])[0].status is InvoiceStatus.PENDING


def test_list_is_ordered_by_issue_date_then_id(repo: SqlAlchemyInvoiceRepository) -> None:
    repo.add(1, make_document(cufe="late", issue_date=date(2026, 9, 9)))
    repo.add(1, make_document(cufe="early", issue_date=date(2026, 9, 1)))
    stored = repo.list_by_status(1, [InvoiceStatus.PENDING, InvoiceStatus.RELEASED])
    assert [s.document.cufe for s in stored] == ["early", "late"]


def test_assign_line_and_get_by_line(repo: SqlAlchemyInvoiceRepository) -> None:
    invoice_id = repo.add(1, make_document())
    stored = repo.get(1, invoice_id)
    assert stored is not None
    line_id = stored.lines[1].id
    repo.assign_line(line_id, LineMapping("P-01", "CC-ADM"))
    owner = repo.get_by_line(1, line_id)
    assert owner is not None and owner.id == invoice_id
    line = owner.line(line_id)
    assert line is not None
    assert line.assigned == LineMapping("P-01", "CC-ADM")
    assert owner.lines[0].assigned is None
    assert repo.get_by_line(2, line_id) is None
    repo.assign_line(line_id, None)
    cleared = repo.get(1, invoice_id)
    assert cleared is not None and cleared.lines[1].assigned is None


def test_assign_line_without_cost_center(repo: SqlAlchemyInvoiceRepository) -> None:
    invoice_id = repo.add(1, make_document())
    stored = repo.get(1, invoice_id)
    assert stored is not None
    repo.assign_line(stored.lines[0].id, LineMapping("P-01", None))
    reloaded = repo.get(1, invoice_id)
    assert reloaded is not None
    assert reloaded.lines[0].assigned == LineMapping("P-01", None)


def test_decimal_amounts_are_kept_as_text(repo: SqlAlchemyInvoiceRepository) -> None:
    invoice_id = repo.add(1, make_document(payable_amount=Decimal("0.1") + Decimal("0.2")))
    stored = repo.get(1, invoice_id)
    assert stored is not None and stored.document.payable_amount == Decimal("0.3")


def test_set_status_joins_the_unit_of_work_transaction(
    repo: SqlAlchemyInvoiceRepository, session_factory: sessionmaker[Session]
) -> None:
    repo.add(1, make_document(cufe="a"))

    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(session_factory).transaction():
        repo.set_status(1, ["a"], InvoiceStatus.EXPORTED)
        raise RuntimeError("fallo posterior")

    assert repo.get_by_cufe(1, "a").status is InvoiceStatus.PENDING  # type: ignore[union-attr]


def test_list_by_cufes_returns_known_documents_of_the_company(
    repo: SqlAlchemyInvoiceRepository,
) -> None:
    repo.add(1, make_document(cufe="late", issue_date=date(2026, 9, 9)))
    repo.add(1, make_document(cufe="early", issue_date=date(2026, 9, 1)))
    repo.add(2, make_document(cufe="other"))

    found = repo.list_by_cufes(1, ["late", "missing", "other", "early", "late"])

    assert [s.document.cufe for s in found] == ["early", "late"]
    assert all(len(s.lines) == 2 for s in found)


def test_list_by_cufes_without_cufes_does_not_query(
    repo: SqlAlchemyInvoiceRepository, session_factory: sessionmaker[Session]
) -> None:
    with count_queries(session_factory.kw["bind"]) as counter:
        assert repo.list_by_cufes(1, []) == []
    assert counter.count == 0


def test_list_by_cufes_query_count_does_not_grow_with_documents(
    repo: SqlAlchemyInvoiceRepository, session_factory: sessionmaker[Session]
) -> None:
    cufes = [f"c{i}" for i in range(30)]
    for cufe in cufes:
        repo.add(1, make_document(cufe=cufe))
    engine = session_factory.kw["bind"]

    with count_queries(engine) as one:
        repo.list_by_cufes(1, cufes[:1])
    with count_queries(engine) as many:
        found = repo.list_by_cufes(1, cufes)

    assert len(found) == 30
    assert many.count == one.count
