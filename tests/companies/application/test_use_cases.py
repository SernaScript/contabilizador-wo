import pytest
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.companies.application.errors import DuplicateCompanyNameError
from contabilizador.companies.application.use_cases import (
    CreateCompany,
    DeleteCompany,
    ListCompanies,
    UpdateCompany,
)
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository


def test_create_applies_world_office_defaults(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    company = CreateCompany(repo).execute(name="ACME", internal_third_party_id="123")
    assert company.id is not None
    assert (company.warehouse, company.unit, company.payment_form) == (
        "Principal",
        "Und.",
        "Credito",
    )


def test_create_rejects_blank_name(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    with pytest.raises(ValueError):
        CreateCompany(repo).execute(name=" ", internal_third_party_id="1")


def test_update_changes_fields(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    created = CreateCompany(repo).execute(name="ACME", internal_third_party_id="1")
    assert created.id is not None
    updated = UpdateCompany(repo).execute(created.id, name="ACME 2", warehouse="Norte")
    assert (updated.name, updated.warehouse, updated.unit) == ("ACME 2", "Norte", "Und.")


def test_update_unknown_company_fails(session_factory: sessionmaker[Session]) -> None:
    with pytest.raises(LookupError):
        UpdateCompany(SqlAlchemyCompanyRepository(session_factory)).execute(5, name="x")


def test_list_and_delete(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    created = CreateCompany(repo).execute(name="ACME", internal_third_party_id="1")
    assert len(ListCompanies(repo).execute()) == 1
    assert created.id is not None
    DeleteCompany(repo).execute(created.id)
    assert ListCompanies(repo).execute() == []


def test_create_rejects_a_name_already_used(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    CreateCompany(repo).execute(name="WEARE DEV S.A.S", internal_third_party_id="1")

    # mayusculas y espacios no cambian el nombre para World Office
    with pytest.raises(DuplicateCompanyNameError) as error:
        CreateCompany(repo).execute(name="  weare  dev s.a.s ", internal_third_party_id="2")

    assert error.value.name == "weare  dev s.a.s"
    assert len(ListCompanies(repo).execute()) == 1


def test_update_rejects_the_name_of_another_company(
    session_factory: sessionmaker[Session],
) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    CreateCompany(repo).execute(name="ACME", internal_third_party_id="1")
    beta = CreateCompany(repo).execute(name="BETA", internal_third_party_id="1")
    assert beta.id is not None

    with pytest.raises(DuplicateCompanyNameError):
        UpdateCompany(repo).execute(beta.id, name="Acme", warehouse="Norte")

    unchanged = repo.get(beta.id)
    assert unchanged is not None and (unchanged.name, unchanged.warehouse) == ("BETA", "Principal")


def test_update_may_keep_or_recase_its_own_name(session_factory: sessionmaker[Session]) -> None:
    repo = SqlAlchemyCompanyRepository(session_factory)
    created = CreateCompany(repo).execute(name="Acme", internal_third_party_id="1")
    assert created.id is not None

    renamed = UpdateCompany(repo).execute(created.id, name="ACME", warehouse="Norte")

    assert (renamed.name, renamed.warehouse) == ("ACME", "Norte")


def test_duplicate_name_error_is_a_value_error() -> None:
    # las pantallas ya tratan ValueError como dato invalido del usuario
    assert issubclass(DuplicateCompanyNameError, ValueError)
