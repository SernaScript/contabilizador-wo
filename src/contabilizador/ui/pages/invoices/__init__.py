"""Facturas page: import DIAN XML, complete product and cost center, export.

``InvoicesPage`` (container) talks to the use cases through the task runner; the view,
model and delegates are presentational and only emit signals.
"""

from contabilizador.ui.pages.invoices.container import InvoicesPage

__all__ = ["InvoicesPage"]
