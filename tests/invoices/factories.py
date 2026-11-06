from datetime import date
from decimal import Decimal
from pathlib import Path

from contabilizador.invoices.domain.document import DocumentKind, ParsedDocument, ParsedLine


def make_document(**overrides: object) -> ParsedDocument:
    values: dict[str, object] = {
        "cufe": "cufe-1",
        "kind": DocumentKind.INVOICE,
        "supplier_nit": "900123456",
        "supplier_name": "COMERCIALIZADORA EJEMPLO S.A.S.",
        "supplier_prefix": "FEV",
        "supplier_number": "001001",
        "issue_date": date(2026, 8, 31),
        "due_date": date(2026, 9, 30),
        "lines": (
            ParsedLine(
                "RESMA PAPEL CARTA 75G", Decimal("3.00"), Decimal("30000.00"), Decimal("19.00")
            ),
            ParsedLine("TONER IMPRESORA LASER", Decimal("1.5"), Decimal("125000.33"), Decimal("0")),
        ),
        "payable_amount": Decimal("184450.00"),
        "billing_reference_cufe": None,
        "source_file": Path("facturas") / "invoice_plain.xml",
    }
    values.update(overrides)
    return ParsedDocument(**values)  # type: ignore[arg-type]
