from dataclasses import replace
from decimal import Decimal

from contabilizador.invoices.application.suggestions import (
    load_supplier_configs,
    suggest_for_line,
    suggest_lines,
)
from contabilizador.invoices.domain.document import ParsedLine
from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from contabilizador.invoices.domain.suggestion import MappingSource, MappingSuggestion
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from tests.invoices.application.fakes import (
    FakeInvoiceRepository,
    FakeMappingMemory,
    FakeSupplierConfigs,
)
from tests.invoices.factories import make_document

COMPANY = 1
NIT = "900123456"
OTHER_NIT = "800987654"
CONFIG = SupplierConfig(COMPANY, NIT, "COMERCIALIZADORA", ("P-01", "P-02"), "P-02")
LINE = StoredLine(10, 0, ParsedLine("Resma Papel", Decimal(1), Decimal(10), Decimal(0)), None)


def test_suggest_for_line_is_a_pure_priority_rule() -> None:
    remembered = LineMapping("P-01", "CC-9")

    assert suggest_for_line(LINE, CONFIG, remembered) == MappingSuggestion(
        remembered, MappingSource.MEMORY
    )
    assert suggest_for_line(LINE, CONFIG, None) == MappingSuggestion(
        LineMapping("P-02", None), MappingSource.SUPPLIER_DEFAULT
    )
    assert suggest_for_line(LINE, None, None) == MappingSuggestion(None, MappingSource.NONE)
    manual = replace(LINE, assigned=LineMapping("P-01", "CC-1"))
    assert suggest_for_line(manual, CONFIG, remembered).source is MappingSource.ASSIGNED


def stored_invoices(repo: FakeInvoiceRepository) -> list[StoredInvoice]:
    return repo.list_by_cufes(COMPANY, [s.document.cufe for s in repo.invoices.values()])


def test_suggest_lines_reads_the_memory_once_for_every_line() -> None:
    repo = FakeInvoiceRepository()
    memory = FakeMappingMemory()
    repo.add(COMPANY, make_document(cufe="a"))
    repo.add(COMPANY, make_document(cufe="b", supplier_nit=OTHER_NIT))
    memory.remember(
        mapping_key_for(COMPANY, NIT, "RESMA PAPEL CARTA 75G"), LineMapping("P-01", "CC-9")
    )
    invoices = stored_invoices(repo)

    suggestions = suggest_lines(memory, COMPANY, invoices, {NIT: CONFIG, OTHER_NIT: None})

    assert memory.get_many_calls == 1
    by_line = [
        (invoice.document.cufe, suggestions[line.id])
        for invoice in invoices
        for line in invoice.lines
    ]
    assert by_line == [
        ("a", MappingSuggestion(LineMapping("P-01", "CC-9"), MappingSource.MEMORY)),
        ("a", MappingSuggestion(LineMapping("P-02", None), MappingSource.SUPPLIER_DEFAULT)),
        ("b", MappingSuggestion(None, MappingSource.NONE)),
        ("b", MappingSuggestion(None, MappingSource.NONE)),
    ]


def test_suggest_lines_does_not_read_memory_when_every_line_has_a_manual_product() -> None:
    repo = FakeInvoiceRepository()
    memory = FakeMappingMemory()
    invoice = repo.get(COMPANY, repo.add(COMPANY, make_document(cufe="a")))
    assert invoice is not None
    for line in invoice.lines:
        repo.assign_line(line.id, LineMapping("P-01", None))

    suggestions = suggest_lines(memory, COMPANY, stored_invoices(repo), {NIT: CONFIG})

    assert memory.get_many_calls == 0
    assert {s.source for s in suggestions.values()} == {MappingSource.ASSIGNED}


def test_load_supplier_configs_reads_each_supplier_once() -> None:
    suppliers = FakeSupplierConfigs(CONFIG)

    configs = load_supplier_configs(suppliers, COMPANY, [NIT, OTHER_NIT, NIT])

    assert configs == {NIT: CONFIG, OTHER_NIT: None}
    assert suppliers.get_calls == [NIT, OTHER_NIT]
