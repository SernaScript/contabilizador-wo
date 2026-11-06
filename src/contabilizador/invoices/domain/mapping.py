"""Line mapping memory: remembers product and cost center per supplier item."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MappingKey:
    """Lookup key. ``normalized_description`` must come from the invoices domain
    normalization function (owned by the invoices module)."""

    company_id: int
    supplier_nit: str
    normalized_description: str


@dataclass(frozen=True, slots=True)
class LineMapping:
    """World Office product code and cost center code assigned to a line.

    The cost center is stored by code; it is exported by NAME (resolved via catalog).
    """

    product_code: str
    cost_center_code: str | None
