"""SQLAlchemy adapter for CompanyRepository."""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.orm import CompanyModel


def _to_domain(model: CompanyModel) -> Company:
    return Company(
        id=model.id,
        name=model.name,
        internal_third_party_id=model.internal_third_party_id,
        warehouse=model.warehouse,
        unit=model.unit,
        payment_form=model.payment_form,
    )


class SqlAlchemyCompanyRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, company_id: int) -> Company | None:
        with self._session_factory() as session:
            model = session.get(CompanyModel, company_id)
            return _to_domain(model) if model else None

    def list_all(self) -> list[Company]:
        with self._session_factory() as session:
            rows = session.scalars(select(CompanyModel).order_by(CompanyModel.name))
            return [_to_domain(row) for row in rows]

    def save(self, company: Company) -> Company:
        with self._session_factory() as session:
            model = session.get(CompanyModel, company.id) if company.id is not None else None
            if model is None:
                model = CompanyModel()
                session.add(model)
            model.name = company.name
            model.internal_third_party_id = company.internal_third_party_id
            model.warehouse = company.warehouse
            model.unit = company.unit
            model.payment_form = company.payment_form
            session.commit()
            return _to_domain(model)

    def delete(self, company_id: int) -> None:
        with self._session_factory() as session:
            model = session.get(CompanyModel, company_id)
            if model is not None:
                session.delete(model)
                session.commit()
