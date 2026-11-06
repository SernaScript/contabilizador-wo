"""Use cases over existing batches: void, release documents, list history."""

from collections.abc import Sequence

from contabilizador.exports.application.ports import (
    BatchRepository,
    ConsecutiveRepository,
    InvoiceStatusUpdater,
    UnitOfWork,
)
from contabilizador.exports.domain.batch import Batch, is_last_batch
from contabilizador.exports.domain.errors import BatchNotFoundError
from contabilizador.invoices.domain.status import InvoiceStatus


def _get_batch(batches: BatchRepository, batch_id: int) -> Batch:
    batch = batches.get(batch_id)
    if batch is None:
        raise BatchNotFoundError(batch_id)
    return batch


class VoidBatch:
    """Voids a whole batch and releases its documents. Its consecutives go back to the
    pool only when it is the company's last batch; otherwise they stay burned."""

    def __init__(
        self,
        *,
        batches: BatchRepository,
        consecutives: ConsecutiveRepository,
        invoice_status: InvoiceStatusUpdater,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._batches = batches
        self._consecutives = consecutives
        self._invoice_status = invoice_status
        self._unit_of_work = unit_of_work

    def execute(self, batch_id: int) -> Batch:
        batch = _get_batch(self._batches, batch_id)
        company_batches = self._batches.list_by_company(batch.company_id)
        reuse = is_last_batch(batch, company_batches)
        voided = batch.void(reuse_numbers=reuse)
        # los ya liberados pudieron reexportarse en otro lote: no se tocan
        freed = [d.cufe for d in batch.documents if not d.released]
        with self._unit_of_work.transaction():
            self._batches.update(voided)
            if reuse:
                others = [b for b in company_batches if b.id != batch.id and b.holds_numbers]
                self._give_numbers_back(voided, others)
            self._invoice_status.set_status(batch.company_id, freed, InvoiceStatus.RELEASED)
        return voided

    def _give_numbers_back(self, voided: Batch, others: Sequence[Batch]) -> None:
        for document_type, consecutive_range in voided.ranges.items():
            # nunca por debajo de un numero que otro lote aun ocupa
            held = [b.ranges[document_type].last for b in others if document_type in b.ranges]
            target = max([consecutive_range.first - 1, *held])
            current = self._consecutives.last_used(voided.company_id, document_type)
            if current is None or target < current:
                self._consecutives.set_last_used(voided.company_id, document_type, target)


class ReleaseDocuments:
    """Frees some documents of a batch so they can be exported again; their
    consecutives stay burned."""

    def __init__(
        self,
        *,
        batches: BatchRepository,
        invoice_status: InvoiceStatusUpdater,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._batches = batches
        self._invoice_status = invoice_status
        self._unit_of_work = unit_of_work

    def execute(self, batch_id: int, cufes: Sequence[str]) -> Batch:
        batch = _get_batch(self._batches, batch_id)
        released = batch.release(cufes)
        with self._unit_of_work.transaction():
            self._batches.update(released)
            self._invoice_status.set_status(batch.company_id, list(cufes), InvoiceStatus.RELEASED)
        return released


class ListBatches:
    """Batch history of a company, newest first; released documents are kept in
    each batch (``Batch.released_documents``)."""

    def __init__(self, *, batches: BatchRepository) -> None:
        self._batches = batches

    def execute(self, company_id: int) -> list[Batch]:
        return sorted(
            self._batches.list_by_company(company_id),
            key=lambda b: (b.created_at, b.id or 0),
            reverse=True,
        )
