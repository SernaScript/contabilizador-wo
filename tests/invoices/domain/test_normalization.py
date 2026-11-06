from contabilizador.invoices.domain.mapping import MappingKey
from contabilizador.invoices.domain.normalization import mapping_key_for, normalize_description


def test_normalize_casefolds_strips_accents_and_collapses_spaces() -> None:
    assert normalize_description("  Café   Molido\t500G ") == "cafe molido 500g"


def test_normalize_treats_equivalent_descriptions_as_equal() -> None:
    assert normalize_description("RESMA  PAPEL Carta") == normalize_description("resma papel carta")


def test_normalize_removes_enie_tilde() -> None:
    assert normalize_description("PIÑA ÑAME") == "pina name"


def test_normalize_empty_description() -> None:
    assert normalize_description("   ") == ""


def test_mapping_key_for_normalizes_the_description() -> None:
    assert mapping_key_for(1, "900123456", " Café Molido ") == MappingKey(
        1, "900123456", "cafe molido"
    )
