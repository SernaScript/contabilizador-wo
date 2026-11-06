"""Product / cost center suggestion for a document line."""

from dataclasses import dataclass
from enum import StrEnum

from contabilizador.invoices.domain.mapping import LineMapping


class MappingSource(StrEnum):
    """Where the effective mapping of a line comes from."""

    ASSIGNED = "assigned"
    MEMORY = "memory"
    SUPPLIER_DEFAULT = "supplier_default"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class MappingSuggestion:
    mapping: LineMapping | None
    source: MappingSource


def suggest_mapping(
    *,
    assigned: LineMapping | None,
    remembered: LineMapping | None,
    supplier_default_product: str | None,
) -> MappingSuggestion:
    """Priority: explicit assignment > mapping memory > supplier default product.

    An assignment without product (only the cost center was chosen) keeps its cost
    center and still takes the product from memory / supplier default.
    """
    if assigned is not None and assigned.product_code:
        return MappingSuggestion(assigned, MappingSource.ASSIGNED)
    fallback = _suggest_unassigned(remembered, supplier_default_product)
    if assigned is None or not assigned.cost_center_code:
        return fallback
    product = fallback.mapping.product_code if fallback.mapping else ""
    return MappingSuggestion(
        LineMapping(product, assigned.cost_center_code), MappingSource.ASSIGNED
    )


def _suggest_unassigned(
    remembered: LineMapping | None, supplier_default_product: str | None
) -> MappingSuggestion:
    if remembered is not None and remembered.product_code:
        return MappingSuggestion(remembered, MappingSource.MEMORY)
    if supplier_default_product is not None:
        # El producto por defecto del proveedor no trae centro de costo
        return MappingSuggestion(
            LineMapping(supplier_default_product, None), MappingSource.SUPPLIER_DEFAULT
        )
    return MappingSuggestion(None, MappingSource.NONE)
