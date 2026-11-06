from decimal import Decimal

from contabilizador.exports.infrastructure.invoice_candidate_source import (
    InvoiceExportCandidateSource,
)
from contabilizador.invoices.domain.document import ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.status import InvoiceStatus
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.invoices.application.fakes import (
    FakeInvoiceRepository,
    FakeMappingMemory,
    FakeSupplierConfigs,
)
from tests.invoices.factories import make_document

COMPANY = 1


def _config() -> SupplierConfig:
    return SupplierConfig(COMPANY, "900123456", "EJEMPLO", ("P-DEFAULT", "P-OTHER"), "P-DEFAULT")


def test_find_returns_effective_mapping_per_line_in_order() -> None:
    invoices = FakeInvoiceRepository()
    memory = FakeMappingMemory()
    document = make_document(cufe="c1")
    invoice_id = invoices.add(COMPANY, document)
    stored = invoices.get(COMPANY, invoice_id)
    assert stored is not None
    # linea 1: asignada a mano; linea 2: sugerida por memoria
    invoices.assign_line(stored.lines[0].id, LineMapping("P-MANUAL", "CC-1"))
    memory.remember(
        mapping_key_for(COMPANY, "900123456", "TONER IMPRESORA LASER"),
        LineMapping("P-MEMORY", "CC-2"),
    )
    source = InvoiceExportCandidateSource(invoices, memory, FakeSupplierConfigs(_config()))

    [candidate] = source.find(COMPANY, ["c1"])

    assert candidate.document == document
    assert candidate.status is InvoiceStatus.PENDING
    assert candidate.line_mappings == (
        LineMapping("P-MANUAL", "CC-1"),
        LineMapping("P-MEMORY", "CC-2"),
    )


def test_find_uses_supplier_default_without_cost_center_and_skips_unknown_cufes() -> None:
    invoices = FakeInvoiceRepository()
    line = ParsedLine("ALGO", Decimal(1), Decimal(100), Decimal(0))
    invoices.add(COMPANY, make_document(cufe="c1", lines=(line,)))
    source = InvoiceExportCandidateSource(
        invoices, FakeMappingMemory(), FakeSupplierConfigs(_config())
    )

    candidates = source.find(COMPANY, ["missing", "c1"])

    assert [c.document.cufe for c in candidates] == ["c1"]
    assert candidates[0].line_mappings == (LineMapping("P-DEFAULT", None),)


def test_find_leaves_line_unmapped_when_nothing_suggests() -> None:
    invoices = FakeInvoiceRepository()
    invoices.add(COMPANY, make_document(cufe="c1"))
    invoices.set_status(COMPANY, ["c1"], InvoiceStatus.EXPORTED)
    source = InvoiceExportCandidateSource(invoices, FakeMappingMemory(), FakeSupplierConfigs())

    [candidate] = source.find(COMPANY, ["c1"])

    assert candidate.status is InvoiceStatus.EXPORTED
    assert candidate.line_mappings == (None, None)
