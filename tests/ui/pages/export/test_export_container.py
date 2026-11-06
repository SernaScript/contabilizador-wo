"""Export sheet container: previews, live consecutive checks, export, errors and success,
against real use cases on a temporary database (jobs run inline)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication, QWidget

from contabilizador.exports.domain.batch import Batch
from contabilizador.exports.domain.errors import (
    CompanyNotFoundError,
    ExportBlockedError,
    ExportProblem,
    ProblemKind,
)
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.ui.composition import Services
from contabilizador.ui.pages.export.container import ExportSheetContainer
from contabilizador.ui.pages.export.view import ExportSheet
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import QtTaskRunner, SyncTaskRunner, TaskRunner
from contabilizador.ui.widgets import Toast, ToastHost
from tests.ui.pages.export.support import (
    DEFAULT_FILE,
    NOW,
    SUPPLIER,
    SUPPLIER_NIT,
    DeferredRunner,
    FailingOnce,
    Opener,
    Seed,
    SpyPresenter,
)

FC = DocumentType.FC
NC = DocumentType.NC

type Chooser = Callable[[QWidget | None, Path], Path | None]


@pytest.fixture
def make_container(
    qtbot,
    seed: Seed,
    presenter: SpyPresenter,
    settings: AppSettings,
    window: QWidget,
    opener: Opener,
    documents_folder: Path,
) -> Callable[..., ExportSheetContainer]:
    def factory(
        *,
        services: Services | None = None,
        runner: TaskRunner | None = None,
        choose_destination: Chooser | None = None,
        debounce_ms: int = 0,
    ) -> ExportSheetContainer:
        container = ExportSheetContainer(
            services or seed.services,
            runner or SyncTaskRunner(),
            presenter,
            ToastHost(window),
            settings=settings,
            parent=window,
            opener=opener,
            choose_destination=choose_destination or (lambda parent, suggested: None),
            clock=lambda: NOW,
            fallback_folder=documents_folder,
            debounce_ms=debounce_ms,
        )
        return container

    return factory


def open_sheet(container: ExportSheetContainer, seed: Seed, *cufes: str) -> ExportSheet:
    container.open(seed.company_id, list(cufes))
    sheet = container.sheet
    assert sheet is not None
    return sheet


def test_opening_previews_the_selection_with_counts_and_next_consecutives(
    seed: Seed,
    make_container: Callable[..., ExportSheetContainer],
    documents_folder: Path,
) -> None:
    seed.previous_batch("old-1", start=40)
    cufes = (
        seed.invoice("fc-1", "5731"),
        seed.invoice("fc-2", "5732"),
        seed.invoice("nc-1", "120", kind=DocumentKind.CREDIT_NOTE),
        seed.invoice("x-1", "5733", cost_center=None),
    )
    container = make_container()

    sheet = open_sheet(container, seed, *cufes)

    assert sheet.isVisible()
    fc, nc = sheet.rows[FC], sheet.rows[NC]
    assert (fc.count.text(), fc.start.value(), fc.range.text()) == ("2", 41, "41 a 42")
    assert (nc.count.text(), nc.start.value(), nc.range.text()) == ("1", 1, "1")
    assert sheet.skipped_label.text() == "1 factura no está lista y queda pendiente."
    assert sheet.primary_button.text() == "Exportar 3 facturas"
    assert sheet.destination() == documents_folder / DEFAULT_FILE
    assert sheet.primary_button.isEnabled()


def test_the_remembered_folder_is_checked_in_the_worker_not_in_the_window(
    qtbot,
    qapp: QApplication,
    seed: Seed,
    settings: AppSettings,
    tmp_path: Path,
    make_container: Callable[..., ExportSheetContainer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remembered = tmp_path / "unidad de red"
    remembered.mkdir()
    settings.last_export_folder = remembered
    cufe = seed.invoice("fc-1", "5731")
    on_gui_thread: list[bool] = []
    real_is_dir = Path.is_dir

    def watching_is_dir(path: Path) -> bool:
        if path == remembered:
            # una carpeta de red caida bloquea aqui decenas de segundos
            on_gui_thread.append(QThread.currentThread() == qapp.thread())
        return real_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", watching_is_dir)
    runner = QtTaskRunner()
    try:
        container = make_container(runner=runner)
        container.open(seed.company_id, [cufe])
        qtbot.waitUntil(lambda: container.sheet is not None, timeout=5000)

        sheet = container.sheet
        assert sheet is not None
        assert sheet.destination() == remembered / DEFAULT_FILE
        assert on_gui_thread == [False]
        sheet.browse_requested.emit()  # el dialogo parte de la carpeta ya resuelta
        assert on_gui_thread == [False]
    finally:
        runner.shutdown()


def toasts_of(window: QWidget) -> list[tuple[str, str]]:
    return [(toast.message(), toast.kind) for toast in window.findChildren(Toast)]


def test_with_nothing_ready_the_sheet_stays_closed_and_a_toast_says_why(
    seed: Seed, make_container: Callable[..., ExportSheetContainer], window: QWidget
) -> None:
    incomplete = seed.invoice("x-1", "5733", cost_center=None)
    container = make_container()

    container.open(seed.company_id, [incomplete])

    assert container.sheet is None
    assert toasts_of(window) == [("Ninguna factura está lista para exportar.", "warning")]


def test_a_failed_preview_is_explained_by_the_presenter(
    seed: Seed, make_container: Callable[..., ExportSheetContainer], presenter: SpyPresenter
) -> None:
    container = make_container()

    container.open(seed.company_id + 99, ["fc-1"])

    assert container.sheet is None
    [(error, context)] = presenter.shown
    assert isinstance(error, CompanyNotFoundError)
    # la vista previa no escribe archivos: sin el contexto de exportar ("cierra Excel")
    assert context is None


def test_a_failed_live_check_never_blames_a_file_in_use(
    qtbot, seed: Seed, services: Services, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    flaky = FailingOnce(services.preview_export, failing_call=2, error=OSError("disk I/O error"))
    container = make_container(services=replace(services, preview_export=flaky))
    sheet = open_sheet(container, seed, cufe)

    sheet.rows[FC].start.setValue(50)

    qtbot.waitUntil(lambda: not sheet.error_notice.isHidden())
    assert "Excel" not in sheet.error_notice.body_label.text()


def test_opening_again_while_open_keeps_a_single_sheet(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    container = make_container()
    first = open_sheet(container, seed, cufe)

    container.open(seed.company_id, [cufe])

    assert container.sheet is first


def test_exportar_writes_the_workbook_and_shows_what_was_exported(
    seed: Seed,
    make_container: Callable[..., ExportSheetContainer],
    settings: AppSettings,
    documents_folder: Path,
) -> None:
    cufes = (
        seed.invoice("fc-1", "5731"),
        seed.invoice("nc-1", "120", kind=DocumentKind.CREDIT_NOTE),
    )
    container = make_container()
    exported: list[Batch] = []
    changes: list[bool] = []
    container.exported.connect(exported.append)
    container.changed.connect(lambda: changes.append(True))
    sheet = open_sheet(container, seed, *cufes)

    sheet.primary_button.click()

    destination = documents_folder / DEFAULT_FILE
    assert destination.is_file()
    [batch] = exported
    assert batch.file_path == destination
    assert {document.cufe for document in batch.documents} == set(cufes)
    assert sheet.is_success
    assert sheet.title_label.text() == "2 facturas exportadas"
    assert sheet.success_saved_label.text() == f"Se guardó {DEFAULT_FILE} en {documents_folder}."
    assert sheet.success_ranges_label.text() == "Consecutivos usados: FC 1 y NC 1."
    assert settings.last_export_folder == documents_folder
    assert changes


def test_the_start_numbers_typed_are_the_ones_exported(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufes = (seed.invoice("fc-1", "5731"), seed.invoice("fc-2", "5732"))
    container = make_container()
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    sheet = open_sheet(container, seed, *cufes)

    sheet.rows[FC].start.setValue(500)
    sheet.primary_button.click()

    [batch] = exported
    assert sorted(document.number for document in batch.documents) == [500, 501]


def test_typing_a_used_consecutive_warns_about_the_collision_while_typing(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    previous = seed.previous_batch("old-1", start=40)
    cufes = (seed.invoice("fc-1", "5731"), seed.invoice("fc-2", "5732"))
    container = make_container()
    sheet = open_sheet(container, seed, *cufes)
    assert sheet.collision_notice.isHidden()

    sheet.rows[FC].start.setValue(39)

    qtbot.waitUntil(lambda: not sheet.collision_notice.isHidden())
    assert sheet.collision_notice.body_label.text() == (
        f"FC 39 a 40 se cruza con el lote {previous.id}, que ya usó FC 40."
    )
    assert not sheet.primary_button.isEnabled()

    sheet.collision_notice.action_button.click()

    qtbot.waitUntil(lambda: sheet.collision_notice.isHidden())
    assert sheet.rows[FC].start.value() == 41
    assert sheet.primary_button.isEnabled()


def test_a_confirmed_collision_is_exported_with_the_numbers_chosen(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    seed.previous_batch("old-1", start=40)
    cufe = seed.invoice("fc-1", "5731")
    container = make_container()
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    sheet = open_sheet(container, seed, cufe)
    sheet.rows[FC].start.setValue(40)
    qtbot.waitUntil(lambda: not sheet.collision_notice.isHidden())

    sheet.collision_notice.checkbox.click()
    sheet.primary_button.click()

    [batch] = exported
    assert [document.number for document in batch.documents] == [40]


def test_exportar_right_after_typing_checks_the_new_numbers_before_exporting(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    seed.previous_batch("old-1", start=40)
    cufe = seed.invoice("fc-1", "5731")
    # el debounce no alcanza a correr: Exportar llega antes
    container = make_container(debounce_ms=60_000)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    sheet = open_sheet(container, seed, cufe)

    sheet.rows[FC].start.setValue(40)
    sheet.primary_button.click()

    assert exported == []
    assert not sheet.collision_notice.isHidden()
    assert not sheet.is_success


def mismatched_selection(seed: Seed) -> tuple[str, str, str]:
    """Two invoices that match their XML and one whose lines do not add up."""
    return (
        seed.invoice("fc-1", "5731"),
        seed.invoice("fc-2", "5732"),
        seed.invoice("fc-m", "5734", payable=Decimal(100)),
    )


def test_mismatched_invoices_stay_out_until_the_person_includes_them(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    container = make_container()

    sheet = open_sheet(container, seed, *mismatched_selection(seed))

    # por defecto solo salen las que cuadran: ni la cuenta ni los consecutivos incluyen la otra
    assert not sheet.mismatch_notice.isHidden()
    assert not sheet.mismatch_confirmed()
    assert sheet.rows[FC].count.text() == "2"
    assert sheet.rows[FC].range.text() == "1 a 2"
    assert sheet.primary_button.text() == "Exportar 2 facturas"
    assert sheet.primary_button.isEnabled()
    assert sheet.mismatch_notice.body_label.text().endswith(
        "FPI-5734 · FERRETERIA CENTRAL: las líneas suman $ 19 más que el XML."
    )

    sheet.mismatch_notice.checkbox.click()

    assert sheet.rows[FC].count.text() == "3"
    assert sheet.rows[FC].range.text() == "1 a 3"
    assert sheet.primary_button.text() == "Exportar 3 facturas"

    sheet.mismatch_notice.checkbox.click()

    assert sheet.rows[FC].count.text() == "2"
    assert sheet.primary_button.text() == "Exportar 2 facturas"


def test_without_the_opt_in_the_mismatched_invoice_stays_pending(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    clean_one, clean_two, off = mismatched_selection(seed)
    container = make_container()
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    sheet = open_sheet(container, seed, clean_one, clean_two, off)

    sheet.primary_button.click()

    [batch] = exported
    assert {document.cufe for document in batch.documents} == {clean_one, clean_two}
    # la factura con descuadre sigue en la lista, lista para decidir otro dia
    pending = seed.services.list_pending.execute(seed.company_id)
    assert [d.invoice.document.cufe for d in pending.documents] == [off]


def test_with_the_opt_in_the_mismatched_invoice_goes_in_the_batch(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufes = mismatched_selection(seed)
    container = make_container()
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    sheet = open_sheet(container, seed, *cufes)

    sheet.mismatch_notice.checkbox.click()
    sheet.primary_button.click()

    [batch] = exported
    assert {document.cufe for document in batch.documents} == set(cufes)
    assert sorted(document.number for document in batch.documents) == [1, 2, 3]


def test_exporting_right_after_ticking_the_box_exports_what_the_box_says(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufes = mismatched_selection(seed)
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, list(cufes))
    runner.run()
    sheet = container.sheet
    assert sheet is not None

    # la vista previa con la factura incluida aun no llego cuando se pulsa Exportar
    sheet.mismatch_notice.checkbox.click()
    sheet.primary_button.click()
    assert exported == []
    while runner.jobs:
        runner.run()

    [batch] = exported
    assert {document.cufe for document in batch.documents} == set(cufes)


def test_only_mismatched_invoices_open_the_sheet_and_wait_for_the_opt_in(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    off = seed.invoice("fc-m", "5734", payable=Decimal(100))
    container = make_container()
    exported: list[Batch] = []
    container.exported.connect(exported.append)

    sheet = open_sheet(container, seed, off)

    assert sheet.rows == {}
    assert not sheet.primary_button.isEnabled()
    assert sheet.primary_button.toolTip() == (
        "Solo hay facturas con descuadre. Marca la casilla para exportarlas."
    )

    sheet.mismatch_notice.checkbox.click()

    assert sheet.primary_button.text() == "Exportar 1 factura"
    assert sheet.primary_button.isEnabled()
    sheet.primary_button.click()
    assert [document.cufe for document in exported[0].documents] == [off]


def test_typing_numbers_keeps_the_mismatch_notice_and_the_choice(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    seed.previous_batch("old-1", start=40)
    sheet = open_sheet(make_container(), seed, *mismatched_selection(seed))
    assert sheet.mismatch_notice.isVisibleTo(sheet)

    sheet.rows[FC].start.setValue(39)
    qtbot.waitUntil(lambda: not sheet.collision_notice.isHidden())

    # la vista previa que se repite al escribir no pierde el aviso de la factura que quedo fuera
    assert sheet.mismatch_notice.isVisibleTo(sheet)
    assert not sheet.mismatch_confirmed()
    assert sheet.primary_button.text() == "Exportar 2 facturas"


def test_a_file_that_cannot_be_written_is_explained_and_can_be_retried(
    seed: Seed,
    make_container: Callable[..., ExportSheetContainer],
    documents_folder: Path,
    tmp_path: Path,
) -> None:
    # el archivo sugerido no se puede escribir (ya hay una carpeta con ese nombre)
    (documents_folder / DEFAULT_FILE).mkdir()
    cufe = seed.invoice("fc-1", "5731")
    suggestions: list[Path] = []

    def choose(parent: QWidget | None, suggested: Path) -> Path:
        suggestions.append(suggested)
        return tmp_path / "otra" / "lote"

    container = make_container(choose_destination=choose)
    sheet = open_sheet(container, seed, cufe)

    sheet.primary_button.click()

    notice = sheet.error_notice
    assert not notice.isHidden()
    assert notice.title_label.text() == "No se pudo guardar el archivo"
    assert notice.body_label.text() == (
        "El archivo está en uso o la carpeta no permite escribir.\n"
        "Cierra el archivo en Excel e inténtalo de nuevo."
    )
    assert not sheet.is_success
    assert not sheet.is_exporting
    assert sheet.primary_button.isEnabled()
    assert seed.services.list_batches.execute(seed.company_id) == []

    sheet.browse_button.click()

    assert suggestions == [documents_folder / DEFAULT_FILE]
    assert sheet.destination() == tmp_path / "otra" / "lote.xlsx"

    sheet.primary_button.click()

    assert sheet.is_success
    assert (tmp_path / "otra" / "lote.xlsx").is_file()


def test_cancelling_the_file_dialog_keeps_the_destination(
    seed: Seed, make_container: Callable[..., ExportSheetContainer], documents_folder: Path
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    container = make_container(choose_destination=lambda parent, suggested: None)
    sheet = open_sheet(container, seed, cufe)

    sheet.browse_button.click()

    assert sheet.destination() == documents_folder / DEFAULT_FILE


class RaisingExport:
    """Stands in for ExportBatch when the data changed between preview and export."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def execute(self, request: object) -> Batch:
        raise self.error


