import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.infrastructure.sqlalchemy_mapping_memory_repository import (
    SqlAlchemyMappingMemoryRepository,
)
from contabilizador.shared.db import SqlAlchemyUnitOfWork
from tests.invoices.query_counter import count_queries


@pytest.fixture
def memory(session_factory: sessionmaker[Session]) -> SqlAlchemyMappingMemoryRepository:
    return SqlAlchemyMappingMemoryRepository(session_factory)


KEY = MappingKey(1, "900123456", "resma papel carta 75g")


def test_get_missing_returns_none(memory: SqlAlchemyMappingMemoryRepository) -> None:
    assert memory.get(KEY) is None


def test_remember_and_get(memory: SqlAlchemyMappingMemoryRepository) -> None:
    memory.remember(KEY, LineMapping("P-01", "CC-ADM"))
    assert memory.get(KEY) == LineMapping("P-01", "CC-ADM")


def test_remember_upserts(memory: SqlAlchemyMappingMemoryRepository) -> None:
    memory.remember(KEY, LineMapping("P-01", "CC-ADM"))
    memory.remember(KEY, LineMapping("P-02", None))
    assert memory.get(KEY) == LineMapping("P-02", None)


def test_keys_are_scoped(memory: SqlAlchemyMappingMemoryRepository) -> None:
    memory.remember(KEY, LineMapping("P-01", "CC-ADM"))
    assert memory.get(MappingKey(2, KEY.supplier_nit, KEY.normalized_description)) is None
    assert memory.get(MappingKey(1, "800987654", KEY.normalized_description)) is None
    assert memory.get(MappingKey(1, KEY.supplier_nit, "toner")) is None


def test_remember_joins_the_unit_of_work(
    memory: SqlAlchemyMappingMemoryRepository, session_factory: sessionmaker[Session]
) -> None:
    # antes abria su propia sesion: dentro de una transaccion daba "database is locked"
    with pytest.raises(RuntimeError), SqlAlchemyUnitOfWork(session_factory).transaction():
        memory.remember(KEY, LineMapping("P-01", "CC-ADM"))
        assert memory.get(KEY) == LineMapping("P-01", "CC-ADM")
        raise RuntimeError("fallo posterior")

    assert memory.get(KEY) is None


def test_get_many_returns_the_known_keys_of_the_company(
    memory: SqlAlchemyMappingMemoryRepository,
) -> None:
    other_item = MappingKey(1, KEY.supplier_nit, "toner")
    other_supplier = MappingKey(1, "800987654", KEY.normalized_description)
    other_company = MappingKey(2, KEY.supplier_nit, KEY.normalized_description)
    memory.remember(KEY, LineMapping("P-01", "CC-ADM"))
    memory.remember(other_item, LineMapping("P-02", None))
    memory.remember(other_supplier, LineMapping("P-03", "CC-1"))
    memory.remember(other_company, LineMapping("P-04", None))

    found = memory.get_many(
        1, [KEY, other_supplier, other_company, MappingKey(1, KEY.supplier_nit, "silla")]
    )

    assert found == {
        KEY: LineMapping("P-01", "CC-ADM"),
        other_supplier: LineMapping("P-03", "CC-1"),
    }


def test_get_many_without_keys_does_not_query(
    memory: SqlAlchemyMappingMemoryRepository, session_factory: sessionmaker[Session]
) -> None:
    engine = session_factory.kw["bind"]
    with count_queries(engine) as counter:
        assert memory.get_many(1, []) == {}
    assert counter.count == 0


def test_get_many_uses_one_query_for_any_number_of_keys(
    memory: SqlAlchemyMappingMemoryRepository, session_factory: sessionmaker[Session]
) -> None:
    keys = [MappingKey(1, f"90000000{i % 3}", f"item {i}") for i in range(40)]
    for key in keys[::2]:
        memory.remember(key, LineMapping("P", None))
    engine = session_factory.kw["bind"]

    with count_queries(engine) as counter:
        found = memory.get_many(1, keys)

    assert set(found) == set(keys[::2])
    assert counter.count == 1
