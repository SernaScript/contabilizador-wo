"""Presentation of batches for the Lotes exportados page: plain data and pure helpers.

The domain decides what a batch is; this module only turns it into the texts and flags the
tables and confirmations show. Nothing here touches Qt or the database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from contabilizador.exports.domain.batch import Batch, BatchDocument, is_last_batch
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.shared import strings
from contabilizador.ui.formatting import document_label, format_date, format_datetime, format_range

# Estados del tema: "archived" para lo cerrado, "incomplete" pide atencion
STATUS_ARCHIVED = "archived"
STATUS_ATTENTION = "incomplete"


@dataclass(frozen=True, slots=True)
class BatchStatusView:
    """Pill of a batch: ``key`` is stable for code and tests, ``status`` is the theme token."""

    key: str
    status: str
    label: str
    tooltip: str


@dataclass(frozen=True, slots=True)
class BatchDocumentRow:
    cufe: str  # llave interna: nunca se muestra
    consecutive: str  # "FC 5731"
    document: str  # "FPI-5731", el numero del proveedor
    supplier_nit: str
    supplier_name: str
    issue_date: str
    released: bool


@dataclass(frozen=True, slots=True)
class BatchRow:
    batch_id: int
    date_text: str
    ranges: str
    file_path: Path
    status: BatchStatusView
    summary: str
    invoices: int
    credit_notes: int
    released_count: int
    voided: bool
    documents: tuple[BatchDocumentRow, ...]

    @property
    def document_count(self) -> int:
        return len(self.documents)


@dataclass(frozen=True, slots=True)
class VoidPlan:
    """What voiding a batch will do, computed from the company's batch list."""

    batch_id: int
    returns_numbers: bool
    ranges: str  # "FC 5731 a 5748 y NC 12 a 14"
    numbers: int  # cuantos consecutivos ocupa el lote
    freed_documents: int  # facturas que vuelven a pendientes (las ya liberadas no cuentan)
    later_batch_id: int | None  # el lote posterior que mantiene usados los consecutivos


def batch_status_view(batch: Batch) -> BatchStatusView:
    if batch.is_voided:
        if batch.numbers_reused:
            return BatchStatusView(
                "voided_returned",
                STATUS_ARCHIVED,
                strings.BATCH_STATUS_VOIDED_RETURNED,
                strings.BATCH_VOIDED_RETURNED_TOOLTIP,
            )
        return BatchStatusView(
            "voided",
            STATUS_ARCHIVED,
            strings.BATCH_STATUS_VOIDED,
            strings.BATCH_VOIDED_KEPT_TOOLTIP,
        )
    released = len(batch.released_documents)
    if released:
        return BatchStatusView(
            "partial",
            STATUS_ATTENTION,
            strings.BATCH_STATUS_PARTIAL,
            strings.batch_partial_tooltip(released, len(batch.documents)),
        )
    return BatchStatusView(
        "exported",
        STATUS_ARCHIVED,
        strings.BATCH_STATUS_EXPORTED,
        strings.BATCH_EXPORTED_TOOLTIP,
    )


def _range_parts(batch: Batch) -> list[str]:
    ordered = sorted(batch.ranges.items(), key=lambda item: item[0].value)
    return [f"{kind.value} {format_range(r.first, r.last)}" for kind, r in ordered]


def ranges_text(batch: Batch) -> str:
    """For table cells: ``FC 5731 a 5748, NC 12 a 14``."""
    return ", ".join(_range_parts(batch))


def ranges_sentence(batch: Batch) -> str:
    """For sentences: ``FC 5731 a 5748 y NC 12 a 14``."""
    return strings.batch_ranges_sentence(_range_parts(batch))


def _document_row(document: BatchDocument) -> BatchDocumentRow:
    return BatchDocumentRow(
        cufe=document.cufe,
        consecutive=f"{document.document_type.value} {document.number}",
        document=document_label(document.external_prefix, document.external_number),
        supplier_nit=document.supplier_nit,
        supplier_name=document.supplier_name,
        issue_date=format_date(document.issue_date),
        released=document.released,
    )


def _summary(batch: Batch, local: datetime, invoices: int, credit_notes: int) -> str:
    return strings.batch_summary(
        format_date(local),
        f"{local:%H:%M}",
        invoices,
        credit_notes,
        released=len(batch.released_documents),
        total=len(batch.documents),
    )


def batch_row(batch: Batch) -> BatchRow:
    if batch.id is None:
        raise ValueError("only saved batches can be listed")
    local = batch.created_at.astimezone()  # la base guarda UTC; la gente lee su hora local
    invoices = sum(1 for d in batch.documents if d.document_type is DocumentType.FC)
    credit_notes = len(batch.documents) - invoices
    return BatchRow(
        batch_id=batch.id,
        date_text=format_datetime(local),
        ranges=ranges_text(batch),
        file_path=batch.file_path,
        status=batch_status_view(batch),
        summary=_summary(batch, local, invoices, credit_notes),
        invoices=invoices,
        credit_notes=credit_notes,
        released_count=len(batch.released_documents),
        voided=batch.is_voided,
        documents=tuple(_document_row(d) for d in batch.documents),
    )


def batch_rows(batches: Sequence[Batch]) -> list[BatchRow]:
    return [batch_row(batch) for batch in batches]


def _order_key(batch: Batch) -> tuple[datetime, int]:
    return batch.created_at, batch.id or 0


def void_plan(batch: Batch, company_batches: Sequence[Batch]) -> VoidPlan:
    """Same rule the use case applies (``is_last_batch``), so the confirmation never promises
    something different from what voiding does."""
    returns = is_last_batch(batch, company_batches)
    later_batch_id: int | None = None
    if not returns:
        holding = [b for b in company_batches if b.holds_numbers]
        newest = max(holding, key=_order_key, default=None)
        if newest is not None and newest.id != batch.id:
            later_batch_id = newest.id
    return VoidPlan(
        batch_id=batch.id or 0,
        returns_numbers=returns,
        ranges=ranges_sentence(batch),
        numbers=sum(r.count for r in batch.ranges.values()),
        freed_documents=sum(1 for d in batch.documents if not d.released),
        later_batch_id=later_batch_id,
    )