def test_errors_about_documents_name_them_by_label_and_refresh_the_lists(
    seed: Seed, services: Services, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    blocked = ExportBlockedError(
        [ExportProblem(ProblemKind.MISSING_COST_CENTER, cufe, line_number=1)]
    )
    container = make_container(services=replace(services, export_batch=RaisingExport(blocked)))
    changes: list[bool] = []
    container.changed.connect(lambda: changes.append(True))
    sheet = open_sheet(container, seed, cufe)

    sheet.primary_button.click()

    notice = sheet.error_notice
    assert notice.title_label.text() == "No se puede exportar"
    assert notice.body_label.text() == (
        "Algunas facturas no están listas.\n"
        "FPI-5731 · FERRETERIA CENTRAL: falta el centro de costo en la línea 1.\n"
        "Completa los pendientes marcados en cada factura y vuelve a exportar."
    )
    assert cufe not in notice.body_label.text()
    assert changes


def export_one(container: ExportSheetContainer, seed: Seed) -> ExportSheet:
    sheet = open_sheet(container, seed, seed.invoice("fc-1", "5731"))
    sheet.primary_button.click()
    assert sheet.is_success
    return sheet


def test_after_exporting_the_file_and_its_folder_open_with_the_system(
    seed: Seed,
    make_container: Callable[..., ExportSheetContainer],
    opener: Opener,
    documents_folder: Path,
) -> None:
    sheet = export_one(make_container(), seed)

    sheet.open_file_button.click()
    sheet.show_in_folder_button.click()

    assert opener.opened == [documents_folder / DEFAULT_FILE, documents_folder]
    assert sheet.error_label.isHidden()


def test_when_the_system_cannot_open_them_the_sheet_says_what_to_do(
    seed: Seed, make_container: Callable[..., ExportSheetContainer], opener: Opener
) -> None:
    opener.succeeds = False
    sheet = export_one(make_container(), seed)

    sheet.open_file_button.click()
    assert sheet.error_label.text() == (
        "No se pudo abrir el archivo. Ábrelo desde Mostrar en carpeta."
    )

    sheet.show_in_folder_button.click()
    assert sheet.error_label.text() == (
        "No se pudo abrir la carpeta. Búscala en la ruta que aparece arriba."
    )


def test_listo_closes_the_sheet_and_confirms_with_a_toast(
    seed: Seed,
    make_container: Callable[..., ExportSheetContainer],
    window: QWidget,
    opener: Opener,
    documents_folder: Path,
) -> None:
    container = make_container()
    sheet = export_one(container, seed)

    sheet.primary_button.click()

    assert container.sheet is None
    [toast] = window.findChildren(Toast)
    assert (toast.message(), toast.kind) == ("1 factura exportada", "success")
    assert toast.action_button.text() == "Mostrar en carpeta"
    toast.action_button.click()
    assert opener.opened == [documents_folder]


def test_cancelar_closes_without_exporting_and_the_sheet_can_open_again(
    seed: Seed, make_container: Callable[..., ExportSheetContainer], window: QWidget
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    container = make_container()
    first = open_sheet(container, seed, cufe)

    first.cancel_button.click()

    assert container.sheet is None
    assert window.findChildren(Toast) == []
    assert seed.services.list_batches.execute(seed.company_id) == []
    second = open_sheet(container, seed, cufe)
    assert second is not first


def test_an_outdated_preview_never_replaces_a_newer_one(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    seed.previous_batch("old-1", start=40)
    cufe = seed.invoice("fc-1", "5731")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    container.open(seed.company_id, [cufe])
    runner.run()
    sheet = container.sheet
    assert sheet is not None

    sheet.rows[FC].start.setValue(40)  # se cruza con el lote anterior
    qtbot.waitUntil(lambda: len(runner.jobs) == 1)
    sheet.rows[FC].start.setValue(41)  # libre
    qtbot.waitUntil(lambda: len(runner.jobs) == 2)
    runner.run(1)
    runner.run(0)  # la respuesta vieja llega tarde

    assert sheet.collision_notice.isHidden()
    assert sheet.primary_button.isEnabled()


def test_numbers_typed_while_exportar_checks_them_are_checked_too(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    seed.previous_batch("old-1", start=5)
    second = seed.previous_batch("old-2", start=25)
    cufe = seed.invoice("fc-1", "5731")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, [cufe])
    runner.run()
    sheet = container.sheet
    assert sheet is not None
    start = sheet.rows[FC].start
    start.setValue(5)
    qtbot.waitUntil(lambda: len(runner.jobs) == 1)
    runner.run()
    sheet.collision_notice.checkbox.click()  # la persona acepta repetir FC 5

    start.setValue(6)
    start.setValue(5)
    sheet.primary_button.click()  # antes del debounce: primero se verifica FC 5
    start.setValue(25)  # y mientras tanto escribe otro numero
    while runner.jobs:
        runner.run()

    # FC 25 nunca se vio ni se confirmo: no sale con la confirmacion que era para FC 5
    assert exported == []
    assert not sheet.is_exporting
    assert sheet.collision_confirmed() is False
    assert f"lote {second.id}" in sheet.collision_notice.body_label.text()


def test_numbers_changed_while_exportar_checks_them_still_end_the_export(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, [cufe])
    runner.run()
    sheet = container.sheet
    assert sheet is not None
    start = sheet.rows[FC].start

    start.setValue(500)
    sheet.primary_button.click()  # verifica 500 antes de exportar
    start.setValue(600)  # cambia mientras se verifica
    runner.run()
    qtbot.wait(20)  # el debounce de lo escrito vence
    while runner.jobs:
        runner.run()
        qtbot.wait(20)

    [batch] = exported
    assert [document.number for document in batch.documents] == [600]
    assert sheet.is_success
    assert not sheet.is_exporting


def test_numbers_changed_while_exportar_checks_them_end_the_export_after_their_debounce(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, [cufe])
    runner.run()
    sheet = container.sheet
    assert sheet is not None
    start = sheet.rows[FC].start

    start.setValue(500)
    sheet.primary_button.click()  # verifica 500 antes de exportar
    start.setValue(600)  # cambia mientras se verifica
    # el debounce de lo escrito vence antes de que llegue esa verificacion
    qtbot.waitUntil(lambda: len(runner.jobs) == 2)
    while runner.jobs:
        runner.run()

    [batch] = exported
    assert [document.number for document in batch.documents] == [600]
    assert sheet.is_success
    assert not sheet.is_exporting


def test_a_sheet_closed_while_exportar_checks_never_exports_from_the_next_one(
    qtbot, seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, [cufe])
    runner.run()
    first = container.sheet
    assert first is not None
    first.rows[FC].start.setValue(500)
    first.primary_button.click()  # verifica 500 antes de exportar...
    first.cancel_button.click()  # ...pero la persona cierra la hoja
    while runner.jobs:
        runner.run()

    container.open(seed.company_id, [cufe])
    runner.run()
    second = container.sheet
    assert second is not None and second is not first
    second.rows[FC].start.setValue(600)  # solo escribe: no pulsa Exportar
    qtbot.waitUntil(lambda: len(runner.jobs) == 1)
    while runner.jobs:
        runner.run()

    assert exported == []
    assert not second.is_success
    assert not second.is_exporting


def _second_company(services: Services, tmp_path: Path) -> Seed:
    company = services.create_company.execute("OTRA EMPRESA S.A.S", "2020")
    assert company.id is not None
    services.save_product.execute(company.id, "P1", "Papelería")
    services.save_cost_center.execute(company.id, "CC1", "Administración")
    services.configure_supplier.execute(company.id, SUPPLIER_NIT, SUPPLIER, ["P1"], "P1")
    return Seed(services, company.id, tmp_path)


def test_a_sheet_still_being_prepared_never_opens_over_another_company(
    seed: Seed, services: Services, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    other = _second_company(services, seed.tmp_path)
    other_cufe = other.invoice("otra-1", "7001")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, [cufe])

    # la ventana cambia de empresa antes de que la hoja aparezca y se pide exportar alli
    container.set_company(other.company_id)
    container.open(other.company_id, [other_cufe])
    runner.run()  # llega la vista previa de la empresa anterior

    assert container.sheet is None
    runner.run()
    sheet = container.sheet
    assert sheet is not None
    sheet.primary_button.click()
    runner.run()
    [batch] = exported
    assert batch.company_id == other.company_id
    assert [document.cufe for document in batch.documents] == [other_cufe]


def test_the_sheet_stays_busy_until_the_export_finishes(
    seed: Seed, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    container.open(seed.company_id, [cufe])
    runner.run()
    sheet = container.sheet
    assert sheet is not None

    sheet.primary_button.click()

    assert sheet.is_exporting
    assert sheet.busy_overlay.message_label.text() == "Exportando 1 factura…"
    sheet.reject()
    assert container.sheet is sheet

    runner.run()

    assert not sheet.is_exporting
    assert sheet.is_success


def test_an_export_finishing_after_its_sheet_closed_is_announced_only_once(
    seed: Seed, make_container: Callable[..., ExportSheetContainer], window: QWidget
) -> None:
    first, second = seed.invoice("fc-1", "5731"), seed.invoice("fc-2", "5732")
    runner = DeferredRunner()
    container = make_container(runner=runner)
    exported: list[Batch] = []
    container.exported.connect(exported.append)
    container.open(seed.company_id, [first])
    runner.run()
    sheet = container.sheet
    assert sheet is not None
    sheet.primary_button.click()
    sheet.done(0)  # la hoja se cerro por otra via mientras se escribia el archivo

    runner.run()

    assert len(exported) == 1
    assert [toast.message() for toast in window.findChildren(Toast)] == ["1 factura exportada"]
    # una hoja nueva no hereda ese lote al cerrarse
    container.open(seed.company_id, [second])
    runner.run()
    assert container.sheet is not None
    container.sheet.cancel_button.click()
    assert len(window.findChildren(Toast)) == 1


def test_a_failed_live_check_is_cleared_by_the_next_one_that_works(
    qtbot, seed: Seed, services: Services, make_container: Callable[..., ExportSheetContainer]
) -> None:
    cufe = seed.invoice("fc-1", "5731")
    flaky = FailingOnce(services.preview_export, failing_call=2)
    container = make_container(services=replace(services, preview_export=flaky))
    sheet = open_sheet(container, seed, cufe)

    sheet.rows[FC].start.setValue(50)
    qtbot.waitUntil(lambda: not sheet.error_notice.isHidden())
    assert sheet.error_notice.title_label.text() == "Algo no salió como se esperaba"
    assert "database is locked" not in sheet.error_notice.body_label.text()

    sheet.rows[FC].start.setValue(51)

    qtbot.waitUntil(lambda: sheet.error_notice.isHidden())


def test_an_export_error_stays_while_the_numbers_are_rechecked(
    qtbot,
    seed: Seed,
    make_container: Callable[..., ExportSheetContainer],
    documents_folder: Path,
) -> None:
    seed.previous_batch("old-1", start=40)
    (documents_folder / DEFAULT_FILE).mkdir()
    sheet = open_sheet(make_container(), seed, seed.invoice("fc-1", "5731"))
    sheet.primary_button.click()
    assert not sheet.error_notice.isHidden()

    sheet.rows[FC].start.setValue(40)
    qtbot.waitUntil(lambda: not sheet.collision_notice.isHidden())

    # el archivo sigue sin poder escribirse: el aviso no desaparece por cambiar numeros
    assert not sheet.error_notice.isHidden()
