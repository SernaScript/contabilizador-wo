from sqlalchemy.orm import Session, sessionmaker

from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository


def _company(name: str = "WEARE DEV S.A.S") -> Company:
    return Company(None, name, "1020304050", "Principal", "Und.")


def test_save_inserts_and_assigns_id(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    saved = repo.save(_company())
    assert saved.id is not None
    assert repo.get(saved.id) == saved


def test_save_with_id_updates(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    saved = repo.save(_company())
    from dataclasses import replace

    repo.save(replace(saved, warehouse="Bodega 2"))
    assert len(repo.list_all()) == 1
    assert saved.id is not None
    fetched = repo.get(saved.id)
    assert fetched is not None and fetched.warehouse == "Bodega 2"


def test_list_all_is_ordered_by_name(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    repo.save(_company("B"))
    repo.save(_company("A"))
    assert [c.name for c in repo.list_all()] == ["A", "B"]


def test_get_missing_returns_none(session_factory: sessionmaker[Session]) -> None:
    assert SqlAlchemyCompanyRepository(session_factory).get(99) is None


def test_delete_removes_company(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    saved = repo.save(_company())
    assert saved.id is not None
    repo.delete(saved.id)
    assert repo.get(saved.id) is None
