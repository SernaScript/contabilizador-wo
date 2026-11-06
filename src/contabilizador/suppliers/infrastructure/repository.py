"""SQLAlchemy adapter for SupplierConfigRepository."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.suppliers.infrastructure.orm import SupplierConfigModel, SupplierProductModel


def _to_domain(model: SupplierConfigModel) -> SupplierConfig:
    return SupplierConfig(
        company_id=model.company_id,
        nit=model.nit,
        name=model.name,
        product_codes=tuple(p.product_code for p in model.products),
        default_product_code=model.default_product_code,
    )


def _find(session: Session, company_id: int, nit: str) -> SupplierConfigModel | None:
    stmt = select(SupplierConfigModel).where(
        SupplierConfigModel.company_id == company_id, SupplierConfigModel.nit == nit
    )
    return session.scalars(stmt).first()


class SqlAlchemySupplierConfigRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, company_id: int, nit: str) -> SupplierConfig | None:
        with self._session_factory() as session:
            model = _find(session, company_id, nit)
            return _to_domain(model) if model else None

    def list_by_company(self, company_id: int) -> list[SupplierConfig]:
        with self._session_factory() as session:
            stmt = (
                select(SupplierConfigModel)
                .where(SupplierConfigModel.company_id == company_id)
                .order_by(SupplierConfigModel.name, SupplierConfigModel.nit)
            )
            return [_to_domain(m) for m in session.scalars(stmt)]

    def save(self, config: SupplierConfig) -> None:
        with self._session_factory() as session:
            model = _find(session, config.company_id, config.nit)
            if model is None:
                model = SupplierConfigModel(company_id=config.company_id, nit=config.nit)
                session.add(model)
            model.name = config.name
            model.default_product_code = config.default_product_code
            # Reemplazo completo de la lista de productos
            model.products.clear()
            session.flush()
            model.products.extend(
                SupplierProductModel(position=i, product_code=code)
                for i, code in enumerate(config.product_codes)
            )
            session.commit()

    def delete(self, company_id: int, nit: str) -> None:
        with self._session_factory() as session:
            model = _find(session, company_id, nit)
            if model is not None:
                session.delete(model)
                session.commit()
