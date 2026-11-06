"""Proveedores page, supplier wizard and product picker.

Integration wires ``SuppliersContainer`` (see its docstring); the other classes are
presentational and exported for completeness.
"""

from contabilizador.ui.pages.suppliers.container import SuppliersContainer
from contabilizador.ui.pages.suppliers.product_picker import ProductPicker
from contabilizador.ui.pages.suppliers.sheet import SupplierSheet
from contabilizador.ui.pages.suppliers.view import SuppliersView
from contabilizador.ui.pages.suppliers.wizard import SupplierWizard

__all__ = [
    "ProductPicker",
    "SupplierSheet",
    "SupplierWizard",
    "SuppliersContainer",
    "SuppliersView",
]
