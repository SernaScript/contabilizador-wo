import importlib
import importlib.util
import pkgutil
from pathlib import Path

import contabilizador

MODULES = ("companies", "suppliers", "catalog", "invoices", "exports")
LAYERS = ("domain", "application", "infrastructure")


def test_every_package_is_importable() -> None:
    names = [
        info.name
        for info in pkgutil.walk_packages(contabilizador.__path__, prefix="contabilizador.")
        if ".migrations" not in info.name
    ]
    for name in names:
        importlib.import_module(name)
    for module in MODULES:
        for layer in LAYERS:
            assert f"contabilizador.{module}.{layer}" in names
    assert "contabilizador.shared" in names
    assert "contabilizador.ui" in names


def test_domain_layers_do_not_import_frameworks() -> None:
    # El dominio es Python puro: sin Qt, SQLAlchemy, openpyxl ni lxml
    forbidden = ("PySide6", "sqlalchemy", "openpyxl", "lxml", "alembic")
    for module in MODULES:
        package = importlib.import_module(f"contabilizador.{module}.domain")
        for info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
            spec = importlib.util.find_spec(info.name)
            assert spec is not None and spec.origin is not None
            source = Path(spec.origin).read_text(encoding="utf-8")
            for lib in forbidden:
                assert f"import {lib}" not in source, (info.name, lib)
                assert f"from {lib}" not in source, (info.name, lib)
