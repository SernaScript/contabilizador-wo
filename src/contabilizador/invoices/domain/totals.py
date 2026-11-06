"""Validation of line totals against the document payable amount.

This is the ONLY totals rule: the documents grid, the export preview and the export
itself all use it, so they never disagree.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from contabilizador.invoices.domain.document import ParsedDocument, ParsedLine

# Diferencia máxima aceptada en COP por redondeos del proveedor
TOTALS_TOLERANCE = Decimal(1)


@dataclass(frozen=True, slots=True)
class TotalsCheck:
    """Result of comparing Σ |line extension|·(1+iva) with the XML `PayableAmount`.

    Both sides are taken as positive (credit notes may come with negative values).
    ``difference`` is ``computed - expected``.
    """

    computed: Decimal
    expected: Decimal

    @property
    def difference(self) -> Decimal:
        return self.computed - self.expected

    @property
    def matches(self) -> bool:
        return abs(self.difference) <= TOTALS_TOLERANCE


def line_total_with_tax(line: ParsedLine) -> Decimal:
    """What World Office computes for the line: qty·valor·(1+iva) = |extension|·(1+iva)."""
    # algunas notas credito traen valores negativos; World Office los recibe positivos
    return abs(line.line_extension_amount) * (1 + line.tax_rate)


def check_totals(lines: Iterable[ParsedLine], payable_amount: Decimal) -> TotalsCheck:
    computed = sum((line_total_with_tax(line) for line in lines), start=Decimal(0))
    return TotalsCheck(computed=computed, expected=abs(payable_amount))


def check_document_totals(document: ParsedDocument) -> TotalsCheck:
    """Totals rule for a whole document (grid, preview and export)."""
    return check_totals(document.lines, document.payable_amount)
