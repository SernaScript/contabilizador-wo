"""Import products / cost centers from an Excel file.

Expected layout (first sheet): row 1 is a header and is skipped; column A = code,
column B = name. Fully empty rows are ignored. Codes are kept as text (numeric
cells like 513515 become "513515").
"""

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from contabilizador.catalog.application.ports import CostCenterRepository, ProductRepository
from contabilizador.catalog.domain.catalog import CostCenter, Product


class CatalogKind(StrEnum):
    PRODUCT = "product"
    COST_CENTER = "cost_center"


@dataclass(frozen=True, slots=True)
class RawCatalogRow:
    row_number: int  # numero de fila en la hoja (1-based)
    code: str
    name: str


class UnreadableCatalogFileError(ValueError):
    """The file is not a readable Excel workbook (legacy .xls, .csv, corrupt .xlsx)."""


class CatalogSheetReader(Protocol):
    def read(self, path: Path) -> Iterable[RawCatalogRow]:
        """Rows after the header; empty rows already skipped.

        Raises:
            UnreadableCatalogFileError: the file is not a readable workbook.
        """
        ...


@dataclass(frozen=True, slots=True)
class InvalidRow:
    row_number: int
    reason: str


@dataclass(slots=True)
class ImportReport:
    created: int = 0
    updated: int = 0
    invalid: list[InvalidRow] = field(default_factory=list)


class ImportCatalogFromExcel:
    def __init__(
        self,
        reader: CatalogSheetReader,
        products: ProductRepository,
        cost_centers: CostCenterRepository,
    ) -> None:
        self._reader = reader
        self._products = products
        self._cost_centers = cost_centers

    def execute(self, company_id: int, path: Path, kind: CatalogKind) -> ImportReport:
        report = ImportReport()
        valid: dict[str, str] = {}
        for row in self._reader.read(path):
            code, name = row.code.strip(), row.name.strip()
            if not code:
                report.invalid.append(InvalidRow(row.row_number, "code is required"))
            elif not name:
                report.invalid.append(InvalidRow(row.row_number, "name is required"))
            elif code in valid:
                report.invalid.append(InvalidRow(row.row_number, "duplicate code in file"))
            else:
                valid[code] = name

        if kind is CatalogKind.PRODUCT:
            existing = {p.code for p in self._products.list_by_company(company_id)}
            self._products.save_many(Product(company_id, c, n) for c, n in valid.items())
        else:
            existing = {c.code for c in self._cost_centers.list_by_company(company_id)}
            self._cost_centers.save_many(CostCenter(company_id, c, n) for c, n in valid.items())

        report.updated = sum(1 for code in valid if code in existing)
        report.created = len(valid) - report.updated
        return report
