"""Use case: assign product and cost center to document lines."""

from collections.abc import Sequence
from dataclasses import dataclass

from contabilizador.invoices.application.errors import (
    DocumentNotEditableError,
    LineNotFoundError,
)
from contabilizador.invoices.application.ports import (
    InvoiceRepository,
    MappingMemoryRepository,
    UnitOfWork,
)
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.stored import StoredInvoice


@dataclass(frozen=True, slots=True)
class LineAssignment:
    """``mapping=None`` clears the manual assignment: the line goes back to its
    suggestion (memory / supplier default) and the memory is left untouched."""

    line_id: int
    mapping: LineMapping | None


class AssignLineMapping:
    def __init__(
        self,
        invoices: InvoiceRepository,
        memory: MappingMemoryRepository,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._invoices = invoices
        self._memory = memory
        self._unit_of_work = unit_of_work

    def execute(
        self, company_id: int, assignments: Sequence[LineAssignment], *, remember: bool = True
    ) -> None:
        """Assign every line (bulk apply = several assignments) in one transaction.

        ``remember`` (manual change by the user) also updates the mapping memory so the
        next document of the same supplier item gets the same suggestion. Mappings
        without product (cost center only) are stored on the line but never remembered.

        Raises:
            LineNotFoundError: a line does not exist in the company. Nothing is changed.
            DocumentNotEditableError: a line belongs to an exported document.
        """
        with self._unit_of_work.transaction():
            # Se valida todo antes de escribir para no dejar asignaciones a medias
            keys = self._memory_keys(company_id, assignments)
            for item, key in zip(assignments, keys, strict=True):
                self._invoices.assign_line(item.line_id, item.mapping)
                # sin producto no hay nada util que recordar
                if remember and item.mapping is not None and item.mapping.product_code.strip():
                    self._memory.remember(key, item.mapping)

    def _memory_keys(
        self, company_id: int, assignments: Sequence[LineAssignment]
    ) -> list[MappingKey]:
        owners: dict[int, StoredInvoice] = {}  # documento ya leido, por id de linea
        keys: list[MappingKey] = []
        for item in assignments:
            invoice = owners.get(item.line_id)
            if invoice is None:
                invoice = self._invoices.get_by_line(company_id, item.line_id)
            line = invoice.line(item.line_id) if invoice is not None else None
            if invoice is None or line is None:
                raise LineNotFoundError(item.line_id)
            if not invoice.is_editable:
                raise DocumentNotEditableError(invoice.document.cufe)
            owners.update(dict.fromkeys((other.id for other in invoice.lines), invoice))
            keys.append(
                mapping_key_for(company_id, invoice.document.supplier_nit, line.line.description)
            )
        return keys
