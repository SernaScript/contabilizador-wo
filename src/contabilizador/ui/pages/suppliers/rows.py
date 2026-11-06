"""Rows of the Proveedores page and the wizard context, built without Qt.

The container turns use case results into these plain values; widgets only paint them.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from decimal import Decimal

from contabilizador.invoices.application.list_pending_documents import PendingDocuments
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.ui.formatting import document_label


def fold(text: str) -> str:
    """Lowercase without accents, so searches ignore both."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


@dataclass(frozen=True, slots=True)
class SupplierRow:
    """One supplier of the list, configured or waiting for its configuration.

    Attributes:
        missing_codes: configured products that are no longer in the catalog (they block
            the invoices that end up using them).
        pending_invoices: documents of the supplier that are still waiting to be exported.
    """

    nit: str
    name: str
    configured: bool
    product_codes: tuple[str, ...] = ()
    default_product_code: str = ""
    missing_codes: tuple[str, ...] = ()
    pending_invoices: int = 0

    def matches(self, query: str) -> bool:
        wanted = fold(query).strip()
        return not wanted or wanted in fold(f"{self.nit} {self.name}")


@dataclass(frozen=True, slots=True)
class ContextLine:
    """A pending line shown in the wizard so the user knows what the supplier sells."""

    document: str
    description: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class SupplierStep:
    """One supplier of the wizard: identity read from the XML, context and any previous
    configuration (so a supplier that is already configured comes prefilled)."""

    nit: str
    name: str
    lines: tuple[ContextLine, ...] = ()
    product_codes: tuple[str, ...] = ()
    default_product_code: str = ""


@dataclass(frozen=True, slots=True)
class SupplierValues:
    """What the wizard and the edit sheet ask the container to save."""

    nit: str
    name: str
    product_codes: tuple[str, ...]
    default_product_code: str


def build_rows(
    configs: Sequence[SupplierConfig],
    pending: PendingDocuments,
    catalog_codes: Collection[str],
) -> list[SupplierRow]:
    """Unconfigured suppliers first (they block the export), then the configured ones."""
    counts = Counter(document.invoice.document.supplier_nit for document in pending.documents)
    configured = {
        config.nit: SupplierRow(
            nit=config.nit,
            name=config.name,
            configured=True,
            product_codes=config.product_codes,
            default_product_code=config.default_product_code,
            missing_codes=tuple(code for code in config.product_codes if code not in catalog_codes),
            pending_invoices=counts[config.nit],
        )
        for config in configs
    }
    waiting = [
        SupplierRow(
            supplier.nit, supplier.name, configured=False, pending_invoices=counts[supplier.nit]
        )
        for supplier in pending.unconfigured_suppliers
        if supplier.nit not in configured
    ]
    return [*_by_name(waiting), *_by_name(configured.values())]


def _by_name(rows: Collection[SupplierRow]) -> list[SupplierRow]:
    return sorted(rows, key=lambda row: (fold(row.name), row.nit))


def build_context(pending: PendingDocuments, nit: str) -> tuple[ContextLine, ...]:
    """Lines of every pending document of the supplier, in document order."""
    lines: list[ContextLine] = []
    for document in pending.documents:
        parsed = document.invoice.document
        if parsed.supplier_nit != nit:
            continue
        label = document_label(parsed.supplier_prefix, parsed.supplier_number)
        lines.extend(
            ContextLine(label, item.stored.line.description, item.stored.line.line_extension_amount)
            for item in document.lines
        )
    return tuple(lines)
