import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository
from contabilizador.suppliers.application.use_cases import (
    ConfigureSupplier,
    DeleteSupplierConfig,
    ListSupplierConfigs,
    ListUnconfiguredSuppliers,
)
from contabilizador.suppliers.infrastructure.repository import SqlAlchemySupplierConfigRepository


def _cid(sf: sessionmaker[Session]) -> int:
    saved = SqlAlchemyCompanyRepository(sf).save(Company(None, "ACME", "1", "P", "U"))
    assert saved.id is not None
    return saved.id


def test_configure_creates_then_updates(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    use_case = ConfigureSupplier(repo)
    use_case.execute(cid, "900123456", "PROV", ["A", "B"], "A")
    use_case.execute(cid, "900123456", "PROV 2", ["A", "B"], "B")
    configs = ListSupplierConfigs(repo).execute(cid)
    assert [(c.name, c.default_product_code) for c in configs] == [("PROV 2", "B")]


def test_configure_dedups_products_keeping_order(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    config = ConfigureSupplier(repo).execute(cid, "900123456", "P", ["B", "A", "B"], "A")
    assert config.product_codes == ("B", "A")


def test_configure_validates(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    use_case = ConfigureSupplier(SqlAlchemySupplierConfigRepository(session_factory))
    with pytest.raises(ValueError):
        use_case.execute(cid, "900123456-1", "P", ["A"], "A")
    with pytest.raises(ValueError):
        use_case.execute(cid, "900123456", "P", [], "A")
    with pytest.raises(ValueError):
        use_case.execute(cid, "900123456", "P", ["A"], "B")


def test_list_unconfigured_returns_missing_nits_once(
    session_factory: sessionmaker[Session],
) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    ConfigureSupplier(repo).execute(cid, "111", "Known", ["A"], "A")
    result = ListUnconfiguredSuppliers(repo).execute(
        cid, [("222", "Unknown"), ("111", "Known"), ("222", "Unknown dup"), ("333", "Other")]
    )
    assert [(s.nit, s.name) for s in result] == [("222", "Unknown"), ("333", "Other")]


def test_list_unconfigured_is_company_scoped(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    other = SqlAlchemyCompanyRepository(session_factory).save(Company(None, "B", "1", "P", "U"))
    assert other.id is not None
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    ConfigureSupplier(repo).execute(other.id, "111", "Known", ["A"], "A")
    assert len(ListUnconfiguredSuppliers(repo).execute(cid, [("111", "Known")])) == 1


def test_delete(session_factory: sessionmaker[Session]) -> None:
    cid = _cid(session_factory)
    repo = SqlAlchemySupplierConfigRepository(session_factory)
    ConfigureSupplier(repo).execute(cid, "111", "K", ["A"], "A")
    DeleteSupplierConfig(repo).execute(cid, "111")
    assert ListSupplierConfigs(repo).execute(cid) == []
