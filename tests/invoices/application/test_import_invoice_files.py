from pathlib import Path

import pytest

from contabilizador.invoices.application.errors import ImportCancelledError
from contabilizador.invoices.application.import_invoice_files import ImportInvoiceFiles
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.invoices.domain.source import LoadResult, SkippedFile
from contabilizador.invoices.domain.status import InvoiceStatus
from tests.invoices.application.fakes import (
    FakeDocumentSource,
    FakeInvoiceRepository,
    FakeUnitOfWork,
)
from tests.invoices.factories import make_document

COMPANY = 1


def run(result: LoadResult, repo: FakeInvoiceRepository | None = None):
    repo = repo or FakeInvoiceRepository()
    source = FakeDocumentSource(result)
    report = ImportInvoiceFiles(source, repo, FakeUnitOfWork()).execute(COMPANY, [Path("in")])
    return report, repo, source


def test_imports_new_documents_as_pending() -> None:
    report, repo, source = run(
        LoadResult(parsed=(make_document(cufe="a"), make_document(cufe="b")))
    )
    assert source.received == [Path("in")]
    assert [item.document.cufe for item in report.imported] == ["a", "b"]
    assert all(repo.get(COMPANY, item.invoice_id) is not None for item in report.imported)
    assert {s.status for s in repo.invoices.values()} == {InvoiceStatus.PENDING}
    assert report.duplicates == ()


def test_skips_documents_already_stored_for_the_company() -> None:
    repo = FakeInvoiceRepository()
    repo.add(COMPANY, make_document(cufe="a"))
    repo.add(2, make_document(cufe="b"))
    report, repo, _ = run(
        LoadResult(parsed=(make_document(cufe="a"), make_document(cufe="b"))), repo
    )
    assert [d.cufe for d in report.duplicates] == ["a"]
    assert [item.document.cufe for item in report.imported] == ["b"]


def test_dedups_within_the_same_import() -> None:
    report, repo, _ = run(LoadResult(parsed=(make_document(cufe="a"), make_document(cufe="a"))))
    assert len(report.imported) == 1
    assert [d.cufe for d in report.duplicates] == ["a"]
    assert len(repo.invoices) == 1


def test_passes_through_ignored_and_failed() -> None:
    ignored = (SkippedFile("r.xml", "Tipo de documento no soportado: ApplicationResponse"),)
    failed = (SkippedFile("x.xml", "XML mal formado"),)
    report, _, _ = run(LoadResult(ignored=ignored, failed=failed))
    assert report.ignored == ignored
    assert report.failed == failed
    assert report.imported == ()


def test_flags_credit_notes_whose_original_invoice_is_missing() -> None:
    orphan = make_document(
        cufe="nc-1", kind=DocumentKind.CREDIT_NOTE, billing_reference_cufe="missing"
    )
    with_original = make_document(
        cufe="nc-2", kind=DocumentKind.CREDIT_NOTE, billing_reference_cufe="inv-1"
    )
    without_reference = make_document(cufe="nc-3", kind=DocumentKind.CREDIT_NOTE)
    report, _, _ = run(
        LoadResult(parsed=(orphan, with_original, make_document(cufe="inv-1"), without_reference))
    )
    assert [d.cufe for d in report.credit_notes_without_original] == ["nc-1", "nc-3"]


def test_credit_note_original_may_already_be_stored() -> None:
    repo = FakeInvoiceRepository()
    repo.add(COMPANY, make_document(cufe="inv-1"))
    note = make_document(cufe="nc", kind=DocumentKind.CREDIT_NOTE, billing_reference_cufe="inv-1")
    report, _, _ = run(LoadResult(parsed=(note,)), repo)
    assert report.credit_notes_without_original == ()


def test_passes_progress_and_cancel_callbacks_to_the_source() -> None:
    source = FakeDocumentSource(LoadResult())
    progress: list[tuple[int, int]] = []

    def on_progress(done: int, total: int) -> None:
        progress.append((done, total))

    def is_cancelled() -> bool:
        return False

    ImportInvoiceFiles(source, FakeInvoiceRepository(), FakeUnitOfWork()).execute(
        COMPANY, [Path("in")], on_progress=on_progress, is_cancelled=is_cancelled
    )

    assert source.on_progress is on_progress
    assert source.is_cancelled is is_cancelled


def test_cancel_while_reading_imports_nothing() -> None:
    repo = FakeInvoiceRepository()
    source = FakeDocumentSource(LoadResult(), error=ImportCancelledError())

    with pytest.raises(ImportCancelledError):
        ImportInvoiceFiles(source, repo, FakeUnitOfWork()).execute(COMPANY, [Path("in")])

    assert repo.invoices == {}


def test_cancel_after_reading_imports_nothing() -> None:
    repo = FakeInvoiceRepository()
    # la fuente termino de leer: se cancela justo antes de guardar
    source = FakeDocumentSource(LoadResult(parsed=(make_document(cufe="a"),)))

    with pytest.raises(ImportCancelledError):
        ImportInvoiceFiles(source, repo, FakeUnitOfWork()).execute(
            COMPANY, [Path("in")], is_cancelled=lambda: True
        )

    assert repo.invoices == {}


def test_documents_are_stored_in_one_transaction() -> None:
    repo = FakeInvoiceRepository()
    unit_of_work = FakeUnitOfWork()
    repo.unit_of_work = unit_of_work
    source = FakeDocumentSource(
        LoadResult(parsed=(make_document(cufe="a"), make_document(cufe="b")))
    )

    ImportInvoiceFiles(source, repo, unit_of_work).execute(COMPANY, [Path("in")])

    assert len(repo.invoices) == 2
    assert unit_of_work.transactions == 1
    assert unit_of_work.writes_outside_transaction == []
