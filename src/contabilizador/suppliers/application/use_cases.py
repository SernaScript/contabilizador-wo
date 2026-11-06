"""Supplier configuration use cases."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from contabilizador.suppliers.application.ports import SupplierConfigRepository
from contabilizador.suppliers.domain.supplier_config import SupplierConfig


@dataclass(frozen=True, slots=True)
class UnconfiguredSupplier:
    """Supplier found in documents without configuration (prefills the form)."""

    nit: str
    name: str


class ConfigureSupplier:
    """Create or replace the configuration of a supplier (upsert)."""

    def __init__(self, suppliers: SupplierConfigRepository) -> None:
        self._suppliers = suppliers

    def execute(
        self,
        company_id: int,
        nit: str,
        name: str,
        product_codes: Sequence[str],
        default_product_code: str,
    ) -> SupplierConfig:
        # dict.fromkeys quita duplicados conservando el orden
        codes = tuple(dict.fromkeys(c.strip() for c in product_codes if c.strip()))
        config = SupplierConfig(
            company_id=company_id,
            nit=nit.strip(),
            name=name.strip(),
            product_codes=codes,
            default_product_code=default_product_code.strip(),
        )
        self._suppliers.save(config)
        return config


class ListSupplierConfigs:
    def __init__(self, suppliers: SupplierConfigRepository) -> None:
        self._suppliers = suppliers

    def execute(self, company_id: int) -> list[SupplierConfig]:
        return self._suppliers.list_by_company(company_id)


class DeleteSupplierConfig:
    def __init__(self, suppliers: SupplierConfigRepository) -> None:
        self._suppliers = suppliers

    def execute(self, company_id: int, nit: str) -> None:
        self._suppliers.delete(company_id, nit)


class ListUnconfiguredSuppliers:
    """Which (nit, name) pairs from the documents have no config in this company."""

    def __init__(self, suppliers: SupplierConfigRepository) -> None:
        self._suppliers = suppliers

    def execute(
        self, company_id: int, suppliers: Iterable[tuple[str, str]]
    ) -> list[UnconfiguredSupplier]:
        configured = {c.nit for c in self._suppliers.list_by_company(company_id)}
        missing: dict[str, UnconfiguredSupplier] = {}
        for nit, name in suppliers:
            if nit not in configured and nit not in missing:
                missing[nit] = UnconfiguredSupplier(nit, name)
        return list(missing.values())
