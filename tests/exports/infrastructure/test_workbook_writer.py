from datetime import date, datetime
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from contabilizador.exports.domain.world_office import (
    DATE_FORMAT,
    HEADER_COLUMNS,
    HEADER_SHEET_NAME,
    LINE_COLUMNS,
    LINE_SHEET_NAME,
    DocumentType,
    WorldOfficeDocument,
    WorldOfficeLine,
)
from contabilizador.exports.infrastructure.workbook_writer import WorldOfficeWorkbookWriter


def _parse_date(value: str) -> date:
    return datetime.strptime(value, DATE_FORMAT).date()  # noqa: DTZ007


def _decimal(value: int | float) -> Decimal:
    # repr de float es el literal mas corto que lo reconstruye exactamente
    return Decimal(repr(value)) if isinstance(value, float) else Decimal(value)


def _rows(sheet: Worksheet) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in sheet.iter_rows(min_row=2, values_only=True)]


def _rebuild_documents(golden_path: Path) -> list[WorldOfficeDocument]:
    workbook = openpyxl.load_workbook(golden_path)
    header_rows = _rows(workbook[HEADER_SHEET_NAME])
    line_rows = _rows(workbook[LINE_SHEET_NAME])

    lines_by_key = {
        key: [
            WorldOfficeLine(
                product_code=row[4],
                warehouse=row[5],
                unit=row[6],
                quantity=_decimal(row[7]),
                tax_rate=_decimal(row[8]),
                unit_value=_decimal(row[9]),
                discount=_decimal(row[10]),
                due_date=_parse_date(row[11]),
                detail_note=row[12],
                cost_center_name=row[13],
            )
            for row in group
        ]
        for key, group in groupby(line_rows, key=lambda row: row[:4])
    }
    # cada documento debe tener sus lineas contiguas en el golden
    assert len(lines_by_key) == len(header_rows)

    return [
        WorldOfficeDocument(
            company_name=row[0],
            document_type=DocumentType(row[1]),
            number=row[3],
            date=_parse_date(row[4]),
            internal_third_party=row[5],
            external_third_party=row[6],
            external_prefix=row[7] or "",
            external_number=row[8],
            note=row[9],
            payment_form=row[10],
            verified=row[11],
            voided=row[12],
            issue_date=_parse_date(row[13]),
            lines=tuple(lines_by_key[row[:4]]),
        )
        for row in header_rows
    ]


def _excel_precision(value: Any) -> Any:
    # openpyxl serializa floats con "%.16g" (Excel guarda 15 digitos significativos)
    return float(f"{value:.16g}") if isinstance(value, float) else value


def _typed_cells(sheet: Worksheet) -> list[list[tuple[Any, type]]]:
    return [
        [(_excel_precision(value), type(value)) for value in row]
        for row in sheet.iter_rows(values_only=True)
    ]


def test_regenerates_golden_workbook_cell_by_cell(golden_workbook_path, tmp_path) -> None:
    documents = _rebuild_documents(golden_workbook_path)
    destination = tmp_path / "out" / "world_office.xlsx"

    WorldOfficeWorkbookWriter().write(documents, destination)

    golden = openpyxl.load_workbook(golden_workbook_path)
    written = openpyxl.load_workbook(destination)
    assert written.sheetnames == [HEADER_SHEET_NAME, LINE_SHEET_NAME]
    assert len(documents) == 26
    assert sum(len(document.lines) for document in documents) == 145
    for sheet_name in (HEADER_SHEET_NAME, LINE_SHEET_NAME):
        assert _typed_cells(written[sheet_name]) == _typed_cells(golden[sheet_name])


def test_writes_headers_even_without_documents(tmp_path) -> None:
    destination = tmp_path / "empty.xlsx"

    WorldOfficeWorkbookWriter().write([], destination)

    workbook = openpyxl.load_workbook(destination)
    assert _typed_cells(workbook[HEADER_SHEET_NAME]) == [[(h, str) for h in HEADER_COLUMNS]]
    assert _typed_cells(workbook[LINE_SHEET_NAME]) == [[(h, str) for h in LINE_COLUMNS]]


