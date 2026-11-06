"""Use case: assign product and/or cost center to every line of whole documents, or to
single lines, keeping the current effective value of the field left out."""

from collections.abc import Collection, Sequence

from contabilizador.invoices.application.errors import (
    DocumentNotEditableError,
    InvoiceNotFoundError,
    LineNotFoundError,
)
from contabilizador.invoices.application.ports import (
    InvoiceRepository,
    MappingMemoryRepository,
    UnitOfWork,
)
from contabilizador.invoices.application.suggestions import load_supplier_configs, suggest_lines
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.stored import StoredInvoice
from contabilizador.invoices.domain.suggestion import MappingSuggestion
from contabilizador.suppliers.application.ports import SupplierConfigRepository


class AssignDocumentMapping:
    """Editing product or cost center on a document row applies it to all its lines;
    ``execute_lines`` does the same for an edit on line rows."""

    def __init__(
        self,
        invoices: InvoiceRepository,
        memory: MappingMemoryRepository,
        suppliers: SupplierConfigRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._invoices = invoices
        self._memory = memory
        self._suppliers = suppliers
        self._unit_of_work = unit_of_work

    def execute(
        self,
        company_id: int,
        invoice_ids: Sequence[int],
        *,
        product_code: str | None = None,
        cost_center_code: str | None = None,
    ) -> None:
        """Each line gets the given value, or keeps its current effective value for the
        field left out, so the memory remembers product and cost center together.

        ``None`` or a blank value = no change for that field; with neither value this
        is a no-op. Everything is written in one transaction (manual change: the memory
        is updated for every line that ends up with a product).

        Raises:
            InvoiceNotFoundError: an id does not exist in the company. Nothing changes.
            DocumentNotEditableError: a document was already exported. Nothing changes.
        """
        product = _chosen(product_code)
        cost_center = _chosen(cost_center_code)
        if product is None and cost_center is None:
            return
        with self._unit_of_work.transaction():
            # Se valida todo antes de escribir para no dejar documentos a medias
            invoices = [self._editable(company_id, i) for i in dict.fromkeys(invoice_ids)]
            self._assign(company_id, invoices, product, cost_center)

    def execute_lines(
        self,
        company_id: int,
        line_ids: Sequence[int],
        *,
        product_code: str | None = None,
        cost_center_code: str | None = None,
    ) -> None:
        """Like ``execute``, for single lines: the field left out keeps the value the line
        has now, read inside the same transaction (never a copy of what a screen showed,
        which may be older than an edit still being saved).

        Raises:
            LineNotFoundError: a line does not exist in the company. Nothing changes.
            DocumentNotEditableError: a line belongs to an exported document. Nothing
                changes.
        """
        product = _chosen(product_code)
        cost_center = _chosen(cost_center_code)
        if product is None and cost_center is None:
            return
        wanted = list(dict.fromkeys(line_ids))
        with self._unit_of_work.transaction():
            # Se valida todo antes de escribir para no dejar lineas a medias
            owners: dict[int, StoredInvoice] = {}  # documento de cada linea, leido una vez
            for line_id in wanted:
                if line_id not in owners:
                    invoice = self._editable_owner(company_id, line_id)
                    owners.update(dict.fromkeys((line.id for line in invoice.lines), invoice))
            invoices = list({owners[line_id].id: owners[line_id] for line_id in wanted}.values())
            self._assign(company_id, invoices, product, cost_center, only=set(wanted))

    def _assign(
        self,
        company_id: int,
        invoices: Sequence[StoredInvoice],
        product: str | None,
        cost_center: str | None,
        *,
        only: Collection[int] | None = None,
    ) -> None:
        """Writes the merged mapping of every line (or of the lines in ``only``)."""
        configs = load_supplier_configs(
            self._suppliers, company_id, (i.document.supplier_nit for i in invoices)
        )
        current = suggest_lines(self._memory, company_id, invoices, configs)
        for invoice in invoices:
            for line in invoice.lines:
                if only is not None and line.id not in only:
                    continue
                mapping = _merge(current[line.id], product, cost_center)
                self._invoices.assign_line(line.id, mapping)
                if mapping.product_code.strip():
                    self._memory.remember(
                        mapping_key_for(
                            company_id, invoice.document.supplier_nit, line.line.description
                        ),
                        mapping,
                    )

    def _editable(self, company_id: int, invoice_id: int) -> StoredInvoice:
        invoice = self._invoices.get(company_id, invoice_id)
        if invoice is None:
            raise InvoiceNotFoundError(invoice_id)
        if not invoice.is_editable:
            raise DocumentNotEditableError(invoice.document.cufe)
        return invoice

    def _editable_owner(self, company_id: int, line_id: int) -> StoredInvoice:
        invoice = self._invoices.get_by_line(company_id, line_id)
        if invoice is None:
            raise LineNotFoundError(line_id)
        if not invoice.is_editable:
            raise DocumentNotEditableError(invoice.document.cufe)
        return invoice


def _chosen(value: str | None) -> str | None:
    return value.strip() if value is not None and value.strip() else None


def _merge(current: MappingSuggestion, product: str | None, cost_center: str | None) -> LineMapping:
    effective = current.mapping
    return LineMapping(
        product if product is not None else (effective.product_code if effective else ""),
        cost_center
        if cost_center is not None
        else (effective.cost_center_code if effective else None),
    )
