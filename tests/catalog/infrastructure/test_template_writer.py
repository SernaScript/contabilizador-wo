from pathlib import Path

from openpyxl import load_workbook

from contabilizador.catalog.application.catalog_template import WriteCatalogTemplate
from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.catalog.infrastructure.excel_reader import OpenpyxlCatalogSheetReader
from contabilizador.catalog.infrastructure.template_writer import OpenpyxlCatalogTemplateWriter


def test_template_has_only_the_header_row(tmp_path: Path) -> None:
    destination = tmp_path / "nueva carpeta" / "plantilla productos.xlsx"

    WriteCatalogTemplate(OpenpyxlCatalogTemplateWriter()).execute(destination, CatalogKind.PRODUCT)

    workbook = load_workbook(destination)
    sheet = workbook.worksheets[0]
    assert workbook.sheetnames == ["Productos"]
    assert [tuple(row) for row in sheet.iter_rows(values_only=True)] == [("Código", "Nombre")]
    assert sheet["A1"].font.bold
    workbook.close()


def test_filled_template_is_read_by_the_catalog_importer(tmp_path: Path) -> None:
    destination = tmp_path / "plantilla.xlsx"
    WriteCatalogTemplate(OpenpyxlCatalogTemplateWriter()).execute(
        destination, CatalogKind.COST_CENTER
    )
    workbook = load_workbook(destination)
    workbook.worksheets[0].append(["10", "Administracion"])
    workbook.save(destination)

    rows = list(OpenpyxlCatalogSheetReader().read(destination))

    assert [(row.row_number, row.code, row.name) for row in rows] == [(2, "10", "Administracion")]
