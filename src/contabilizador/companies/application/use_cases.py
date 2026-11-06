"""Company use cases (CRUD)."""

from dataclasses import replace

from contabilizador.companies.application.errors import DuplicateCompanyNameError
from contabilizador.companies.application.ports import CompanyRepository
from contabilizador.companies.domain.company import DEFAULT_PAYMENT_FORM, Company

# Valores por defecto de World Office para una empresa nueva
DEFAULT_WAREHOUSE = "Principal"
DEFAULT_UNIT = "Und."


def _comparable(name: str) -> str:
    # mismo nombre para el usuario aunque cambien mayusculas o espacios
    return " ".join(name.split()).casefold()


def _ensure_unique_name(
    companies: CompanyRepository, name: str, *, except_id: int | None = None
) -> None:
    wanted = _comparable(name)
    if any(
        _comparable(other.name) == wanted and other.id != except_id
        for other in companies.list_all()
    ):
        raise DuplicateCompanyNameError(name)


class CreateCompany:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    def execute(
        self,
        name: str,
        internal_third_party_id: str,
        warehouse: str = DEFAULT_WAREHOUSE,
        unit: str = DEFAULT_UNIT,
        payment_form: str = DEFAULT_PAYMENT_FORM,
    ) -> Company:
        """Raises:
        DuplicateCompanyNameError: another company already uses the name.
        ValueError: the name is blank.
        """
        company = Company(
            id=None,
            name=name.strip(),
            internal_third_party_id=internal_third_party_id.strip(),
            warehouse=warehouse.strip(),
            unit=unit.strip(),
            payment_form=payment_form.strip(),
        )
        _ensure_unique_name(self._companies, company.name)
        return self._companies.save(company)


class UpdateCompany:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    def execute(
        self,
        company_id: int,
        *,
        name: str | None = None,
        internal_third_party_id: str | None = None,
        warehouse: str | None = None,
        unit: str | None = None,
        payment_form: str | None = None,
    ) -> Company:
        """Only the given fields change.

        Raises:
            LookupError: the company does not exist.
            DuplicateCompanyNameError: another company already uses the new name.
        """
        current = self._companies.get(company_id)
        if current is None:
            raise LookupError(f"company {company_id} not found")
        changes = {
            "name": name,
            "internal_third_party_id": internal_third_party_id,
            "warehouse": warehouse,
            "unit": unit,
            "payment_form": payment_form,
        }
        # Solo se aplican los campos informados
        provided = {k: v.strip() for k, v in changes.items() if v is not None}
        updated = replace(current, **provided)
        _ensure_unique_name(self._companies, updated.name, except_id=company_id)
        return self._companies.save(updated)


class ListCompanies:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    def execute(self) -> list[Company]:
        return self._companies.list_all()


class DeleteCompany:
    def __init__(self, companies: CompanyRepository) -> None:
        self._companies = companies

    def execute(self, company_id: int) -> None:
        self._companies.delete(company_id)
