"""openpyxl adapter for the catalog import template."""

from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

# Anchos pensados para codigos cortos y nombres largos
_COLUMN_WIDTHS = {"A": 18, "B": 48}


class OpenpyxlCatalogTemplateWriter:
    """Implements ``CatalogTemplateWriter``."""

    def write(self, destination: Path, *, sheet_title: str, headers: Sequence[str]) -> None:
        workbook = Workbook()
        sheet = workbook.active
        assert sheet is not None
        sheet.title = sheet_title
        sheet.append(list(headers))
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column, width in _COLUMN_WIDTHS.items():
            sheet.column_dimensions[column].width = width
        sheet.freeze_panes = "A2"
        destination.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(destination)
