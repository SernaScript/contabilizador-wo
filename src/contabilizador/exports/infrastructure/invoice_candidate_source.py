"""``ExportCandidateSource`` backed by the invoices module.

Each line is exported with its effective mapping (manual assignment > mapping memory >
supplier default product), the same suggestion the documents screen shows. The number
of queries does not grow with the number of documents or lines.
"""

from collections.abc import Sequence

from contabilizador.exports.application.ports import ExportCandidate
from contabilizador.invoices.application.ports import InvoiceRepository, MappingMemoryRepository
from contabilizador.invoices.application.suggestions import load_supplier_configs, suggest_lines
from contabilizador.suppliers.application.ports import SupplierConfigRepository


class InvoiceExportCandidateSource:
    def __init__(
        self,
        invoices: InvoiceRepository,
        memory: MappingMemoryRepository,
        suppliers: SupplierConfigRepository,
    ) -> None:
        self._invoices = invoices
        self._memory = memory
        self._suppliers = suppliers

    def find(self, company_id: int, cufes: Sequence[str]) -> list[ExportCandidate]:
        requested = list(dict.fromkeys(cufes))
        stored = self._invoices.list_by_cufes(company_id, requested)
        configs = load_supplier_configs(
            self._suppliers, company_id, (invoice.document.supplier_nit for invoice in stored)
        )
        suggestions = suggest_lines(self._memory, company_id, stored, configs)
        by_cufe = {invoice.document.cufe: invoice for invoice in stored}
        # orden de la solicitud; los CUFE desconocidos simplemente no aparecen
        return [
            ExportCandidate(
                invoice.document,
                invoice.status,
                tuple(suggestions[line.id].mapping for line in invoice.lines),
            )
            for cufe in requested
            if (invoice := by_cufe.get(cufe)) is not None
        ]
