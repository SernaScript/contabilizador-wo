"""Company (World Office "Empresa") and its export defaults."""

from dataclasses import dataclass

DEFAULT_PAYMENT_FORM = "Credito"


@dataclass(frozen=True, slots=True)
class Company:
    """A company the purchases are imported for.

    Attributes:
        id: database id; ``None`` while not persisted.
        name: name EXACTLY as World Office expects it in `Empresa` (e.g. "WEARE DEV S.A.S").
        internal_third_party_id: `Tercero Interno` (ID of the person entering invoices).
        warehouse: `Bodega` (e.g. "Principal").
        unit: `Unidad de medida` (e.g. "Und.").
        payment_form: `FormaPago`; always "Credito" for now.
    """

    id: int | None
    name: str
    internal_third_party_id: str
    warehouse: str
    unit: str
    payment_form: str = DEFAULT_PAYMENT_FORM

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("company name is required")
