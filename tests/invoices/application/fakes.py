"""In-memory fakes of the invoices ports (used by use case tests)."""

from collections.abc import Collection, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from contabilizador.invoices.application.ports import CancelCheck, ProgressCallback
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.source import LoadResult
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from contabilizador.suppliers.domain.supplier_config import SupplierConfig


class FakeUnitOfWork:
    """Counts transactions and records writes made outside of one."""

    def __init__(self) -> None:
        self.active = False
        self.transactions = 0
        self.writes_outside_transaction: list[str] = []

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.transactions += 1
        self.active = True
        try:
            yield
        finally:
            self.active = False

    def record_write(self, name: str) -> None:
        if not self.active:
            self.writes_outside_transaction.append(name)


class _TracksWrites:
    unit_of_work: FakeUnitOfWork | None = None

    def _written(self, name: str) -> None:
        if self.unit_of_work is not None:
            self.unit_of_work.record_write(name)


class FakeDocumentSource:
    def __init__(self, result: LoadResult, *, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.received: list[Path] = []
        self.on_progress: ProgressCallback | None = None
        self.is_cancelled: CancelCheck | None = None

    def load(
        self,
        paths: Iterable[Path],
        *,
        on_progress: ProgressCallback | None = None,
        is_cancelled: CancelCheck | None = None,
    ) -> LoadResult:
        self.received.extend(paths)
        self.on_progress = on_progress
        self.is_cancelled = is_cancelled
        if self.error is not None:
            raise self.error
        return self.result


class FakeInvoiceRepository(_TracksWrites):
    def __init__(self) -> None:
        self.invoices: dict[int, StoredInvoice] = {}
        self._next_line_id = 100
        self.get_by_line_calls = 0

    def exists(self, company_id: int, cufe: str) -> bool:
        return self.get_by_cufe(company_id, cufe) is not None

    def add(self, company_id: int, document: ParsedDocument) -> int:
        self._written("add")
        invoice_id = len(self.invoices) + 1
        lines = []
        for position, line in enumerate(document.lines):
            lines.append(StoredLine(self._next_line_id, position, line, None))
            self._next_line_id += 1
        self.invoices[invoice_id] = StoredInvoice(
            invoice_id, company_id, InvoiceStatus.PENDING, document, tuple(lines)
        )
        return invoice_id

    def set_status(self, company_id: int, cufes: list[str], status: InvoiceStatus) -> None:
        self._written("set_status")
        for invoice_id, stored in self.invoices.items():
            if stored.company_id == company_id and stored.document.cufe in cufes:
                self.invoices[invoice_id] = replace(stored, status=status)

    def get(self, company_id: int, invoice_id: int) -> StoredInvoice | None:
        stored = self.invoices.get(invoice_id)
        return stored if stored and stored.company_id == company_id else None

    def get_by_cufe(self, company_id: int, cufe: str) -> StoredInvoice | None:
        return next(
            (
                s
                for s in self.invoices.values()
                if s.company_id == company_id and s.document.cufe == cufe
            ),
            None,
        )

    def get_by_line(self, company_id: int, line_id: int) -> StoredInvoice | None:
        self.get_by_line_calls += 1
        return next(
            (
                s
                for s in self.invoices.values()
                if s.company_id == company_id and s.line(line_id) is not None
            ),
            None,
        )

    def list_by_status(
        self, company_id: int, statuses: Collection[InvoiceStatus]
    ) -> list[StoredInvoice]:
        return [
            s for s in self.invoices.values() if s.company_id == company_id and s.status in statuses
        ]

    def list_by_cufes(self, company_id: int, cufes: Collection[str]) -> list[StoredInvoice]:
        wanted = set(cufes)
        found = [
            s
            for s in self.invoices.values()
            if s.company_id == company_id and s.document.cufe in wanted
        ]
        return sorted(found, key=lambda s: (s.document.issue_date, s.id))

    def assign_line(self, line_id: int, mapping: LineMapping | None) -> None:
        self._written("assign_line")
        for invoice_id, stored in self.invoices.items():
            if stored.line(line_id) is not None:
                lines = tuple(
                    replace(line, assigned=mapping) if line.id == line_id else line
                    for line in stored.lines
                )
                self.invoices[invoice_id] = replace(stored, lines=lines)


class FakeMappingMemory(_TracksWrites):
    def __init__(self) -> None:
        self.entries: dict[MappingKey, LineMapping] = {}
        self.get_many_calls = 0

    def get(self, key: MappingKey) -> LineMapping | None:
        return self.entries.get(key)

    def get_many(
        self, company_id: int, keys: Collection[MappingKey]
    ) -> dict[MappingKey, LineMapping]:
        self.get_many_calls += 1
        return {
            key: self.entries[key]
            for key in keys
            if key.company_id == company_id and key in self.entries
        }

    def remember(self, key: MappingKey, mapping: LineMapping) -> None:
        self._written("remember")
        self.entries[key] = mapping


class FakeSupplierConfigs:
    def __init__(self, *configs: SupplierConfig) -> None:
        self.configs = {(c.company_id, c.nit): c for c in configs}
        self.get_calls: list[str] = []

    def get(self, company_id: int, nit: str) -> SupplierConfig | None:
        self.get_calls.append(nit)
        return self.configs.get((company_id, nit))

    def list_by_company(self, company_id: int) -> list[SupplierConfig]:
        return [c for (cid, _), c in self.configs.items() if cid == company_id]

    def save(self, config: SupplierConfig) -> None:
        self.configs[(config.company_id, config.nit)] = config

    def delete(self, company_id: int, nit: str) -> None:
        self.configs.pop((company_id, nit), None)
