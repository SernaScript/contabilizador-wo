"""Pure presentation helpers of the Catálogos page (no Qt)."""

import pytest

from contabilizador.ui.pages.catalogs.rows import (
    CatalogRow,
    fold,
    matches,
    natural_key,
    sorted_rows,
)


def test_row_display_joins_code_and_name() -> None:
    assert CatalogRow("1001", "Papelería").display == "1001 - Papelería"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Papelería", "papeleria"),
        ("ÁÉÍÓÚ ñ", "aeiou n"),
        ("  Mixed Case ", "  mixed case "),
        ("", ""),
    ],
)
def test_fold_ignores_case_and_accents(text: str, expected: str) -> None:
    assert fold(text) == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", True),
        ("   ", True),
        ("1001", True),
        ("100", True),
        ("papeleria", True),
        ("PAPELERÍA", True),
        ("papel 1001", True),  # cada palabra debe aparecer, en cualquier orden
        ("1001 papel", True),
        ("papel 2002", False),
        ("zzz", False),
    ],
)
def test_matches_requires_every_word_in_code_or_name(query: str, expected: bool) -> None:
    assert matches(CatalogRow("1001", "Papelería"), query) is expected


def test_natural_order_compares_digit_runs_by_value() -> None:
    codes = ["A-10", "100", "A-2", "99", "513515", "B"]

    ordered = sorted(codes, key=natural_key)

    assert ordered == ["99", "100", "513515", "A-2", "A-10", "B"]


def test_sorted_rows_orders_by_code_naturally_and_keeps_names() -> None:
    rows = [CatalogRow("10", "Diez"), CatalogRow("9", "Nueve"), CatalogRow("2", "Dos")]

    assert [row.code for row in sorted_rows(rows)] == ["2", "9", "10"]
    assert sorted_rows([]) == []
