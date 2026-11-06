from decimal import Decimal

from contabilizador.invoices.domain.document import DocumentKind, ParsedLine
from contabilizador.invoices.domain.totals import (
    TOTALS_TOLERANCE,
    check_document_totals,
    check_totals,
)
from tests.invoices.factories import make_document


def line(qty: str, ext: str, pct: str) -> ParsedLine:
    return ParsedLine("ITEM", Decimal(qty), Decimal(ext), Decimal(pct))


def test_tolerance_is_one_peso() -> None:
    assert Decimal(1) == TOTALS_TOLERANCE


def test_exact_match_with_mixed_iva() -> None:
    lines = (line("1", "100000", "19"), line("2", "50000", "5"), line("1", "30000", "0"))
    result = check_totals(lines, Decimal("201500.00"))
    assert result.computed == Decimal("201500")
    assert result.difference == 0
    assert result.matches


def test_rounding_difference_within_one_peso_matches() -> None:
    result = check_totals((line("1", "168067.23", "19"),), Decimal("200000.00"))
    assert result.matches
    assert abs(result.difference) < 1


def test_difference_above_one_peso_does_not_match() -> None:
    result = check_totals((line("1", "100000", "19"),), Decimal("119001.01"))
    assert not result.matches
    assert result.difference == Decimal("-1.01")


def test_difference_of_exactly_one_peso_matches() -> None:
    assert check_totals((line("1", "100", "0"),), Decimal("101")).matches
    assert check_totals((line("1", "100", "0"),), Decimal("99")).matches


def test_computed_uses_qty_times_unit_value() -> None:
    # 3 x 10000 x 1.19
    result = check_totals((line("3", "30000", "19"),), Decimal("35700"))
    assert result.computed == Decimal("35700")
    assert result.expected == Decimal("35700")


def test_negative_credit_note_lines_are_compared_as_positive() -> None:
    # algunos proveedores envian las notas credito con valores negativos
    result = check_totals((line("1", "-10000", "19"),), Decimal("11900"))
    assert result.computed == Decimal("11900")
    assert result.matches


def test_document_rule_compares_absolute_payable_amount() -> None:
    credit_note = make_document(
        kind=DocumentKind.CREDIT_NOTE,
        lines=(line("2", "-20000", "19"),),
        payable_amount=Decimal("-23800"),
    )

    result = check_document_totals(credit_note)

    assert (result.computed, result.expected) == (Decimal("23800"), Decimal("23800"))
    assert result.matches


def test_document_rule_reports_signed_difference_of_absolute_values() -> None:
    credit_note = make_document(
        kind=DocumentKind.CREDIT_NOTE,
        lines=(line("1", "-10000", "19"),),
        payable_amount=Decimal("12000"),
    )

    result = check_document_totals(credit_note)

    assert result.difference == Decimal("-100")
    assert not result.matches
