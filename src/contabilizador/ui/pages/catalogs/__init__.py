"""Catálogos page: products and cost centers (segmented control, search, entry sheet,
Excel import and template download).

Integration wires ``CatalogsContainer`` (see its docstring); the other classes are
presentational and exported for completeness.
"""

from contabilizador.ui.pages.catalogs.container import CatalogsContainer
from contabilizador.ui.pages.catalogs.entry_sheet import CatalogEntrySheet
from contabilizador.ui.pages.catalogs.report_sheet import CatalogImportReportSheet
from contabilizador.ui.pages.catalogs.view import CatalogsView

__all__ = [
    "CatalogEntrySheet",
    "CatalogImportReportSheet",
    "CatalogsContainer",
    "CatalogsView",
]