def test_keeps_leading_zeros_and_writes_unrounded_values(tmp_path) -> None:
    line = WorldOfficeLine(
        product_code="000123",
        warehouse="Principal",
        unit="Und.",
        quantity=Decimal("3"),
        tax_rate=Decimal("0.1900"),
        unit_value=Decimal("100000") / Decimal("3"),
        discount=Decimal("0"),
        due_date=date(2026, 9, 4),
        detail_note="ALMUERZO",
        cost_center_name="GERENCIA GENERAL",
    )
    document = WorldOfficeDocument(
        company_name="WEARE DEV S.A.S",
        document_type=DocumentType.NC,
        number=7,
        date=date(2026, 9, 4),
        internal_third_party="1037663527",
        external_third_party="1017000111",
        external_prefix="",
        external_number="00450",
        note="ALMUERZO",
        payment_form="Credito",
        issue_date=date(2026, 9, 4),
        lines=(line,),
    )
    destination = tmp_path / "nc.xlsx"

    WorldOfficeWorkbookWriter().write([document], destination)

    workbook = openpyxl.load_workbook(destination)
    header = next(workbook[HEADER_SHEET_NAME].iter_rows(min_row=2, values_only=True))
    row = next(workbook[LINE_SHEET_NAME].iter_rows(min_row=2, values_only=True))
    assert header[:4] == ("WEARE DEV S.A.S", "NC", "NC", 7)
    assert header[4] == "04/09/2026"
    assert header[7] is None  # prefijo externo vacio -> celda vacia (como el golden)
    assert header[8] == "00450"
    assert row[4] == "000123"
    assert row[7] == 3 and isinstance(row[7], int)
    assert row[8] == 0.19
    assert row[9] == _excel_precision(float(Decimal("100000") / Decimal("3")))
    assert row[11] == "04/09/2026"


def _document(*, note: str, detail_note: str, external_number: str = "001") -> WorldOfficeDocument:
    line = WorldOfficeLine(
        product_code="513515",
        warehouse="Principal",
        unit="Und.",
        quantity=Decimal("1"),
        tax_rate=Decimal("0.19"),
        unit_value=Decimal("100"),
        discount=Decimal("0"),
        due_date=date(2026, 9, 4),
        detail_note=detail_note,
        cost_center_name="GERENCIA GENERAL",
    )
    return WorldOfficeDocument(
        company_name="WEARE DEV S.A.S",
        document_type=DocumentType.FC,
        number=1,
        date=date(2026, 9, 4),
        internal_third_party="1037663527",
        external_third_party="900123456",
        external_prefix="FEV",
        external_number=external_number,
        note=note,
        payment_form="Credito",
        issue_date=date(2026, 9, 4),
        lines=(line,),
    )


def test_formula_like_supplier_text_is_written_as_plain_text(tmp_path: Path) -> None:
    payload = '=HYPERLINK("http://x","clic")'
    destination = tmp_path / "formula.xlsx"

    WorldOfficeWorkbookWriter().write(
        [_document(note=payload, detail_note="=1+1", external_number="=2+2")], destination
    )

    workbook = openpyxl.load_workbook(destination)
    header = workbook[HEADER_SHEET_NAME]
    line = workbook[LINE_SHEET_NAME]
    for cell in (header["J2"], header["I2"], line["M2"]):
        assert cell.data_type == "s"
    assert header["J2"].value == payload
    assert line["M2"].value == "=1+1"


def test_failed_save_keeps_the_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "lote.xlsx"
    destination.write_bytes(b"previous export")

    def broken_save(self: Workbook, filename: str | Path) -> None:
        Path(filename).write_bytes(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr(Workbook, "save", broken_save)

    with pytest.raises(OSError):
        WorldOfficeWorkbookWriter().write([], destination)

    assert destination.read_bytes() == b"previous export"
    assert [p.name for p in tmp_path.iterdir()] == ["lote.xlsx"]


def test_overwrites_an_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "lote.xlsx"
    destination.write_bytes(b"previous export")

    WorldOfficeWorkbookWriter().write([], destination)

    assert openpyxl.load_workbook(destination).sheetnames == [HEADER_SHEET_NAME, LINE_SHEET_NAME]
