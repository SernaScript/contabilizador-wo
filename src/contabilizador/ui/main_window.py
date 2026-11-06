"""Main window: sidebar navigation, one page per area and the wiring between pages.

Pages never import each other: each one emits signals (``changed``, ``badge_changed``,
``navigate_requested`` and its own requests) and this window connects them. Every use case
runs through the ``TaskRunner``; without one the window runs them inline (tests, scripts),
the app passes a ``QtTaskRunner``.

Without a company the window shows Primeros pasos, and anything that needs a company says
so with a toast instead of doing nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
)
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui import actions
from contabilizador.ui.branding import app_icon
from contabilizador.ui.composition import Services
from contabilizador.ui.dialogs.shortcuts_dialog import ShortcutsDialog
from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.pages.batches import BatchesContainer
from contabilizador.ui.pages.catalogs import CatalogsContainer
from contabilizador.ui.pages.company.container import CompanyContainer
from contabilizador.ui.pages.company.new_company_flow import NewCompanyFlow
from contabilizador.ui.pages.export.container import ExportSheetContainer
from contabilizador.ui.pages.invoices import InvoicesPage
from contabilizador.ui.pages.onboarding.container import OnboardingContainer
from contabilizador.ui.pages.suppliers import SuppliersContainer
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import SyncTaskRunner, TaskContext, TaskRunner
from contabilizador.ui.widgets import CompanySwitcher, DropOverlay, Sidebar, ToastHost
from contabilizador.ui.widgets.drop_overlay import paths_from_mime

PAGE_INVOICES, PAGE_SUPPLIERS, PAGE_CATALOGS, PAGE_BATCHES, PAGE_COMPANY = actions.PAGE_ORDER
PAGE_ONBOARDING = "onboarding"
NAV_SHORTCUTS = "shortcuts"
DEFAULT_SIZE = QSize(1280, 820)

# Orden, texto e icono de la barra lateral (las teclas Ctrl/Cmd+1..5 siguen este orden)
_NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    (PAGE_INVOICES, strings.NAV_INVOICES, "invoices"),
    (PAGE_SUPPLIERS, strings.NAV_SUPPLIERS, "suppliers"),
    (PAGE_CATALOGS, strings.NAV_CATALOGS, "catalogs"),
    (PAGE_BATCHES, strings.NAV_BATCHES, "batches"),
    (PAGE_COMPANY, strings.NAV_COMPANY, "company"),
)


class _CompanyPage(Protocol):
    """What the window asks of every page when the company changes."""

    def set_company(self, company_id: int | None) -> None: ...


class MainWindow(QMainWindow):
    def __init__(
        self,
        services: Services,
        runner: TaskRunner | None = None,
        *,
        settings: AppSettings | None = None,
        presenter: ErrorPresenter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner: TaskRunner = runner if runner is not None else SyncTaskRunner(self)
        self._settings = settings if settings is not None else AppSettings()
        self._presenter = presenter if presenter is not None else ErrorPresenter()
        self._company_id: int | None = None
        self._busy: set[str] = set()
        # Primeros pasos lee todas las facturas para saber si hay alguna: solo se pone al dia
        # mientras esta a la vista (empresa con la que se cargo; None = nunca)
        self._onboarding_company: int | None = None
        self._onboarding_loaded = False
        self._onboarding_stale = False
        self.shortcuts_dialog: ShortcutsDialog | None = None
        self.setWindowTitle(strings.APP_TITLE)
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)

        self._build_shell()
        self._build_pages()
        # Atajos globales por id (no se llama ``actions``: taparia QWidget.actions())
        self.shortcut_actions = actions.build_actions(self)
        for action in self.shortcut_actions.values():
            self.addAction(action)
        self._wire()
        self._restore_geometry()
        self.reload_companies(initial=True)

    # --- construccion ------------------------------------------------------------------
    def _build_shell(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = Sidebar()
        self.company_switcher = CompanySwitcher()
        self.sidebar.set_company_widget(self.company_switcher)
        for key, label, icon_name in _NAV_ITEMS:
            self.sidebar.add_item(key, label, icon_name, shortcut_id=f"nav_{key}")
        self.sidebar.add_item(
            NAV_SHORTCUTS,
            strings.NAV_SHORTCUTS,
            "keyboard",
            shortcut_id="show_shortcuts",
            footer=True,
        )
        layout.addWidget(self.sidebar)

        self.page_area = QWidget()
        area = QVBoxLayout(self.page_area)
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(0)
        self.stack = QStackedWidget()
        # Pagina vacia hasta saber si hay empresas: sin destellos de Primeros pasos al abrir
        self._blank = QWidget()
        self.stack.addWidget(self._blank)
        area.addWidget(self.stack)
        layout.addWidget(self.page_area, 1)
        self.setCentralWidget(root)

        # Los avisos viven sobre el area de paginas: nunca tapan la barra lateral
        self.toasts = ToastHost(self.page_area)
        self.drop_overlay = DropOverlay(root)

    def _build_pages(self) -> None:
        services, runner = self._services, self._runner
        presenter, toasts, settings = self._presenter, self.toasts, self._settings
        self.onboarding_page = OnboardingContainer(services, runner, presenter, toasts)
        self.invoices_page = InvoicesPage(services, runner, presenter, toasts, settings=settings)
        self.suppliers_page = SuppliersContainer(services, runner, presenter, toasts)
        self.catalogs_page = CatalogsContainer(services, runner, presenter, toasts)
        self.batches_page = BatchesContainer(services, runner, presenter, toasts, settings=settings)
        self.company_page = CompanyContainer(services, runner, presenter, toasts)
        self._pages: dict[str, QWidget] = {
            PAGE_ONBOARDING: self.onboarding_page,
            PAGE_INVOICES: self.invoices_page,
            PAGE_SUPPLIERS: self.suppliers_page,
            PAGE_CATALOGS: self.catalogs_page,
            PAGE_BATCHES: self.batches_page,
            PAGE_COMPANY: self.company_page,
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        self._company_pages: tuple[_CompanyPage, ...] = (
            self.invoices_page,
            self.suppliers_page,
            self.catalogs_page,
            self.batches_page,
            self.company_page,
        )
        self.export_sheet = ExportSheetContainer(
            services, runner, presenter, toasts, settings=settings, parent=self
        )
        self.new_company_flow = NewCompanyFlow(services, runner, presenter, toasts, self)

    def _wire(self) -> None:
        self.sidebar.navigated.connect(self.navigate)
        switcher = self.company_switcher
        switcher.company_changed.connect(self._on_company_changed)
        switcher.new_company_requested.connect(self.new_company_flow.open)
        self.new_company_flow.company_created.connect(self._on_company_created)

        invoices = self.invoices_page
        invoices.badge_changed.connect(self._on_invoices_badge)
        invoices.navigate_requested.connect(self.navigate)
        invoices.configure_suppliers_requested.connect(self._configure_suppliers)
        invoices.export_requested.connect(self._open_export)
        invoices.changed.connect(self._on_invoices_changed)

        suppliers = self.suppliers_page
        suppliers.badge_changed.connect(self._on_suppliers_badge)
        suppliers.navigate_requested.connect(self.navigate)
        suppliers.changed.connect(self._on_suppliers_changed)

        self.catalogs_page.navigate_requested.connect(self.navigate)
        self.catalogs_page.changed.connect(self._on_catalogs_changed)
        self.batches_page.navigate_requested.connect(self.navigate)
        self.batches_page.changed.connect(self._on_batches_changed)
        # Importar, borrar del catalogo o anular un lote bloquean el cambio de empresa
        for source, busy_page in (
            (PAGE_INVOICES, self.invoices_page),
            (PAGE_CATALOGS, self.catalogs_page),
            (PAGE_BATCHES, self.batches_page),
        ):
            busy_page.busy_changed.connect(lambda busy, key=source: self._set_busy(key, bool(busy)))

        self.company_page.changed.connect(self._on_company_saved)
        self.company_page.create_company_requested.connect(self.new_company_flow.open)

        onboarding = self.onboarding_page
        onboarding.create_company_requested.connect(self.new_company_flow.open)
        onboarding.navigate_requested.connect(self.navigate)
        onboarding.import_requested.connect(self.import_files)

        self.export_sheet.changed.connect(self._on_exported)

        self._connect_action("import_files", self.import_files)
        self._connect_action("import_folder", self.import_folder)
        self._connect_action("export", self.export)
        self._connect_action("search", self.focus_search)
        self._connect_action("show_shortcuts", self.show_shortcuts)
        for key in actions.PAGE_ORDER:
            self.shortcut_actions[f"nav_{key}"].triggered.connect(
                lambda _checked=False, page=key: self.navigate(page)
            )

    def _connect_action(self, action_id: str, slot: Callable[[], None]) -> None:
        action: QAction = self.shortcut_actions[action_id]
        action.triggered.connect(lambda _checked=False: slot())

    # --- paginas ---------------------------------------------------------------------------
    def page(self, key: str) -> QWidget:
        return self._pages[key]

    def current_page(self) -> str | None:
        current = self.stack.currentWidget()
        return next((key for key, page in self._pages.items() if page is current), None)

    def navigate(self, key: str) -> None:
        """Shows a page (or the shortcuts for ``"shortcuts"``); without a company it stays
        on Primeros pasos and says why."""
        if key == NAV_SHORTCUTS:
            self.show_shortcuts()
            return
        if key != PAGE_ONBOARDING and self._company_id is None:
            self._explain_needs_company()
            self._show_page(PAGE_ONBOARDING)
            return
        self._show_page(key)

    def _show_page(self, key: str) -> None:
        focused = self.focusWidget()
        from_sidebar = focused is not None and self.sidebar.isAncestorOf(focused)
        if key == PAGE_ONBOARDING:
            self._sync_onboarding()
        self.stack.setCurrentWidget(self._pages[key])
        self.sidebar.set_active(key if key in actions.PAGE_ORDER else None)
        self._sync_toast_offset()
        # Quien navega con el teclado por la barra lateral sigue en ella; si no, el foco
        # entra al contenido de la pagina (y no al primer boton que encuentre Qt)
        if not from_sidebar:
            self._focus_content()

    def _explain_needs_company(self) -> None:
        self.onboarding_page.explain_needs_company()

    # --- empresas --------------------------------------------------------------------------
    @property
    def company_id(self) -> int | None:
        return self._company_id

    def reload_companies(self, select_id: int | None = None, *, initial: bool = False) -> None:
        """Reads the companies; ``select_id`` selects one (a company just created)."""
        services = self._services

        def job(_ctx: TaskContext) -> list[tuple[int, str]]:
            return [
                (company.id, company.name)
                for company in services.list_companies.execute()
                if company.id is not None
            ]

        self._runner.submit(
            job,
            on_done=lambda companies: self._apply_companies(companies, select_id, initial),
            on_error=lambda error: self._companies_failed(error, initial),
            owner=self,
        )

    def _apply_companies(
        self, companies: Sequence[tuple[int, str]], select_id: int | None, initial: bool
    ) -> None:
        wanted = select_id if select_id is not None else self._company_id
        if wanted is None and initial:
            wanted = self._settings.last_company_id
        switcher = self.company_switcher
        # La ventana reparte la empresa una sola vez, no por cada aviso del selector
        switcher.blockSignals(True)
        try:
            switcher.set_companies(companies, current=wanted)
        finally:
            switcher.blockSignals(False)
        current = switcher.current_company_id()
        if initial or current != self._company_id:
            self._apply_company(current)
        if initial:
            self._show_page(PAGE_INVOICES if current is not None else PAGE_ONBOARDING)

    def _companies_failed(self, error: BaseException, initial: bool) -> None:
        self._presenter.show(self, error)
        if initial:
            self._apply_company(None)

    def _keep_focus_in_page(self) -> None:
        """A step that just got done hides its button: the focus would jump to the sidebar,
        so it goes back into the page instead."""
        page = self.stack.currentWidget()
        focused = self.focusWidget()
        if page is None or focused is None:
            self._focus_content()
            return
        inside = focused is page or page.isAncestorOf(focused)
        if not (inside and not focused.isHidden() and focused.isEnabled()):
            self._focus_content()

    def _focus_content(self) -> None:
        """Keyboard focus starts in the page (the invoice tree, or the first pending step),
        not in the company switcher, the first widget of the window."""
        target: QWidget | None = None
        if self.current_page() == PAGE_INVOICES:
            view = self.invoices_page.view
            showing_list = view.stack.currentWidget() is view.content
            target = view.tree if showing_list else view.empty_state.action_button
        elif self.current_page() == PAGE_ONBOARDING:
            target = next(
                (
                    step.action_button
                    for step in self.onboarding_page.view.steps()
                    if not step.action_button.isHidden() and step.action_button.isEnabled()
                ),
                None,
            )
        if target is None:
            target = self.stack.currentWidget()  # Tab sigue por el primer control de la pagina
        if target is not None:
            target.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_company_changed(self, company_id: object) -> None:
        chosen = company_id if isinstance(company_id, int) else None
        if chosen != self._company_id:
            self._apply_company(chosen)

    def _apply_company(self, company_id: int | None) -> None:
        self._company_id = company_id
        if company_id is not None:
            self._settings.last_company_id = company_id
        for page in self._company_pages:
            page.set_company(company_id)
        # Una hoja de exportar que aun se prepara para la empresa anterior ya no se abre
        self.export_sheet.set_company(company_id)
        if company_id is None:
            self.sidebar.set_badge(PAGE_INVOICES, 0)
            self.sidebar.set_badge(PAGE_SUPPLIERS, 0)
            self._show_page(PAGE_ONBOARDING)
        elif self.current_page() == PAGE_ONBOARDING:
            self._sync_onboarding()
        self._keep_focus_in_page()

    def _sync_onboarding(self) -> None:
        """Brings Primeros pasos up to date with the company (it is only read on screen)."""
        page = self.onboarding_page
        if not self._onboarding_loaded or self._onboarding_company != self._company_id:
            self._onboarding_loaded = True
            self._onboarding_company = self._company_id
            self._onboarding_stale = False
            page.set_company(self._company_id)
        elif self._onboarding_stale:
            self._onboarding_stale = False
            page.refresh()

    def _refresh_onboarding(self) -> None:
        if self.current_page() == PAGE_ONBOARDING:
            self.onboarding_page.refresh()
        else:
            self._onboarding_stale = True

    def _on_company_created(self, company_id: int) -> None:
        # Se queda en la pagina actual: desde Primeros pasos se sigue con el paso 2
        self.reload_companies(select_id=company_id)

    def _on_company_saved(self) -> None:
        self.reload_companies()  # el nombre pudo cambiar

    def _set_busy(self, source: str, busy: bool) -> None:
        if busy:
            self._busy.add(source)
        else:
            self._busy.discard(source)
        self.company_switcher.set_locked(bool(self._busy))

    # --- acciones globales -------------------------------------------------------------------
    def import_files(self) -> None:
        if self._company_id is None:
            self._explain_needs_company()
            return
        self._show_page(PAGE_INVOICES)
        self.invoices_page.open_files_dialog()

    def import_folder(self) -> None:
        if self._company_id is None:
            self._explain_needs_company()
            return
        self._show_page(PAGE_INVOICES)
        self.invoices_page.open_folder_dialog()

    def import_paths(self, paths: Sequence[Path]) -> None:
        """Files dropped anywhere on the window go to Facturas."""
        if self._company_id is None:
            self._explain_needs_company()
            return
        self._show_page(PAGE_INVOICES)
        self.invoices_page.import_paths(list(paths))

    def export(self) -> None:
        if self._company_id is None:
            self._explain_needs_company()
            return
        self._show_page(PAGE_INVOICES)
        self.invoices_page.request_export()

    def focus_search(self) -> None:
        focus = getattr(self.stack.currentWidget(), "focus_search", None)
        if callable(focus):
            focus()

    def show_shortcuts(self) -> None:
        if self.shortcuts_dialog is not None:
            self.shortcuts_dialog.raise_()
            self.shortcuts_dialog.activateWindow()
            return
        dialog = ShortcutsDialog(self)
        self.shortcuts_dialog = dialog
        dialog.finished.connect(lambda _result: self._forget_shortcuts(dialog))
        dialog.open()

    def _forget_shortcuts(self, dialog: ShortcutsDialog) -> None:
        if self.shortcuts_dialog is dialog:
            self.shortcuts_dialog = None
        dialog.deleteLater()

    # --- avisos entre paginas ------------------------------------------------------------------
    def _configure_suppliers(self, suppliers: list[tuple[str, str]]) -> None:
        self.suppliers_page.configure([(nit, name) for nit, name in suppliers])

    def _open_export(self, cufes: list[str]) -> None:
        if self._company_id is not None:
            self.export_sheet.open(self._company_id, list(cufes))

    def _on_invoices_changed(self) -> None:
        # Importar trae proveedores nuevos y cambia las facturas pendientes de cada uno
        self.suppliers_page.refresh()
        self._refresh_onboarding()

    def _on_suppliers_changed(self) -> None:
        self.invoices_page.refresh()

    def _on_catalogs_changed(self) -> None:
        # La preparacion (producto inexistente) y el selector de productos dependen del catalogo
        self.invoices_page.refresh()
        self.suppliers_page.refresh()
        self._refresh_onboarding()

    def _on_batches_changed(self) -> None:
        # Anular o liberar devuelve facturas a pendientes
        self.invoices_page.refresh()
        self.suppliers_page.refresh()

    def _on_exported(self) -> None:
        self.invoices_page.refresh()
        self.batches_page.refresh()
        self.company_page.refresh()  # ultimos consecutivos
        self.suppliers_page.refresh()

    def _on_invoices_badge(self, count: int) -> None:
        self.sidebar.set_badge(PAGE_INVOICES, count)
        self._sync_toast_offset()

    def _on_suppliers_badge(self, count: int) -> None:
        self.sidebar.set_badge(PAGE_SUPPLIERS, count, "blocked")

    def _sync_toast_offset(self) -> None:
        """Lifts the toasts above the readiness footer while Facturas shows it."""
        readiness = self.invoices_page.view.readiness
        on_invoices = self.stack.currentWidget() is self.invoices_page
        visible = on_invoices and readiness.isVisibleTo(self.invoices_page)
        self.toasts.set_bottom_offset(readiness.sizeHint().height() if visible else 0)

    # --- arrastrar y soltar en toda la ventana --------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        event.acceptProposedAction()
        self.drop_overlay.show_overlay()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802 - Qt API
        self.drop_overlay.hide_overlay()
        event.accept()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        self.drop_overlay.hide_overlay()
        paths = paths_from_mime(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        self.import_paths(paths)

    # --- ventana -----------------------------------------------------------------------------
    def _restore_geometry(self) -> None:
        geometry = self._settings.window_geometry
        if geometry is None or not self.restoreGeometry(geometry):
            self.resize(DEFAULT_SIZE)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self._settings.window_geometry = self.saveGeometry()
        self._settings.sync()
        super().closeEvent(event)


__all__ = ["DEFAULT_SIZE", "NAV_SHORTCUTS", "PAGE_ONBOARDING", "MainWindow"]
