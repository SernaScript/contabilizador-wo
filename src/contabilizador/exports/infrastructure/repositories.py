"""SQLAlchemy adapters for the exports ports. Each call runs in its own transaction unless
a ``SqlAlchemyUnitOfWork`` transaction is active, which it then joins."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from contabilizador.exports.domain.batch import Batch, BatchDocument, BatchStatus
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.exports.infrastructure.orm import BatchDocumentRow, BatchRow, ConsecutiveRow
from contabilizador.shared.db import read_session, write_session


class SqlAlchemyConsecutiveRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def last_used(self, company_id: int, document_type: DocumentType) -> int | None:
        with read_session(self._session_factory) as session:
            row = session.get(ConsecutiveRow, (company_id, document_type.value))
            return row.last_used if row else None

    def set_last_used(self, company_id: int, document_type: DocumentType, number: int) -> None:
        with write_session(self._session_factory) as session:
            session.merge(
                ConsecutiveRow(
                    company_id=company_id, document_type=document_type.value, last_used=number
                )
            )


def _to_utc_naive(value: datetime) -> datetime:
    # datetimes sin zona se asumen UTC
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).replace(tzinfo=None)


def _document_row(position: int, document: BatchDocument) -> BatchDocumentRow:
    return BatchDocumentRow(
        position=position,
        cufe=document.cufe,
        document_type=document.document_type.value,
        number=document.number,
        supplier_nit=document.supplier_nit,
        supplier_name=document.supplier_name,
        external_prefix=document.external_prefix,
        external_number=document.external_number,
        issue_date=document.issue_date,
        released=document.released,
    )


def _to_domain(row: BatchRow) -> Batch:
    return Batch(
        id=row.id,
        company_id=row.company_id,
        file_path=Path(row.file_path),
        created_at=row.created_at.replace(tzinfo=UTC),
        status=BatchStatus(row.status),
        numbers_reused=row.numbers_reused,
        documents=tuple(
            BatchDocument(
                cufe=d.cufe,
                document_type=DocumentType(d.document_type),
                number=d.number,
                supplier_nit=d.supplier_nit,
                supplier_name=d.supplier_name,
                external_prefix=d.external_prefix,
                external_number=d.external_number,
                issue_date=d.issue_date,
                released=d.released,
            )
            for d in row.documents
        ),
    )


class SqlAlchemyBatchRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, batch: Batch) -> Batch:
        if batch.id is not None:
            raise ValueError("batch is already persisted")
        with write_session(self._session_factory) as session:
            row = BatchRow(
                company_id=batch.company_id,
                file_path=str(batch.file_path),
                created_at=_to_utc_naive(batch.created_at),
                status=batch.status.value,
                numbers_reused=batch.numbers_reused,
                documents=[_document_row(i, d) for i, d in enumerate(batch.documents)],
            )
            session.add(row)
            session.flush()
            return replace(batch, id=row.id)

    def get(self, batch_id: int) -> Batch | None:
        with read_session(self._session_factory) as session:
            row = session.get(BatchRow, batch_id, options=[selectinload(BatchRow.documents)])
            return _to_domain(row) if row else None

    def list_by_company(self, company_id: int) -> list[Batch]:
        with read_session(self._session_factory) as session:
            rows = session.scalars(
                select(BatchRow)
                .where(BatchRow.company_id == company_id)
                .options(selectinload(BatchRow.documents))
                .order_by(BatchRow.created_at.desc(), BatchRow.id.desc())
            )
            return [_to_domain(row) for row in rows]

    def update(self, batch: Batch) -> None:
        with write_session(self._session_factory) as session:
            row = session.get(BatchRow, batch.id) if batch.id is not None else None
            if row is None:
                raise LookupError(f"batch {batch.id} not found")
            row.status = batch.status.value
            row.numbers_reused = batch.numbers_reused
            released = {d.cufe: d.released for d in batch.documents}
            for document_row in row.documents:
                document_row.released = released.get(document_row.cufe, document_row.released)
