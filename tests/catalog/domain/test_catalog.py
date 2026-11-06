import dataclasses

import pytest

from contabilizador.catalog.domain.catalog import CostCenter, Product


def test_product_is_scoped_by_company_and_immutable() -> None:
    product = Product(company_id=1, code="513515", name="Mantenimiento")
    with pytest.raises(dataclasses.FrozenInstanceError):
        product.code = "x"  # type: ignore[misc]


def test_cost_center_requires_code_and_name() -> None:
    assert CostCenter(1, "1", "GERENCIA GENERAL").name == "GERENCIA GENERAL"
    with pytest.raises(ValueError):
        CostCenter(1, "", "GERENCIA GENERAL")
    with pytest.raises(ValueError):
        Product(1, "513515", " ")
