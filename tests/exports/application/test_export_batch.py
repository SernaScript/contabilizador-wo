from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from contabilizador.exports.application.export_batch import ExportRequest
from contabilizador.exports.application.manage_batches import ListBatches
from contabilizador.exports.domain.batch import BatchStatus
from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    BatchNotFoundError,
    CompanyNotFoundError,
    ConsecutiveCollisionError,
    ExportBlockedError,
    NothingToExportError,
    ProblemKind,
    TotalsMismatchError,
)
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from tests.exports.application.builders import (
    COMPANY_ID,
    FC,
    NC,
    candidate,
    harness,
    request,
)

# --- PlanConsecutives ---


def test_plan_suggests_last_used_plus_one_per_type() -> None:
    h = harness()
    h.consecutives.set_last_used(COMPANY_ID, FC, 9420378243)

    plan = h.planner.execute(COMPANY_ID, {FC: 2, NC: 1})

    assert plan.ranges == {
        FC: ConsecutiveRange(FC, 9420378244, 9420378245),
        NC: ConsecutiveRange(NC, 1, 1),
    }
    assert plan.collisions == ()


def test_plan_detects_collision_with_existing_batch() -> None:
    h = harness(candidate("a"), candidate("b"))
    h.export.execute(request("a", "b"))

    plan = h.planner.execute(COMPANY_ID, {FC: 1}, starts={FC: 2})

    assert len(plan.collisions) == 1
    assert plan.collisions[0].existing == ConsecutiveRange(FC, 1, 2)


# --- ExportBatch ---


def test_export_writes_workbook_and_records_batch() -> None:
    h = harness(
        candidate("b", issue_date=date(2026, 9, 2)),
        candidate("a", issue_date=date(2026, 9, 1)),
        candidate("n", kind=DocumentKind.CREDIT_NOTE),
    )
    h.consecutives.set_last_used(COMPANY_ID, FC, 99)

    batch = h.export.execute(request("b", "a", "n"))

    [(documents, destination)] = h.exporter.written
    assert destination == Path("out") / "lote.xlsx"
    # orden cronologico; consecutivos por tipo
    assert [(d.document_type, d.number, d.external_number) for d in documents] == [
        (NC, 1, "0n"),
        (FC, 100, "0a"),
        (FC, 101, "0b"),
    ]
    assert documents[1].lines[0].cost_center_name == "GERENCIA GENERAL"
    assert batch.id == 1
    assert batch.file_path == destination
    assert batch.ranges == {FC: ConsecutiveRange(FC, 100, 101), NC: ConsecutiveRange(NC, 1, 1)}
    assert h.consecutives.last_used(COMPANY_ID, FC) == 101
    assert h.consecutives.last_used(COMPANY_ID, NC) == 1
    assert h.invoice_status.calls == [(COMPANY_ID, ["b", "a", "n"], InvoiceStatus.EXPORTED)]


def test_export_uses_explicit_start_numbers() -> None:
    h = harness(candidate("a"))

    batch = h.export.execute(request("a", start_numbers={FC: 9420378244}))

    assert batch.documents[0].number == 9420378244


def test_export_requires_known_company() -> None:
    h = harness(candidate("a"))
    with pytest.raises(CompanyNotFoundError):
        h.export.execute(ExportRequest(company_id=99, cufes=("a",), destination=Path("x.xlsx")))


def test_export_requires_documents() -> None:
    with pytest.raises(NothingToExportError):
        harness().export.execute(request())


