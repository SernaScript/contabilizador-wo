from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.invoices.infrastructure import orm  # noqa: F401  (registra las tablas)
from contabilizador.shared.db import Base, create_engine_for, create_session_factory


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine_for(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)
