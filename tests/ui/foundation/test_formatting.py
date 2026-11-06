"""Pure formatting helpers: es-CO money, quantities, dates and compact labels."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from contabilizador.ui import formatting as fmt


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("2380000"), "$ 2.380.000"),
        (Decimal("2380000.00"), "$ 2.380.000"),
        (Decimal("160700.33"), "$ 160.700,33"),
        (Decimal("0"), "$ 0"),
        (Decimal("-125000"), "-$ 125.000"),
        (Decimal("999.5"), "$ 999,50"),
        (1500, "$ 1.500"),
    ],
)
def test_format_money_es_co(value: Decimal | int, expected: str) -> None:
    assert fmt.format_money(value) == expected


def test_format_money_with_fixed_decimals() -> None:
    assert fmt.format_money(Decimal("2380000"), decimals=2) == "$ 2.380.000,00"
    assert fmt.format_money(Decimal("10.456"), decimals=2) == "$ 10,46"


def test_format_money_none_is_empty() -> None:
    assert fmt.format_money(None) == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("3"), "3"),
        (Decimal("3.000"), "3"),
        (Decimal("2.5"), "2,5"),
        (Decimal("1234.25"), "1.234,25"),
        (Decimal("0.12345"), "0,1235"),
    ],
)
def test_format_quantity_trims_zeros(value: Decimal, expected: str) -> None:
    assert fmt.format_quantity(value) == expected


def test_format_date_day_month_year() -> None:
    assert fmt.format_date(date(2026, 9, 3)) == "03/09/2026"
    assert fmt.format_date(datetime(2026, 12, 25, 10, 0, tzinfo=UTC)) == "25/12/2026"
    assert fmt.format_date(None) == ""


def test_format_datetime_includes_time() -> None:
    assert fmt.format_datetime(datetime(2026, 9, 3, 14, 5, tzinfo=UTC)) == "03/09/2026 14:05"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Decimal("19"), "19 %"), (Decimal("19.00"), "19 %"), (Decimal("5.5"), "5,5 %"), (None, "")],
)
def test_format_percent(value: Decimal | None, expected: str) -> None:
    assert fmt.format_percent(value) == expected


def test_document_label_and_human_label() -> None:
    assert fmt.document_label("FPI", "5731") == "FPI-5731"
    assert fmt.document_label("", "5731") == "5731"
    assert fmt.document_label(None, "5731") == "5731"
    assert fmt.document_title("FPI", "5731", "Proveedor S.A.S.") == "FPI-5731 · Proveedor S.A.S."
    assert fmt.document_title("FPI", "5731", "") == "FPI-5731"


def test_code_and_name() -> None:
    assert fmt.code_and_name("1001", "Papelería") == "1001 - Papelería"
    assert fmt.code_and_name("1001", "") == "1001"
    assert fmt.code_and_name("1001", None) == "1001"


def test_short_cufe() -> None:
    assert fmt.short_cufe("abcdef1234567890xyz") == "abcdef123456…"
    assert fmt.short_cufe("abc") == "abc"


def test_format_difference_is_signed_money() -> None:
    assert fmt.format_difference(Decimal("1500")) == "+$ 1.500"
    assert fmt.format_difference(Decimal("-1500")) == "-$ 1.500"
    assert fmt.format_difference(Decimal("0")) == "$ 0"


def test_format_range() -> None:
    assert fmt.format_range(5731, 5748) == "5731 a 5748"
    assert fmt.format_range(5731, 5731) == "5731"


def test_amounts_that_round_to_zero_carry_no_sign() -> None:
    # Una diferencia de fracciones de centavo no es un descuadre visible: "$ 0", sin signo
    assert fmt.format_difference(Decimal("0.0037")) == "$ 0"
    assert fmt.format_difference(Decimal("-0.004")) == "$ 0"
    assert fmt.format_money(Decimal("-0.004")) == "$ 0"
    assert fmt.format_difference(Decimal("0.005")) == "+$ 0,01"
    assert fmt.format_difference(Decimal("-1500")) == "-$ 1.500"
