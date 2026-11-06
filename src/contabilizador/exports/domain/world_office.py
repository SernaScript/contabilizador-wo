"""World Office purchase import workbook model (sheets `Encabezados` +
`Movimiento inventarios`). Column order and header text are the contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from contabilizador.invoices.domain.document import DocumentKind

HEADER_SHEET_NAME = "Encabezados"
LINE_SHEET_NAME = "Movimiento inventarios"

# Encabezados verbatim (incluye el prefijo "Encab: ")
HEADER_COLUMNS: tuple[str, ...] = (
    "Encab: Empresa",  # WorldOfficeDocument.company_name
    "Encab: Tipo Documento",  # document_type.value
    "Encab: Prefijo",  # prefix (== document_type.value)
    "Encab: Documento Número",  # number (int)
    "Encab: Fecha",  # date -> text dd/mm/yyyy
    "Encab: Tercero Interno",  # internal_third_party (text)
    "Encab: Tercero Externo",  # external_third_party (supplier NIT, text)
    "Encab: Pref Dto Ext",  # external_prefix (text)
    "Encab: No. Dto Ext",  # external_number (text, leading zeros kept)
    "Encab: Nota",  # note
    "Encab: FormaPago",  # payment_form
    "Encab: Verificado",  # verified (0)
    "Encab: Anulado",  # voided (0)
    "Encab: Fecha Emision",  # issue_date -> text dd/mm/yyyy
)

LINE_COLUMNS: tuple[str, ...] = (
    "EMPRESA",  # parent company_name
    "Tipo Documento",  # parent document_type.value
    "Prefijo",  # parent prefix
    "Numero documento",  # parent number
    "Producto",  # product_code (text)
    "Bodega",  # warehouse
    "Unidad de medida",  # unit
    "Cantidades",  # quantity (number)
    "Iva %",  # tax_rate (fraction, 0.19)
    "Valor",  # unit_value (number)
    "Descuento",  # discount (0)
    "Vencimiento",  # due_date -> text dd/mm/yyyy
    "Nota detalle",  # detail_note
    "Centro Costos",  # cost_center_name
)

DATE_FORMAT = "%d/%m/%Y"


class DocumentType(StrEnum):
    """World Office document type; also used as the prefix."""

    FC = "FC"  # factura de compra
    NC = "NC"  # nota credito de compra

    @classmethod
    def for_kind(cls, kind: DocumentKind) -> DocumentType:
        return cls.NC if kind is DocumentKind.CREDIT_NOTE else cls.FC


@dataclass(frozen=True, slots=True)
class WorldOfficeLine:
    """One row of `Movimiento inventarios` (line-specific columns only; the join key
    Empresa+Tipo+Prefijo+Número comes from the parent document).

    Values are positive also for credit notes. Decimals are converted to float only
    by the xlsx writer.
    """

    product_code: str
    warehouse: str
    unit: str
    quantity: Decimal
    tax_rate: Decimal
    unit_value: Decimal
    discount: Decimal
    due_date: date
    detail_note: str
    cost_center_name: str


@dataclass(frozen=True, slots=True)
class WorldOfficeDocument:
    """One row of `Encabezados` plus its inventory lines."""

    company_name: str
    document_type: DocumentType
    number: int
    date: date
    internal_third_party: str
    external_third_party: str
    external_prefix: str
    external_number: str
    note: str
    payment_form: str
    issue_date: date
    lines: tuple[WorldOfficeLine, ...]
    verified: int = field(default=0)
    voided: int = field(default=0)

    def __post_init__(self) -> None:
        if not self.lines:
            raise ValueError("a World Office document needs at least one line")

    @property
    def prefix(self) -> str:
        return self.document_type.value
