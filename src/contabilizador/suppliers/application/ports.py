"""Ports of the suppliers module."""

from typing import Protocol

from contabilizador.suppliers.domain.supplier_config import SupplierConfig


class SupplierConfigRepository(Protocol):
    def get(self, company_id: int, nit: str) -> SupplierConfig | None:
        """``nit`` without verification digit."""
        ...

    def list_by_company(self, company_id: int) -> list[SupplierConfig]: ...

    def save(self, config: SupplierConfig) -> None:
        """Upsert by (company_id, nit)."""
        ...

    def delete(self, company_id: int, nit: str) -> None: ...
