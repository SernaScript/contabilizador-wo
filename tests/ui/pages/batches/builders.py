"""Domain builders for the Lotes exportados tests (no database, no Qt)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from contabilizador.exports.domain.batch import Batch, BatchDocument, BatchStatus
from contabilizador.exports.domain.world_office import DocumentType

FC = DocumentType.FC
NC = DocumentType.NC


def doc(
    cufe: str,
    document_type: DocumentType,
    number: int,
    *,
    released: bool = False,
    supplier: str = "COMERCIALIZADORA EJEMPLO S.A.S.",
    nit: str = "900123456",
    prefix: str = "FEV",
    external_number: str | None = None,
) -> BatchDocument:
    return BatchDocument(
        cufe=cufe,
        document_type=document_type,
        number=number,
        supplier_nit=nit,
        supplier_name=supplier,
        external_prefix=prefix,
        external_number=external_number or cufe.upper(),
        issue_date=date(2026, 8, 31),
        released=released,
    )


def make_batch(
    batch_id: int,
    *documents: BatchDocument,
    voided: bool = False,
    reused: bool = False,
    day: int | None = None,
    file_path: Path | None = None,
    company_id: int = 1,
) -> Batch:
    """Batches created on consecutive days so ``batch_id`` also orders them in time."""
    return Batch(
        id=batch_id,
        company_id=company_id,
        file_path=file_path or Path("exports") / f"lote-{batch_id}.xlsx",
        created_at=datetime(2026, 9, day or batch_id, 14, 5, tzinfo=UTC),
        documents=documents,
        status=BatchStatus.VOIDED if voided else BatchStatus.EXPORTED,
        numbers_reused=reused,
    )
