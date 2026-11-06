from collections.abc import Sequence
from pathlib import Path

import pytest

from contabilizador.catalog.application.catalog_template import (
    TEMPLATE_HEADERS,
    WriteCatalogTemplate,
)
from contabilizador.catalog.application.import_catalog import CatalogKind


class FakeTemplateWriter:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str, tuple[str, ...]]] = []

    def write(self, destination: Path, *, sheet_title: str, headers: Sequence[str]) -> None:
        self.calls.append((destination, sheet_title, tuple(headers)))


def test_headers_match_the_import_layout() -> None:
    # columna A codigo, columna B nombre (la fila 1 se omite al importar)
    assert TEMPLATE_HEADERS == ("Código", "Nombre")


@pytest.mark.parametrize(
    ("kind", "title"),
    [(CatalogKind.PRODUCT, "Productos"), (CatalogKind.COST_CENTER, "Centros de costo")],
)
def test_writes_one_sheet_named_after_the_catalog(kind: CatalogKind, title: str) -> None:
    writer = FakeTemplateWriter()
    destination = Path("plantillas") / "catalogo.xlsx"

    WriteCatalogTemplate(writer).execute(destination, kind)

    assert writer.calls == [(destination, title, TEMPLATE_HEADERS)]
