"""Per-company supplier configuration."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SupplierConfig:
    """Products a supplier's lines can map to, within one company.

    Attributes:
        company_id: owning company.
        nit: supplier NIT WITHOUT verification digit, digits only.
        name: supplier name (prefilled from the XML).
        product_codes: allowed World Office product codes (1..N, ordered, unique).
        default_product_code: suggested product; must be in ``product_codes``.
    """

    company_id: int
    nit: str
    name: str
    product_codes: tuple[str, ...]
    default_product_code: str

    def __post_init__(self) -> None:
        if not self.nit.isdigit():
            raise ValueError("nit must contain only digits (no verification digit)")
        if not self.product_codes:
            raise ValueError("supplier needs at least one product")
        if self.default_product_code not in self.product_codes:
            raise ValueError("default product must be one of the supplier products")
