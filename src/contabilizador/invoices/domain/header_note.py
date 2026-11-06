"""World Office header note built from the document lines."""

from collections.abc import Iterable

# Límite de caracteres de la nota en World Office
HEADER_NOTE_MAX_LENGTH = 499
HEADER_NOTE_SEPARATOR = " & "


def build_header_note(descriptions: Iterable[str]) -> str:
    note = HEADER_NOTE_SEPARATOR.join(description.strip() for description in descriptions)
    return note[:HEADER_NOTE_MAX_LENGTH]