def test_export_is_blocked_listing_every_problem() -> None:
    h = harness(
        candidate("unconfigured", nit="811111111"),
        candidate("no-mapping", mapping=None),
        candidate("no-cc", mapping=LineMapping("513515", None)),
        candidate("bad-cc", mapping=LineMapping("513515", "ZZ")),
        candidate("exported", status=InvoiceStatus.EXPORTED),
        candidate("ok"),
    )

    with pytest.raises(ExportBlockedError) as error:
        h.export.execute(
            request("unconfigured", "no-mapping", "no-cc", "bad-cc", "exported", "missing", "ok")
        )

    problems = {(p.kind, p.cufe, p.line_number, p.detail) for p in error.value.problems}
    assert problems == {
        (ProblemKind.UNCONFIGURED_SUPPLIER, "unconfigured", None, "811111111"),
        (ProblemKind.MISSING_PRODUCT, "no-mapping", 1, ""),
        (ProblemKind.MISSING_COST_CENTER, "no-mapping", 1, ""),
        (ProblemKind.MISSING_COST_CENTER, "no-cc", 1, ""),
        (ProblemKind.UNKNOWN_COST_CENTER, "bad-cc", 1, "ZZ"),
        (ProblemKind.ALREADY_EXPORTED, "exported", None, ""),
        (ProblemKind.DOCUMENT_NOT_FOUND, "missing", None, ""),
    }
    assert h.exporter.written == []
    assert h.batches.items == {}


def test_export_is_blocked_by_products_missing_from_the_catalog() -> None:
    h = harness(candidate("a", mapping=LineMapping("999999", "CC1")))

    with pytest.raises(ExportBlockedError) as error:
        h.export.execute(request("a"))

    assert [(p.kind, p.cufe, p.line_number, p.detail) for p in error.value.problems] == [
        (ProblemKind.UNKNOWN_PRODUCT, "a", 1, "999999")
    ]
    assert h.exporter.written == []


def test_blocked_problems_list_missing_documents_first() -> None:
    h = harness(candidate("no-cc", mapping=LineMapping("513515", None)))

    with pytest.raises(ExportBlockedError) as error:
        h.export.execute(request("no-cc", "missing"))

    assert [(p.kind, p.cufe) for p in error.value.problems] == [
        (ProblemKind.DOCUMENT_NOT_FOUND, "missing"),
        (ProblemKind.MISSING_COST_CENTER, "no-cc"),
    ]


def test_released_documents_can_be_exported_again() -> None:
    h = harness(candidate("a", status=InvoiceStatus.RELEASED))
    assert h.export.execute(request("a")).documents[0].cufe == "a"


def test_totals_mismatch_requires_confirmation() -> None:
    h = harness(candidate("a", payable=Decimal("150.00")))

    with pytest.raises(TotalsMismatchError) as error:
        h.export.execute(request("a"))

    assert [(m.cufe, m.difference) for m in error.value.mismatches] == [("a", Decimal("-31"))]
    assert h.exporter.written == []
    assert h.export.execute(request("a", confirm_totals_mismatch=True)).id == 1


def test_totals_within_one_peso_do_not_require_confirmation() -> None:
    h = harness(candidate("a", payable=Decimal("119.90")))
    assert h.export.execute(request("a")).id == 1


def test_consecutive_collision_requires_confirmation() -> None:
    h = harness(candidate("a"), candidate("b"))
    h.export.execute(request("a"))

    with pytest.raises(ConsecutiveCollisionError):
        h.export.execute(request("b", start_numbers={FC: 1}))

    batch = h.export.execute(
        request("b", start_numbers={FC: 1}, confirm_consecutive_collision=True)
    )
    assert batch.documents[0].number == 1
    # el ultimo usado nunca retrocede
    assert h.consecutives.last_used(COMPANY_ID, FC) == 1


def test_failed_write_does_not_record_anything() -> None:
    h = harness(candidate("a"))
    h.exporter.fail = True

    with pytest.raises(OSError):
        h.export.execute(request("a"))

    assert h.batches.items == {}
    assert h.consecutives.values == {}
    assert h.invoice_status.calls == []


# --- VoidBatch / ReleaseDocuments / ListBatches ---


