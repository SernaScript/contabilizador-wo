"""Helpers of the export sheet tests: seeding real services, spies for the presenter and
the system opener."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QWidget

from contabilizador.exports.application.export_batch import ExportRequest
from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import DocumentKind, ParsedLine
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import ErrorPresentation, ErrorPresenter
from contabilizador.ui.tasks import TaskHandle
from tests.invoices.factories import make_document

# Una linea de $ 100 con IVA del 19 %: el XML que cuadra paga $ 119
LINE_TOTAL = Decimal(119)
SUPPLIER_NIT = "900123456"
SUPPLIER = "FERRETERIA CENTRAL"
# Hora local fija (Bogota) para el nombre sugerido del archivo
NOW = datetime(2026, 10, 3, 10, 15, 0, tzinfo=timezone(timedelta(hours=-5)))
DEFAULT_FILE = "world-office-compras-20261003-101500.xlsx"


@dataclass
class Seed:
    """Company with catalog and a configured supplier; adds invoices on demand."""

    services: Services
    company_id: int
    tmp_path: Path

    def invoice(
        self,
        cufe: str,
        number: str,
        *,
        kind: DocumentKind = DocumentKind.INVOICE,
        payable: Decimal = LINE_TOTAL,
        cost_center: str | None = "CC1",
    ) -> str:
        """Ready invoice (supplier default product + ``cost_center``); returns its CUFE.

        Its only line has a description of its own, so the mapping memory of other
        invoices never completes it."""
        document = make_document(
            cufe=cufe,
            kind=kind,
            supplier_nit=SUPPLIER_NIT,
            supplier_prefix="FPI",
            supplier_number=number,
            supplier_name=SUPPLIER,
            lines=(ParsedLine(f"SERVICIO {cufe}", Decimal(1), Decimal(100), Decimal(19)),),
            payable_amount=payable,
        )
        invoice_id = self.services.invoices.add(self.company_id, document)
        if cost_center is not None:
            self.services.assign_document_mapping.execute(
                self.company_id, [invoice_id], cost_center_code=cost_center
            )
        return cufe

    def previous_batch(self, cufe: str, start: int) -> Batch:
        """Exports one more invoice beforehand, taking FC numbers from ``start``."""
        self.invoice(cufe, f"9{start}")
        return self.services.export_batch.execute(
            ExportRequest(
                company_id=self.company_id,
                cufes=[cufe],
                destination=self.tmp_path / "anteriores" / f"{cufe}.xlsx",
                start_numbers={DocumentType.FC: start},
            )
        )


def seed_company(services: Services, tmp_path: Path) -> Seed:
    company = services.create_company.execute("WEARE DEV S.A.S", "1017")
    assert company.id is not None
    services.save_product.execute(company.id, "P1", "Papelería")
    services.save_cost_center.execute(company.id, "CC1", "Administración")
    services.configure_supplier.execute(company.id, SUPPLIER_NIT, SUPPLIER, ["P1"], "P1")
    return Seed(services, company.id, tmp_path)


class SpyPresenter(ErrorPresenter):
    """Real Spanish copy, but ``show`` records instead of opening a modal box."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[tuple[BaseException, str | None]] = []

    def show(
        self, parent: QWidget | None, error: BaseException, *, context: str | None = None
    ) -> ErrorPresentation:
        self.shown.append((error, context))
        return self.present(error, context=context)


class _Context:
    def report(self, done: int, total: int) -> None:
        return None

    def cancelled(self) -> bool:
        return False


class DeferredRunner(QObject):
    """Queues jobs; the test decides when, and in which order, each one runs."""

    def __init__(self) -> None:
        super().__init__()
        self.jobs: list[tuple[Callable[[Any], Any], Callable[[Any], None] | None, Any]] = []

    @property
    def is_busy(self) -> bool:
        return bool(self.jobs)

    def submit(
        self,
        job: Callable[[Any], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        self.jobs.append((job, on_done, on_error))
        return TaskHandle()

    def run(self, index: int = 0) -> None:
        job, on_done, on_error = self.jobs.pop(index)
        try:
            result = job(_Context())
        except Exception as error:
            if on_error is None:
                raise
            on_error(error)
        else:
            if on_done is not None:
                on_done(result)

    def shutdown(self) -> None:
        self.jobs.clear()


@dataclass
class Opener:
    """Records what the sheet asked the system to open."""

    opened: list[Path] = field(default_factory=list)
    succeeds: bool = True

    def __call__(self, path: Path) -> bool:
        self.opened.append(path)
        return self.succeeds


class FailingOnce:
    """PreviewExport that fails on the given call (1-based) and works otherwise."""

    def __init__(self, inner: object, failing_call: int, error: Exception | None = None) -> None:
        self.inner = inner
        self.failing_call = failing_call
        self.error = error or RuntimeError("database is locked")
        self.calls = 0

    def execute(self, *args: object) -> object:
        self.calls += 1
        if self.calls == self.failing_call:
            raise self.error
        return self.inner.execute(*args)  # type: ignore[attr-defined]
