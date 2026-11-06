"""SQLAlchemy adapters for the catalog repositories."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.catalog.infrastructure.orm import CostCenterModel, ProductModel


class _SqlAlchemyCodeNameRepository[
    ModelT: (ProductModel, CostCenterModel),
    EntityT: (Product, CostCenter),
]:
    """Shared upsert/list/delete logic: both catalogs are (company, code, name)."""

    _model: type[ModelT]
    _entity: type[EntityT]

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _find(self, session: Session, company_id: int, code: str) -> ModelT | None:
        stmt = select(self._model).where(
            self._model.company_id == company_id, self._model.code == code
        )
        return session.scalars(stmt).first()

    def _upsert(self, session: Session, item: EntityT) -> None:
        model = self._find(session, item.company_id, item.code)
        if model is None:
            session.add(self._model(company_id=item.company_id, code=item.code, name=item.name))
        else:
            model.name = item.name
        session.flush()

    def get(self, company_id: int, code: str) -> EntityT | None:
        with self._session_factory() as session:
            model = self._find(session, company_id, code)
            return self._entity(model.company_id, model.code, model.name) if model else None

    def list_by_company(self, company_id: int) -> list[EntityT]:
        with self._session_factory() as session:
            stmt = (
                select(self._model)
                .where(self._model.company_id == company_id)
                .order_by(self._model.code)
            )
            return [self._entity(m.company_id, m.code, m.name) for m in session.scalars(stmt)]

    def _save_one(self, item: EntityT) -> None:
        self._save_all([item])

    def _save_all(self, items: Iterable[EntityT]) -> None:
        # Una sola transaccion: si algo falla no queda importacion parcial
        with self._session_factory() as session:
            for item in items:
                self._upsert(session, item)
            session.commit()

    def delete(self, company_id: int, code: str) -> None:
        with self._session_factory() as session:
            model = self._find(session, company_id, code)
            if model is not None:
                session.delete(model)
                session.commit()


class SqlAlchemyProductRepository(_SqlAlchemyCodeNameRepository[ProductModel, Product]):
    _model = ProductModel
    _entity = Product

    def save(self, product: Product) -> None:
        self._save_one(product)

    def save_many(self, products: Iterable[Product]) -> None:
        self._save_all(products)


class SqlAlchemyCostCenterRepository(_SqlAlchemyCodeNameRepository[CostCenterModel, CostCenter]):
    _model = CostCenterModel
    _entity = CostCenter

    def save(self, cost_center: CostCenter) -> None:
        self._save_one(cost_center)

    def save_many(self, cost_centers: Iterable[CostCenter]) -> None:
        self._save_all(cost_centers)
