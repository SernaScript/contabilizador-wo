from pathlib import Path
from zipfile import ZipFile

import pytest

from contabilizador.catalog.application.import_catalog import UnreadableCatalogFileError
from contabilizador.catalog.infrastructure.excel_reader import OpenpyxlCatalogSheetReader


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("legacy.xls", b"\xd0\xcf\x11\xe0 old binary excel"),
        ("catalog.csv", b"code,name\n513515,Papeleria\n"),
        ("corrupt.xlsx", b"not a zip at all"),
    ],
)
def test_unreadable_files_raise_a_catalog_error(tmp_path: Path, name: str, content: bytes) -> None:
    path = tmp_path / name
    path.write_bytes(content)

    with pytest.raises(UnreadableCatalogFileError):
        list(OpenpyxlCatalogSheetReader().read(path))


def test_unreadable_file_error_is_a_value_error() -> None:
    # la UI ya atrapa ValueError al importar
    assert issubclass(UnreadableCatalogFileError, ValueError)


def test_zip_without_workbook_parts_raises_a_catalog_error(tmp_path: Path) -> None:
    path = tmp_path / "fake.xlsx"
    with ZipFile(path, "w") as archive:
        archive.writestr("hola.txt", "no es excel")

    with pytest.raises(UnreadableCatalogFileError):
        list(OpenpyxlCatalogSheetReader().read(path))
