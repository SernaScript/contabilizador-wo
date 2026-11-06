"""SQLAlchemy models of the exports module (registered in the shared Base).

``company_id`` has no foreign key on purpose: the companies table is owned by another
module; the integration migration may add it.
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from contabilizador.shared.db import Base


class ConsecutiveRow(Base):
    __tablename__ = "export_consecutives"

    company_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_type: Mapped[str] = mapped_column(String(2), primary_key=True)
    last_used: Mapped[int] = mapped_column(BigInteger)


class BatchRow(Base):
    __tablename__ = "export_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, index=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    # UTC sin zona (SQLite no guarda tz); el repositorio la vuelve a poner
    created_at: Mapped[datetime] = mapped_column(DateTime())
    status: Mapped[str] = mapped_column(String(16))
    numbers_reused: Mapped[bool] = mapped_column(default=False)

    documents: Mapped[list["BatchDocumentRow"]] = relationship(
        back_populates="batch",
        cascade="all, delete-orphan",
        order_by="BatchDocumentRow.position",
    )


class BatchDocumentRow(Base):
    __tablename__ = "export_batch_documents"
    __table_args__ = (
        UniqueConstraint("batch_id", "cufe"),
        UniqueConstraint("batch_id", "document_type", "number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("export_batches.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    cufe: Mapped[str] = mapped_column(String(128), index=True)
    document_type: Mapped[str] = mapped_column(String(2))
    number: Mapped[int] = mapped_column(BigInteger)
    supplier_nit: Mapped[str] = mapped_column(String(20))
    supplier_name: Mapped[str] = mapped_column(String(255))
    external_prefix: Mapped[str] = mapped_column(String(20))
    external_number: Mapped[str] = mapped_column(String(40))
    issue_date: Mapped[date] = mapped_column(Date())
    released: Mapped[bool] = mapped_column(default=False)

    batch: Mapped[BatchRow] = relationship(back_populates="documents")
