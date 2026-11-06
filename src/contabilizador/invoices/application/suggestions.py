"""Effective product / cost center of stored lines (assigned > memory > supplier default).

The documents screen and the export candidates use the same functions, so a line is
exported with exactly the mapping the screen shows. Queries stay constant: one memory
read for any number of lines, one supplier read per distinct supplier.
"""

from collections.abc import Iterable, Mapping, Sequence

from contabilizador.invoices.application.ports import MappingMemoryRepository
from contabilizador.invoices.domain.mapping import LineMapping, MappingKey
from contabilizador.invoices.domain.normalization import mapping_key_for
from contabilizador.invoices.domain.stored import StoredInvoice, StoredLine
from contabilizador.invoices.domain.suggestion import MappingSuggestion, suggest_mapping
from contabilizador.suppliers.application.ports import SupplierConfigRepository
from contabilizador.suppliers.domain.supplier_config import SupplierConfig


def suggest_for_line(
    line: StoredLine, config: SupplierConfig | None, remembered: LineMapping | None
) -> MappingSuggestion:
    """Pure rule: ``remembered`` is the memory entry of the line's key (if any)."""
    return suggest_mapping(
        assigned=line.assigned,
        remembered=remembered,
        supplier_default_product=config.default_product_code if config else None,
    )


def suggest_lines(
    memory: MappingMemoryRepository,
    company_id: int,
    invoices: Sequence[StoredInvoice],
    configs: Mapping[str, SupplierConfig | None],
) -> dict[int, MappingSuggestion]:
    """Effective mapping of every line of ``invoices`` by line id (one memory read).

    ``configs``: supplier configuration by NIT (``None`` or absent = not configured).
    """
    keys: dict[int, MappingKey] = {
        line.id: mapping_key_for(company_id, invoice.document.supplier_nit, line.line.description)
        for invoice in invoices
        for line in invoice.lines
        if _needs_memory(line)
    }
    remembered = memory.get_many(company_id, set(keys.values())) if keys else {}
    suggestions: dict[int, MappingSuggestion] = {}
    for invoice in invoices:
        config = configs.get(invoice.document.supplier_nit)
        for line in invoice.lines:
            key = keys.get(line.id)
            suggestions[line.id] = suggest_for_line(
                line, config, remembered.get(key) if key is not None else None
            )
    return suggestions


def load_supplier_configs(
    suppliers: SupplierConfigRepository, company_id: int, nits: Iterable[str]
) -> dict[str, SupplierConfig | None]:
    """Configuration of each distinct NIT (``None`` = not configured), read once each."""
    return {nit: suppliers.get(company_id, nit) for nit in dict.fromkeys(nits)}


def _needs_memory(line: StoredLine) -> bool:
    # solo una asignacion con producto hace innecesaria la memoria
    return line.assigned is None or not line.assigned.product_code
