from decimal import Decimal

from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from tests.invoices.factories import make_document


def make_stored(status: InvoiceStatus = InvoiceStatus.PENDING) -> StoredInvoice:
    document = make_document()
    lines = tuple(
        StoredLine(id=10 + i, position=i, line=line, assigned=None)
        for i, line in enumerate(document.lines)
    )
    return StoredInvoice(id=1, company_id=7, status=status, document=document, lines=lines)


def test_header_note_joins_line_descriptions() -> None:
    assert make_stored().header_note == "RESMA PAPEL CARTA 75G & TONER IMPRESORA LASER"


def test_totals_check_uses_document_lines() -> None:
    totals = make_stored().totals
    assert totals.expected == Decimal("184450.00")
    assert totals.computed == Decimal("30000") * Decimal("1.19") + Decimal("125000.33")


def test_is_editable_only_when_pending_or_released() -> None:
    assert make_stored(InvoiceStatus.PENDING).is_editable
    assert make_stored(InvoiceStatus.RELEASED).is_editable
    assert not make_stored(InvoiceStatus.EXPORTED).is_editable


def test_line_lookup() -> None:
    stored = make_stored()
    assert stored.line(11) is stored.lines[1]
    assert stored.line(99) is None
