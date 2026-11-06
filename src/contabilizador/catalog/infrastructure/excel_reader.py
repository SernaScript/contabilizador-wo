"""openpyxl adapter: reads (code, name) rows from the first sheet."""

from collections.abc import Iterator
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from contabilizador.catalog.application.import_catalog import (
    RawCatalogRow,
    UnreadableCatalogFileError,
)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    # Excel guarda numeros como float: 513515 llega como 513515.0
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class OpenpyxlCatalogSheetReader:
    def read(self, path: Path) -> Iterator[RawCatalogRow]:
        try:
            workbook = load_workbook(path, read_only=True, data_only=True)
        except (InvalidFileException, BadZipFile, KeyError) as error:
            # .xls, .csv o .xlsx corrupto (KeyError = zip sin partes de Excel)
            raise UnreadableCatalogFileError(f"{path.name} is not a readable .xlsx") from error
        try:
            sheet = workbook.worksheets[0]
            # Fila 1 = encabezado
            for number, row in enumerate(
                sheet.iter_rows(min_row=2, max_col=2, values_only=True), 2
            ):
                code, name = _cell_text(row[0]), _cell_text(row[1] if len(row) > 1 else None)
                if code.strip() or name.strip():
                    yield RawCatalogRow(number, code, name)
        finally:
            workbook.close()
