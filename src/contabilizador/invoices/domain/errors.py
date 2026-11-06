"""Errors raised while reading DIAN documents."""


class DocumentError(Exception):
    """Base error for documents that cannot be imported."""


class UnsupportedDocumentError(DocumentError):
    """The XML is valid but is not an Invoice/CreditNote (e.g. ApplicationResponse).

    Callers should skip and log it, not fail the import.
    """


class InvalidDocumentError(DocumentError):
    """The XML is malformed or misses a required element."""
