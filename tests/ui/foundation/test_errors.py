"""ErrorPresenter: every exception becomes Spanish copy (what happened + how to fix it)."""

from decimal import Decimal

import pytest
from PySide6.QtWidgets import QMessageBox

from contabilizador.catalog.application.import_catalog import UnreadableCatalogFileError
from contabilizador.companies.application.errors import DuplicateCompanyNameError
from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    BatchAlreadyVoidedError,
    BatchNotFoundError,
    CompanyNotFoundError,
    ConsecutiveCollision,
    ConsecutiveCollisionError,
    DocumentAlreadyReleasedError,
    DocumentNotInBatchError,
    ExportBlockedError,
    ExportProblem,
    NothingToExportError,
    ProblemKind,
    TotalsMismatch,
    TotalsMismatchError,
)
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.application.errors import (
    DocumentNotEditableError,
    ImportCancelledError,
    InvoiceNotFoundError,
    LineNotFoundError,
)
from contabilizador.invoices.domain.errors import InvalidDocumentError, UnsupportedDocumentError
from contabilizador.shared import strings
from contabilizador.ui.errors import ErrorPresentation, ErrorPresenter
from contabilizador.ui.tasks import TaskCancelledError


@pytest.fixture
def presenter() -> ErrorPresenter:
    return ErrorPresenter()


def test_permission_error_on_export_tells_to_close_excel(presenter: ErrorPresenter) -> None:
    shown = presenter.present(PermissionError(13, "Permission denied"), context="export")

    assert shown.title == strings.ERROR_FILE_LOCKED_TITLE
    assert shown.hint == "Cierra el archivo en Excel e inténtalo de nuevo."
    assert "Permission denied" not in shown.message
    assert "Permission denied" in shown.details


def test_os_error_on_export_is_treated_as_locked_file(presenter: ErrorPresenter) -> None:
    shown = presenter.present(OSError("device busy"), context="export")

    assert shown.hint == strings.ERROR_FILE_LOCKED_HINT


def test_file_not_found_outside_export_explains_reading(presenter: ErrorPresenter) -> None:
    shown = presenter.present(FileNotFoundError("missing.xml"), context="import")

    assert shown.title == strings.ERROR_FILE_READ_TITLE
    assert shown.message == strings.ERROR_FILE_NOT_FOUND_MESSAGE


def test_generic_fallback_has_no_raw_english_outside_details(presenter: ErrorPresenter) -> None:
    shown = presenter.present(RuntimeError("database is locked"))

    assert shown.title == strings.ERROR_GENERIC_TITLE
    assert "database is locked" not in shown.title
    assert "database is locked" not in shown.message
    assert "database is locked" not in shown.hint
    assert "database is locked" in shown.details
    assert "RuntimeError" in shown.details


def test_export_blocked_says_how_many_invoices_and_why(presenter: ErrorPresenter) -> None:
    error = ExportBlockedError(
        [
            ExportProblem(ProblemKind.MISSING_PRODUCT, "cufe-abcdefghijkl-rest", line_number=2),
            ExportProblem(ProblemKind.MISSING_PRODUCT, "cufe-abcdefghijkl-rest", line_number=3),
            ExportProblem(ProblemKind.UNKNOWN_PRODUCT, "cufe-zyxw", line_number=1, detail="P-9"),
        ]
    )

    shown = presenter.present(error)

    assert shown.title == strings.ERROR_EXPORT_BLOCKED_TITLE
    assert shown.message == strings.export_blocked_message(
        2,
        [
            strings.problem_kind_message("missing_product"),
            strings.problem_kind_message("unknown_product"),
        ],
    )
    assert shown.hint == strings.ERROR_EXPORT_BLOCKED_HINT


def test_totals_mismatch_and_nothing_to_export(presenter: ErrorPresenter) -> None:
    mismatch = presenter.present(TotalsMismatchError([TotalsMismatch("cufe-1", Decimal("2.50"))]))
    nothing = presenter.present(NothingToExportError())
    voided = presenter.present(BatchAlreadyVoidedError())

    assert mismatch.title == strings.ERROR_EXPORT_TOTALS_TITLE
    assert mismatch.message == strings.totals_mismatch_count(1)
    assert nothing.title == strings.ERROR_NOTHING_TO_EXPORT_TITLE
    assert voided.title == strings.ERROR_BATCH_VOIDED_TITLE


def test_collisions_are_written_as_ranges_and_batches(presenter: ErrorPresenter) -> None:
    collision = ConsecutiveCollision(
        3,
        ConsecutiveRange(DocumentType.FC, 5725, 5742),
        ConsecutiveRange(DocumentType.FC, 5730, 5730),
    )

    shown = presenter.present(ConsecutiveCollisionError([collision]))

    assert shown.title == strings.ERROR_EXPORT_COLLISION_TITLE
    assert shown.message == strings.collision_sentence("FC 5725 a 5742", 3, "FC 5730")


