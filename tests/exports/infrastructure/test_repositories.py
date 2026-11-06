from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.exports.domain.batch import Batch, BatchDocument, BatchStatus
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.exports.infrastructure.repositories import (
    SqlAlchemyBatchRepository,
    SqlAlchemyConsecutiveRepository,
)
from contabilizador.shared.db import Base, create_engine_for, create_session_factory

FC = DocumentType.FC
NC = DocumentType.NC


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine_for(tmp_path / "db" / "test.db")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def doc(cufe: str, document_type: DocumentType, number: int) -> BatchDocument:
    return BatchDocument(
        cufe=cufe,
        document_type=document_type,
        number=number,
        supplier_nit="900123456",
        supplier_name="PROVEEDOR",
        external_prefix="",
        external_number="00450",
        issue_date=date(2026, 8, 31),
    )


def new_batch(company_id: int, day: int, *documents: BatchDocument) -> Batch:
    return Batch(
        id=None,
        company_id=company_id,
        file_path=Path("salidas") / f"lote {day}.xlsx",
        created_at=datetime(2026, 9, day, 10, 30, tzinfo=UTC),
        documents=documents,
    )


def test_consecutives_start_empty_and_upsert(session_factory) -> None:
    repo = SqlAlchemyConsecutiveRepository(session_factory)
    assert repo.last_used(1, FC) is None

    repo.set_last_used(1, FC, 9420378244)
    repo.set_last_used(1, FC, 9420378245)
    repo.set_last_used(1, NC, 3)
    repo.set_last_used(2, FC, 7)

    assert repo.last_used(1, FC) == 9420378245
    assert repo.last_used(1, NC) == 3
    assert repo.last_used(2, FC) == 7


def test_batch_round_trip(session_factory) -> None:
    repo = SqlAlchemyBatchRepository(session_factory)
    batch = new_batch(1, 1, doc("a", FC, 9420378244), doc("b", NC, 1))

    stored = repo.add(batch)

    assert stored.id is not None
    loaded = repo.get(stored.id)
    assert loaded == stored
    assert loaded is not None
    assert loaded.created_at == datetime(2026, 9, 1, 10, 30, tzinfo=UTC)
    assert loaded.file_path == Path("salidas") / "lote 1.xlsx"
    assert loaded.documents[0].external_number == "00450"


def test_get_missing_batch_returns_none(session_factory) -> None:
    assert SqlAlchemyBatchRepository(session_factory).get(99) is None


def test_list_by_company_newest_first(session_factory) -> None:
    repo = SqlAlchemyBatchRepository(session_factory)
    first = repo.add(new_batch(1, 1, doc("a", FC, 1)))
    second = repo.add(new_batch(1, 2, doc("b", FC, 2)))
    repo.add(new_batch(2, 3, doc("c", FC, 1)))

    assert [b.id for b in repo.list_by_company(1)] == [second.id, first.id]


def test_update_persists_status_and_released_flags(session_factory) -> None:
    repo = SqlAlchemyBatchRepository(session_factory)
    stored = repo.add(new_batch(1, 1, doc("a", FC, 1), doc("b", FC, 2)))

    repo.update(stored.release(["a"]))
    assert [d.released for d in repo.get(stored.id or 0).documents] == [True, False]  # type: ignore[union-attr]

    voided = stored.void(reuse_numbers=True)
    repo.update(voided)
    loaded = repo.get(stored.id or 0)
    assert loaded == voided
    assert loaded is not None
    assert loaded.status is BatchStatus.VOIDED


def test_update_unknown_batch_fails(session_factory) -> None:
    repo = SqlAlchemyBatchRepository(session_factory)
    stored = repo.add(new_batch(1, 1, doc("a", FC, 1)))
    from dataclasses import replace

    with pytest.raises(LookupError):
        repo.update(replace(stored, id=999))
