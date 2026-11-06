"""End to end on the real main window (synchronous task runner, temporary database):
first run, company, catalogs, import, supplier wizard, cost centers per invoice, readiness
footer, export of the ready invoices only, the batch in Lotes exportados and its void."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from openpyxl import load_workbook
from PySide6.QtCore import Qt

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.exports.domain.readiness import Readiness
from contabilizador.exports.domain.world_office import (
    HEADER_COLUMNS,
    HEADER_SHEET_NAME,
    LINE_SHEET_NAME,
    DocumentType,
)
from contabilizador.shared import strings
from contabilizador.ui.composition import build_services
from contabilizador.ui.main_window import PAGE_ONBOARDING, MainWindow
from contabilizador.ui.pages.invoices.model import Column
from contabilizador.ui.pages.onboarding.view import STEP_CATALOG, STEP_COMPANY, STEP_IMPORT
from tests.ui.shell import SUPPLIERS, Shell, toast_messages

PRODUCTS = (("P-SERV", "Servicios"), ("P-PAPEL", "Papeleria"))
COST_CENTER = ("CC-ADM", "Administracion")


@pytest.fixture
def shell(tmp_path: Path) -> Iterator[Shell]:
    services = build_services(tmp_path / "app.db")
    yield Shell(services, tmp_path / "settings.ini")
    services.close()


def _create_company(window: MainWindow) -> None:
    window.onboarding_page.view.step(STEP_COMPANY).action_button.click()
    dialog = window.new_company_flow.dialog
    assert dialog is not None
    dialog.form.name_edit.setText("WEARE DEV S.A.S")
    dialog.form.third_party_edit.setText("1017")
    dialog.primary_button.click()


def _add_catalog_entry(window: MainWindow, kind: CatalogKind, code: str, name: str) -> None:
    catalogs = window.catalogs_page
    catalogs.view.segmented.set_current(kind.value)
    catalogs.view.set_kind(kind)
    catalogs.view.new_button.click()
    sheet = catalogs.entry_sheet
    assert sheet is not None and sheet.code_edit is not None
    sheet.code_edit.setText(code)
    sheet.name_edit.setText(name)
    sheet.primary_button.click()
    assert catalogs.entry_sheet is None  # guardado y cerrado


def _configure_suppliers_with_the_wizard(window: MainWindow) -> None:
    window.invoices_page.view.banner.action_button.click()
    wizard = window.suppliers_page.wizard
    assert wizard is not None
    assert wizard.step_count() == len(SUPPLIERS)
    for _step in SUPPLIERS:
        wizard.picker.set_checked("P-SERV", True)  # el primero marcado queda por defecto
        wizard.picker.set_checked("P-PAPEL", True)
        wizard.primary_button.click()
    assert window.suppliers_page.wizard is None


def _assign_cost_center(window: MainWindow, invoice_ids: list[int]) -> None:
    """Bulk bar for several invoices, the invoice row's own cell for a single one."""
    view = window.invoices_page.view
    if len(invoice_ids) == 1:
        model = window.invoices_page.model
        cell = model.index_for_invoice(invoice_ids[0]).siblingAtColumn(Column.COST_CENTER)
        model.setData(cell, COST_CENTER[0], Qt.ItemDataRole.EditRole)
    else:
        view.select_invoices(invoice_ids)
        assert view.bulk_bar.isVisible()
        combo = view.bulk_bar.cost_center_combo
        position = combo.findData(COST_CENTER[0])
        combo.setCurrentIndex(position)
        combo.activated.emit(position)
        view.bulk_bar.apply_button.click()
        view.bulk_bar.clear_button.click()  # Quitar seleccion: el pie vuelve a contar todo
    window.invoices_page.flush_refresh()


