"""SQLAlchemy models for supplier configuration."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Garantiza que la tabla companies exista en el metadata para la FK
import contabilizador.companies.infrastructure.orm  # noqa: F401
from contabilizador.shared.db import Base


class SupplierConfigModel(Base):
    __tablename__ = "supplier_configs"
    __table_args__ = (UniqueConstraint("company_id", "nit"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    nit: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(300))
    default_product_code: Mapped[str] = mapped_column(String(100))
    products: Mapped[list["SupplierProductModel"]] = relationship(
        cascade="all, delete-orphan",
        order_by="SupplierProductModel.position",
        passive_deletes=True,
    )


class SupplierProductModel(Base):
    __tablename__ = "supplier_products"
    __table_args__ = (UniqueConstraint("supplier_config_id", "product_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_config_id: Mapped[int] = mapped_column(
        ForeignKey("supplier_configs.id", ondelete="CASCADE")
    )
    position: Mapped[int]  # conserva el orden elegido por el usuario
    product_code: Mapped[str] = mapped_column(String(100))
