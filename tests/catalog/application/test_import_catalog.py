from pathlib import Path

from openpyxl import Workbook
from sqlalchemy.orm import Session, sessionmaker

from contabilizador.catalog.application.import_catalog import (
    CatalogKind,
    ImportCatalogFromExcel,
)
from contabilizador.catalog.domain.catalog import Product
from contabilizador.catalog.infrastructure.excel_reader import OpenpyxlCatalogSheetReader
from contabilizador.catalog.infrastructure.repository import (
    SqlAlchemyCostCenterRepository,
    SqlAlchemyProductRepository,
)
from contabilizador.companies.domain.company import Company
from contabilizador.companies.infrastructure.repository import SqlAlchemyCompanyRepository


def _write_xlsx(path: Path, rows: list[list[object]]) -> Path:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def _setup(
    sf: sessionmaker[Session],
) -> tuple[int, ImportCatalogFromExcel, SqlAlchemyProductRepository]:
    saved = SqlAlchemyCompanyRepository(sf).save(Company(None, "ACME", "1", "P", "U"))
    assert saved.id is not None
    products = SqlAlchemyProductRepository(sf)
    use_case = ImportCatalogFromExcel(
        OpenpyxlCatalogSheetReader(), products, SqlAlchemyCostCenterRepository(sf)
    )
    return saved.id, use_case, products


def test_imports_products_reporting_created_updated_invalid(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    cid, use_case, products = _setup(session_factory)
    products.save(Product(cid, "002", "Old name"))
    path = _write_xlsx(
        tmp_path / "products.xlsx",
        [
            ["Codigo", "Nombre"],
            ["001", "Papel"],
            ["002", "Tinta"],
            ["", "Sin codigo"],
            ["003", None],
            ["001", "Duplicado"],
            [None, None],
        ],
    )
    report = use_case.execute(cid, path, CatalogKind.PRODUCT)
    assert (report.created, report.updated) == (1, 1)
    assert [(r.row_number, r.reason) for r in report.invalid] == [
        (4, "code is required"),
        (5, "name is required"),
        (6, "duplicate code in file"),
    ]
    assert {p.code: p.name for p in products.list_by_company(cid)} == {
        "001": "Papel",
        "002": "Tinta",
    }


def test_numeric_codes_keep_integer_text(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> None:
    cid, use_case, products = _setup(session_factory)
    path = _write_xlsx(tmp_path / "p.xlsx", [["Codigo", "Nombre"], [513515, "Aseo"]])
    use_case.execute(cid, path, CatalogKind.PRODUCT)
    assert products.get(cid, "513515") is not None


def test_imports_cost_centers(session_factory: sessionmaker[Session], tmp_path: Path) -> None:
    cid, use_case, _ = _setup(session_factory)
    path = _write_xlsx(tmp_path / "cc.xlsx", [["Codigo", "Nombre"], ["10", "Admin"]])
    report = use_case.execute(cid, path, CatalogKind.COST_CENTER)
    assert report.created == 1 and report.invalid == []
