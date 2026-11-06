"""SQLAlchemy model for companies."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from contabilizador.shared.db import Base


class CompanyModel(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    internal_third_party_id: Mapped[str] = mapped_column(String(50))
    warehouse: Mapped[str] = mapped_column(String(100))
    unit: Mapped[str] = mapped_column(String(50))
    payment_form: Mapped[str] = mapped_column(String(50))
