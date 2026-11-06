from sqlalchemy.orm import Session, sessionmaker

from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.suppliers.infrastructure.repository import SqlAlchemySupplierConfigRepository


def _cid(sf: sessionmaker[Session], name: str = "ACME") -> int:
    saved = SqlAlchemyCompanyRepository(sf).save(Company(None, name, "1", "P", "U"))
    assert saved.id is not None
    return saved.id


def _config(cid: int, products: tuple[str, ...] = ("A", "B"), default: str = "B") -> SupplierConfig:
    return SupplierConfig(cid, "900123456", "PROVEEDOR", products, default)


def test_save_and_get_preserves_product_order_and_default(
    session_factory: sessionmaker[Session],
) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    repo.save(_config(cid, ("Z", "A", "M"), "A"))
    assert repo.get(cid, "900123456") == _config(cid, ("Z", "A", "M"), "A")


def test_save_is_upsert_and_replaces_products(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    repo.save(_config(cid))
    repo.save(_config(cid, ("C",), "C"))
    assert len(repo.list_by_company(cid)) == 1
    got = repo.get(cid, "900123456")
    assert got is not None and got.product_codes == ("C",)


def test_scoped_by_company(session_factory: sessionmaker[Session]) -> None:
    a, b = _cid(session_factory, "A"), _cid(session_factory, "B")
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    repo.save(_config(a))
    assert repo.get(b, "900123456") is None
    assert repo.list_by_company(b) == []


def test_delete(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    repo.save(_config(cid))
    repo.delete(cid, "900123456")
    assert repo.get(cid, "900123456") is None


def test_deleting_company_cascades_to_suppliers(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    repo.save(_config(cid))
    SqlAlchemyCompanyRepository(session_factory).delete(cid)
    assert repo.list_by_company(cid) == []
