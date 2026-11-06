"""Ports of the catalog module."""

from collections.abc import Iterable
from typing import Protocol

from contabilizador.catalog.domain.catalog import CostCenter, Product


class ProductRepository(Protocol):
    def get(self, company_id: int, code: str) -> Product | None: ...

    def list_by_company(self, company_id: int) -> list[Product]: ...

    def save(self, product: Product) -> None:
        """Upsert by (company_id, code)."""
        ...

    def save_many(self, products: Iterable[Product]) -> None: ...

    def delete(self, company_id: int, code: str) -> None: ...


class CostCenterRepository(Protocol):
    def get(self, company_id: int, code: str) -> CostCenter | None: ...

    def list_by_company(self, company_id: int) -> list[CostCenter]: ...

    def save(self, cost_center: CostCenter) -> None:
        """Upsert by (company_id, code)."""
        ...

    def save_many(self, cost_centers: Iterable[CostCenter]) -> None: ...

    def delete(self, company_id: int, code: str) -> None: ...
