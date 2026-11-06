"""Use case: import DIAN XML files into the pending documents of a company."""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from contabilizador.invoices.application.errors import ImportCancelledError
from contabilizador.invoices.application.ports import (
    CancelCheck,
    DocumentSource,
    InvoiceRepository,
    ProgressCallback,
    UnitOfWork,
)
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.domain.source import SkippedFile


@dataclass(frozen=True, slots=True)
class ImportedDocument:
    invoice_id: int
    document: ParsedDocument


@dataclass(frozen=True, slots=True)
class ImportReport:
    """Outcome of an import.

    Attributes:
        imported: new documents stored as pending.
        duplicates: documents whose CUFE already exists for the company (or repeated in
            the same import); not stored again.
        ignored: valid XML of another type (e.g. ApplicationResponse).
        failed: unreadable or invalid files.
        credit_notes_without_original: imported credit notes whose referenced invoice is
            not stored for the company (warning only).
    """

    imported: tuple[ImportedDocument, ...]
    duplicates: tuple[ParsedDocument, ...]
    ignored: tuple[SkippedFile, ...]
    failed: tuple[SkippedFile, ...]
    credit_notes_without_original: tuple[ParsedDocument, ...]


class ImportInvoiceFiles:
    def __init__(
        self, source: DocumentSource, invoices: InvoiceRepository, unit_of_work: UnitOfWork
    ) -> None:
        self._source = source
        self._invoices = invoices
        self._unit_of_work = unit_of_work

    def execute(
        self,
        company_id: int,
        paths: Iterable[Path],
        *,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> ImportReport:
        """Reads every file first and then stores the new documents in one transaction.

        ``on_progress(done, total)`` reports the reading of the files.

        Raises:
            ImportCancelledError: ``is_cancelled()`` returned True before storing;
                nothing was imported.
        """
        # Se lee todo antes de guardar: cancelar nunca deja una importacion a medias
        loaded = self._source.load(paths, on_progress=on_progress, is_cancelled=is_cancelled)
        if is_cancelled is not None and is_cancelled():
            raise ImportCancelledError()
        with self._unit_of_work.transaction():
            imported, duplicates = self._store(company_id, loaded.parsed)
            # Se valida al final para aceptar factura y nota crédito en el mismo lote
            orphans = tuple(
                item.document
                for item in imported
                if item.document.is_credit_note
                and not self._has_original(company_id, item.document)
            )
        return ImportReport(
            imported=imported,
            duplicates=duplicates,
            ignored=loaded.ignored,
            failed=loaded.failed,
            credit_notes_without_original=orphans,
        )

    def _store(
        self, company_id: int, documents: Iterable[ParsedDocument]
    ) -> tuple[tuple[ImportedDocument, ...], tuple[ParsedDocument, ...]]:
        imported: list[ImportedDocument] = []
        duplicates: list[ParsedDocument] = []
        for document in documents:
            # Dedup por (empresa, CUFE); cubre también repetidos dentro del mismo lote
            if self._invoices.exists(company_id, document.cufe):
                duplicates.append(document)
                continue
            imported.append(ImportedDocument(self._invoices.add(company_id, document), document))
        return tuple(imported), tuple(duplicates)

    def _has_original(self, company_id: int, credit_note: ParsedDocument) -> bool:
        reference = credit_note.billing_reference_cufe
        return reference is not None and self._invoices.exists(company_id, reference)
