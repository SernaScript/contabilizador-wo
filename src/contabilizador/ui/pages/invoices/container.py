"""Facturas page container: runs the use cases through the task runner and feeds the view.

Readiness, problems and the exportable set come from ``PreviewExport`` (one rule for the
pills, the footer and the export). Edits run ``AssignDocumentMapping`` (only the edited
field: the other one is read in the worker) and trigger one debounced refresh; stale
results are dropped with a ``(company_id, generation)`` token, and every edit makes the
reads already queued stale. Imports run in the worker with progress and cancel.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QVBoxLayout, QWidget

from contabilizador.catalog.domain.catalog import CostCenter, Product
from contabilizador.exports.application.preview_export import ExportPreview
from contabilizador.invoices.application.assign_line_mapping import LineAssignment
from contabilizador.invoices.application.errors import ImportCancelledError
from contabilizador.invoices.application.import_invoice_files import ImportReport
from contabilizador.invoices.application.list_pending_documents import PendingDocuments
from contabilizador.shared import strings
from contabilizador.suppliers.domain.supplier_config import SupplierConfig
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import CONTEXT_IMPORT, ErrorPresenter
from contabilizador.ui.pages.invoices.import_report import ImportReportDialog, has_details
from contabilizador.ui.pages.invoices.model import DocumentTreeModel
from contabilizador.ui.pages.invoices.rows import (
    FIELD_PRODUCT,
    InvoiceRow,
    PageSummary,
    build_rows,
    summarize_page,
)
from contabilizador.ui.pages.invoices.view import InvoicesView
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import TaskCancelledError, TaskContext, TaskHandle, TaskRunner
from contabilizador.ui.widgets.code_combo import CodeItem
from contabilizador.ui.widgets.toast import ToastHost

REFRESH_DEBOUNCE_MS = 150
SPLITTER_KEY = "invoices"
COPY_TOAST_MS = 2000
PAGE_CATALOGS = "catalogs"


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Everything one refresh reads, taken in the worker."""

    pending: PendingDocuments
    preview: ExportPreview
    products: list[Product]
    cost_centers: list[CostCenter]
    configs: list[SupplierConfig]


