from datetime import date
from decimal import Decimal

import openpyxl
import pytest

from contabilizador.exports.domain.world_office import (
    HEADER_COLUMNS,
    HEADER_SHEET_NAME,
    LINE_COLUMNS,
    LINE_SHEET_NAME,
    DocumentType,
    WorldOfficeDocument,
    WorldOfficeLine,
)
from contabilizador.invoices.domain.document import DocumentKind


def make_line() -> WorldOfficeLine:
    return WorldOfficeLine(
        product_code="513515",
        warehouse="Principal",
        unit="Und.",
        quantity=Decimal("1"),
        tax_rate=Decimal("0.19"),
        unit_value=Decimal("168067.23"),
        discount=Decimal("0"),
        due_date=date(2026, 8, 31),
        detail_note="SERVICIO TECNICO",
        cost_center_name="GERENCIA GENERAL",
    )


def test_column_headers_match_golden_workbook(golden_workbook_path) -> None:
    workbook = openpyxl.load_workbook(golden_workbook_path, read_only=True)
    header_row = next(workbook[HEADER_SHEET_NAME].iter_rows(max_row=1, values_only=True))
    line_row = next(workbook[LINE_SHEET_NAME].iter_rows(max_row=1, values_only=True))
    assert tuple(header_row) == HEADER_COLUMNS
    assert tuple(line_row) == LINE_COLUMNS
    assert len(HEADER_COLUMNS) == 14
    assert len(LINE_COLUMNS) == 14


def test_document_type_for_kind() -> None:
    assert DocumentType.for_kind(DocumentKind.INVOICE) is DocumentType.FC
    assert DocumentType.for_kind(DocumentKind.CREDIT_NOTE) is DocumentType.NC
    assert DocumentType.FC.value == "FC"


def test_document_prefix_equals_document_type_code() -> None:
    document = WorldOfficeDocument(
        company_name="WEARE DEV S.A.S",
        document_type=DocumentType.NC,
        number=9420378244,
        date=date(2026, 8, 31),
        internal_third_party="1037663527",
        external_third_party="900041754",
        external_prefix="FPI",
        external_number="5731",
        note="SERVICIO TECNICO",
        payment_form="Credito",
        issue_date=date(2026, 8, 31),
        lines=(make_line(),),
    )
    assert document.prefix == "NC"
    assert document.verified == 0
    assert document.voided == 0


def test_document_requires_lines() -> None:
    with pytest.raises(ValueError):
        WorldOfficeDocument(
            company_name="WEARE DEV S.A.S",
            document_type=DocumentType.FC,
            number=1,
            date=date(2026, 8, 31),
            internal_third_party="1",
            external_third_party="2",
            external_prefix="",
            external_number="3",
            note="",
            payment_form="Credito",
            issue_date=date(2026, 8, 31),
            lines=(),
        )
