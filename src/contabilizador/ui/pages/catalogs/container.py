"""Catálogos container: loads both catalogs through the task runner and drives the entry
sheet, the delete confirmation, the Excel import and the template download."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.desktop import show_in_file_manager
from contabilizador.ui.errors import CONTEXT_CATALOG, CONTEXT_EXPORT, ErrorPresenter
from contabilizador.ui.pages.catalogs.dialogs import FileDialogs, QtFileDialogs, downloads_folder
from contabilizador.ui.pages.catalogs.entry_sheet import CatalogEntrySheet
from contabilizador.ui.pages.catalogs.report_sheet import CatalogImportReportSheet
from contabilizador.ui.pages.catalogs.rows import CatalogRow, ImportOutcome
from contabilizador.ui.pages.catalogs.view import CatalogsView
from contabilizador.ui.tasks import TaskRunner
from contabilizador.ui.widgets import ConfirmSheet, ToastHost

EXCEL_SUFFIX = ".xlsx"


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Both catalogs of one company, tagged with the request that asked for them."""

    token: tuple[int, int]  # (empresa, generacion)
    products: tuple[CatalogRow, ...]
    cost_centers: tuple[CatalogRow, ...]


class CatalogsContainer(QWidget):
    """Catálogos page container.

    Wiring: ``CatalogsContainer(services, runner, presenter, toasts, parent)``, then
    ``set_company(id | None)`` whenever the company changes and ``refresh()`` to reload.
    Keyword-only extras: ``dialogs`` (native file dialogs) and ``reveal_file`` (shows a file
    in Finder/Explorer); both default to the real ones.

    Signals: ``changed`` after any save, delete or import (reload Facturas and Proveedores:
    their readiness depends on the catalogs), ``busy_changed(bool)`` while an import, a
    delete check or a template download runs (lock the company switcher), ``badge_changed``
    (always 0) and ``navigate_requested`` (never emitted here).

    ``focus_search()`` is the hook for the global Ctrl/Cmd+F shortcut. ``entry_sheet``,
    ``confirmation`` and ``report_sheet`` expose the sheet currently open, if any.
    """

    changed = Signal()  # el catalogo cambio: Facturas y Proveedores deben releerlo
    badge_changed = Signal(int)  # esta pagina no lleva insignia: siempre 0
    navigate_requested = Signal(str)  # parte del contrato de contenedores; esta pagina no navega
    busy_changed = Signal(bool)  # importando o eliminando: bloquea el selector de empresa

    def __init__(
        self,
        services: Services,
        runner: TaskRunner,
        presenter: ErrorPresenter,
        toasts: ToastHost,
        parent: QWidget | None = None,
        *,
        dialogs: FileDialogs | None = None,
        reveal_file: Callable[[Path], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._presenter = presenter
        self._toasts = toasts
        self._dialogs: FileDialogs = dialogs or QtFileDialogs()
        self._reveal_file = reveal_file or show_in_file_manager
        self._company_id: int | None = None
        self._generation = 0
        self._loading = False  # hay una carga en curso para la empresa actual
        self._reload_requested = False  # llegaron peticiones de recarga mientras cargaba
        self._action_running = False
        self._rows: dict[CatalogKind, dict[str, CatalogRow]] = {kind: {} for kind in CatalogKind}
        # Hojas abiertas: visibles para quien necesite inspeccionarlas (p. ej. las pruebas)
        self.entry_sheet: CatalogEntrySheet | None = None
        self.confirmation: ConfirmSheet | None = None
        self.report_sheet: CatalogImportReportSheet | None = None

        self.view = CatalogsView()
        self.view.set_has_company(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self.view.new_requested.connect(lambda: self._open_entry(None))
        self.view.edit_requested.connect(self._open_entry)
        self.view.delete_requested.connect(self._request_delete)
        self.view.import_requested.connect(self._request_import)
        self.view.template_requested.connect(self._request_template)

    # --- contrato de paginas -------------------------------------------------
    def set_company(self, company_id: int | None) -> None:
        self._company_id = company_id
        self._generation += 1  # lo que llegue de la empresa anterior se descarta
        self._loading = False
        self._reload_requested = False
        self._rows = {kind: {} for kind in CatalogKind}
        self.view.reset()
        self.view.set_has_company(company_id is not None)
        self._reload()

    def refresh(self) -> None:
        """Reloads both catalogs; requests that arrive while a load runs become one more."""
        if self._loading:
            self._reload_requested = True
            return
        self._reload()

    def focus_search(self) -> None:
        self.view.focus_search()

    # --- carga ---------------------------------------------------------------
    def _reload(self, reveal: tuple[CatalogKind, str] | None = None) -> None:
        company_id = self._company_id
        if company_id is None:
            return
        self._generation += 1
        token = (company_id, self._generation)
        services = self._services
        self._loading = True
        self._reload_requested = False

        def job(_ctx: object) -> _Snapshot:
            products = tuple(
                CatalogRow(p.code, p.name) for p in services.list_products.execute(company_id)
            )
            centers = tuple(
                CatalogRow(c.code, c.name) for c in services.list_cost_centers.execute(company_id)
            )
            return _Snapshot(token, products, centers)

        def done(snapshot: _Snapshot) -> None:
            if snapshot.token != (self._company_id, self._generation):
                return  # llego tarde: la empresa o una recarga mas reciente ya la reemplazo
            self._apply(snapshot, reveal)
            self._load_finished()

        def failed(error: BaseException) -> None:
            if token != (self._company_id, self._generation):
                return
            self._presenter.show(self, error)
            self._load_finished()

        self._runner.submit(job, on_done=done, on_error=failed, owner=self)

    def _load_finished(self) -> None:
        self._loading = False
        if self._reload_requested:
            self._reload()

    def _apply(self, snapshot: _Snapshot, reveal: tuple[CatalogKind, str] | None) -> None:
        by_kind = {
            CatalogKind.PRODUCT: snapshot.products,
            CatalogKind.COST_CENTER: snapshot.cost_centers,
        }
        for kind, rows in by_kind.items():
            self._rows[kind] = {row.code: row for row in rows}
            self.view.set_rows(kind, rows)
        # solo si la persona sigue mirando el catalogo donde creo el registro
        if reveal is not None and reveal[0] is self.view.current_kind():
            self.view.reveal_code(reveal[1])
        self.badge_changed.emit(0)

    # --- crear y editar ------------------------------------------------------
    def _open_entry(self, code: str | None) -> None:
        if self.entry_sheet is not None or self._company_id is None:
            return
        kind = self.view.current_kind()
        name = ""
        if code is not None:
            row = self._rows[kind].get(code)
            if row is None:
                return
            name = row.name
        sheet = CatalogEntrySheet(kind, code=code, name=name, parent=self)
        creating = code is None
        sheet.submitted.connect(
            lambda saved_code, saved_name: self._save_entry(
                sheet, kind, saved_code, saved_name, creating=creating
            )
        )
        sheet.finished.connect(lambda _result: self._entry_closed(sheet))
        self.entry_sheet = sheet
        sheet.open()

    def _save_entry(
        self, sheet: CatalogEntrySheet, kind: CatalogKind, code: str, name: str, *, creating: bool
    ) -> None:
        company_id = self._company_id
        if company_id is None:
            return
        if creating and code in self._rows[kind]:
            # guardar sobrescribiria el registro existente sin avisar
            sheet.show_error(strings.catalog_code_exists(kind, code), field="code")
            return
        services = self._services
        sheet.set_saving(True)

        def job(_ctx: object) -> str:
            if kind is CatalogKind.PRODUCT:
                services.save_product.execute(company_id, code, name)
            else:
                services.save_cost_center.execute(company_id, code, name)
            return code

        self._runner.submit(
            job,
            on_done=lambda saved: self._entry_saved(sheet, kind, saved),
            on_error=lambda error: self._entry_failed(sheet, error),
            owner=self,
        )

    def _entry_saved(self, sheet: CatalogEntrySheet, kind: CatalogKind, code: str) -> None:
        # La hoja pudo cerrarse por otra via: lo guardado cuenta igual
        if self.entry_sheet is sheet:
            sheet.set_saving(False)
            sheet.close_saved()
        self._toasts.show_toast(strings.catalog_saved(kind), kind="success")
        self.changed.emit()
        self._reload(reveal=(kind, code))

    def _entry_failed(self, sheet: CatalogEntrySheet, error: BaseException) -> None:
        if self.entry_sheet is not sheet:
            self._presenter.show(self, error)  # la hoja ya no esta: se explica sobre la pagina
            return
        sheet.set_saving(False)  # la hoja sigue abierta para poder reintentar
        self._presenter.show(sheet, error)

    def _entry_closed(self, sheet: CatalogEntrySheet) -> None:
        if self.entry_sheet is sheet:
            self.entry_sheet = None
        sheet.deleteLater()

    # --- eliminar ------------------------------------------------------------
    def _request_delete(self, code: str) -> None:
        company_id = self._company_id
        if company_id is None or self._action_running or self.confirmation is not None:
            return
        kind = self.view.current_kind()
        row = self._rows[kind].get(code)
        label = row.display if row is not None else code
        services = self._services

        def job(_ctx: object) -> tuple[str, ...]:
            if kind is not CatalogKind.PRODUCT:
                return ()
            # el aviso se calcula al momento: los proveedores pudieron cambiar desde la ultima carga
            configs = services.list_supplier_configs.execute(company_id)
            return tuple(sorted(config.name for config in configs if code in config.product_codes))

        self._begin_action()
        self._runner.submit(
            job,
            on_done=lambda names: self._confirm_delete(kind, code, label, names),
            on_error=self._action_failed,
            owner=self,
        )

    def _confirm_delete(
        self, kind: CatalogKind, code: str, label: str, supplier_names: tuple[str, ...]
    ) -> None:
        self._end_action()
        if supplier_names:
            message, notes = (
                strings.catalog_product_in_use(supplier_names),
                [strings.CATALOG_DELETE_NOTE],
            )
        elif kind is CatalogKind.COST_CENTER:
            message, notes = strings.CATALOG_COST_CENTER_DELETE_NOTE, [strings.CATALOG_DELETE_NOTE]
        else:
            message, notes = strings.CATALOG_DELETE_NOTE, []
        sheet = ConfirmSheet(
            strings.confirm_delete(label),
            message,
            confirm_label=strings.ACTION_DELETE,
            notes=notes,
            parent=self,
        )
        sheet.accepted.connect(lambda: self._delete(kind, code))
        sheet.finished.connect(lambda _result: self._confirmation_closed(sheet))
        self.confirmation = sheet
        sheet.open()

    def _confirmation_closed(self, sheet: ConfirmSheet) -> None:
        if self.confirmation is sheet:
            self.confirmation = None
        sheet.deleteLater()

    def _delete(self, kind: CatalogKind, code: str) -> None:
        company_id = self._company_id
        if company_id is None:
            return
        services = self._services

        def job(_ctx: object) -> None:
            if kind is CatalogKind.PRODUCT:
                services.delete_product.execute(company_id, code)
            else:
                services.delete_cost_center.execute(company_id, code)

        def done(_result: None) -> None:
            self._end_action()
            self._toasts.show_toast(strings.catalog_deleted(kind), kind="success")
            self.changed.emit()
            self._reload()

        self._begin_action()
        self._runner.submit(job, on_done=done, on_error=self._action_failed, owner=self)

    # --- importar desde Excel ------------------------------------------------
    def _request_import(self) -> None:
        company_id = self._company_id
        if company_id is None or self._action_running:
            return
        path = self._dialogs.choose_workbook(self)
        if path is None:
            return
        kind = self.view.current_kind()
        services = self._services

        def job(_ctx: object) -> ImportOutcome:
            report = services.import_catalog.execute(company_id, path, kind)
            invalid = tuple((row.row_number, row.reason) for row in report.invalid)
            return ImportOutcome(report.created, report.updated, invalid)

        self._begin_action()
        self._runner.submit(
            job,
            on_done=lambda outcome: self._import_done(kind, outcome),
            on_error=self._import_failed,
            owner=self,
        )

    def _import_done(self, kind: CatalogKind, outcome: ImportOutcome) -> None:
        self._end_action()
        sentence = strings.catalog_import_sentence(
            kind, outcome.created, outcome.updated, len(outcome.invalid)
        )
        if outcome.invalid:
            sheet = CatalogImportReportSheet(kind, outcome, parent=self)
            sheet.finished.connect(lambda _result: self._report_closed(sheet))
            self.report_sheet = sheet
            sheet.open()
        elif outcome.created or outcome.updated:
            self._toasts.show_toast(sentence, kind="success")
        else:
            self._toasts.show_toast(sentence, kind="warning")
        if outcome.created or outcome.updated:
            self.changed.emit()
            self._reload()

    def _report_closed(self, sheet: CatalogImportReportSheet) -> None:
        if self.report_sheet is sheet:
            self.report_sheet = None
        sheet.deleteLater()

    def _import_failed(self, error: BaseException) -> None:
        self._end_action()
        self._presenter.show(self, error, context=CONTEXT_CATALOG)

    # --- plantilla -----------------------------------------------------------
    def _request_template(self) -> None:
        if self._company_id is None or self._action_running:
            return
        kind = self.view.current_kind()
        suggested = downloads_folder() / strings.catalog_template_filename(kind)
        chosen = self._dialogs.choose_template_destination(self, suggested)
        if chosen is None:
            return
        destination = _with_excel_suffix(chosen)
        services = self._services

        def job(_ctx: object) -> Path:
            services.write_catalog_template.execute(destination, kind)
            return destination

        self._begin_action()
        self._runner.submit(
            job,
            on_done=self._template_saved,
            on_error=self._template_failed,
            owner=self,
        )

    def _template_saved(self, destination: Path) -> None:
        self._end_action()
        self._toasts.show_toast(
            strings.CATALOG_TEMPLATE_SAVED,
            kind="success",
            action_label=strings.ACTION_SHOW_IN_FOLDER,
            on_action=lambda: self._reveal(destination),
        )

    def _template_failed(self, error: BaseException) -> None:
        self._end_action()
        # escribir el libro falla igual que exportar: normalmente el archivo esta abierto en Excel
        self._presenter.show(self, error, context=CONTEXT_EXPORT)

    def _reveal(self, path: Path) -> None:
        try:
            self._reveal_file(path)
        except OSError as error:
            self._presenter.show(self, error, context=CONTEXT_EXPORT)

    # --- estado de las acciones ----------------------------------------------
    def _begin_action(self) -> None:
        self._action_running = True
        self.view.set_busy(True)
        self.busy_changed.emit(True)

    def _end_action(self) -> None:
        if not self._action_running:
            return
        self._action_running = False
        self.view.set_busy(False)
        self.busy_changed.emit(False)

    def _action_failed(self, error: BaseException) -> None:
        self._end_action()
        self._presenter.show(self, error)


def _with_excel_suffix(path: Path) -> Path:
    """Keeps the name the person typed and only appends ``.xlsx`` when it is missing."""
    if path.suffix.lower() == EXCEL_SUFFIX:
        return path
    return path.with_name(path.name + EXCEL_SUFFIX)
