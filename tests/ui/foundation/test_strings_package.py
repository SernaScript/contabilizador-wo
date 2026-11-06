"""The strings package: one area module per page, star re-exported, no duplicated names."""

import importlib
import pkgutil
from types import ModuleType

from contabilizador.shared import strings

AREA_MODULES = (
    "common",
    "companies",
    "invoices",
    "export",
    "suppliers",
    "catalogs",
    "batches",
    "onboarding",
    "shortcuts",
    "errors",
)
# Nombres de infraestructura que todo modulo puede repetir sin ser copy de UI
PLUMBING_NAMES = {"annotations", "TYPE_CHECKING"}


def _public_names(module: ModuleType) -> set[str]:
    return {
        name
        for name, value in vars(module).items()
        if not name.startswith("_")
        and not isinstance(value, ModuleType)
        and name not in PLUMBING_NAMES
    }


def test_every_area_module_exists() -> None:
    found = {info.name for info in pkgutil.iter_modules(strings.__path__)}

    assert set(AREA_MODULES) <= found


def test_no_public_name_is_defined_in_two_area_modules() -> None:
    owners: dict[str, list[str]] = {}
    for area in AREA_MODULES:
        module = importlib.import_module(f"contabilizador.shared.strings.{area}")
        for name in _public_names(module):
            owners.setdefault(name, []).append(area)

    duplicated = {name: areas for name, areas in owners.items() if len(areas) > 1}
    assert duplicated == {}


def test_package_re_exports_every_area_name() -> None:
    for area in AREA_MODULES:
        module = importlib.import_module(f"contabilizador.shared.strings.{area}")
        for name in _public_names(module):
            assert getattr(strings, name) is getattr(module, name), name


def test_legacy_names_still_reachable_from_package() -> None:
    assert strings.APP_TITLE == "Contabilizador WO"
    assert strings.ACTION_CANCEL == "Cancelar"
    assert strings.TAB_CATALOGS == "Catálogos"
    assert strings.EXPORT_DIALOG_TITLE == "Exportar a World Office"
    assert strings.export_problem_message is not None
