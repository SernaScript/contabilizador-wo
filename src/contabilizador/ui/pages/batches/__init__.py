"""Lotes exportados page: batch history, void a batch, release invoices, show the file.

Integration wires ``BatchesContainer`` (see its docstring); ``BatchesView`` is
presentational and exported for completeness.
"""

from contabilizador.ui.pages.batches.container import BatchesContainer
from contabilizador.ui.pages.batches.view import BatchesView

__all__ = ["BatchesContainer", "BatchesView"]
