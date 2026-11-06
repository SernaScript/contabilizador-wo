import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.catalog.infrastructure.repository import (
    SqlAlchemyCostCenterRepository,
    SqlAlchemyProductRepository,
)
from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository


def _company_id(session_factory: sessionmaker[Session], name: str = "ACME") -> int:
    saved = SqlAlchemyCompanyRepository(session_factory).save(Company(None, name, "1", "P", "U"))
    assert saved.id is not None
    return saved.id


def test_product_save_is_upsert(session_factory: sessionmaker[Session]) -> None:
    cid = _company_id(session_factory)
    repo = SqlAlchemyProductRepository(session_factory)
    repo.save(Product(cid, "001", "Old"))
    repo.save(Product(cid, "001", "New"))
    assert repo.list_by_company(cid) == [Product(cid, "001", "New")]
    assert repo.get(cid, "001") == Product(cid, "001", "New")
    assert repo.get(cid, "zzz") is None


def test_product_codes_are_company_scoped(session_factory: sessionmaker[Session]) -> None:
    a = _company_id(session_factory, "A")
    b = _company_id(session_factory, "B")
    repo = SqlAlchemyProductRepository(session_factory)
    repo.save(Product(a, "001", "A prod"))
    repo.save(Product(b, "001", "B prod"))
    assert [p.name for p in repo.list_by_company(a)] == ["A prod"]


def test_product_save_many_and_delete(session_factory: sessionmaker[Session]) -> None:
    cid = _company_id(session_factory)
    repo = SqlAlchemyProductRepository(session_factory)
    repo.save_many([Product(cid, "002", "B"), Product(cid, "001", "A"), Product(cid, "002", "B2")])
    assert [(p.code, p.name) for p in repo.list_by_company(cid)] == [("001", "A"), ("002", "B2")]
    repo.delete(cid, "001")
    assert repo.get(cid, "001") is None


def test_cost_center_roundtrip(session_factory: sessionmaker[Session]) -> None:
    cid = _company_id(session_factory)
    repo = SqlAlchemyCostCenterRepository(session_factory)
    repo.save(CostCenter(cid, "10", "Administracion"))
    repo.save_many([CostCenter(cid, "10", "Admin"), CostCenter(cid, "20", "Ventas")])
    assert [(c.code, c.name) for c in repo.list_by_company(cid)] == [
        ("10", "Admin"),
        ("20", "Ventas"),
    ]
    repo.delete(cid, "20")
    assert repo.get(cid, "20") is None


def test_product_requires_existing_company(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(IntegrityError):
        SqlAlchemyProductRepository(session_factory).save(Product(999, "1", "X"))
