"""ErrorPresenter: maps exceptions to Spanish copy (title, message, hint) with the raw
text only in the expandable details.

Formatters are registered per exception type (subclasses match through the MRO) or per
class name for types the UI cannot import. Every error of the application layer has its
own copy (see ``register_defaults``); documents are counted, never named by their CUFE
(pages that know the labels, like the export sheet, rewrite the message themselves).

``context`` tells which flow raised (``"export"``, ``"import"``, ``"catalog"``...) so an
``OSError`` can say "close the file in Excel" only when writing a workbook:
``CONTEXT_EXPORT`` covers every workbook the app writes, the catalog template included.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from PySide6.QtWidgets import QMessageBox, QWidget

from contabilizador.catalog.application.import_catalog import UnreadableCatalogFileError
from contabilizador.companies.application.errors import DuplicateCompanyNameError
from contabilizador.exports.domain.consecutives import ConsecutiveRange
from contabilizador.exports.domain.errors import (
    BatchAlreadyVoidedError,
    BatchNotFoundError,
    CompanyNotFoundError,
    ConsecutiveCollisionError,
    DocumentAlreadyReleasedError,
    DocumentNotInBatchError,
    ExportBlockedError,
    NothingToExportError,
    TotalsMismatchError,
)
from contabilizador.invoices.application.errors import (
    DocumentNotEditableError,
    ImportCancelledError,
    InvoiceNotFoundError,
    LineNotFoundError,
)
from contabilizador.invoices.domain.errors import InvalidDocumentError, UnsupportedDocumentError
from contabilizador.shared import strings
from contabilizador.ui.formatting import format_range
from contabilizador.ui.tasks import TaskCancelledError

CONTEXT_EXPORT = "export"
CONTEXT_IMPORT = "import"
CONTEXT_CATALOG = "catalog"


@dataclass(frozen=True, slots=True)
class ErrorPresentation:
    title: str
    message: str
    hint: str = ""
    details: str = ""


Formatter = Callable[[BaseException, str | None], ErrorPresentation]


def static(title: str, message: str, hint: str = "") -> Formatter:
    """Formatter that ignores the exception and always shows the same copy."""

    def format_error(error: BaseException, context: str | None) -> ErrorPresentation:
        return ErrorPresentation(title, message, hint)

    return format_error


def technical_details(error: BaseException) -> str:
    text = str(error)
    name = type(error).__name__
    return f"{name}: {text}" if text else name


def _os_error(error: BaseException, context: str | None) -> ErrorPresentation:
    if isinstance(error, PermissionError) or context == CONTEXT_EXPORT:
        return ErrorPresentation(
            strings.ERROR_FILE_LOCKED_TITLE,
            strings.ERROR_FILE_LOCKED_MESSAGE,
            strings.ERROR_FILE_LOCKED_HINT,
        )
    message = (
        strings.ERROR_FILE_NOT_FOUND_MESSAGE
        if isinstance(error, FileNotFoundError)
        else strings.ERROR_FILE_READ_MESSAGE
    )
    return ErrorPresentation(strings.ERROR_FILE_READ_TITLE, message, strings.ERROR_FILE_READ_HINT)


def _export_blocked(error: BaseException, context: str | None) -> ErrorPresentation:
    assert isinstance(error, ExportBlockedError)
    documents = len({problem.cufe for problem in error.problems})
    reasons = list(
        dict.fromkeys(strings.problem_kind_message(p.kind.value) for p in error.problems)
    )
    return ErrorPresentation(
        strings.ERROR_EXPORT_BLOCKED_TITLE,
        strings.export_blocked_message(documents, reasons),
        strings.ERROR_EXPORT_BLOCKED_HINT,
    )


def _totals_mismatch(error: BaseException, context: str | None) -> ErrorPresentation:
    assert isinstance(error, TotalsMismatchError)
    return ErrorPresentation(
        strings.ERROR_EXPORT_TOTALS_TITLE,
        strings.totals_mismatch_count(len(error.mismatches)),
        strings.ERROR_EXPORT_TOTALS_HINT,
    )


def _range_text(numbers: ConsecutiveRange) -> str:
    return f"{numbers.document_type.value} {format_range(numbers.first, numbers.last)}"


def _consecutive_collision(error: BaseException, context: str | None) -> ErrorPresentation:
    assert isinstance(error, ConsecutiveCollisionError)
    message = "\n".join(
        strings.collision_sentence(_range_text(c.proposed), c.batch_id, _range_text(c.existing))
        for c in error.collisions
    )
    return ErrorPresentation(
        strings.ERROR_EXPORT_COLLISION_TITLE, message, strings.ERROR_EXPORT_COLLISION_HINT
    )


def _documents_not_in_batch(error: BaseException, context: str | None) -> ErrorPresentation:
    assert isinstance(error, DocumentNotInBatchError)
    return ErrorPresentation(
        strings.ERROR_DOCUMENT_NOT_IN_BATCH_TITLE,
        strings.documents_not_in_batch(len(error.cufes)),
        strings.ERROR_BATCH_NOT_FOUND_HINT,
    )


def _documents_released(error: BaseException, context: str | None) -> ErrorPresentation:
    assert isinstance(error, DocumentAlreadyReleasedError)
    return ErrorPresentation(
        strings.ERROR_DOCUMENT_RELEASED_TITLE,
        strings.documents_already_released(len(error.cufes)),
        strings.ERROR_DOCUMENT_RELEASED_HINT,
    )


def _duplicate_company(error: BaseException, context: str | None) -> ErrorPresentation:
    assert isinstance(error, DuplicateCompanyNameError)
    return ErrorPresentation(
        strings.ERROR_DUPLICATE_COMPANY_TITLE,
        strings.company_name_taken(error.name),
        strings.ERROR_DUPLICATE_COMPANY_HINT,
    )


class ErrorPresenter:
    def __init__(self, *, defaults: bool = True) -> None:
        self._by_type: dict[type[BaseException], Formatter] = {}
        self._by_name: dict[str, Formatter] = {}
        if defaults:
            register_defaults(self)

    def register(self, error_type: type[BaseException] | str, formatter: Formatter) -> None:
        if isinstance(error_type, str):
            self._by_name[error_type] = formatter
        else:
            self._by_type[error_type] = formatter

    def _formatter_for(self, error: BaseException) -> Formatter | None:
        for cls in type(error).__mro__:
            if cls in self._by_type:
                return self._by_type[cls]  # type: ignore[index]
            if cls.__name__ in self._by_name:
                return self._by_name[cls.__name__]
        return None

    def present(self, error: BaseException, *, context: str | None = None) -> ErrorPresentation:
        formatter = self._formatter_for(error)
        if formatter is None:
            shown = ErrorPresentation(
                strings.ERROR_GENERIC_TITLE,
                strings.ERROR_GENERIC_MESSAGE,
                strings.ERROR_GENERIC_HINT,
            )
        else:
            shown = formatter(error, context)
        if not shown.details:
            shown = replace(shown, details=technical_details(error))
        return shown

    def build_message_box(
        self, parent: QWidget | None, error: BaseException, *, context: str | None = None
    ) -> QMessageBox:
        shown = self.present(error, context=context)
        box = QMessageBox(parent)
        box.setIcon(QMessageBox.Icon.Warning)
        # macOS no muestra el titulo de la ventana: el titular va en el texto principal
        box.setWindowTitle(shown.title)
        box.setText(shown.title)
        body = shown.message if not shown.hint else f"{shown.message}\n\n{shown.hint}"
        box.setInformativeText(body)
        box.setDetailedText(shown.details)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        return box

    def show(
        self, parent: QWidget | None, error: BaseException, *, context: str | None = None
    ) -> ErrorPresentation:
        box = self.build_message_box(parent, error, context=context)
        box.exec()
        return self.present(error, context=context)


def register_defaults(presenter: ErrorPresenter) -> None:
    presenter.register(OSError, _os_error)
    presenter.register(ExportBlockedError, _export_blocked)
    presenter.register(TotalsMismatchError, _totals_mismatch)
    presenter.register(ConsecutiveCollisionError, _consecutive_collision)
    presenter.register(
        NothingToExportError,
        static(
            strings.ERROR_NOTHING_TO_EXPORT_TITLE,
            strings.ERROR_NOTHING_TO_EXPORT_MESSAGE,
            strings.ERROR_NOTHING_TO_EXPORT_HINT,
        ),
    )
    presenter.register(
        CompanyNotFoundError,
        static(
            strings.ERROR_COMPANY_NOT_FOUND_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ERROR_COMPANY_NOT_FOUND_HINT,
        ),
    )
    presenter.register(
        BatchNotFoundError,
        static(
            strings.ERROR_BATCH_NOT_FOUND_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ERROR_BATCH_NOT_FOUND_HINT,
        ),
    )
    presenter.register(
        BatchAlreadyVoidedError,
        static(
            strings.ERROR_BATCH_VOIDED_TITLE,
            strings.BATCH_ALREADY_VOIDED,
            strings.ERROR_BATCH_VOIDED_HINT,
        ),
    )
    presenter.register(DocumentNotInBatchError, _documents_not_in_batch)
    presenter.register(DocumentAlreadyReleasedError, _documents_released)
    presenter.register(
        DocumentNotEditableError,
        static(
            strings.ERROR_DOCUMENT_NOT_EDITABLE_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ERROR_DOCUMENT_NOT_EDITABLE_HINT,
        ),
    )
    presenter.register(
        LineNotFoundError,
        static(
            strings.ERROR_LINE_NOT_FOUND_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ERROR_LINE_NOT_FOUND_HINT,
        ),
    )
    presenter.register(
        InvalidDocumentError,
        static(
            strings.ERROR_INVALID_DOCUMENT_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ERROR_INVALID_DOCUMENT_HINT,
        ),
    )
    presenter.register(
        UnsupportedDocumentError,
        static(
            strings.ERROR_UNSUPPORTED_DOCUMENT_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.ERROR_UNSUPPORTED_DOCUMENT_HINT,
        ),
    )
    presenter.register(
        UnreadableCatalogFileError,
        static(
            strings.ERROR_CATALOG_UNREADABLE_TITLE,
            strings.CATALOG_UNREADABLE_FILE,
            strings.ERROR_CATALOG_UNREADABLE_HINT,
        ),
    )
    presenter.register(
        TaskCancelledError,
        static(strings.ERROR_TASK_CANCELLED_TITLE, strings.ERROR_TASK_CANCELLED_MESSAGE),
    )
    presenter.register(DuplicateCompanyNameError, _duplicate_company)
    # Cancelar es una decision de la persona: informa, no alarma
    presenter.register(
        ImportCancelledError,
        static(strings.ERROR_IMPORT_CANCELLED_TITLE, strings.ERROR_IMPORT_CANCELLED_MESSAGE),
    )
    # La lista estaba desactualizada: la pagina la vuelve a leer
    presenter.register(
        InvoiceNotFoundError,
        static(
            strings.INVOICE_NOT_FOUND_TITLE,
            strings.ERROR_GENERIC_MESSAGE,
            strings.INVOICE_NOT_FOUND_HINT,
        ),
    )
