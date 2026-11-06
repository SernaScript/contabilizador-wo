"""openpyxl adapter for the World Office purchase import workbook."""

import os
import tempfile
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from contabilizador.exports.domain.world_office import (
    DATE_FORMAT,
    HEADER_COLUMNS,
    HEADER_SHEET_NAME,
    LINE_COLUMNS,
    LINE_SHEET_NAME,
    WorldOfficeDocument,
    WorldOfficeLine,
)

type CellValue = str | int | float | None


def _text(value: str) -> str | None:
    # WO espera celda vacia (no "") cuando no hay valor, p. ej. prefijo externo
    return value or None


def _date(value: date) -> str:
    return value.strftime(DATE_FORMAT)


def _number(value: Decimal) -> int | float:
    # Decimal -> float solo en esta frontera; enteros se escriben como int (igual al golden)
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _header_row(document: WorldOfficeDocument) -> list[CellValue]:
    return [
        _text(document.company_name),
        document.document_type.value,
        document.prefix,
        document.number,
        _date(document.date),
        _text(document.internal_third_party),
        _text(document.external_third_party),
        _text(document.external_prefix),
        _text(document.external_number),
        _text(document.note),
        _text(document.payment_form),
        document.verified,
        document.voided,
        _date(document.issue_date),
    ]


def _line_row(document: WorldOfficeDocument, line: WorldOfficeLine) -> list[CellValue]:
    return [
        _text(document.company_name),
        document.document_type.value,
        document.prefix,
        document.number,
        _text(line.product_code),
        _text(line.warehouse),
        _text(line.unit),
        _number(line.quantity),
        _number(line.tax_rate),
        _number(line.unit_value),
        _number(line.discount),
        _date(line.due_date),
        _text(line.detail_note),
        _text(line.cost_center_name),
    ]


def _append_as_data(sheet: Worksheet, values: list[CellValue]) -> None:
    sheet.append(values)
    # openpyxl guarda como formula todo texto que empieza con "=": el texto del XML del
    # proveedor nunca debe evaluarse, se fuerza a texto plano
    for cell in sheet[sheet.max_row]:
        if cell.data_type == "f":
            cell.data_type = "s"


def _save_atomically(workbook: Workbook, destination: Path) -> None:
    """Saves next to ``destination`` and then replaces it, so a failed save never
    leaves a truncated file nor destroys a previous export."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".xlsx", dir=destination.parent
    )
    os.close(handle)  # en Windows el archivo abierto no se puede reemplazar
    temporary = Path(temporary_name)
    try:
        workbook.save(temporary)
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class WorldOfficeWorkbookWriter:
    """Writes `Encabezados` (one row per document) and `Movimiento inventarios`
    (one row per line). Implements ``PurchaseImportExporter``."""

    def write(self, documents: Sequence[WorldOfficeDocument], destination: Path) -> None:
        workbook = Workbook()
        header_sheet = workbook.active
        assert header_sheet is not None
        header_sheet.title = HEADER_SHEET_NAME
        line_sheet = workbook.create_sheet(LINE_SHEET_NAME)

        header_sheet.append(list(HEADER_COLUMNS))
        line_sheet.append(list(LINE_COLUMNS))
        for document in documents:
            _append_as_data(header_sheet, _header_row(document))
            for line in document.lines:
                _append_as_data(line_sheet, _line_row(document, line))

        _save_atomically(workbook, destination)
