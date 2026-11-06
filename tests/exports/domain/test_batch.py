from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from contabilizador.exports.domain.batch import (
    Batch,
    BatchDocument,
    BatchStatus,
    find_collisions,
    is_last_batch,
)
from contabilizador.exports.domain.consecutives import ConsecutiveRange, suggest_start
from contabilizador.exports.domain.errors import (
    BatchAlreadyVoidedError,
    DocumentAlreadyReleasedError,
    DocumentNotInBatchError,
)
from contabilizador.exports.domain.world_office import DocumentType

FC = DocumentType.FC
NC = DocumentType.NC


def doc(cufe: str, document_type: DocumentType, number: int) -> BatchDocument:
    return BatchDocument(
        cufe=cufe,
        document_type=document_type,
        number=number,
        supplier_nit="900123456",
        supplier_name="PROVEEDOR",
        external_prefix="FEV",
        external_number=cufe.upper(),
        issue_date=date(2026, 8, 31),
    )


def make_batch(batch_id: int, *documents: BatchDocument) -> Batch:
    return Batch(
        id=batch_id,
        company_id=1,
        file_path=Path("exports") / f"lote-{batch_id}.xlsx",
        created_at=datetime(2026, 9, batch_id, tzinfo=UTC),
        documents=documents,
    )


# --- consecutivos ---


def test_suggest_start_is_last_used_plus_one() -> None:
    assert suggest_start(41) == 42


def test_suggest_start_without_history_is_one() -> None:
    assert suggest_start(None) == 1


def test_range_from_start_and_count() -> None:
    consecutive_range = ConsecutiveRange.from_start(FC, start=10, count=3)
    assert (consecutive_range.first, consecutive_range.last) == (10, 12)
    assert list(consecutive_range.numbers()) == [10, 11, 12]


@pytest.mark.parametrize(("first", "last"), [(0, 1), (5, 4)])
def test_range_rejects_invalid_bounds(first: int, last: int) -> None:
    with pytest.raises(ValueError):
        ConsecutiveRange(FC, first, last)


def test_ranges_overlap_only_for_same_type() -> None:
    fc = ConsecutiveRange(FC, 10, 12)
    assert fc.overlaps(ConsecutiveRange(FC, 12, 20))
    assert not fc.overlaps(ConsecutiveRange(FC, 13, 20))
    assert not fc.overlaps(ConsecutiveRange(NC, 10, 12))


# --- lote ---


def test_batch_ranges_per_type() -> None:
    batch = make_batch(1, doc("a", FC, 10), doc("b", FC, 11), doc("c", NC, 3))
    assert batch.ranges == {FC: ConsecutiveRange(FC, 10, 11), NC: ConsecutiveRange(NC, 3, 3)}


def test_batch_requires_documents() -> None:
    with pytest.raises(ValueError):
        make_batch(1)


def test_batch_rejects_duplicated_numbers() -> None:
    with pytest.raises(ValueError):
        make_batch(1, doc("a", FC, 10), doc("b", FC, 10))


def test_release_marks_only_selected_documents() -> None:
    batch = make_batch(1, doc("a", FC, 10), doc("b", FC, 11))

    released = batch.release(["b"])

    assert [d.released for d in released.documents] == [False, True]
    assert released.status is BatchStatus.EXPORTED
    assert [d.cufe for d in released.released_documents] == ["b"]
    # los numeros liberados quedan quemados: el rango no cambia
    assert released.ranges == batch.ranges


def test_release_rejects_unknown_document() -> None:
    with pytest.raises(DocumentNotInBatchError):
        make_batch(1, doc("a", FC, 10)).release(["zzz"])


def test_release_rejects_already_released_document() -> None:
    batch = make_batch(1, doc("a", FC, 10), doc("b", FC, 11)).release(["a"])
    with pytest.raises(DocumentAlreadyReleasedError):
        batch.release(["a"])


def test_void_releases_every_document() -> None:
    batch = make_batch(1, doc("a", FC, 10), doc("b", FC, 11)).release(["a"])

    voided = batch.void(reuse_numbers=True)

    assert voided.status is BatchStatus.VOIDED
    assert voided.numbers_reused is True
    assert all(d.released for d in voided.documents)
    assert not voided.holds_numbers


def test_void_twice_fails() -> None:
    voided = make_batch(1, doc("a", FC, 10)).void(reuse_numbers=False)
    assert voided.holds_numbers  # anulado sin reutilizar: numeros quemados
    with pytest.raises(BatchAlreadyVoidedError):
        voided.void(reuse_numbers=False)


def test_release_on_voided_batch_fails() -> None:
    voided = make_batch(1, doc("a", FC, 10)).void(reuse_numbers=False)
    with pytest.raises(BatchAlreadyVoidedError):
        voided.release(["a"])


def test_is_last_batch_ignores_batches_whose_numbers_were_reused() -> None:
    first = make_batch(1, doc("a", FC, 1))
    second = make_batch(2, doc("b", FC, 2))
    third = make_batch(3, doc("c", FC, 3)).void(reuse_numbers=True)
    batches = [first, second, third]

    assert is_last_batch(second, batches)
    assert not is_last_batch(first, batches)


def test_burned_voided_batch_still_counts_as_last() -> None:
    first = make_batch(1, doc("a", FC, 1))
    second = make_batch(2, doc("b", FC, 2)).void(reuse_numbers=False)
    assert not is_last_batch(first, [first, second])


def test_find_collisions_against_batches_holding_numbers() -> None:
    held = make_batch(1, doc("a", FC, 10), doc("b", FC, 11))
    reused = make_batch(2, doc("c", FC, 12)).void(reuse_numbers=True)

    collisions = find_collisions([ConsecutiveRange(FC, 11, 13)], [held, reused])

    assert len(collisions) == 1
    assert collisions[0].batch_id == 1
    assert collisions[0].proposed == ConsecutiveRange(FC, 11, 13)
    assert collisions[0].existing == ConsecutiveRange(FC, 10, 11)


def test_find_collisions_empty_when_no_overlap() -> None:
    held = make_batch(1, doc("a", FC, 10))
    assert (
        find_collisions([ConsecutiveRange(FC, 11, 13), ConsecutiveRange(NC, 10, 10)], [held]) == []
    )
