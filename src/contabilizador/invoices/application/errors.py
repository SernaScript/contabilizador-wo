"""Errors raised by the invoices use cases."""


class LineNotFoundError(LookupError):
    """The line does not exist or belongs to another company."""


class InvoiceNotFoundError(LookupError):
    """The document does not exist or belongs to another company."""

    def __init__(self, invoice_id: int) -> None:
        self.invoice_id = invoice_id
        super().__init__(f"invoice {invoice_id} not found")


class DocumentNotEditableError(Exception):
    """The document was already exported; its lines cannot be reassigned."""


class ImportCancelledError(Exception):
    """The user cancelled the import before anything was stored."""
