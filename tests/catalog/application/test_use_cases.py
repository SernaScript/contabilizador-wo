from sqlalchemy.orm import Session, sessionmaker

from contabilizador.catalog.application.use_cases import (
    DeleteCostCenter,
    DeleteProduct,
    ListCostCenters,
    ListProducts,
    SaveCostCenter,
    SaveProduct,
)
from contabilizador.catalog.infrastructure.repository import (
    SqlAlchemyCostCenterRepository,
    SqlAlchemyProductRepository,
)
from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository


def _cid(sf: sessionmaker[Session]) -> int:
    saved = SqlAlchemyCompanyRepository(sf).save(Company(None, "ACME", "1", "P", "U"))
    assert saved.id is not None
    return saved.id


def test_product_crud(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemyProductRepository(session_factory)
    SaveProduct(repo).execute(cid, " 001 ", " Papel ")
    products = ListProducts(repo).execute(cid)
    assert [(p.code, p.name) for p in products] == [("001", "Papel")]
    DeleteProduct(repo).execute(cid, "001")
    assert ListProducts(repo).execute(cid) == []


def test_cost_center_crud(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemyCostCenterRepository(session_factory)
    SaveCostCenter(repo).execute(cid, "10", "Admin")
    assert [c.name for c in ListCostCenters(repo).execute(cid)] == ["Admin"]
    DeleteCostCenter(repo).execute(cid, "10")
    assert ListCostCenters(repo).execute(cid) == []
