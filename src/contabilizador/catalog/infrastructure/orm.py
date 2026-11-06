"""SQLAlchemy models for products and cost centers."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

# Garantiza que la tabla companies exista en el metadata para la FK
import contabilizador.companies.infrastructure.orm  # noqa: F401
from contabilizador.shared.db import Base


class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("company_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))


class CostCenterModel(Base):
    __tablename__ = "cost_centers"
    __table_args__ = (UniqueConstraint("company_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(300))
