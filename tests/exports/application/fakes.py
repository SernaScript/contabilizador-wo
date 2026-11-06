"""In-memory adapters for the exports ports."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.companies.domain.company import Company
from contabilizador.exports.application.ports import ExportCandidate
from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.world_office import DocumentType, WorldOfficeDocument
from contabilizador.invoices.domain.status import InvoiceStatus
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


class FakeCompanies:
    def __init__(self, *companies: Company) -> None:
        self._companies = {c.id: c for c in companies}

    def get(self, company_id: int) -> Company | None:
        return self._companies.get(company_id)


class FakeSuppliers:
    def __init__(self, *configs: SupplierConfig) -> None:
        self._configs = {(c.company_id, c.nit): c for c in configs}

    def get(self, company_id: int, nit: str) -> SupplierConfig | None:
        return self._configs.get((company_id, nit))


class FakeProducts:
    def __init__(self, *products: Product) -> None:
        self._items = {(p.company_id, p.code): p for p in products}

    def list_by_company(self, company_id: int) -> list[Product]:
        return [p for (cid, _), p in self._items.items() if cid == company_id]


class FakeCostCenters:
    def __init__(self, *cost_centers: CostCenter) -> None:
        self._items = {(c.company_id, c.code): c for c in cost_centers}

    def get(self, company_id: int, code: str) -> CostCenter | None:
        return self._items.get((company_id, code))

    def list_by_company(self, company_id: int) -> list[CostCenter]:
        return [c for (cid, _), c in self._items.items() if cid == company_id]


class FakeCandidates:
    def __init__(self, company_id: int, *candidates: ExportCandidate) -> None:
        self.company_id = company_id
        self.candidates = {c.document.cufe: c for c in candidates}

    def find(self, company_id: int, cufes: Sequence[str]) -> list[ExportCandidate]:
        if company_id != self.company_id:
            return []
        return [self.candidates[cufe] for cufe in cufes if cufe in self.candidates]


class FakeInvoiceStatus(_TracksWrites):
    def __init__(self) -> None:
        self.calls: list[tuple[int, list[str], InvoiceStatus]] = []

    def set_status(self, company_id: int, cufes: list[str], status: InvoiceStatus) -> None:
        self._written("set_status")
        self.calls.append((company_id, list(cufes), status))


class FakeConsecutives(_TracksWrites):
    def __init__(self, initial: dict[tuple[int, DocumentType], int] | None = None) -> None:
        self.values = dict(initial or {})

    def last_used(self, company_id: int, document_type: DocumentType) -> int | None:
        return self.values.get((company_id, document_type))

    def set_last_used(self, company_id: int, document_type: DocumentType, number: int) -> None:
        self._written("set_last_used")
        self.values[(company_id, document_type)] = number


class FakeBatches(_TracksWrites):
    def __init__(self) -> None:
        self.items: dict[int, Batch] = {}

    def add(self, batch: Batch) -> Batch:
        self._written("add")
        stored = replace(batch, id=len(self.items) + 1)
        self.items[stored.id or 0] = stored
        return stored

    def get(self, batch_id: int) -> Batch | None:
        return self.items.get(batch_id)

    def list_by_company(self, company_id: int) -> list[Batch]:
        found = [b for b in self.items.values() if b.company_id == company_id]
        return sorted(found, key=lambda b: (b.created_at, b.id or 0), reverse=True)

    def update(self, batch: Batch) -> None:
        self._written("update")
        assert batch.id in self.items
        self.items[batch.id or 0] = batch


class FakeExporter:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.written: list[tuple[list[WorldOfficeDocument], Path]] = []

    def write(self, documents: Sequence[WorldOfficeDocument], destination: Path) -> None:
        if self.fail:
            raise OSError("disk full")
        self.written.append((list(documents), destination))


class FakeClock:
    """Each call advances one minute so batches keep a strict order."""

    def __init__(self) -> None:
        self.current = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.current += timedelta(minutes=1)
        return self.current
