"""Export batch: one generated workbook with the consecutives it assigned."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path

from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    BatchAlreadyVoidedError,
    ConsecutiveCollision,
    DocumentAlreadyReleasedError,
    DocumentNotInBatchError,
)
from contabilizador.exports.domain.world_office import DocumentType


class BatchStatus(StrEnum):
    EXPORTED = "exported"
    VOIDED = "voided"


@dataclass(frozen=True, slots=True)
class BatchDocument:
    """A document exported in a batch with its assigned World Office consecutive.
    Supplier data is denormalized so the history survives without the invoices module."""

    cufe: str
    document_type: DocumentType
    number: int
    supplier_nit: str
    supplier_name: str
    external_prefix: str
    external_number: str
    issue_date: date
    released: bool = False


@dataclass(frozen=True, slots=True)
class Batch:
    """Attributes:
    numbers_reused: the batch was voided while being the last one, so its
        consecutives went back to the pool. Otherwise its numbers stay burned.
    """

    id: int | None
    company_id: int
    file_path: Path
    created_at: datetime
    documents: tuple[BatchDocument, ...]
    status: BatchStatus = BatchStatus.EXPORTED
    numbers_reused: bool = field(default=False)

    def __post_init__(self) -> None:
        if not self.documents:
            raise ValueError("a batch needs at least one document")
        keys = [(d.document_type, d.number) for d in self.documents]
        if len(set(keys)) != len(keys):
            raise ValueError("a batch cannot repeat a consecutive")
        if self.numbers_reused and self.status is not BatchStatus.VOIDED:
            raise ValueError("only voided batches can give their numbers back")

    @property
    def ranges(self) -> dict[DocumentType, ConsecutiveRange]:
        """First..last consecutive per document type present in the batch."""
        numbers: dict[DocumentType, list[int]] = {}
        for document in self.documents:
            numbers.setdefault(document.document_type, []).append(document.number)
        return {
            document_type: ConsecutiveRange(document_type, min(values), max(values))
            for document_type, values in numbers.items()
        }

    @property
    def is_voided(self) -> bool:
        return self.status is BatchStatus.VOIDED

    @property
    def holds_numbers(self) -> bool:
        """Whether its consecutives are still taken (anything but a reused void)."""
        return not self.numbers_reused

    @property
    def released_documents(self) -> tuple[BatchDocument, ...]:
        return tuple(d for d in self.documents if d.released)

    def _ensure_not_voided(self) -> None:
        if self.is_voided:
            raise BatchAlreadyVoidedError(f"batch {self.id} is voided")

    def release(self, cufes: Iterable[str]) -> Batch:
        """Free some documents; their consecutives stay burned."""
        self._ensure_not_voided()
        selected = set(cufes)
        known = {d.cufe for d in self.documents}
        if missing := sorted(selected - known):
            raise DocumentNotInBatchError(missing)
        if already := sorted(d.cufe for d in self.documents if d.cufe in selected and d.released):
            raise DocumentAlreadyReleasedError(already)
        return replace(
            self,
            documents=tuple(
                replace(d, released=True) if d.cufe in selected else d for d in self.documents
            ),
        )

    def void(self, *, reuse_numbers: bool) -> Batch:
        """Void the whole batch, releasing every document."""
        self._ensure_not_voided()
        return replace(
            self,
            status=BatchStatus.VOIDED,
            numbers_reused=reuse_numbers,
            documents=tuple(replace(d, released=True) for d in self.documents),
        )


def _order_key(batch: Batch) -> tuple[datetime, int]:
    return batch.created_at, batch.id or 0


def is_last_batch(batch: Batch, company_batches: Sequence[Batch]) -> bool:
    """True when no later batch of the company still holds consecutives, i.e. its
    numbers can go back to the pool without leaving gaps."""
    holding = [b for b in company_batches if b.holds_numbers]
    return bool(holding) and max(holding, key=_order_key).id == batch.id


def find_collisions(
    proposed: Iterable[ConsecutiveRange], batches: Iterable[Batch]
) -> list[ConsecutiveCollision]:
    """Overlaps between proposed ranges and batches whose numbers are still taken."""
    holding = [b for b in batches if b.holds_numbers]
    return [
        ConsecutiveCollision(batch_id=batch.id or 0, proposed=candidate, existing=existing)
        for candidate in proposed
        for batch in holding
        for existing in batch.ranges.values()
        if candidate.overlaps(existing)
    ]