# Errores de la capa de aplicacion: cada uno con su titulo en espanol, nunca el generico
APPLICATION_ERRORS = [
    (DuplicateCompanyNameError("WEARE DEV S.A.S"), strings.ERROR_DUPLICATE_COMPANY_TITLE),
    (ImportCancelledError(), strings.ERROR_IMPORT_CANCELLED_TITLE),
    (InvoiceNotFoundError(7), strings.INVOICE_NOT_FOUND_TITLE),
    (LineNotFoundError("line 3"), strings.ERROR_LINE_NOT_FOUND_TITLE),
    (DocumentNotEditableError("cufe-123"), strings.ERROR_DOCUMENT_NOT_EDITABLE_TITLE),
    (UnreadableCatalogFileError("not a workbook"), strings.ERROR_CATALOG_UNREADABLE_TITLE),
    (InvalidDocumentError("broken"), strings.ERROR_INVALID_DOCUMENT_TITLE),
    (UnsupportedDocumentError("ApplicationResponse"), strings.ERROR_UNSUPPORTED_DOCUMENT_TITLE),
    (CompanyNotFoundError(3), strings.ERROR_COMPANY_NOT_FOUND_TITLE),
    (BatchNotFoundError(4), strings.ERROR_BATCH_NOT_FOUND_TITLE),
    (BatchAlreadyVoidedError(), strings.ERROR_BATCH_VOIDED_TITLE),
    (DocumentNotInBatchError(["cufe-abc"]), strings.ERROR_DOCUMENT_NOT_IN_BATCH_TITLE),
    (DocumentAlreadyReleasedError(["cufe-abc"]), strings.ERROR_DOCUMENT_RELEASED_TITLE),
    (NothingToExportError(), strings.ERROR_NOTHING_TO_EXPORT_TITLE),
]


@pytest.mark.parametrize(("error", "title"), APPLICATION_ERRORS)
def test_every_application_error_has_its_own_spanish_copy(
    presenter: ErrorPresenter, error: Exception, title: str
) -> None:
    shown = presenter.present(error)

    assert shown.title == title
    assert shown.message
    assert type(error).__name__ in shown.details


def test_duplicate_company_names_the_company(presenter: ErrorPresenter) -> None:
    shown = presenter.present(DuplicateCompanyNameError("WEARE DEV S.A.S"))

    assert shown.message == strings.company_name_taken("WEARE DEV S.A.S")
    assert shown.hint == strings.ERROR_DUPLICATE_COMPANY_HINT


def test_stale_invoice_says_the_list_was_refreshed(presenter: ErrorPresenter) -> None:
    shown = presenter.present(InvoiceNotFoundError(7))

    assert shown.hint == strings.INVOICE_NOT_FOUND_HINT


@pytest.mark.parametrize(
    "error",
    [
        ExportBlockedError([ExportProblem(ProblemKind.UNCONFIGURED_SUPPLIER, "cufe-abcdefgh")]),
        TotalsMismatchError([TotalsMismatch("cufe-abcdefgh", Decimal("2.50"))]),
        DocumentNotInBatchError(["cufe-abcdefgh", "cufe-ijklmnop"]),
        DocumentAlreadyReleasedError(["cufe-abcdefgh"]),
        DocumentNotEditableError("cufe-abcdefgh"),
    ],
)
def test_documents_are_never_named_by_cufe(presenter: ErrorPresenter, error: Exception) -> None:
    shown = presenter.present(error)

    visible = f"{shown.title} {shown.message} {shown.hint}".lower()
    assert "cufe" not in visible
    assert "cufe-abcdefgh" in shown.details or type(error).__name__ in shown.details


def test_released_and_foreign_documents_are_counted(presenter: ErrorPresenter) -> None:
    released = presenter.present(DocumentAlreadyReleasedError(["a", "b"]))
    foreign = presenter.present(DocumentNotInBatchError(["a"]))

    assert released.message == strings.documents_already_released(2)
    assert foreign.message == strings.documents_not_in_batch(1)


def test_register_custom_type_and_subclass_lookup(presenter: ErrorPresenter) -> None:
    class QuotaError(Exception):
        pass

    class DailyQuotaError(QuotaError):
        pass

    presenter.register(
        QuotaError,
        lambda error, context: ErrorPresentation("Sin cupo", "Se agotó el cupo.", "Espera."),
    )

    shown = presenter.present(DailyQuotaError("quota"))

    assert shown.title == "Sin cupo"
    assert shown.details.startswith("DailyQuotaError")


def test_register_by_class_name_for_types_defined_elsewhere(presenter: ErrorPresenter) -> None:
    class PluginQuotaError(Exception):
        pass

    presenter.register(
        "PluginQuotaError",
        lambda error, context: ErrorPresentation("Sin cupo", "Se agotó el cupo."),
    )

    shown = presenter.present(PluginQuotaError("quota"))

    assert shown.title == "Sin cupo"


def test_task_cancelled_has_its_own_copy(presenter: ErrorPresenter) -> None:
    shown = presenter.present(TaskCancelledError())

    assert shown.title == strings.ERROR_TASK_CANCELLED_TITLE


def test_message_box_carries_title_message_hint_and_details(
    presenter: ErrorPresenter, qtbot
) -> None:
    box = presenter.build_message_box(None, RuntimeError("raw text"))
    qtbot.addWidget(box)

    assert isinstance(box, QMessageBox)
    # El titular va en el texto principal: macOS no muestra el titulo de la ventana
    assert box.text() == strings.ERROR_GENERIC_TITLE
    assert strings.ERROR_GENERIC_MESSAGE in box.informativeText()
    assert strings.ERROR_GENERIC_HINT in box.informativeText()
    assert "raw text" not in box.text()
    assert "raw text" not in box.informativeText()
    assert "raw text" in box.detailedText()
    assert box.standardButtons() == QMessageBox.StandardButton.Ok
