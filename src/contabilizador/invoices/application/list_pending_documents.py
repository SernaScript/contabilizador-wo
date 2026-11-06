"""Use case: documents waiting to be exported, with mapping suggestions per line."""

from dataclasses import dataclass

from contabilizador.invoices.application.ports import InvoiceRepository, MappingMemoryRepository
from contabilizador.invoices.application.suggestions import load_supplier_configs, suggest_lines
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from contabilizador.invoices.domain.suggestion import MappingSuggestion
from contabilizador.invoices.domain.totals import TotalsCheck
from contabilizador.suppliers.application.ports import SupplierConfigRepository

# Liberado = sacado de un lote, vuelve a estar disponible para exportar
EXPORTABLE_STATUSES = (InvoiceStatus.PENDING, InvoiceStatus.RELEASED)


@dataclass(frozen=True, slots=True)
class PendingLine:
    stored: StoredLine
    suggestion: MappingSuggestion

    @property
    def mapping(self) -> LineMapping | None:
        return self.suggestion.mapping


@dataclass(frozen=True, slots=True)
class PendingDocument:
    """Attributes:
    original_found: for credit notes, whether the referenced invoice is stored for the
        company (in any status); ``None`` for invoices.
    """

    invoice: StoredInvoice
    supplier_configured: bool
    lines: tuple[PendingLine, ...]
    original_found: bool | None = None

    @property
    def totals(self) -> TotalsCheck:
        return self.invoice.totals

    @property
    def header_note(self) -> str:
        return self.invoice.header_note

    @property
    def is_fully_mapped(self) -> bool:
        return all(line.mapping is not None for line in self.lines)


@dataclass(frozen=True, slots=True)
class UnconfiguredSupplier:
    nit: str
    name: str


@dataclass(frozen=True, slots=True)
class PendingDocuments:
    documents: tuple[PendingDocument, ...]

    @property
    def unconfigured_suppliers(self) -> tuple[UnconfiguredSupplier, ...]:
        """Distinct unconfigured suppliers, in document order (export is blocked for them)."""
        seen: dict[str, UnconfiguredSupplier] = {}
        for pending in self.documents:
            document = pending.invoice.document
            if not pending.supplier_configured and document.supplier_nit not in seen:
                seen[document.supplier_nit] = UnconfiguredSupplier(
                    document.supplier_nit, document.supplier_name
                )
        return tuple(seen.values())


class ListPendingDocuments:
    def __init__(
        self,
        invoices: InvoiceRepository,
        memory: MappingMemoryRepository,
        suppliers: SupplierConfigRepository,
    ) -> None:
        self._invoices = invoices
        self._memory = memory
        self._suppliers = suppliers

    def execute(self, company_id: int) -> PendingDocuments:
        """Constant number of queries, whatever the number of documents or lines."""
        stored = self._invoices.list_by_status(company_id, EXPORTABLE_STATUSES)
        configs = load_supplier_configs(
            self._suppliers, company_id, (invoice.document.supplier_nit for invoice in stored)
        )
        suggestions = suggest_lines(self._memory, company_id, stored, configs)
        originals = self._stored_originals(company_id, stored)
        documents = tuple(
            PendingDocument(
                invoice,
                configs[invoice.document.supplier_nit] is not None,
                tuple(PendingLine(line, suggestions[line.id]) for line in invoice.lines),
                _original_found(invoice, originals),
            )
            for invoice in stored
        )
        return PendingDocuments(documents)

    def _stored_originals(self, company_id: int, stored: list[StoredInvoice]) -> set[str]:
        """CUFEs referenced by the credit notes that exist for the company."""
        references = {
            invoice.document.billing_reference_cufe
            for invoice in stored
            if invoice.document.is_credit_note and invoice.document.billing_reference_cufe
        }
        listed = {invoice.document.cufe for invoice in stored}
        # la original puede estar ya exportada: se busca solo lo que no esta en la lista
        missing = references - listed
        found = self._invoices.list_by_cufes(company_id, missing) if missing else []
        return (references & listed) | {invoice.document.cufe for invoice in found}


def _original_found(invoice: StoredInvoice, originals: set[str]) -> bool | None:
    document = invoice.document
    if not document.is_credit_note:
        return None
    return document.billing_reference_cufe in originals
