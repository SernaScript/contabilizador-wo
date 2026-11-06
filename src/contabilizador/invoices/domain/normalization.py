"""Normalization of supplier item descriptions for the mapping memory."""

import unicodedata

from contabilizador.invoices.domain.mapping import MappingKey


def normalize_description(description: str) -> str:
    """Casefold, strip accents and collapse whitespace.

    Two descriptions that differ only in case, accents or spacing share the same key.
    """
    # NFKD separa las tildes en caracteres combinantes que luego se descartan
    decomposed = unicodedata.normalize("NFKD", description)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.casefold().split())


def mapping_key_for(company_id: int, supplier_nit: str, description: str) -> MappingKey:
    return MappingKey(company_id, supplier_nit, normalize_description(description))
