from pathlib import Path

from sqlalchemy import inspect

from contabilizador.shared.db import create_engine_for
from contabilizador.shared.migrations_runner import upgrade_to_head


def test_upgrade_to_head_creates_version_table(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    upgrade_to_head(db_path)
    engine = create_engine_for(db_path)
    assert "alembic_version" in inspect(engine).get_table_names()
    engine.dispose()


def test_upgrade_to_head_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    upgrade_to_head(db_path)
    upgrade_to_head(db_path)


EXPECTED_TABLES = {
    "companies",
    "supplier_configs",
    "supplier_products",
    "products",
    "cost_centers",
    "invoices",
    "invoice_lines",
    "line_mapping_memory",
    "export_consecutives",
    "export_batches",
    "export_batch_documents",
}


def test_upgrade_to_head_creates_every_module_table(tmp_path: Path) -> None:
    db_path = tmp_path / "data.db"
    upgrade_to_head(db_path)
    engine = create_engine_for(db_path)
    assert set(inspect(engine).get_table_names()) >= EXPECTED_TABLES
    engine.dispose()


def test_migrated_schema_matches_orm_metadata(tmp_path: Path) -> None:
    # Si el ORM cambia sin nueva revision, autogenerate detectaria diferencias
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    import contabilizador.catalog.infrastructure.orm
    import contabilizador.companies.infrastructure.orm
    import contabilizador.exports.infrastructure.orm
    import contabilizador.invoices.infrastructure.orm
    import contabilizador.suppliers.infrastructure.orm  # noqa: F401
    from contabilizador.shared.db import Base

    db_path = tmp_path / "data.db"
    upgrade_to_head(db_path)
    engine = create_engine_for(db_path)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"render_as_batch": True})
        assert compare_metadata(context, Base.metadata) == []
    engine.dispose()
