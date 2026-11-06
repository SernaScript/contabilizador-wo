import dataclasses
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine


def make_document(**overrides: object) -> ParsedDocument:
    values: dict[str, object] = {
        "cufe": "abc123",
        "kind": DocumentKind.INVOICE,
        "supplier_nit": "900123456",
        "supplier_name": "COMERCIALIZADORA EJEMPLO S.A.S.",
        "supplier_prefix": "FE",
        "supplier_number": "00450",
        "issue_date": date(2026, 9, 4),
        "due_date": None,
        "lines": (ParsedLine("ALMUERZO", Decimal("4"), Decimal("10000"), Decimal("0")),),
        "payable_amount": Decimal("10000"),
        "billing_reference_cufe": None,
        "source_file": Path("factura.xml"),
    }
    values.update(overrides)
    return ParsedDocument(**values)  # type: ignore[arg-type]


def test_line_unit_value_is_line_extension_divided_by_quantity() -> None:
    line = ParsedLine("SILLA", Decimal("2"), Decimal("90000.00"), Decimal("19.00"))
    assert line.unit_value == Decimal("45000")


def test_line_tax_rate_is_percent_over_100() -> None:
    line = ParsedLine("SILLA", Decimal("1"), Decimal("100"), Decimal("19.00"))
    assert line.tax_rate == Decimal("0.19")


def test_line_rejects_zero_quantity() -> None:
    with pytest.raises(ValueError):
        ParsedLine("SILLA", Decimal("0"), Decimal("100"), Decimal("19"))


def test_parsed_document_is_immutable() -> None:
    document = make_document()
    with pytest.raises(dataclasses.FrozenInstanceError):
        document.cufe = "other"  # type: ignore[misc]


def test_effective_due_date_falls_back_to_issue_date() -> None:
    assert make_document(due_date=None).effective_due_date == date(2026, 9, 4)
    assert make_document(due_date=date(2026, 10, 4)).effective_due_date == date(2026, 10, 4)


def test_supplier_number_keeps_leading_zeros() -> None:
    assert make_document().supplier_number == "00450"


def test_is_credit_note() -> None:
    assert not make_document().is_credit_note
    assert make_document(kind=DocumentKind.CREDIT_NOTE).is_credit_note