def test_void_last_batch_gives_consecutives_back() -> None:
    h = harness(candidate("a"), candidate("b"), candidate("c"))
    h.export.execute(request("a"))
    last = h.export.execute(request("b", "c"))

    voided = h.void.execute(last.id or 0)

    assert voided.status is BatchStatus.VOIDED
    assert voided.numbers_reused
    assert h.consecutives.last_used(COMPANY_ID, FC) == 1
    assert h.invoice_status.calls[-1] == (COMPANY_ID, ["b", "c"], InvoiceStatus.RELEASED)
    assert h.planner.execute(COMPANY_ID, {FC: 2}).ranges[FC] == ConsecutiveRange(FC, 2, 3)


def test_void_older_batch_burns_its_consecutives() -> None:
    h = harness(candidate("a"), candidate("b"))
    first = h.export.execute(request("a"))
    h.export.execute(request("b"))

    voided = h.void.execute(first.id or 0)

    assert voided.status is BatchStatus.VOIDED
    assert not voided.numbers_reused
    assert h.consecutives.last_used(COMPANY_ID, FC) == 2
    plan = h.planner.execute(COMPANY_ID, {FC: 1}, starts={FC: 1})
    assert [c.batch_id for c in plan.collisions] == [first.id]


def test_void_last_batch_after_jump_returns_to_number_before_its_range() -> None:
    h = harness(candidate("a"), candidate("b"))
    h.export.execute(request("a"))
    last = h.export.execute(request("b", start_numbers={FC: 500}))

    h.void.execute(last.id or 0)

    assert h.consecutives.last_used(COMPANY_ID, FC) == 499


def test_void_unknown_batch_fails() -> None:
    with pytest.raises(BatchNotFoundError):
        harness().void.execute(42)


def test_release_documents_burns_their_consecutives() -> None:
    h = harness(candidate("a"), candidate("b"))
    batch = h.export.execute(request("a", "b"))

    released = h.release.execute(batch.id or 0, ["a"])

    assert [d.cufe for d in released.released_documents] == ["a"]
    assert h.consecutives.last_used(COMPANY_ID, FC) == 2
    assert h.invoice_status.calls[-1] == (COMPANY_ID, ["a"], InvoiceStatus.RELEASED)
    assert h.batches.get(batch.id or 0) == released


def test_release_unknown_batch_fails() -> None:
    with pytest.raises(BatchNotFoundError):
        harness().release.execute(42, ["a"])


def test_list_batches_newest_first_with_released_history() -> None:
    h = harness(candidate("a"), candidate("b"))
    first = h.export.execute(request("a"))
    second = h.export.execute(request("b"))
    h.void.execute(first.id or 0)

    batches = ListBatches(batches=h.batches).execute(COMPANY_ID)

    assert [b.id for b in batches] == [second.id, first.id]
    assert [d.cufe for d in batches[1].released_documents] == ["a"]


def test_void_does_not_release_documents_already_released_and_reexported() -> None:
    h = harness(candidate("a"), candidate("b"))
    first = h.export.execute(request("a", "b"))
    h.release.execute(first.id or 0, ["a"])
    h.export.execute(request("a"))  # "a" vuelve a exportarse en otro lote

    h.void.execute(first.id or 0)

    assert h.invoice_status.calls[-1] == (COMPANY_ID, ["b"], InvoiceStatus.RELEASED)


def test_export_persists_inside_one_transaction() -> None:
    h = harness(candidate("a"))

    h.export.execute(request("a"))

    assert h.unit_of_work.writes_outside_transaction == []
    assert h.unit_of_work.transactions == 1


def test_void_and_release_persist_inside_one_transaction_each() -> None:
    h = harness(candidate("a"), candidate("b"))
    batch = h.export.execute(request("a", "b"))

    h.release.execute(batch.id or 0, ["a"])
    h.void.execute(batch.id or 0)

    assert h.unit_of_work.writes_outside_transaction == []
    assert h.unit_of_work.transactions == 3
