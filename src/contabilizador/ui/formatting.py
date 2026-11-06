"""Pure display formatting (es-CO conventions). No Qt, no locale state.

Money: ``$ 2.380.000`` (thousands with dot, decimals with comma, cents only when present).
Dates: ``dd/mm/yyyy``. Document labels: ``FPI-5731`` and ``FPI-5731 · Proveedor``
(the middle dot is kept only for this compact identifier).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

CURRENCY_SIGN = "$"
MIDDLE_DOT = " · "


def _group_thousands(integer_digits: str) -> str:
    groups = []
    while integer_digits:
        groups.append(integer_digits[-3:])
        integer_digits = integer_digits[:-3]
    return ".".join(reversed(groups))


def _format_number(value: Decimal, decimals: int) -> str:
    quantum = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    rounded = abs(value).quantize(quantum, rounding=ROUND_HALF_UP)
    text = f"{rounded:f}"
    integer_part, _, fraction = text.partition(".")
    grouped = _group_thousands(integer_part)
    return f"{grouped},{fraction}" if decimals else grouped


def _rounded(amount: Decimal, decimals: int) -> Decimal:
    quantum = Decimal(1).scaleb(-decimals) if decimals else Decimal(1)
    return amount.quantize(quantum, rounding=ROUND_HALF_UP)


def format_money(value: Decimal | int | float | None, *, decimals: int | None = None) -> str:
    """``decimals=None`` hides cents when the value is whole and shows two otherwise."""
    if value is None:
        return ""
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if decimals is None:
        cents = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        decimals = 0 if cents == cents.to_integral_value() else 2
    # El signo sale del valor que se muestra: -0,004 se ve "$ 0", no "-$ 0"
    sign = "-" if _rounded(amount, decimals) < 0 else ""
    return f"{sign}{CURRENCY_SIGN} {_format_number(amount, decimals)}"


def format_difference(value: Decimal | None) -> str:
    """Signed money for XML-vs-computed totals: ``+$ 1.500`` / ``-$ 1.500``; a difference
    that rounds to zero is ``$ 0``."""
    if value is None:
        return ""
    amount = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = format_money(amount)
    return f"+{text}" if amount > 0 else text


def format_quantity(value: Decimal | int | None, *, max_decimals: int = 4) -> str:
    if value is None:
        return ""
    amount = value if isinstance(value, Decimal) else Decimal(value)
    rounded = amount.quantize(Decimal(1).scaleb(-max_decimals), rounding=ROUND_HALF_UP)
    normalized = rounded.normalize()
    exponent = normalized.as_tuple().exponent
    decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    sign = "-" if amount < 0 else ""
    return f"{sign}{_format_number(normalized, decimals)}"


def format_percent(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{format_quantity(value, max_decimals=2)} %"


def format_date(value: date | datetime | None) -> str:
    if value is None:
        return ""
    return f"{value:%d/%m/%Y}"


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return ""
    return f"{value:%d/%m/%Y %H:%M}"


def document_label(prefix: str | None, number: str | int) -> str:
    """``PREFIX-NUMBER``; just the number when the prefix is empty."""
    return f"{prefix}-{number}" if prefix else str(number)


def document_title(prefix: str | None, number: str | int, supplier: str | None) -> str:
    """Compact human label used in export sheets and batches: ``FPI-5731 · Proveedor``."""
    label = document_label(prefix, number)
    return f"{label}{MIDDLE_DOT}{supplier}" if supplier else label


def code_and_name(code: str, name: str | None) -> str:
    return f"{code} - {name}" if name else code


def short_cufe(cufe: str, length: int = 12) -> str:
    return f"{cufe[:length]}…" if len(cufe) > length else cufe


def format_range(first: int, last: int) -> str:
    return str(first) if first == last else f"{first} a {last}"
