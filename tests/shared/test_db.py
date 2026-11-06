from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.shared.db import (
    Base,
    SqlAlchemyUnitOfWork,
    create_engine_for,
    create_session_factory,
    read_session,
    write_session,
)


def test_engine_creates_sqlite_file_with_foreign_keys(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "data.db"
    engine = create_engine_for(db_path)
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1
    assert db_path.exists()
    engine.dispose()


def test_session_factory_opens_working_sessions(tmp_path: Path) -> None:
    engine = create_engine_for(tmp_path / "data.db")
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        assert session.execute(text("SELECT 1")).scalar() == 1
    engine.dispose()


def test_single_declarative_base_exposes_metadata() -> None:
    assert Base.metadata is not None


def _counter_table(tmp_path: Path) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_engine_for(tmp_path / "data.db")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE counter (value INTEGER)"))
    return engine, create_session_factory(engine)


def _count(session_factory: sessionmaker[Session]) -> int:
    with read_session(session_factory) as session:
        return int(session.execute(text("SELECT COUNT(*) FROM counter")).scalar() or 0)


def test_write_session_commits_on_its_own(tmp_path: Path) -> None:
    engine, session_factory = _counter_table(tmp_path)
    with write_session(session_factory) as session:
        session.execute(text("INSERT INTO counter VALUES (1)"))
    assert _count(session_factory) == 1
    engine.dispose()


def test_unit_of_work_rolls_back_every_write_on_error(tmp_path: Path) -> None:
    engine, session_factory = _counter_table(tmp_path)
    try:
        with SqlAlchemyUnitOfWork(session_factory).transaction():
            for value in (1, 2):
                with write_session(session_factory) as session:
                    session.execute(text("INSERT INTO counter VALUES (:v)"), {"v": value})
            raise RuntimeError("fallo a mitad")
    except RuntimeError:
        pass
    assert _count(session_factory) == 0
    engine.dispose()


def test_unit_of_work_commits_writes_together(tmp_path: Path) -> None:
    engine, session_factory = _counter_table(tmp_path)
    with SqlAlchemyUnitOfWork(session_factory).transaction():
        with write_session(session_factory) as session:
            session.execute(text("INSERT INTO counter VALUES (1)"))
        # las lecturas dentro de la transaccion ven lo escrito
        assert _count(session_factory) == 1
    assert _count(session_factory) == 1
    engine.dispose()
