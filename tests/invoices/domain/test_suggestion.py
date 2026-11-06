from contabilizador.invoices.domain.mapping import LineMapping
from contabilizador.invoices.domain.suggestion import MappingSource, suggest_mapping


def test_explicit_assignment_wins() -> None:
    assigned = LineMapping("P1", "CC1")
    result = suggest_mapping(
        assigned=assigned, remembered=LineMapping("P2", "CC2"), supplier_default_product="P3"
    )
    assert result.mapping == assigned
    assert result.source is MappingSource.ASSIGNED


def test_memory_beats_supplier_default() -> None:
    result = suggest_mapping(
        assigned=None, remembered=LineMapping("P2", "CC2"), supplier_default_product="P3"
    )
    assert result.mapping == LineMapping("P2", "CC2")
    assert result.source is MappingSource.MEMORY


def test_supplier_default_product_without_cost_center() -> None:
    result = suggest_mapping(assigned=None, remembered=None, supplier_default_product="P3")
    assert result.mapping == LineMapping("P3", None)
    assert result.source is MappingSource.SUPPLIER_DEFAULT


def test_no_suggestion() -> None:
    result = suggest_mapping(assigned=None, remembered=None, supplier_default_product=None)
    assert result.mapping is None
    assert result.source is MappingSource.NONE


def test_cost_center_only_assignment_keeps_supplier_default_product() -> None:
    result = suggest_mapping(
        assigned=LineMapping("", "CC1"), remembered=None, supplier_default_product="P3"
    )
    assert result.mapping == LineMapping("P3", "CC1")
    assert result.source is MappingSource.ASSIGNED


def test_cost_center_only_assignment_keeps_remembered_product() -> None:
    result = suggest_mapping(
        assigned=LineMapping("", "CC1"),
        remembered=LineMapping("P2", "CC2"),
        supplier_default_product="P3",
    )
    assert result.mapping == LineMapping("P2", "CC1")
    assert result.source is MappingSource.ASSIGNED


def test_cost_center_only_assignment_without_any_product_keeps_cost_center() -> None:
    result = suggest_mapping(
        assigned=LineMapping("", "CC1"), remembered=None, supplier_default_product=None
    )
    assert result.mapping == LineMapping("", "CC1")
    assert result.source is MappingSource.ASSIGNED