def _open_folder(folder: Path) -> bool:
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class InvoicesPage(QWidget):
    """Container of the Facturas page (see the page contract in the plan)."""

    changed = Signal()
    badge_changed = Signal(int)
    navigate_requested = Signal(str)
    configure_suppliers_requested = Signal(list)  # [(nit, nombre), ...]
    export_requested = Signal(list)  # CUFEs exportables
    busy_changed = Signal(bool)  # importacion en curso (bloquea el selector de empresa)

    def __init__(
        self,
        services: Services,
        runner: TaskRunner,
        presenter: ErrorPresenter,
        toasts: ToastHost,
        *,
        settings: AppSettings | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._presenter = presenter
        self._toasts = toasts
        self._settings = settings if settings is not None else AppSettings()
        self._company_id: int | None = None
        self._generation = 0
        self._summary: PageSummary | None = None
        self._importing = False
        self._import_handle: TaskHandle | None = None
        self._report_dialog: ImportReportDialog | None = None
        # Dialogos y apertura de carpetas inyectables (las pruebas no abren ventanas nativas)
        self.ask_files: Callable[[Path | None], list[Path]] = self._default_ask_files
        self.ask_folder: Callable[[Path | None], Path | None] = self._default_ask_folder
        self.open_folder: Callable[[Path], bool] = _open_folder

        self.model = DocumentTreeModel(self)
        self.view = InvoicesView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.set_model(self.model)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self.refresh)
        self._connect()
        self._restore_layout()

    def _connect(self) -> None:
        view = self.view
        view.import_files_requested.connect(self.open_files_dialog)
        view.import_folder_requested.connect(self.open_folder_dialog)
        view.paths_dropped.connect(self.import_paths)
        view.configure_suppliers_requested.connect(self._request_all_suppliers)
        view.configure_supplier_requested.connect(self._request_one_supplier)
        view.export_requested.connect(self.request_export)
        view.bulk_apply_requested.connect(self._bulk_apply)
        view.restore_suggestion_requested.connect(self._restore_suggestions)
        view.copy_cufe_requested.connect(self._copy_cufe)
        view.show_in_folder_requested.connect(self._show_in_folder)
        view.edit_line_requested.connect(view.edit_line)
        view.refresh_requested.connect(self.refresh)
        view.cancel_requested.connect(self._cancel_import)
        view.catalog_missing.connect(self._on_catalog_missing)
        view.detail_visibility_changed.connect(self._on_detail_toggled)
        view.splitter.splitterMoved.connect(self._on_splitter_moved)
        self.model.document_edited.connect(self._assign_document)
        self.model.line_edited.connect(self._assign_line)

    def _restore_layout(self) -> None:
        self.view.set_detail_visible(self._settings.detail_panel_visible)
        state = self._settings.splitter_state(SPLITTER_KEY)
        if state is not None:
            self.view.splitter.restoreState(state)

    # --- empresa y datos -----------------------------------------------------
    @property
    def company_id(self) -> int | None:
        return self._company_id

    def rows(self) -> tuple[InvoiceRow, ...]:
        return self.model.rows()

    def summary(self) -> PageSummary | None:
        return self._summary

    def set_company(self, company_id: int | None) -> None:
        self._company_id = company_id
        self._generation += 1  # cualquier lectura en curso queda obsoleta
        self.view.clear_selection()
        self.refresh()

    def refresh(self) -> None:
        """Reads the pending documents and their export preview in the worker."""
        self._refresh_timer.stop()
        company_id = self._company_id
        if company_id is None:
            self._apply_empty()
            return
        self._generation += 1
        token = (company_id, self._generation)
        services = self._services

        def job(_ctx: TaskContext) -> _Snapshot:
            pending = services.list_pending.execute(company_id)
            cufes = [document.invoice.document.cufe for document in pending.documents]
            return _Snapshot(
                pending=pending,
                preview=services.preview_export.execute(company_id, cufes),
                products=services.list_products.execute(company_id),
                cost_centers=services.list_cost_centers.execute(company_id),
                configs=services.list_supplier_configs.execute(company_id),
            )

        self._runner.submit(
            job,
            on_done=lambda snapshot: self._apply_snapshot(token, snapshot),
            on_error=self._show_error,
            owner=self,
        )

    def has_pending_refresh(self) -> bool:
        return self._refresh_timer.isActive()

    def flush_refresh(self) -> None:
        """Runs a debounced refresh now (tests and integration)."""
        if self._refresh_timer.isActive():
            self.refresh()

    def _schedule_refresh(self) -> None:
        self._refresh_timer.start()

    def _apply_snapshot(self, token: tuple[int, int], snapshot: _Snapshot) -> None:
        if token != (self._company_id, self._generation):
            return  # resultado obsoleto: cambio la empresa o hubo otro refresco
        rows = build_rows(snapshot.pending, snapshot.preview)
        products = [CodeItem(p.code, p.name) for p in snapshot.products]
        cost_centers = [CodeItem(c.code, c.name) for c in snapshot.cost_centers]
        self.model.set_catalog(
            products, cost_centers, {c.nit: c.product_codes for c in snapshot.configs}
        )
        self.model.set_documents(rows)
        summary = summarize_page(rows, snapshot.preview)
        self._summary = summary
        self.view.set_catalog(products, cost_centers)
        self.view.update_summary(summary)
        self.badge_changed.emit(summary.attention)

    def _apply_empty(self) -> None:
        self.model.set_documents([])
        self._summary = None
        self.view.update_summary(
            PageSummary(
                total=0,
                readiness_counts={},
                filter_counts={},
                unconfigured=(),
                attention=0,
                exportable_cufes=(),
                flow_step=0,
            )
        )
        self.badge_changed.emit(0)

    # --- importacion ---------------------------------------------------------
    def open_files_dialog(self) -> None:
        if self._company_id is None or self._importing:
            return
        chosen = self.ask_files(self._settings.last_import_folder)
        if chosen:
            self.import_paths(chosen)

    def open_folder_dialog(self) -> None:
        if self._company_id is None or self._importing:
            return
        chosen = self.ask_folder(self._settings.last_import_folder)
        if chosen is not None:
            self.import_paths([chosen])

    def import_paths(self, paths: Sequence[Path]) -> None:
        company_id = self._company_id
        chosen = [Path(path) for path in paths]
        if company_id is None or not chosen or self._importing:
            return
        self._remember_import_folder(chosen[0])
        self._importing = True
        self.view.set_busy(strings.IMPORT_PROGRESS, cancellable=True)
        self.busy_changed.emit(True)
        services = self._services

        def job(ctx: TaskContext) -> ImportReport:
            return services.import_invoices.execute(
                company_id, chosen, on_progress=ctx.report, is_cancelled=ctx.cancelled
            )

        handle = self._runner.submit(
            job,
            on_done=self._on_imported,
            on_error=self._on_import_failed,
            on_progress=self.view.set_progress,
            owner=self,
        )
        if not handle.is_finished:
            self._import_handle = handle

    def _cancel_import(self) -> None:
        if self._import_handle is not None:
            self._import_handle.cancel()

    def _finish_import(self) -> None:
        self._importing = False
        self._import_handle = None
        self.view.set_idle()
        self.busy_changed.emit(False)

    def _on_imported(self, report: ImportReport) -> None:
        self._finish_import()
        self.refresh()
        self.changed.emit()
        message = strings.import_result_sentence(
            len(report.imported), len(report.duplicates), len(report.ignored), len(report.failed)
        )
        detailed = has_details(report)
        self._toasts.show_toast(
            message,
            kind="success" if report.imported or not detailed else "warning",
            action_label=strings.ACTION_SHOW_DETAILS if detailed else None,
            on_action=(lambda: self._show_report(report)) if detailed else None,
            timeout_ms=0 if detailed else 6000,
        )

    def _on_import_failed(self, error: BaseException) -> None:
        self._finish_import()
        if isinstance(error, ImportCancelledError | TaskCancelledError):
            self._toasts.show_toast(strings.IMPORT_CANCELLED, kind="info")
            return
        self._show_error(error, context=CONTEXT_IMPORT)

    def _show_report(self, report: ImportReport) -> None:
        dialog = ImportReportDialog(report, self.window())
        self._report_dialog = dialog
        dialog.finished.connect(lambda _result: self._forget_report(dialog))
        dialog.open()

    def _forget_report(self, dialog: ImportReportDialog) -> None:
        if self._report_dialog is dialog:
            self._report_dialog = None
        dialog.deleteLater()

    def report_dialog(self) -> ImportReportDialog | None:
        return self._report_dialog

    def _remember_import_folder(self, path: Path) -> None:
        folder = path if path.is_dir() else path.parent
        self._settings.last_import_folder = folder

    def _default_ask_files(self, start: Path | None) -> list[Path]:
        chosen, _filter = QFileDialog.getOpenFileNames(
            self,
            strings.FILE_DIALOG_IMPORT_TITLE,
            str(start) if start is not None else "",
            strings.FILE_DIALOG_XML_FILTER,
        )
        return [Path(item) for item in chosen]

    def _default_ask_folder(self, start: Path | None) -> Path | None:
        chosen = QFileDialog.getExistingDirectory(
            self, strings.FILE_DIALOG_FOLDER_TITLE, str(start) if start is not None else ""
        )
        return Path(chosen) if chosen else None

    # --- asignaciones --------------------------------------------------------
    def _run_mutation(
        self, action: Callable[[], None], *, on_success: Callable[[], object] | None = None
    ) -> None:
        if self._company_id is None:
            return
        # Una lectura en cola se leyo antes de esta edicion: al llegar desharia lo que la
        # pantalla ya muestra. Se descarta; ``done`` pide otra despues de guardar
        self._generation += 1

        def job(_ctx: TaskContext) -> None:
            action()

        def done(_result: object) -> None:
            self.changed.emit()
            if on_success is not None:
                on_success()
            self._schedule_refresh()

        def failed(error: BaseException) -> None:
            self._show_error(error)
            self.refresh()  # la pantalla vuelve a lo que hay en la base de datos

        self._runner.submit(job, on_done=done, on_error=failed, owner=self)

    def _assign_document(self, invoice_id: int, field: str, code: str) -> None:
        company_id = self._company_id
        if company_id is None:
            return
        services = self._services
        product = code if field == FIELD_PRODUCT else None
        cost_center = code if field != FIELD_PRODUCT else None
        self._run_mutation(
            lambda: services.assign_document_mapping.execute(
                company_id, [invoice_id], product_code=product, cost_center_code=cost_center
            )
        )

    def _assign_line(self, line_id: int, field: str, code: str) -> None:
        company_id = self._company_id
        if company_id is None:
            return
        services = self._services
        product = code if field == FIELD_PRODUCT else None
        cost_center = code if field != FIELD_PRODUCT else None
        # Solo el campo editado: el otro se toma de la base de datos al guardar, nunca de una
        # copia de la pantalla que puede ser anterior a otra edicion aun en cola
        self._run_mutation(
            lambda: services.assign_document_mapping.execute_lines(
                company_id, [line_id], product_code=product, cost_center_code=cost_center
            )
        )

    def _bulk_apply(self, invoice_ids: list[int], product: object, cost_center: object) -> None:
        company_id = self._company_id
        if company_id is None or not invoice_ids:
            return
        services = self._services
        ids = list(invoice_ids)
        self._run_mutation(
            lambda: services.assign_document_mapping.execute(
                company_id,
                ids,
                product_code=str(product) if product else None,
                cost_center_code=str(cost_center) if cost_center else None,
            ),
            on_success=lambda: self._toasts.show_toast(
                strings.invoices_updated(len(ids)), kind="success"
            ),
        )

    def _restore_suggestions(self, line_ids: list[int]) -> None:
        company_id = self._company_id
        if company_id is None or not line_ids:
            return
        services = self._services
        assignments = [LineAssignment(line_id, None) for line_id in line_ids]
        self._run_mutation(lambda: services.assign_mapping.execute(company_id, assignments))

    # --- exportacion y proveedores -------------------------------------------
    def request_export(self) -> None:
        """Exports the exportable subset of the selection, or every exportable invoice."""
        summary = self._summary
        exportable = list(summary.exportable_cufes) if summary is not None else []
        if not exportable:
            self._toasts.show_toast(strings.EXPORT_NOTHING_READY, kind="warning")
            return
        selected = set(self.view.selected_cufes())
        chosen = [cufe for cufe in exportable if cufe in selected] or exportable
        self.export_requested.emit(chosen)

    def _request_all_suppliers(self) -> None:
        if self._summary is not None and self._summary.unconfigured:
            self.configure_suppliers_requested.emit(list(self._summary.unconfigured))

    def _request_one_supplier(self, nit: str, name: str) -> None:
        self.configure_suppliers_requested.emit([(nit, name)])

    # --- acciones del detalle ------------------------------------------------
    def _copy_cufe(self, cufe: str) -> None:
        QApplication.clipboard().setText(cufe)
        self._toasts.show_toast(strings.COPIED, kind="success", timeout_ms=COPY_TOAST_MS)

    def _show_in_folder(self, path: object) -> None:
        file = Path(str(path))
        if not file.exists():
            self._toasts.show_toast(strings.FILE_NOT_FOUND_TOAST, kind="warning")
            return
        self.open_folder(file.parent)

    def _on_catalog_missing(self, field: str) -> None:
        message = (
            strings.CATALOG_EMPTY_PRODUCTS
            if field == FIELD_PRODUCT
            else strings.CATALOG_EMPTY_COST_CENTERS
        )
        self._toasts.show_toast(
            message,
            kind="warning",
            action_label=strings.ACTION_GO_TO_CATALOGS,
            on_action=lambda: self.navigate_requested.emit(PAGE_CATALOGS),
        )

    # --- atajos (los conecta la ventana principal) ---------------------------
    def focus_search(self) -> None:
        self.view.focus_search()

    def clear_selection(self) -> None:
        self.view.clear_selection()

    # --- preferencias --------------------------------------------------------
    def _on_detail_toggled(self, visible: bool) -> None:
        self._settings.detail_panel_visible = visible

    def _on_splitter_moved(self, *_args: object) -> None:
        self._settings.set_splitter_state(SPLITTER_KEY, self.view.splitter.saveState())

    # --- errores -------------------------------------------------------------
    def _show_error(self, error: BaseException, *, context: str | None = None) -> None:
        self._presenter.show(self.window(), error, context=context)
