"""View-model of the export sheet: pure translation of an ``ExportPreview`` into copy.

No Qt here: the sheet receives these values and only lays them out. Documents are named
by their human label (``FPI-5731 · Proveedor``), never by CUFE.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from contabilizador.exports.application.preview_export import ExportPreview
from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    ConsecutiveCollision,
    ConsecutiveCollisionError,
    ExportBlockedError,
    TotalsMismatch,
    TotalsMismatchError,
)
from contabilizador.exports.domain.readiness import DocumentAssessment
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.shared import strings
from contabilizador.ui.formatting import document_title, format_money, format_range

# Las listas largas se cortan: el detalle de cada factura vive en la pagina Facturas
MAX_LISTED = 5


@dataclass(frozen=True, slots=True)
class TypeRow:
    """One document type of the export: how many and the first consecutive to use."""

    document_type: DocumentType
    label: str
    count: int
    start: int


@dataclass(frozen=True, slots=True)
class MismatchNotice:
    """Exportable documents whose totals differ. They leave only when the person ticks
    ``include_label``; otherwise the batch goes out without them."""

    title: str
    explanation: str
    items: tuple[str, ...]
    include_label: str = strings.EXPORT_CONFIRM_MISMATCH


@dataclass(frozen=True, slots=True)
class CollisionNotice:
    """Proposed consecutives already taken by a batch.

    Attributes:
        suggested_starts: first free number per colliding type (right after the
            highest number the colliding batches used).
        collisions: every collision, including those hidden behind the capped list;
            part of equality so a confirmation never covers collisions nobody saw.
    """

    title: str
    items: tuple[str, ...]
    suggested_starts: Mapping[DocumentType, int]
    action_label: str
    collisions: tuple[ConsecutiveCollision, ...] = ()


@dataclass(frozen=True, slots=True)
class ExportSheetState:
    """Attributes:
    skipped_text: sentence about the requested documents that are not exported
        (empty when every one is).
    mismatches / collisions: ``None`` when there is nothing to decide. The mismatches
        are listed even while they are left out of the counts.
    labels: human label of every requested document by CUFE (for error messages).
    """

    rows: tuple[TypeRow, ...]
    exportable_count: int
    skipped_text: str
    mismatches: MismatchNotice | None
    collisions: CollisionNotice | None
    labels: Mapping[str, str]


def document_label(assessment: DocumentAssessment) -> str:
    document = assessment.document
    if document is None:
        return strings.EXPORT_UNKNOWN_DOCUMENT
    return document_title(
        document.supplier_prefix, document.supplier_number, document.supplier_name
    )


def build_state(
    preview: ExportPreview, *, selection: ExportPreview | None = None
) -> ExportSheetState:
    """``preview``: what would be exported now (counts, consecutives, collisions).
    ``selection``: the preview of everything that was requested, when ``preview`` leaves
    out the invoices with a totals mismatch; they are still named and listed."""
    everything = selection if selection is not None else preview
    labels = {d.cufe: document_label(d) for d in everything.documents}
    skipped = len(preview.documents) - len(preview.exportable_cufes)
    rows = tuple(
        TypeRow(
            document_type=document_type,
            label=strings.DOCUMENT_TYPE_LABELS[document_type.value],
            count=preview.counts[document_type],
            start=preview.plan.ranges[document_type].first,
        )
        # orden estable: facturas primero, luego notas credito
        for document_type in DocumentType
        if preview.counts.get(document_type, 0) > 0
    )
    return ExportSheetState(
        rows=rows,
        exportable_count=len(preview.exportable_cufes),
        skipped_text=strings.export_skipped(skipped) if skipped else "",
        mismatches=_mismatch_notice(everything.mismatches, labels),
        collisions=collision_notice(preview.plan.collisions),
        labels=labels,
    )


def collision_notice(collisions: Sequence[ConsecutiveCollision]) -> CollisionNotice | None:
    if not collisions:
        return None
    suggested: dict[DocumentType, int] = {}
    for found in collisions:
        document_type = found.proposed.document_type
        after_batch = found.existing.last + 1
        suggested[document_type] = max(suggested.get(document_type, after_batch), after_batch)
    ordered = {t: suggested[t] for t in DocumentType if t in suggested}
    return CollisionNotice(
        title=strings.EXPORT_COLLISION_TITLE,
        items=_capped([_collision_sentence(c) for c in collisions]),
        suggested_starts=ordered,
        action_label=strings.collision_fix(list(ordered.values())),
        collisions=tuple(collisions),
    )


def _collision_sentence(collision: ConsecutiveCollision) -> str:
    return strings.collision_sentence(
        range_label(collision.proposed), collision.batch_id, range_label(collision.existing)
    )


def range_label(consecutives: ConsecutiveRange) -> str:
    """``FC 5731 a 5748`` (``FC 5731`` for a single number)."""
    numbers = format_range(consecutives.first, consecutives.last)
    return f"{consecutives.document_type.value} {numbers}"


@dataclass(frozen=True, slots=True)
class SuccessSummary:
    title: str
    saved_text: str
    ranges_text: str


def success_summary(batch: Batch) -> SuccessSummary:
    ranges = batch.ranges
    return SuccessSummary(
        title=strings.invoices_exported(len(batch.documents)),
        saved_text=strings.export_saved_in(batch.file_path.name, str(batch.file_path.parent)),
        ranges_text=strings.export_ranges_used(
            [range_label(ranges[t]) for t in DocumentType if t in ranges]
        ),
    )


def default_destination(folder: Path | None, fallback: Path, moment: datetime) -> Path:
    """Dated file name (never overwrites an earlier batch) in the last export folder,
    or in ``fallback`` when that folder is unknown, gone or unreachable.

    Checking ``folder`` touches the disk (it may be a network drive): call it off the GUI
    thread."""
    chosen = folder if folder is not None and _is_reachable_folder(folder) else fallback
    return chosen / strings.export_default_filename(moment)


def _is_reachable_folder(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:  # unidad de red caida o sin permiso: se usa la carpeta por defecto
        return False


def with_xlsx_suffix(path: Path) -> Path:
    # algunos dialogos nativos no agregan la extension del filtro
    if path.suffix.lower() == ".xlsx":
        return path
    return path.with_name(f"{path.name}.xlsx")


def labelled_error_message(error: BaseException, labels: Mapping[str, str]) -> str | None:
    """Message for the export errors that list documents, written with their labels.

    ``None`` for any other error: the ``ErrorPresenter`` copy already fits.
    """
    if isinstance(error, ExportBlockedError):
        problems = [strings.document_problem(_label(p.cufe, labels), p) for p in error.problems]
        return "\n".join([strings.ERROR_EXPORT_BLOCKED_MESSAGE, *_capped(problems)])
    if isinstance(error, TotalsMismatchError):
        return "\n".join(_capped([_mismatch_sentence(m, labels) for m in error.mismatches]))
    if isinstance(error, ConsecutiveCollisionError):
        return "\n".join(_capped([_collision_sentence(c) for c in error.collisions]))
    return None


def _mismatch_notice(
    mismatches: Sequence[TotalsMismatch], labels: Mapping[str, str]
) -> MismatchNotice | None:
    if not mismatches:
        return None
    return MismatchNotice(
        title=strings.mismatch_title(len(mismatches)),
        explanation=strings.mismatch_explanation(len(mismatches)),
        items=_capped([_mismatch_sentence(m, labels) for m in mismatches]),
        include_label=strings.export_include_mismatch(len(mismatches)),
    )


def _mismatch_sentence(mismatch: TotalsMismatch, labels: Mapping[str, str]) -> str:
    # diferencia = calculado - XML: positiva cuando las lineas suman mas
    return strings.mismatch_item(
        _label(mismatch.cufe, labels),
        format_money(abs(mismatch.difference)),
        lines_exceed=mismatch.difference > 0,
    )


def _label(cufe: str, labels: Mapping[str, str]) -> str:
    return labels.get(cufe, strings.EXPORT_UNKNOWN_DOCUMENT)


def _capped(items: Sequence[str]) -> tuple[str, ...]:
    if len(items) <= MAX_LISTED:
        return tuple(items)
    return (*items[:MAX_LISTED], strings.more_items(len(items) - MAX_LISTED))
