"""Pure presentation of batches: status, ranges, rows and the void plan (no Qt)."""

from pathlib import Path

import pytest

from contabilizador.exports.domain.batch import Batch
from contabilizador.shared import strings
from contabilizador.ui.formatting import format_date, format_datetime
from contabilizador.ui.pages.batches.rows import (
    batch_row,
    batch_rows,
    batch_status_view,
    ranges_sentence,
    ranges_text,
    void_plan,
)
from tests.ui.pages.batches.builders import FC, NC, doc, make_batch


def mixed_batch(batch_id: int = 3, **kwargs: object) -> Batch:
    return make_batch(
        batch_id,
        doc("a", FC, 5731),
        doc("b", FC, 5732),
        doc("c", FC, 5748),
        doc("d", NC, 12),
        doc("e", NC, 14),
        **kwargs,  # type: ignore[arg-type]
    )


# --- estado ---------------------------------------------------------------------


def test_exported_batch_is_a_quiet_archived_pill() -> None:
    view = batch_status_view(mixed_batch())

    assert (view.key, view.status, view.label) == (
        "exported",
        "archived",
        strings.BATCH_STATUS_EXPORTED,
    )
    assert view.tooltip == strings.BATCH_EXPORTED_TOOLTIP


def test_batch_with_released_documents_is_partial_and_asks_for_attention() -> None:
    batch = make_batch(2, doc("a", FC, 1, released=True), doc("b", FC, 2), doc("c", FC, 3))

    view = batch_status_view(batch)

    assert (view.key, view.status, view.label) == (
        "partial",
        "incomplete",
        strings.BATCH_STATUS_PARTIAL,
    )
    assert view.tooltip == strings.batch_partial_tooltip(1, 3)


def test_voided_batch_says_whether_the_consecutives_came_back() -> None:
    returned = batch_status_view(mixed_batch(voided=True, reused=True))
    kept = batch_status_view(mixed_batch(voided=True, reused=False))

    assert (returned.key, returned.status, returned.label) == (
        "voided_returned",
        "archived",
        "Anulado con consecutivos devueltos",
    )
    assert returned.tooltip == strings.BATCH_VOIDED_RETURNED_TOOLTIP
    assert (kept.key, kept.status, kept.label) == ("voided", "archived", "Anulado")
    assert kept.tooltip == strings.BATCH_VOIDED_KEPT_TOOLTIP


def test_voided_wins_over_partial() -> None:
    batch = make_batch(2, doc("a", FC, 1, released=True), doc("b", FC, 2), voided=True)

    assert batch_status_view(batch).key == "voided"


# --- consecutivos ---------------------------------------------------------------


def test_ranges_are_listed_per_type_in_a_stable_order() -> None:
    batch = mixed_batch()

    assert ranges_text(batch) == "FC 5731 a 5748, NC 12 a 14"
    assert ranges_sentence(batch) == "FC 5731 a 5748 y NC 12 a 14"


def test_a_single_number_is_not_shown_as_a_range() -> None:
    batch = make_batch(1, doc("a", NC, 40))

    assert ranges_text(batch) == "NC 40"
    assert ranges_sentence(batch) == "NC 40"


# --- filas ----------------------------------------------------------------------


def test_batch_row_formats_everything_the_tables_show() -> None:
    batch = mixed_batch(file_path=Path("/tmp/salidas/compras septiembre.xlsx"))

    row = batch_row(batch)

    local = batch.created_at.astimezone()
    assert row.batch_id == 3
    assert row.date_text == format_datetime(local)
    assert row.ranges == "FC 5731 a 5748, NC 12 a 14"
    assert row.file_path == Path("/tmp/salidas/compras septiembre.xlsx")
    assert row.invoices == 3
    assert row.credit_notes == 2
    assert row.voided is False
    assert row.released_count == 0
    assert row.summary == strings.batch_summary(format_date(local), f"{local:%H:%M}", 3, 2)
    assert row.status.key == "exported"


def test_partial_batch_summary_adds_how_many_were_released() -> None:
    batch = make_batch(2, doc("a", FC, 1, released=True), doc("b", FC, 2))

    row = batch_row(batch)

    assert row.released_count == 1
    assert row.summary.endswith(strings.batch_released_summary(1, 2) + ".")


def test_document_rows_use_human_labels_never_cufes() -> None:
    batch = make_batch(
        1, doc("zzz-long-cufe", FC, 5731, external_number="5731", prefix="FPI", released=True)
    )

    [document] = batch_row(batch).documents

    assert document.cufe == "zzz-long-cufe"  # solo como llave interna
    assert document.consecutive == "FC 5731"
    assert document.document == "FPI-5731"
    assert document.supplier_nit == "900123456"
    assert document.supplier_name == "COMERCIALIZADORA EJEMPLO S.A.S."
    assert document.issue_date == "31/08/2026"
    assert document.released is True


def test_rows_keep_the_order_of_the_use_case() -> None:
    batches = [make_batch(3, doc("c", FC, 3)), make_batch(2, doc("b", FC, 2))]

    assert [row.batch_id for row in batch_rows(batches)] == [3, 2]


def test_a_batch_that_was_never_saved_cannot_be_listed() -> None:
    unsaved = make_batch(1, doc("a", FC, 1))
    unsaved = Batch(
        id=None,
        company_id=unsaved.company_id,
        file_path=unsaved.file_path,
        created_at=unsaved.created_at,
        documents=unsaved.documents,
    )

    with pytest.raises(ValueError):
        batch_row(unsaved)


# --- plan de anulacion ----------------------------------------------------------


def test_the_last_batch_gets_its_consecutives_back() -> None:
    first = make_batch(1, doc("a", FC, 1), doc("b", FC, 2))
    second = make_batch(2, doc("c", FC, 3), doc("d", NC, 7))

    plan = void_plan(second, [second, first])

    assert plan.batch_id == 2
    assert plan.returns_numbers is True
    assert plan.later_batch_id is None
    assert plan.ranges == "FC 3 y NC 7"
    assert plan.numbers == 2
    assert plan.freed_documents == 2


def test_an_older_batch_keeps_its_consecutives_and_names_the_later_one() -> None:
    first = make_batch(1, doc("a", FC, 1), doc("b", FC, 2))
    second = make_batch(2, doc("c", FC, 3))

    plan = void_plan(first, [second, first])

    assert plan.returns_numbers is False
    assert plan.later_batch_id == 2
    assert plan.ranges == "FC 1 a 2"
    assert plan.numbers == 2


def test_a_later_batch_that_gave_its_numbers_back_no_longer_blocks() -> None:
    first = make_batch(1, doc("a", FC, 1))
    second = make_batch(2, doc("b", FC, 2), voided=True, reused=True)

    plan = void_plan(first, [second, first])

    assert plan.returns_numbers is True


def test_a_later_voided_batch_that_kept_its_numbers_still_blocks() -> None:
    first = make_batch(1, doc("a", FC, 1))
    second = make_batch(2, doc("b", FC, 2), voided=True, reused=False)

    plan = void_plan(first, [second, first])

    assert plan.returns_numbers is False
    assert plan.later_batch_id == 2


def test_documents_released_earlier_are_not_counted_as_freed() -> None:
    batch = make_batch(1, doc("a", FC, 1, released=True), doc("b", FC, 2), doc("c", FC, 3))

    plan = void_plan(batch, [batch])

    assert plan.freed_documents == 2
    assert plan.numbers == 3
