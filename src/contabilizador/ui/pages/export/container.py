"""Export sheet container: runs ``PreviewExport`` and ``ExportBatch`` through the task
runner and drives the presentational ``ExportSheet``.

Opened with ``open(company_id, cufes)``: the preview runs first (and checks the
remembered export folder, which may be an unreachable network drive, off the GUI thread)
and the sheet appears already filled; the start numbers re-run the preview (debounced) so
collisions show while typing. Results of outdated previews are dropped with a
``(company_id, generation)`` token.

The invoices whose totals do not match their XML are an opt-in: the sheet first counts only
the ones that do, and ticking the box previews (and exports) them too. Every live preview
therefore reads the whole selection once, to know which invoices those are, and a second
time without them while the box is unchecked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

from contabilizador.exports.application.export_batch import ExportRequest
from contabilizador.exports.application.preview_export import ExportPreview, PreviewExport
from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.errors import (
    ConsecutiveCollisionError,
    ExportBlockedError,
    NothingToExportError,
    TotalsMismatchError,
)
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.shared import strings
from contabilizador.ui.composition import Services
from contabilizador.ui.errors import CONTEXT_EXPORT, ErrorPresentation, ErrorPresenter
from contabilizador.ui.pages.export.desktop import (
    DestinationChooser,
    Opener,
    ask_save_path,
    documents_folder,
    open_with_system,
)
from contabilizador.ui.pages.export.model import (
    build_state,
    default_destination,
    labelled_error_message,
    success_summary,
    with_xlsx_suffix,
)
from contabilizador.ui.pages.export.view import ExportSheet
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import TaskRunner
from contabilizador.ui.widgets import ToastHost

DEBOUNCE_MS = 250
# La seleccion cambio entre la vista previa y la exportacion (otra ventana, otro lote)
STALE_SELECTION_ERRORS = (
    ExportBlockedError,
    TotalsMismatchError,
    ConsecutiveCollisionError,
    NothingToExportError,
)

type Token = tuple[int, int]


def _local_now() -> datetime:
    return datetime.now().astimezone()


@dataclass(frozen=True, slots=True)
class _Previews:
    """What one preview run found.

    Attributes:
        shown: what an export would do with the box as it was when the run started.
        selection: the preview of everything requested (the mismatches come from here).
        included: ``shown`` includes the invoices with a totals mismatch.
    """

    shown: ExportPreview
    selection: ExportPreview
    included: bool


@dataclass(frozen=True, slots=True)
class _Opening:
    """What the sheet needs to appear: the first preview and where to save."""

    previews: _Previews
    destination: Path


def _preview_selection(
    preview_export: PreviewExport,
    company_id: int,
    cufes: Sequence[str],
    starts: Mapping[DocumentType, int] | None,
    *,
    include_mismatched: bool,
) -> _Previews:
    selection = preview_export.execute(company_id, cufes, starts)
    if include_mismatched or not selection.mismatches:
        return _Previews(selection, selection, included=bool(selection.mismatches))
    held_back = {mismatch.cufe for mismatch in selection.mismatches}
    kept = [cufe for cufe in cufes if cufe not in held_back]
    return _Previews(preview_export.execute(company_id, kept, starts), selection, included=False)


class ExportSheetContainer(QObject):
    """Signals:
    exported(Batch): the workbook was written and the batch registered.
    changed(): data shown elsewhere changed (exported invoices, stale lists).
    """

    exported = Signal(object)
    changed = Signal()

    def __init__(
        self,
        services: Services,
        runner: TaskRunner,
        presenter: ErrorPresenter,
        toasts: ToastHost | None,
        *,
        settings: AppSettings,
        parent: QWidget | None = None,
        opener: Opener = open_with_system,
        choose_destination: DestinationChooser = ask_save_path,
        clock: Callable[[], datetime] = _local_now,
        fallback_folder: Path | None = None,
        debounce_ms: int = DEBOUNCE_MS,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._presenter = presenter
        self._toasts = toasts
        self._settings = settings
        self._parent_widget = parent
        self._opener = opener
        self._choose_destination = choose_destination
        self._clock = clock
        self._fallback_folder = fallback_folder
        self._debounce_ms = debounce_ms
        self._generation = 0
        self._token: Token | None = None
        self._company_id: int | None = None
        self._cufes: tuple[str, ...] = ()
        self._preview: ExportPreview | None = None
        self._labels: Mapping[str, str] = {}
        self._previewed_starts: dict[DocumentType, int] = {}
        self._previewed_included = False
        self._export_after_preview = False
        self._error_from_preview = False
        self._sheet: ExportSheet | None = None
        self._batch: Batch | None = None
        self._opening = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_debounce_elapsed)

    @property
    def sheet(self) -> ExportSheet | None:
        """The open sheet, if any."""
        return self._sheet

    # --- apertura --------------------------------------------------------------------
    def open(self, company_id: int, cufes: Sequence[str]) -> None:
        """Previews ``cufes`` and opens the sheet with the exportable subset; with nothing
        exportable a toast says so instead. Ignored while a sheet is already open."""
        if self._sheet is not None:
            self._sheet.raise_()
            self._sheet.activateWindow()
            return
        if self._opening:
            return
        requested = tuple(dict.fromkeys(cufes))
        self._company_id = company_id
        self._cufes = requested
        self._opening = True
        token = self._next_token(company_id)
        preview_export = self._services.preview_export
        remembered = self._settings.last_export_folder
        fallback = self._fallback_folder or documents_folder()
        moment = self._clock()

        def job(_ctx: object) -> _Opening:
            previews = _preview_selection(
                preview_export, company_id, requested, None, include_mismatched=False
            )
            # La carpeta recordada puede ser una unidad de red caida: se revisa aqui, en el
            # hilo de trabajo, y nunca congela la ventana
            return _Opening(previews, default_destination(remembered, fallback, moment))

        self._runner.submit(
            job,
            on_done=lambda opening: self._on_opening_preview(token, opening),
            on_error=lambda error: self._on_opening_failed(token, error),
            owner=self,
        )

    def set_company(self, company_id: int | None) -> None:
        """The window changed company: a sheet still being prepared for another company
        never opens (it would export that company's invoices over this one), and an open
        one that is not writing its file closes."""
        if company_id == self._company_id:
            return
        if self._opening:
            self._opening = False
            self._token = None  # su vista previa llega despues y se descarta
        sheet = self._sheet
        if sheet is not None and not sheet.is_exporting:
            sheet.reject()

    def _on_opening_preview(self, token: Token, opening: _Opening) -> None:
        if token != self._token:
            return  # otra empresa u otra apertura: esta respuesta ya no cuenta
        self._opening = False
        previews = opening.previews
        if previews.selection.needs_refresh:
            self.changed.emit()
        # Con solo facturas con descuadre la hoja abre igual: la casilla es lo que falta
        if not previews.selection.exportable_cufes:
            self._toast(strings.EXPORT_NOTHING_READY, kind="warning")
            return
        sheet = ExportSheet(self._parent_widget)
        sheet.set_destination(opening.destination)
        self._sheet = sheet
        self._show_preview(sheet, previews)
        sheet.start_numbers_changed.connect(self._on_start_numbers_changed)
        sheet.mismatch_inclusion_changed.connect(self._on_mismatch_inclusion_changed)
        sheet.export_requested.connect(self._on_export_requested)
        sheet.browse_requested.connect(self._browse)
        sheet.open_file_requested.connect(self._open_file)
        sheet.show_in_folder_requested.connect(self._show_in_folder)
        sheet.finished.connect(self._on_finished)
        sheet.open()

    def _on_opening_failed(self, token: Token, error: BaseException) -> None:
        if token != self._token:
            return
        self._opening = False
        # la vista previa solo lee: sin el contexto de exportar ("cierra Excel")
        self._presenter.show(self._parent_widget, error)

    # --- vista previa en vivo -----------------------------------------------------------
    def _show_preview(self, sheet: ExportSheet, previews: _Previews) -> None:
        self._preview = previews.shown
        state = build_state(previews.shown, selection=previews.selection)
        self._labels = state.labels
        sheet.set_state(state)
        # consecutivos y casilla con los que se calculo lo que la hoja muestra
        self._previewed_starts = {t: r.first for t, r in previews.shown.plan.ranges.items()}
        self._previewed_included = previews.included

    def _on_start_numbers_changed(self, _starts: object) -> None:
        self._timer.start(self._debounce_ms)

    def _on_debounce_elapsed(self) -> None:
        # Si Exportar estaba verificando, los numeros nuevos se verifican para esa misma
        # exportacion: el clic no se pierde porque el debounce gane la carrera
        self._run_preview(export_after=self._export_after_preview)

    def _on_mismatch_inclusion_changed(self, _included: bool) -> None:
        # Un clic suelto, no una tecla repetida: se recalcula de inmediato
        self._run_preview()

    def _run_preview(self, *, export_after: bool = False) -> None:
        self._timer.stop()
        sheet = self._sheet
        company_id = self._company_id
        # Escribiendo el archivo (o ya exportado) no hay nada que verificar: una vista previa
        # cambiaria el token y la exportacion en curso no terminaria la hoja
        if sheet is None or company_id is None or sheet.is_exporting or sheet.is_success:
            return
        starts = sheet.start_numbers()
        cufes = self._cufes
        include = sheet.mismatch_confirmed()
        token = self._next_token(company_id)
        self._export_after_preview = export_after
        preview_export = self._services.preview_export
        self._runner.submit(
            lambda _ctx: _preview_selection(
                preview_export, company_id, cufes, starts, include_mismatched=include
            ),
            on_done=lambda previews: self._on_preview(token, previews),
            on_error=lambda error: self._on_preview_failed(token, error),
            owner=sheet,
        )

    def _on_preview(self, token: Token, previews: _Previews) -> None:
        sheet = self._sheet
        if token != self._token or sheet is None:
            return
        self._show_preview(sheet, previews)
        if self._error_from_preview:
            # solo se retira el error de una verificacion anterior, no el de exportar
            self._error_from_preview = False
            sheet.show_error(None)
        if previews.selection.needs_refresh:
            self.changed.emit()
        if sheet.mismatch_confirmed() != self._previewed_included:
            # La casilla cambio mientras llegaba esta vista previa, o la hoja la limpio por
            # una lista distinta de descuadres: lo que se muestra no es lo que se exportaria
            self._run_preview(export_after=self._export_after_preview)
            return
        if self._export_after_preview:
            if not self._preview_is_current(sheet):
                # Los numeros cambiaron mientras se verificaban: se verifican los nuevos; las
                # confirmaciones de lo anterior no valen para numeros que nadie ha visto
                self._run_preview(export_after=True)
                return
            self._export_after_preview = False
            # solo si lo nuevo no pide otra confirmacion (p. ej. un cruce recien visto)
            if sheet.can_export():
                self._export(sheet)

    def _on_preview_failed(self, token: Token, error: BaseException) -> None:
        sheet = self._sheet
        if token != self._token or sheet is None:
            return
        self._export_after_preview = False
        self._error_from_preview = True
        sheet.show_error(self._present(error, context=None))

    def _preview_is_current(self, sheet: ExportSheet) -> bool:
        return (
            not self._timer.isActive()
            and sheet.start_numbers() == self._previewed_starts
            and sheet.mismatch_confirmed() == self._previewed_included
        )

    # --- exportacion -------------------------------------------------------------------
    def _on_export_requested(self) -> None:
        sheet = self._sheet
        if sheet is None:
            return
        if self._preview_is_current(sheet):
            self._export(sheet)
        else:
            # Exportar antes del debounce: primero se verifican los numeros escritos
            self._run_preview(export_after=True)

    def _export(self, sheet: ExportSheet) -> None:
        preview = self._preview
        company_id = self._company_id
        destination = sheet.destination()
        if preview is None or company_id is None or destination is None:
            return
        request = ExportRequest(
            company_id=company_id,
            cufes=preview.exportable_cufes,
            destination=destination,
            start_numbers=sheet.start_numbers(),
            confirm_totals_mismatch=sheet.mismatch_confirmed(),
            confirm_consecutive_collision=sheet.collision_confirmed(),
        )
        # Nada de vistas previas mientras se escribe el archivo (el formulario queda bloqueado)
        self._timer.stop()
        self._export_after_preview = False
        token = self._next_token(company_id)
        self._error_from_preview = False
        sheet.show_error(None)
        sheet.set_exporting(True, strings.exporting(len(request.cufes)))
        export_batch = self._services.export_batch
        self._runner.submit(
            lambda _ctx: export_batch.execute(request),
            on_done=lambda batch: self._on_exported(token, batch),
            on_error=lambda error: self._on_export_failed(token, error),
            owner=self,
        )

    def _on_exported(self, token: Token, batch: Batch) -> None:
        self._settings.last_export_folder = batch.file_path.parent
        sheet = self._sheet
        if sheet is not None and token == self._token:
            self._batch = batch
            sheet.set_exporting(False)
            sheet.show_success(success_summary(batch))
        else:
            # la hoja ya no esta, pero el lote si: se confirma de todas formas
            self._announce(batch)
        self.exported.emit(batch)
        self.changed.emit()

    def _on_export_failed(self, token: Token, error: BaseException) -> None:
        sheet = self._sheet
        if sheet is None or token != self._token:
            return
        sheet.set_exporting(False)
        self._error_from_preview = False
        sheet.show_error(self._present(error))
        if isinstance(error, STALE_SELECTION_ERRORS):
            # los datos cambiaron desde la vista previa: las listas y la hoja se ponen al dia
            self.changed.emit()
            self._run_preview()

    def _present(
        self, error: BaseException, *, context: str | None = CONTEXT_EXPORT
    ) -> ErrorPresentation:
        """Presenter copy; documents named by label instead of the presenter's CUFEs."""
        shown = self._presenter.present(error, context=context)
        message = labelled_error_message(error, self._labels)
        return replace(shown, message=message) if message else shown

    # --- destino -----------------------------------------------------------------------
    def _browse(self) -> None:
        sheet = self._sheet
        if sheet is None:
            return
        current = sheet.destination() or self._fallback_destination()
        chosen = self._choose_destination(sheet, current)
        if chosen is not None:
            sheet.set_destination(with_xlsx_suffix(chosen))

    # --- despues de exportar --------------------------------------------------------------
    def _open_file(self) -> None:
        if self._batch is not None and self._sheet is not None:
            opened = self._opener(self._batch.file_path)
            self._sheet.set_error(None if opened else strings.EXPORT_OPEN_FILE_FAILED)

    def _show_in_folder(self) -> None:
        if self._batch is not None and self._sheet is not None:
            opened = self._opener(self._batch.file_path.parent)
            self._sheet.set_error(None if opened else strings.EXPORT_OPEN_FOLDER_FAILED)

    def _on_finished(self, _result: int) -> None:
        sheet, batch = self._sheet, self._batch
        self._timer.stop()
        self._sheet = None
        self._batch = None
        self._preview = None
        self._token = None  # lo que aun este en cola para esta hoja se descarta
        # un Exportar pendiente era de esta hoja: la siguiente no exporta sin su propio clic
        self._export_after_preview = False
        if sheet is not None:
            sheet.deleteLater()
        if batch is not None:
            self._announce(batch)

    def _announce(self, batch: Batch) -> None:
        """Confirms in the main window, where the exported invoices are now gone."""
        folder = batch.file_path.parent
        self._toast(
            strings.invoices_exported(len(batch.documents)),
            kind="success",
            action_label=strings.ACTION_SHOW_IN_FOLDER,
            on_action=lambda: self._opener(folder),
        )

    # --- apoyo -----------------------------------------------------------------------
    def _toast(self, message: str, **options: Any) -> None:
        if self._toasts is not None:
            self._toasts.show_toast(message, **options)

    def _next_token(self, company_id: int) -> Token:
        self._generation += 1
        self._token = (company_id, self._generation)
        return self._token

    def _fallback_destination(self) -> Path:
        """Dated file in Documentos (or the injected folder), without touching the disk."""
        fallback = self._fallback_folder or documents_folder()
        return default_destination(None, fallback, self._clock())
