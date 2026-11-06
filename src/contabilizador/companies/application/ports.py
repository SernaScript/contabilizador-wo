"""Ports of the companies module."""

from typing import Protocol

from contabilizador.companies.domain.company import Company


class CompanyRepository(Protocol):
    def get(self, company_id: int) -> Company | None: ...

    def list_all(self) -> list[Company]:
        """All companies ordered by name."""
        ...

    def save(self, company: Company) -> Company:
        """Insert (``id is None``) or update; returns the company with its id."""
        ...

    def delete(self, company_id: int) -> None:
        """Remove the company; its company-scoped data cascades."""
        ...
