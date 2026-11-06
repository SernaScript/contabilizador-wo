"""Parsed DIAN electronic documents (UBL 2.1), independent of the XML library."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


class DocumentKind(StrEnum):
    """Kind of purchase document received from a supplier."""

    INVOICE = "invoice"
    CREDIT_NOTE = "credit_note"


@dataclass(frozen=True, slots=True)
class ParsedLine:
    """One `cac:InvoiceLine` / `cac:CreditNoteLine` of a DIAN document.

    Attributes:
        description: `cac:Item/cbc:Description` (raw, not normalized).
        quantity: `cbc:InvoicedQuantity` or `cbc:CreditedQuantity`. Must be > 0.
        line_extension_amount: `cbc:LineExtensionAmount`, line total before taxes and
            already net of line-level discounts (`cac:AllowanceCharge`).
        tax_percent: IVA `cac:TaxTotal/.../cac:TaxCategory/cbc:Percent` as written in
            the XML (e.g. ``Decimal("19.00")``). ``Decimal("0")`` when the line has no IVA.
    """

    description: str
    quantity: Decimal
    line_extension_amount: Decimal
    tax_percent: Decimal

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be greater than zero")

    @property
    def unit_value(self) -> Decimal:
        """World Office `Valor`: line extension amount divided by quantity (unrounded)."""
        return self.line_extension_amount / self.quantity

    @property
    def tax_rate(self) -> Decimal:
        """World Office `Iva %`: percent as a fraction (19.00 -> 0.19)."""
        return self.tax_percent / Decimal(100)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """A purchase invoice or credit note extracted from a DIAN XML.

    Attributes:
        cufe: `cbc:UUID` of the document (CUFE for invoices, CUDE for credit notes).
            Dedup key together with the company.
        kind: invoice or credit note.
        supplier_nit: supplier NIT WITHOUT verification digit, digits only
            (`cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID`;
            the DV is in its ``schemeID`` attribute and is discarded).
        supplier_name: supplier registration name.
        supplier_prefix: supplier numbering prefix (e.g. ``"FPI"``); may be ``""``.
        supplier_number: document number without prefix, as text, leading zeros kept.
        issue_date: `cbc:IssueDate`.
        due_date: `cbc:DueDate` when present, else ``None``.
        lines: document lines in XML order (at least one).
        payable_amount: `cac:LegalMonetaryTotal/cbc:PayableAmount` (positive, also for
            credit notes).
        billing_reference_cufe: for credit notes, the referenced invoice
            `cac:BillingReference/cac:InvoiceDocumentReference/cbc:UUID`; else ``None``.
        source_file: file the document came from (for zips: the zip path).
    """

    cufe: str
    kind: DocumentKind
    supplier_nit: str
    supplier_name: str
    supplier_prefix: str
    supplier_number: str
    issue_date: date
    due_date: date | None
    lines: tuple[ParsedLine, ...]
    payable_amount: Decimal
    billing_reference_cufe: str | None
    source_file: Path

    @property
    def effective_due_date(self) -> date:
        """Due date for World Office `Vencimiento`: DueDate, falling back to IssueDate."""
        return self.due_date if self.due_date is not None else self.issue_date

    @property
    def is_credit_note(self) -> bool:
        return self.kind is DocumentKind.CREDIT_NOTE
