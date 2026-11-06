"""SQLAlchemy models of the invoices module."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from contabilizador.shared.db import Base


class DecimalText(TypeDecorator[Decimal]):
    """Decimal stored as text: SQLite NUMERIC would round-trip through float."""

    impl = String(64)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        return None if value is None else str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InvoiceRow(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("company_id", "cufe"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Sin FK a companies: el módulo invoices no depende del esquema de companies
    company_id: Mapped[int] = mapped_column(Integer, index=True)
    cufe: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), index=True)
    supplier_nit: Mapped[str] = mapped_column(String(20), index=True)
    supplier_name: Mapped[str] = mapped_column(String(255))
    supplier_prefix: Mapped[str] = mapped_column(String(20))
    supplier_number: Mapped[str] = mapped_column(String(50))
    issue_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payable_amount: Mapped[Decimal] = mapped_column(DecimalText)
    billing_reference_cufe: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file: Mapped[str] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    lines: Mapped[list["InvoiceLineRow"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineRow.position",
        lazy="selectin",
    )


class InvoiceLineRow(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (UniqueConstraint("invoice_id", "position"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[Decimal] = mapped_column(DecimalText)
    line_extension_amount: Mapped[Decimal] = mapped_column(DecimalText)
    tax_percent: Mapped[Decimal] = mapped_column(DecimalText)
    product_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost_center_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    invoice: Mapped[InvoiceRow] = relationship(back_populates="lines")


class MappingMemoryRow(Base):
    __tablename__ = "line_mapping_memory"
    __table_args__ = (UniqueConstraint("company_id", "supplier_nit", "normalized_description"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(Integer)
    supplier_nit: Mapped[str] = mapped_column(String(20))
    normalized_description: Mapped[str] = mapped_column(Text)
    product_code: Mapped[str] = mapped_column(String(64))
    cost_center_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
