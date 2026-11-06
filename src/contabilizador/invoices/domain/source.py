"""Outcome of reading input files (XML, folders, zips) into documents."""

from dataclasses import dataclass, field

from contabilizador.invoices.domain.document import ParsedDocument


@dataclass(frozen=True, slots=True)
class SkippedFile:
    """A file that produced no document.

    Attributes:
        source: display name; for zip members ``"<zip path>::<member>"``.
        reason: human readable reason (Spanish, shown in the UI).
    """

    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class LoadResult:
    """``ignored``: valid XML of another type (e.g. ApplicationResponse), logged only.
    ``failed``: unreadable, malformed or incomplete files."""

    parsed: tuple[ParsedDocument, ...] = ()
    ignored: tuple[SkippedFile, ...] = field(default=())
    failed: tuple[SkippedFile, ...] = field(default=())
