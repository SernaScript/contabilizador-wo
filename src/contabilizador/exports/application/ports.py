"""Ports of the exports module.

The narrow ``*Reader`` / ``*Updater`` protocols are structural subsets of the ports
owned by companies, suppliers, catalog and invoices: their repositories satisfy them
without this module importing their infrastructure.
"""

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.companies.domain.company import Company
from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.world_office import DocumentType, WorldOfficeDocument
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.suppliers.domain.supplier_config import SupplierConfig


class PurchaseImportExporter(Protocol):
    def write(self, documents: Sequence[WorldOfficeDocument], destination: Path) -> None:
        """Write the World Office import workbook (overwrites ``destination``)."""
        ...


class ConsecutiveRepository(Protocol):
    """Last consecutive used per (company, document type)."""

    def last_used(self, company_id: int, document_type: DocumentType) -> int | None: ...

    def set_last_used(self, company_id: int, document_type: DocumentType, number: int) -> None: ...


class BatchRepository(Protocol):
    def add(self, batch: Batch) -> Batch:
        """Persist a new batch (``id is None``); returns it with its id."""
        ...

    def get(self, batch_id: int) -> Batch | None: ...

    def list_by_company(self, company_id: int) -> list[Batch]:
        """Company batches, newest first."""
        ...

    def update(self, batch: Batch) -> None:
        """Persist status, ``numbers_reused`` and document ``released`` flags."""
        ...


class UnitOfWork(Protocol):
    """Groups repository writes so they commit together or not at all."""

    def transaction(self) -> AbstractContextManager[None]:
        """Writes made inside the block commit on exit and roll back on error."""
        ...


@dataclass(frozen=True, slots=True)
class ExportCandidate:
    """An imported document as the invoices module hands it to the export.

    ``line_mappings`` is parallel to ``document.lines``; ``None`` = line not mapped.
    """

    document: ParsedDocument
    status: InvoiceStatus
    line_mappings: tuple[LineMapping | None, ...]

    def __post_init__(self) -> None:
        if len(self.line_mappings) != len(self.document.lines):
            raise ValueError("one mapping slot is required per document line")


class ExportCandidateSource(Protocol):
    """Implemented by the invoices module (documents + current line mappings)."""

    def find(self, company_id: int, cufes: Sequence[str]) -> list[ExportCandidate]:
        """Documents found among ``cufes``; unknown cufes are simply absent."""
        ...


class InvoiceStatusUpdater(Protocol):
    """Subset of ``invoices.application.ports.InvoiceRepository``."""

    def set_status(self, company_id: int, cufes: list[str], status: InvoiceStatus) -> None: ...


class CompanyReader(Protocol):
    """Subset of ``companies.application.ports.CompanyRepository``."""

    def get(self, company_id: int) -> Company | None: ...


class SupplierConfigReader(Protocol):
    """Subset of ``suppliers.application.ports.SupplierConfigRepository``."""

    def get(self, company_id: int, nit: str) -> SupplierConfig | None: ...


class ProductReader(Protocol):
    """Subset of ``catalog.application.ports.ProductRepository``."""

    def list_by_company(self, company_id: int) -> list[Product]: ...


class CostCenterReader(Protocol):
    """Subset of ``catalog.application.ports.CostCenterRepository``."""

    def list_by_company(self, company_id: int) -> list[CostCenter]: ...


type Clock = Callable[[], datetime]
