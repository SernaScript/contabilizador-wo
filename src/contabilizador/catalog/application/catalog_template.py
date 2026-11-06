"""Use case: write an empty Excel template the catalog importer understands.

The header row and the sheet titles are part of the file the user fills in, so they
are Spanish; the importer skips row 1 and reads column A (code) and B (name).
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from contabilizador.catalog.application.import_catalog import CatalogKind

TEMPLATE_HEADERS: tuple[str, ...] = ("Código", "Nombre")
TEMPLATE_SHEET_TITLES: dict[CatalogKind, str] = {
    CatalogKind.PRODUCT: "Productos",
    CatalogKind.COST_CENTER: "Centros de costo",
}


class CatalogTemplateWriter(Protocol):
    def write(self, destination: Path, *, sheet_title: str, headers: Sequence[str]) -> None:
        """Write a workbook with one sheet holding only ``headers`` (overwrites).

        Raises:
            OSError: the file cannot be written (e.g. open in Excel).
        """
        ...


class WriteCatalogTemplate:
    def __init__(self, writer: CatalogTemplateWriter) -> None:
        self._writer = writer

    def execute(self, destination: Path, kind: CatalogKind) -> None:
        self._writer.write(
            destination, sheet_title=TEMPLATE_SHEET_TITLES[kind], headers=TEMPLATE_HEADERS
        )
