"""Catalog use cases: CRUD for products and cost centers."""

from contabilizador.catalog.application.ports import CostCenterRepository, ProductRepository
from contabilizador.catalog.domain.catalog import CostCenter, Product


class SaveProduct:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, company_id: int, code: str, name: str) -> Product:
        product = Product(company_id, code.strip(), name.strip())
        self._products.save(product)
        return product


class ListProducts:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, company_id: int) -> list[Product]:
        return self._products.list_by_company(company_id)


class DeleteProduct:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, company_id: int, code: str) -> None:
        self._products.delete(company_id, code)


class SaveCostCenter:
    def __init__(self, cost_centers: CostCenterRepository) -> None:
        self._cost_centers = cost_centers

    def execute(self, company_id: int, code: str, name: str) -> CostCenter:
        cost_center = CostCenter(company_id, code.strip(), name.strip())
        self._cost_centers.save(cost_center)
        return cost_center


class ListCostCenters:
    def __init__(self, cost_centers: CostCenterRepository) -> None:
        self._cost_centers = cost_centers

    def execute(self, company_id: int) -> list[CostCenter]:
        return self._cost_centers.list_by_company(company_id)


class DeleteCostCenter:
    def __init__(self, cost_centers: CostCenterRepository) -> None:
        self._cost_centers = cost_centers

    def execute(self, company_id: int, code: str) -> None:
        self._cost_centers.delete(company_id, code)
