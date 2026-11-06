"""World Office catalogs supplied by the user, scoped by company."""

from dataclasses import dataclass


def _require(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} is required")


@dataclass(frozen=True, slots=True)
class Product:
    """World Office product (WO handles the accounting behind it)."""

    company_id: int
    code: str
    name: str

    def __post_init__(self) -> None:
        _require(self.code, "code")
        _require(self.name, "name")


@dataclass(frozen=True, slots=True)
class CostCenter:
    """Cost center; exported to World Office by ``name``."""

    company_id: int
    code: str
    name: str

    def __post_init__(self) -> None:
        _require(self.code, "code")
        _require(self.name, "name")
