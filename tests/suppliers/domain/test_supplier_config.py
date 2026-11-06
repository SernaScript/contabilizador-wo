import pytest

from contabilizador.suppliers.domain.supplier_config import SupplierConfig


def test_supplier_config_keeps_products_and_default() -> None:
    config = SupplierConfig(
        company_id=1,
        nit="900123456",
        name="COMERCIALIZADORA EJEMPLO S.A.S.",
        product_codes=("513515", "519560"),
        default_product_code="519560",
    )
    assert config.default_product_code in config.product_codes


def test_default_product_must_belong_to_product_codes() -> None:
    with pytest.raises(ValueError):
        SupplierConfig(1, "900123456", "X", ("513515",), "999999")


def test_supplier_config_requires_at_least_one_product() -> None:
    with pytest.raises(ValueError):
        SupplierConfig(1, "900123456", "X", (), "513515")


def test_nit_must_be_digits_without_verification_digit() -> None:
    with pytest.raises(ValueError):
        SupplierConfig(1, "900123456-7", "X", ("513515",), "513515")
