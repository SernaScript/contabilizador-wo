"""Imported documents as persisted, with the per-line product/cost center assignment."""

from dataclasses import dataclass

from contabilizador.invoices.domain.document import ParsedDocument, ParsedLine
from contabilizador.invoices.domain.header_note import build_header_note
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.totals import TotalsCheck, check_document_totals

EDITABLE_STATUSES = frozenset({InvoiceStatus.PENDING, InvoiceStatus.RELEASED})


@dataclass(frozen=True, slots=True)
class StoredLine:
    """A persisted document line.

    Attributes:
        id: line id (used to assign mappings).
        position: 0-based order within the document.
        line: parsed values.
        assigned: product/cost center explicitly assigned by the user; ``None`` when the
            line still relies on suggestions.
    """

    id: int
    position: int
    line: ParsedLine
    assigned: LineMapping | None


@dataclass(frozen=True, slots=True)
class StoredInvoice:
    id: int
    company_id: int
    status: InvoiceStatus
    document: ParsedDocument
    lines: tuple[StoredLine, ...]

    @property
    def header_note(self) -> str:
        return build_header_note(line.description for line in self.document.lines)

    @property
    def totals(self) -> TotalsCheck:
        return check_document_totals(self.document)

    @property
    def is_editable(self) -> bool:
        # Solo se reasignan líneas de documentos aún no exportados (o liberados)
        return self.status in EDITABLE_STATUSES

    def line(self, line_id: int) -> StoredLine | None:
        return next((line for line in self.lines if line.id == line_id), None)
