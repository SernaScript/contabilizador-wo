"""Presentation rows of the Catálogos page: plain data and pure helpers (no Qt)."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from contabilizador.ui.formatting import code_and_name

_DIGIT_RUNS = re.compile(r"(\d+)")


@dataclass(frozen=True, slots=True)
class CatalogRow:
    """One product or cost center as the table shows it."""

    code: str
    name: str

    @property
    def display(self) -> str:
        return code_and_name(self.code, self.name)


@dataclass(frozen=True, slots=True)
class ImportOutcome:
    """Result of an Excel import: counts plus the rows that were skipped."""

    created: int
    updated: int
    invalid: tuple[tuple[int, str], ...] = ()  # (fila de la hoja, motivo tecnico)


def fold(text: str) -> str:
    """Lower-case text without accents, so ``papeleria`` finds ``Papelería``."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def matches(row: CatalogRow, query: str) -> bool:
    """Every word of ``query`` must appear in the code or the name (any order)."""
    words = fold(query).split()
    if not words:
        return True
    haystack = fold(f"{row.code} {row.name}")
    return all(word in haystack for word in words)


def natural_key(code: str) -> list[str | int]:
    """Sort key that compares digit runs by value: ``2 < 10``, ``A-2 < A-10``."""
    # re.split con grupo alterna texto y numero, asi que las posiciones siempre son comparables
    return [
        int(part) if index % 2 else part.casefold()
        for index, part in enumerate(_DIGIT_RUNS.split(code))
    ]


def sorted_rows(rows: Iterable[CatalogRow]) -> list[CatalogRow]:
    return sorted(rows, key=lambda row: natural_key(row.code))
