from collections.abc import Callable
from decimal import Decimal

import pytest

from contabilizador.exports.application.ports import ExportCandidate
from contabilizador.exports.application.preview_export import ExportPreview, PreviewExport
from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    CompanyNotFoundError,
    ExportBlockedError,
    ProblemKind,
    TotalsMismatch,
    TotalsMismatchError,
)
from contabilizador.exports.domain.readiness import Readiness
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.status import InvoiceStatus
from tests.exports.application.builders import (
    COMPANY_ID,
    FC,
    NC,
    Harness,
    candidate,
    harness,
    request,
)


def preview_use_case(h: Harness) -> PreviewExport:
    return PreviewExport(
        companies=h.companies,
        candidates=h.candidates,
        suppliers=h.suppliers,
        products=h.products,
        cost_centers=h.cost_centers,
        planner=h.planner,
    )


def mixed_candidates() -> list[ExportCandidate]:
    """One document per readiness state (cufes say what they are)."""
    return [
        candidate("ready"),
        candidate("credit", kind=DocumentKind.CREDIT_NOTE),
        candidate("incomplete", mapping=LineMapping("513515", None)),
        candidate("unconfigured", nit="811111111"),
        candidate("unknown-product", mapping=LineMapping("999999", "CC1")),
        candidate("mismatch", payable=Decimal("150.00")),
        candidate("exported", status=InvoiceStatus.EXPORTED),
    ]


ALL_CUFES = (
    "ready",
    "credit",
    "incomplete",
    "unconfigured",
    "unknown-product",
    "mismatch",
    "exported",
    "gone",
)


def test_preview_assesses_every_requested_document() -> None:
    h = harness(*mixed_candidates())

    preview = preview_use_case(h).execute(COMPANY_ID, [*ALL_CUFES, "ready"])

    assert isinstance(preview, ExportPreview)
    assert [(d.cufe, d.readiness) for d in preview.documents] == [
        ("ready", Readiness.READY),
        ("credit", Readiness.READY),
        ("incomplete", Readiness.INCOMPLETE),
        ("unconfigured", Readiness.BLOCKED),
        ("unknown-product", Readiness.BLOCKED),
        ("mismatch", Readiness.MISMATCH),
        ("exported", Readiness.BLOCKED),
        ("gone", Readiness.BLOCKED),
    ]
    assert preview.readiness_counts == {
        Readiness.BLOCKED: 4,
        Readiness.INCOMPLETE: 1,
        Readiness.MISMATCH: 1,
        Readiness.READY: 2,
    }
    assert preview.needs_refresh
    unknown = preview.assessment("unknown-product")
    assert unknown is not None and unknown.primary_problem is not None
    assert unknown.primary_problem.kind is ProblemKind.UNKNOWN_PRODUCT
    assert preview.assessment("not-requested") is None
    assert list(preview.by_cufe) == list(ALL_CUFES)
    assert preview.by_cufe["gone"] is preview.assessment("gone")


def test_preview_plans_consecutives_for_the_exportable_subset_only() -> None:
    h = harness(*mixed_candidates())
    h.consecutives.set_last_used(COMPANY_ID, FC, 99)

    preview = preview_use_case(h).execute(COMPANY_ID, ALL_CUFES)

    assert preview.exportable_cufes == ("ready", "credit", "mismatch")
    assert preview.counts == {FC: 2, NC: 1}
    assert preview.plan.ranges == {
        FC: ConsecutiveRange(FC, 100, 101),
        NC: ConsecutiveRange(NC, 1, 1),
    }
    assert preview.plan.collisions == ()
    assert preview.mismatches == (TotalsMismatch("mismatch", Decimal("-31")),)


def test_preview_uses_start_numbers_and_reports_collisions() -> None:
    h = harness(candidate("a"), candidate("b"))
    h.export.execute(request("a"))

    preview = preview_use_case(h).execute(COMPANY_ID, ["b"], start_numbers={FC: 1})

    assert preview.plan.ranges == {FC: ConsecutiveRange(FC, 1, 1)}
    [collision] = preview.plan.collisions
    assert collision.existing == ConsecutiveRange(FC, 1, 1)


def test_preview_is_read_only() -> None:
    h = harness(*mixed_candidates())

    preview_use_case(h).execute(COMPANY_ID, ALL_CUFES)

    assert h.exporter.written == []
    assert h.batches.items == {}
    assert h.consecutives.values == {}
    assert h.invoice_status.calls == []
    assert h.unit_of_work.transactions == 0


def test_preview_of_an_empty_selection_is_empty() -> None:
    preview = preview_use_case(harness(candidate("a"))).execute(COMPANY_ID, [])

    assert preview.documents == ()
    assert preview.exportable_cufes == ()
    assert preview.counts == {}
    assert preview.plan.ranges == {}
    assert preview.plan.collisions == ()
    assert preview.mismatches == ()
    assert not preview.needs_refresh
    assert set(preview.readiness_counts.values()) == {0}


def test_preview_requires_known_company() -> None:
    with pytest.raises(CompanyNotFoundError):
        preview_use_case(harness(candidate("a"))).execute(99, ["a"])


# --- Paridad: lo que la vista previa ofrece es exactamente lo que la exportacion acepta ---


def assert_export_accepts(make: Callable[[], Harness], cufe: str) -> None:
    make().export.execute(
        request(cufe, confirm_totals_mismatch=True, confirm_consecutive_collision=True)
    )


def test_preview_exportable_set_is_exactly_what_export_accepts() -> None:
    def make() -> Harness:
        return harness(*mixed_candidates())

    preview = preview_use_case(make()).execute(COMPANY_ID, ALL_CUFES)

    for assessment in preview.documents:
        if assessment.exportable:
            assert_export_accepts(make, assessment.cufe)
        else:
            with pytest.raises(ExportBlockedError) as error:
                assert_export_accepts(make, assessment.cufe)
            assert error.value.problems == assessment.problems

    with pytest.raises(ExportBlockedError) as everything:
        make().export.execute(request(*ALL_CUFES))
    flattened = {p for d in preview.documents for p in d.problems}
    assert set(everything.value.problems) == flattened


def test_export_of_the_previewed_subset_matches_the_preview() -> None:
    h = harness(*mixed_candidates())
    h.consecutives.set_last_used(COMPANY_ID, FC, 99)
    preview = preview_use_case(h).execute(COMPANY_ID, ALL_CUFES)

    with pytest.raises(TotalsMismatchError) as error:
        h.export.execute(request(*preview.exportable_cufes))
    assert error.value.mismatches == preview.mismatches

    batch = h.export.execute(request(*preview.exportable_cufes, confirm_totals_mismatch=True))

    assert {d.cufe for d in batch.documents} == set(preview.exportable_cufes)
    assert batch.ranges == preview.plan.ranges
