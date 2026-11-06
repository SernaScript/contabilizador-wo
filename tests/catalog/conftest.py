from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

# Importar todos los ORM para que create_all conozca las FK entre modulos
import contabilizador.catalog.infrastructure.orm
import contabilizador.companies.infrastructure.orm
import contabilizador.suppliers.infrastructure.orm  # noqa: F401
from contabilizador.shared.db import Base, create_engine_for, create_session_factory


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine_for(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()