def test_first_run_to_exported_batch_and_back(
    qtbot, shell: Shell, tmp_path: Path, xml_fixtures_dir: Path
) -> None:
    window = shell.build(qtbot)

    # --- primera ejecucion: solo Primeros pasos -----------------------------------------
    assert window.current_page() == PAGE_ONBOARDING
    _create_company(window)
    company_id = window.company_id
    assert company_id is not None
    assert window.company_switcher.combo.currentText() == "WEARE DEV S.A.S"
    assert window.current_page() == PAGE_ONBOARDING  # sigue con el paso 2

    # --- catalogos desde el paso 2 -------------------------------------------------------
    window.onboarding_page.view.step(STEP_CATALOG).action_button.click()
    assert window.current_page() == "catalogs"
    for code, name in PRODUCTS:
        _add_catalog_entry(window, CatalogKind.PRODUCT, code, name)
    _add_catalog_entry(window, CatalogKind.COST_CENTER, *COST_CENTER)
    assert [row.code for row in shell.services.list_products.execute(company_id)] == [
        "P-PAPEL",
        "P-SERV",
    ]

    # --- importar la carpeta de XML desde el paso 3 ----------------------------------------
    window.invoices_page.ask_files = lambda _start: [xml_fixtures_dir]
    window.navigate(PAGE_ONBOARDING)
    assert [step.state for step in window.onboarding_page.view.steps()] == [
        "done",
        "done",
        "current",
    ]
    window.onboarding_page.view.step(STEP_IMPORT).action_button.click()
    assert window.current_page() == "invoices"
    assert toast_messages(window)[-1] == strings.import_result_sentence(6, 2, 1, 0)
    summary = window.invoices_page.summary()
    assert summary is not None
    assert summary.total == 6
    assert summary.readiness_counts[Readiness.BLOCKED] == 6  # proveedores sin configurar
    assert window.sidebar.item("suppliers").badge.text() == "3"
    assert window.invoices_page.view.banner.isVisible()

    # --- asistente de proveedores desde el aviso ------------------------------------------
    _configure_suppliers_with_the_wizard(window)
    assert not window.invoices_page.view.banner.isVisible()
    assert window.sidebar.item("suppliers").badge.isHidden()
    summary = window.invoices_page.summary()
    assert summary is not None
    assert summary.readiness_counts[Readiness.INCOMPLETE] == 6  # falta centro de costo

    # --- centro de costo por factura: cinco quedan listas, una por completar ---------------
    rows = window.invoices_page.rows()
    ids = [row.invoice_id for row in rows]
    pending_id = next(row.invoice_id for row in rows if row.document_type == "FC")
    _assign_cost_center(window, [i for i in ids if i != pending_id][:4])
    _assign_cost_center(window, [[i for i in ids if i != pending_id][4]])
    summary = window.invoices_page.summary()
    assert summary is not None
    counts = summary.readiness_counts
    assert counts[Readiness.INCOMPLETE] == 1
    exportable = counts[Readiness.READY] + counts[Readiness.MISMATCH]
    assert exportable == 5
    footer = window.invoices_page.view.readiness
    assert footer.cta_button.text() == strings.export_cta(5)
    assert footer.caption_label.text() == strings.readiness_caption(counts[Readiness.READY], 6)

    # --- exportar solo lo que esta listo -------------------------------------------------------
    footer.cta_button.click()
    sheet = window.export_sheet.sheet
    assert sheet is not None
    destination = tmp_path / "salida" / "compras.xlsx"
    destination.parent.mkdir()
    sheet.set_destination(destination)
    if sheet.mismatch_notice.isVisible():
        sheet.mismatch_notice.checkbox.setChecked(True)
    assert sheet.can_export()
    sheet.primary_button.click()
    assert sheet.is_success
    sheet.primary_button.click()  # Listo
    assert window.export_sheet.sheet is None
    assert toast_messages(window)[-1] == strings.invoices_exported(5)

    workbook = load_workbook(destination)
    assert workbook.sheetnames == [HEADER_SHEET_NAME, LINE_SHEET_NAME]
    headers = list(workbook[HEADER_SHEET_NAME].iter_rows(values_only=True))
    assert tuple(headers[0]) == HEADER_COLUMNS
    assert len(headers) == 1 + 5
    workbook.close()
    summary = window.invoices_page.summary()
    assert summary is not None
    assert summary.total == 1  # solo queda la que no estaba lista
    assert [row.invoice_id for row in window.invoices_page.rows()] == [pending_id]

    # --- el lote aparece en Lotes exportados ---------------------------------------------------
    window.sidebar.item("batches").click()
    batches = window.batches_page
    assert batches.view.batches_model.rowCount() == 1
    batch_id = batches.view.selected_batch_id()
    assert batch_id is not None
    assert batches.view.documents_model.rowCount() == 5
    last_fc = shell.services.plan_consecutives.suggest(company_id, DocumentType.FC)

    # --- anular el lote devuelve las facturas y los consecutivos ------------------------------
    batches.view.void_button.click()
    confirmation = batches.confirmation
    assert confirmation is not None
    confirmation.primary_button.click()
    assert batches.view.selected_batch_id() == batch_id
    summary = window.invoices_page.summary()
    assert summary is not None
    assert summary.total == 6
    assert shell.services.plan_consecutives.suggest(company_id, DocumentType.FC) < last_fc
    assert shell.presenter.shown == []
