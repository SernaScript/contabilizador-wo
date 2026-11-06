"""Test doubles and seeding of the Lotes exportados page tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal

from contabilizador.exports.application.export_batch import ExportRequest
from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.tasks import TaskContext, TaskHandle


class RecordingPresenter(ErrorPresenter):
    """Records what would have been shown in a modal message box."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[tuple[BaseException, str | None]] = []

    def show(self, parent, error, *, context=None):  # type: ignore[override]
        self.shown.append((error, context))
        return self.present(error, context=context)


class _Context:
    def report(self, done: int, total: int) -> None:
        return None

    def cancelled(self) -> bool:
        return False


@dataclass
class _Pending:
    job: Callable[[TaskContext], Any]
    on_done: Callable[[Any], None] | None
    on_error: Callable[[BaseException], None] | None


class ManualRunner(QObject):
    """Runner whose jobs wait in a queue until the test decides to run them, so tests can
    interleave refreshes and look at the busy state."""

    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.pending: list[_Pending] = []

    @property
    def is_busy(self) -> bool:
        return bool(self.pending)

    def submit(
        self,
        job: Callable[[TaskContext], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        self.pending.append(_Pending(job, on_done, on_error))
        return TaskHandle()

    def run_next(self) -> None:
        item = self.pending.pop(0)
        try:
            result = item.job(_Context())
        except BaseException as error:
            if item.on_error is None:
                raise
            item.on_error(error)
        else:
            if item.on_done is not None:
                item.on_done(result)

    def run_all(self) -> None:
        while self.pending:
            self.run_next()

    def shutdown(self) -> None:
        return None


def seed_batches(services, company_id: int, xml_dir: Path, out_dir: Path) -> list[Batch]:
    """Imports the fixture invoices, makes them exportable and exports them in two batches
    (first three documents, then the rest). Returns the company batches, newest first."""
    services.save_product.execute(company_id, "P-1", "Papeleria")
    services.save_cost_center.execute(company_id, "CC-1", "Administracion")
    services.import_invoices.execute(company_id, [xml_dir])
    pending = services.list_pending.execute(company_id)
    for supplier in pending.unconfigured_suppliers:
        services.configure_supplier.execute(company_id, supplier.nit, supplier.name, ["P-1"], "P-1")
    ids = [document.invoice.id for document in pending.documents]
    services.assign_document_mapping.execute(company_id, ids, cost_center_code="CC-1")
    cufes = [
        document.invoice.document.cufe
        for document in services.list_pending.execute(company_id).documents
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    services.export_batch.execute(
        ExportRequest(
            company_id,
            cufes[:3],
            out_dir / "lote-a.xlsx",
            start_numbers={DocumentType.FC: 100, DocumentType.NC: 50},
        )
    )
    services.export_batch.execute(ExportRequest(company_id, cufes[3:], out_dir / "lote-b.xlsx"))
    return services.list_batches.execute(company_id)
