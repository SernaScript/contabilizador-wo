"""SQLAlchemy setup: single declarative Base, engine and session factory."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Nombres de constraints deterministas (necesario para batch mode de Alembic en SQLite)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Single declarative base. Each module declares its ORM models in
    ``contabilizador.<module>.infrastructure.orm`` subclassing this Base."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def sqlite_url(db_path: Path) -> str:
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_engine_for(db_path: Path) -> Engine:
    """Engine for a SQLite file; creates parent folders and enables foreign keys."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(sqlite_url(db_path))
    event.listen(engine, "connect", _enable_foreign_keys)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


# Sesion de la unidad de trabajo activa (por factory) a la que se unen los repositorios
_active: ContextVar[tuple[sessionmaker[Session], Session] | None] = ContextVar(
    "contabilizador_active_session", default=None
)


def _active_session(session_factory: sessionmaker[Session]) -> Session | None:
    active = _active.get()
    if active is not None and active[0] is session_factory:
        return active[1]
    return None


@contextmanager
def read_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Session for reads: the active unit of work's, or a short-lived one."""
    active = _active_session(session_factory)
    if active is not None:
        yield active
        return
    with session_factory() as session:
        yield session


@contextmanager
def write_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Session for writes: joins the active unit of work (committed by it), otherwise
    runs in its own transaction."""
    active = _active_session(session_factory)
    if active is not None:
        yield active
        active.flush()  # los errores de BD aparecen en la llamada, no al confirmar
        return
    with session_factory.begin() as session:
        yield session


class SqlAlchemyUnitOfWork:
    """Implements the ``UnitOfWork`` port: repository writes made with ``read_session`` /
    ``write_session`` on the same factory share one transaction."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if _active_session(self._session_factory) is not None:
            yield  # anidada: se une a la transaccion externa
            return
        with self._session_factory.begin() as session:
            token = _active.set((self._session_factory, session))
            try:
                yield
            finally:
                _active.reset(token)
