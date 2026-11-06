import dataclasses

import pytest

from contabilizador.companies.domain.company import Company


def test_company_defaults_payment_form_to_credito() -> None:
    company = Company(
        id=None,
        name="WEARE DEV S.A.S",
        internal_third_party_id="1037663527",
        warehouse="Principal",
        unit="Und.",
    )
    assert company.payment_form == "Credito"


def test_company_is_immutable() -> None:
    company = Company(1, "WEARE DEV S.A.S", "1037663527", "Principal", "Und.")
    with pytest.raises(dataclasses.FrozenInstanceError):
        company.name = "X"  # type: ignore[misc]


def test_company_requires_name() -> None:
    with pytest.raises(ValueError):
        Company(None, "  ", "1037663527", "Principal", "Und.")
