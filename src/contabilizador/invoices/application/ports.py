"""Ports of the invoices module."""

from collections.abc import Callable, Collection, Iterable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol

from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.source import LoadResult
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice

# on_progress(hechos, total): avance de la lectura de archivos
type ProgressCallback = Callable[[int, int], None]
# is_cancelled(): True cuando el usuario pidio cancelar
type CancelCheck = Callable[[], bool]


class DocumentParser(Protocol):
    def parse(self, content: bytes, source_file: Path) -> ParsedDocument:
        """Parse one XML (plain Invoice/CreditNote or AttachedDocument wrapper).

        Raises:
            UnsupportedDocumentError: valid XML of another type (skip and log).
            InvalidDocumentError: malformed or incomplete XML.
        """
        ...


class DocumentSource(Protocol):
    def load(
        self,
        paths: Iterable[Path],
        *,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> LoadResult:
        """Read XML files, folders (recursive) and zips. Never raises per file:
        unsupported documents go to ``ignored`` and unreadable ones to ``failed``.

        Every input is listed first, then each XML (zip members included) is read,
        calling ``on_progress(done, total)`` once with ``done=0`` and after each one.

        Raises:
            ImportCancelledError: ``is_cancelled()`` returned True (checked while
                listing and before each file).
        """
        ...


class InvoiceRepository(Protocol):
    """Imported documents, unique by (company_id, cufe). The invoices module may
    extend this port (e.g. line mappings, listing) as long as these stay stable."""

    def exists(self, company_id: int, cufe: str) -> bool: ...

    def add(self, company_id: int, document: ParsedDocument) -> int:
        """Store a new document as ``pending``; returns its id."""
        ...

    def set_status(self, company_id: int, cufes: list[str], status: InvoiceStatus) -> None: ...

    def get(self, company_id: int, invoice_id: int) -> StoredInvoice | None: ...

    def get_by_cufe(self, company_id: int, cufe: str) -> StoredInvoice | None: ...

    def get_by_line(self, company_id: int, line_id: int) -> StoredInvoice | None:
        """Document that owns ``line_id`` within the company."""
        ...

    def list_by_status(
        self, company_id: int, statuses: Collection[InvoiceStatus]
    ) -> list[StoredInvoice]:
        """Ordered by issue date, then id."""
        ...

    def list_by_cufes(self, company_id: int, cufes: Collection[str]) -> list[StoredInvoice]:
        """Documents of the company among ``cufes`` (unknown ones are absent), in any
        status, ordered by issue date, then id. Constant number of queries."""
        ...

    def assign_line(self, line_id: int, mapping: LineMapping | None) -> None:
        """Set (or clear with ``None``) the explicit product/cost center of a line."""
        ...


class MappingMemoryRepository(Protocol):
    def get(self, key: MappingKey) -> LineMapping | None: ...

    def get_many(
        self, company_id: int, keys: Collection[MappingKey]
    ) -> dict[MappingKey, LineMapping]:
        """Remembered mappings among ``keys`` (one query); keys of another company and
        unknown keys are absent from the result."""
        ...

    def remember(self, key: MappingKey, mapping: LineMapping) -> None:
        """Upsert the mapping for ``key``."""
        ...


class UnitOfWork(Protocol):
    """Groups repository writes so they commit together or not at all."""

    def transaction(self) -> AbstractContextManager[None]:
        """Writes made inside the block commit on exit and roll back on error."""
        ...
