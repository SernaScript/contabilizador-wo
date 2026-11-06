"""Alembic environment wired to contabilizador.shared.db.Base."""

import importlib
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from contabilizador.shared.db import Base, sqlite_url

MODULES = ("companies", "suppliers", "catalog", "invoices", "exports")


def import_orm_models() -> None:
    # Registra en Base.metadata los modelos de cada modulo (si ya existen)
    for module in MODULES:
        name = f"contabilizador.{module}.infrastructure.orm"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as error:
            if error.name != name:
                raise


import_orm_models()

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# CLI: `alembic -x db=ruta/archivo.db ...` apunta a otra base SQLite
_db_argument = context.get_x_argument(as_dictionary=True).get("db")
if _db_argument:
    config.set_main_option("sqlalchemy.url", sqlite_url(Path(_db_argument)))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # render_as_batch: SQLite no soporta ALTER TABLE completo
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
