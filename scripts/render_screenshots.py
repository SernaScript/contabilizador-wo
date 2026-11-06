"""Renders the states of the main window that the visual review looks at, as PNG files.

A temporary database is seeded through the real use cases: the company, its catalogs, the
XML fixtures plus generated variants (ready, incomplete, unconfigured supplier, a totals
mismatch and a credit note) and one exported batch. The real ``MainWindow`` is then driven
offscreen with the synchronous task runner and temporary settings. Sheets are drawn over
the window, centered, the way Qt places them.

Usage: QT_QPA_PLATFORM=offscreen uv run python scripts/render_screenshots.py --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QModelIndex, QRect
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from contabilizador.exports.application.export_batch import ExportRequest
from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.invoices.domain.document import ParsedDocument
from contabilizador.ui.app import bootstrap
from contabilizador.ui.composition import Services, build_services
from contabilizador.ui.main_window import MainWindow
from contabilizador.ui.pages.invoices.model import Column
from contabilizador.ui.settings import AppSettings
from contabilizador.ui.tasks import SyncTaskRunner
from contabilizador.ui.widgets import Toast

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "xml"
WIDE = (1280, 820)
NARROW = (1024, 700)

COMPANY = ("WEARE DEV S.A.S", "1017")
PRODUCTS = (
    ("P-PAPEL", "Papelería y útiles"),
    ("P-TONER", "Tóner e insumos de impresión"),
    ("P-EQUIPO", "Equipos de cómputo"),
    ("P-CAFE", "Cafetería"),
    ("P-ALIM", "Alimentación"),
    ("P-SERV", "Servicios técnicos"),
    ("P-FERR", "Ferretería y mantenimiento"),
)
COST_CENTERS = (
    ("CC-ADM", "Administración"),
    ("CC-VEN", "Ventas"),
    ("CC-OPE", "Operaciones"),
    ("CC-TI", "Tecnología"),
)
# Proveedor -> (productos permitidos, predeterminado); Ferreteria queda sin configurar
SUPPLIER_PRODUCTS = {
    ("900123456", "COMERCIALIZADORA EJEMPLO S.A.S."): (("P-PAPEL", "P-TONER"), "P-PAPEL"),
    ("1017000111", "PEDRO PRUEBA RESTREPO"): (("P-ALIM",), "P-ALIM"),
    ("800987654", "SERVICIOS TECNICOS DEMO LTDA"): (("P-SERV",), "P-SERV"),
    ("901234567", "PAPELERÍA LA ESTRELLA S.A.S."): (("P-PAPEL", "P-TONER"), "P-PAPEL"),
    ("830045678", "DISTRIBUIDORA ANDINA LTDA"): (("P-CAFE", "P-ALIM", "P-EQUIPO"), "P-CAFE"),
    ("900765432", "TECNOLOGÍA Y REDES S.A.S."): (("P-EQUIPO", "P-SERV"), "P-SERV"),
}


@dataclass(frozen=True, slots=True)
class Template:
    """A fixture and the values its copies replace."""

    file_name: str
    document_id: str
    nit: str
    name: str
    issue: str
    due: str | None
    payable: str
    descriptions: tuple[str, ...]
    cufe: str = field(init=False)

    def __post_init__(self) -> None:
        stem = self.file_name.removesuffix(".xml")
        object.__setattr__(self, "cufe", hashlib.sha384(stem.encode()).hexdigest())


PLAIN = Template(
    "invoice_plain.xml",
    "FEV1001",
    "900123456",
    "COMERCIALIZADORA EJEMPLO S.A.S.",
    "2026-08-31",
    "2026-09-30",
    "184450.00",
    ("RESMA PAPEL CARTA 75G", "TONER IMPRESORA LASER"),
)
MIXED = Template(
    "invoice_mixed_iva.xml",
    "FEV1003",
    "900123456",
    "COMERCIALIZADORA EJEMPLO S.A.S.",
    "2026-09-03",
    "2026-10-03",
    "201500.00",
    ("PORTATIL 14 PULGADAS", "CAFE MOLIDO 500G", "LIBRO CONTABILIDAD BASICA"),
)
NO_DUE = Template(
    "invoice_without_due_date.xml",
    "FE00450",
    "1017000111",
    "PEDRO PRUEBA RESTREPO",
    "2026-09-04",
    None,
    "10000.00",
    ("ALMUERZO EJECUTIVO",),
)
ATTACHED = Template(
    "attached_document_invoice.xml",
    "SETT2045",
    "800987654",
    "SERVICIOS TECNICOS DEMO LTDA",
    "2026-08-31",
    "2026-09-15",
    "200000.00",
    ("SERVICIO TECNICO",),
)


@dataclass(frozen=True, slots=True)
class Variant:
    """A copy of a fixture from another supplier, number, date and descriptions (each with
    its own descriptions, so the mapping memory never completes it by accident)."""

    template: Template
    document_id: str
    nit: str
    name: str
    issue: date
    descriptions: tuple[str, ...]
    payable_extra: Decimal = Decimal(0)  # distinto de cero: descuadre con el XML

    def xml(self) -> str:
        t = self.template
        text = (FIXTURES / t.file_name).read_text(encoding="utf-8")
        replacements = [
            (t.cufe, hashlib.sha384(self.document_id.encode()).hexdigest()),
            (t.document_id, self.document_id),
            (t.nit, self.nit),
            (t.name, self.name),
            (t.issue, self.issue.isoformat()),
        ]
        if t.due is not None:
            replacements.append((t.due, (self.issue + timedelta(days=30)).isoformat()))
        replacements.extend(zip(t.descriptions, self.descriptions, strict=True))
        if self.payable_extra:
            payable = Decimal(t.payable) + self.payable_extra
            replacements.append(
                (f">{t.payable}</cbc:PayableAmount>", f">{payable:.2f}</cbc:PayableAmount>")
            )
        for old, new in replacements:
            text = text.replace(old, new)
        return text


STAR = ("901234567", "PAPELERÍA LA ESTRELLA S.A.S.")
ANDINA = ("830045678", "DISTRIBUIDORA ANDINA LTDA")
TECH = ("900765432", "TECNOLOGÍA Y REDES S.A.S.")
HARDWARE = ("901998877", "FERRETERÍA CENTRAL S.A.S.")
PEDRO = ("1017000111", "PEDRO PRUEBA RESTREPO")
SEPTEMBER = date(2026, 9, 1)


def _variant(
    template: Template,
    document_id: str,
    supplier: tuple[str, str],
    day: int,
    descriptions: tuple[str, ...],
    payable_extra: str = "0",
) -> Variant:
    nit, name = supplier
    issue = SEPTEMBER + timedelta(days=day - 1)
    return Variant(template, document_id, nit, name, issue, descriptions, Decimal(payable_extra))


VARIANTS = (
    _variant(PLAIN, "FEV1010", STAR, 8, ("CUADERNO ARGOLLADO 100H", "TONER HP 105A")),
    _variant(PLAIN, "FEV1011", STAR, 12, ("CARPETA AZ OFICIO", "CINTA EMPAQUE TRANSPARENTE")),
    _variant(
        MIXED, "FEV2201", ANDINA, 9, ("MONITOR 24 PULGADAS", "CAFE TOSTADO 1KG", "AGENDA 2027")
    ),
    _variant(
        MIXED,
        "FEV2202",
        ANDINA,
        15,
        ("TECLADO INALAMBRICO", "AZUCAR BLANCA 2.5KG", "REVISTA FINANZAS"),
        payable_extra="1500",
    ),
    _variant(ATTACHED, "SETT3101", TECH, 10, ("MANTENIMIENTO SERVIDOR",)),
    _variant(ATTACHED, "SETT3102", TECH, 18, ("SOPORTE RED LOCAL",)),
    _variant(PLAIN, "FEV0870", HARDWARE, 11, ("BOMBILLO LED 12W", "CINTA AISLANTE")),
    _variant(NO_DUE, "FE00512", PEDRO, 16, ("REFRIGERIO REUNION",)),
    _variant(PLAIN, "FEV1012", STAR, 20, ("LAPICERO NEGRO X12", "TONER BROTHER TN660")),
    _variant(MIXED, "FEV2203", ANDINA, 22, ("MOUSE OPTICO", "TE VERDE X20", "MANUAL NIIF")),
    _variant(PLAIN, "FEV0871", HARDWARE, 23, ("EXTENSION ELECTRICA 3M", "TOMA DOBLE")),
)
# Quedan por completar (sin centro de costo) y el lote que ya se exporto (prefijo + numero)
INCOMPLETE = {"FEV1011", "SETT3102", "FEV2203"}
EXPORTED = {"FEV1001", "FEV1002", "FE00450"}


# --- semilla --------------------------------------------------------------------------------
def _label(document: ParsedDocument) -> str:
    return f"{document.supplier_prefix}{document.supplier_number}"


def _seed(services: Services, folder: Path) -> int:
    company = services.create_company.execute(*COMPANY)
    assert company.id is not None
    company_id = company.id
    for code, name in PRODUCTS:
        services.save_product.execute(company_id, code, name)
    for code, name in COST_CENTERS:
        services.save_cost_center.execute(company_id, code, name)

    generated = folder / "xml"
    generated.mkdir()
    for variant in VARIANTS:
        (generated / f"{variant.document_id}.xml").write_text(variant.xml(), encoding="utf-8")
    services.import_invoices.execute(company_id, [FIXTURES, generated])

    for (nit, name), (codes, default) in SUPPLIER_PRODUCTS.items():
        services.configure_supplier.execute(company_id, nit, name, list(codes), default)
    pending = services.list_pending.execute(company_id)
    centers = [code for code, _name in COST_CENTERS]
    for position, document in enumerate(pending.documents):
        if _label(document.invoice.document) in INCOMPLETE:
            continue
        services.assign_document_mapping.execute(
            company_id,
            [document.invoice.id],
            cost_center_code=centers[position % len(centers)],
        )

    exported = [
        document.invoice.document.cufe
        for document in pending.documents
        if _label(document.invoice.document) in EXPORTED
    ]
    services.export_batch.execute(
        ExportRequest(
            company_id=company_id,
            cufes=exported,
            destination=folder / "exportados" / "world-office-agosto.xlsx",
            start_numbers={DocumentType.FC: 5731, DocumentType.NC: 210},
        )
    )
    return company_id


# --- captura -------------------------------------------------------------------------------
def _settle(milliseconds: int = 30) -> None:
    QCoreApplication.processEvents()
    QTest.qWait(milliseconds)


def _grab(window: QWidget, dialog: QWidget | None = None) -> QPixmap:
    _settle()
    shot = window.grab()
    if dialog is None:
        return shot
    sheet = dialog.grab()
    x = (shot.width() - sheet.width()) // 2
    y = max(24, (shot.height() - sheet.height()) // 3)
    painter = QPainter(shot)
    # Un velo leve marca que la hoja es modal; la sombra la separa de la ventana
    painter.fillRect(shot.rect(), QColor(11, 31, 69, 40))
    shadow = QRect(x, y + 6, sheet.width(), sheet.height())
    for spread, alpha in ((14, 8), (9, 12), (5, 18)):
        grown = shadow.adjusted(-spread, -spread, spread, spread)
        painter.fillRect(grown, QColor(11, 31, 69, alpha))
    painter.drawPixmap(x, y, sheet)
    painter.end()
    return shot


@dataclass
class _Shots:
    folder: Path
    written: list[Path] = field(default_factory=list)

    def save(self, name: str, pixmap: QPixmap) -> None:
        path = self.folder / f"{name}.png"
        if not pixmap.save(str(path)):
            raise OSError(f"could not write {path}")
        self.written.append(path)


def _window(services: Services, settings_path: Path, size: tuple[int, int]) -> MainWindow:
    window = MainWindow(services, SyncTaskRunner(), settings=AppSettings.in_file(settings_path))
    window.resize(*size)
    window.show()
    _settle()
    return window


def _dispose(window: MainWindow) -> None:
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _first_run(shots: _Shots, folder: Path) -> None:
    services = build_services(folder / "primera-vez.db")
    try:
        window = _window(services, folder / "primera-vez.ini", WIDE)
        shots.save("01-first-run", _grab(window))
        company = services.create_company.execute(*COMPANY)
        window.reload_companies(select_id=company.id)
        window.navigate("invoices")
        shots.save("02-invoices-empty", _grab(window))
        _dispose(window)
    finally:
        services.close()


def _invoices(shots: _Shots, window: MainWindow) -> None:
    page = window.invoices_page
    view = page.view
    window.navigate("invoices")
    shots.save("03-invoices-with-data", _grab(window))
    window.resize(*NARROW)
    shots.save("03-invoices-with-data-1024", _grab(window))
    window.resize(*WIDE)
    _settle()

    rows = page.rows()
    _hover_a_row(shots, window, rows[3].invoice_id)
    incomplete = next(row for row in rows if f"{row.prefix}{row.number}" in INCOMPLETE)
    mismatch = next(row for row in rows if row.needs_confirmation)
    for row in (incomplete, mismatch):
        view.tree.expand(view.proxy.mapFromSource(page.model.index_for_invoice(row.invoice_id)))
    view.set_detail_visible(True)
    view.select_invoices([incomplete.invoice_id])
    shots.save("04-invoices-expanded-with-detail-panel", _grab(window))
    view.tree.collapseAll()

    view.select_invoices([row.invoice_id for row in rows[:3]])
    shots.save("05-invoices-bulk-selection", _grab(window))
    view.clear_selection()


def _hover_a_row(shots: _Shots, window: MainWindow, invoice_id: int) -> None:
    """The pointer on a row: its editable cells show their chevron, the rest of the table
    stays quiet (the amber "Elegir…" cells always show it)."""
    page = window.invoices_page
    view = page.view
    view.tree.setCurrentIndex(QModelIndex())  # sin fila actual: solo la que toca el puntero
    row = view.proxy.mapFromSource(page.model.index_for_invoice(invoice_id))
    cell = view.tree.visualRect(row.siblingAtColumn(Column.PRODUCT))
    QTest.mouseMove(view.tree.viewport(), cell.center())
    _settle()
    shots.save("03b-invoices-hover-affordance", _grab(window))
    QApplication.sendEvent(view.tree.viewport(), QEvent(QEvent.Type.Leave))


def _sheets(shots: _Shots, window: MainWindow, folder: Path) -> None:
    view = window.invoices_page.view
    view.banner.action_button.click()
    wizard = window.suppliers_page.wizard
    if wizard is None:
        raise RuntimeError("the supplier wizard did not open")
    shots.save("06-supplier-wizard", _grab(window, wizard))
    wizard.reject()
    _settle()

    view.readiness.cta_button.click()
    sheet = window.export_sheet.sheet
    if sheet is None:
        raise RuntimeError("the export sheet did not open")
    shots.save("07-export-sheet", _grab(window, sheet))
    sheet.set_destination(folder / "exportados" / "world-office-septiembre.xlsx")
    if not sheet.mismatch_notice.isHidden():
        # La casilla es opcional: marcarla suma la factura con descuadre a las cuentas
        sheet.mismatch_notice.checkbox.click()
        _settle()
        shots.save("07b-export-sheet-with-mismatch", _grab(window, sheet))
    sheet.primary_button.click()
    _settle()
    shots.save("08-export-success", _grab(window, sheet))
    sheet.primary_button.click()  # Listo
    _settle()


def _clear_toasts(window: MainWindow) -> None:
    """The success toast of the export would cover the actions at the bottom right."""
    window.toasts.dismiss_all()
    QTest.qWait(Toast.FADE_MS + 100)


def _pages(shots: _Shots, window: MainWindow) -> None:
    _clear_toasts(window)
    for number, key in ((9, "suppliers"), (10, "catalogs"), (11, "batches"), (12, "company")):
        window.navigate(key)
        shots.save(f"{number:02d}-{key}", _grab(window))
    window.show_shortcuts()
    dialog = window.shortcuts_dialog
    if dialog is None:
        raise RuntimeError("the shortcuts dialog did not open")
    shots.save("13-shortcuts", _grab(window, dialog))
    dialog.reject()
    _settle()


def _with_data(shots: _Shots, folder: Path) -> None:
    services = build_services(folder / "datos.db")
    try:
        _seed(services, folder)
        window = _window(services, folder / "datos.ini", WIDE)
        _invoices(shots, window)
        _sheets(shots, window, folder)
        _pages(shots, window)
        _dispose(window)
    finally:
        services.close()


def render(out: Path) -> list[Path]:
    """Writes every screenshot into ``out`` (created when missing) and returns the files."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    previous = (app.styleSheet(), app.style().name(), app.palette(), app.font())
    bootstrap(app)
    out.mkdir(parents=True, exist_ok=True)
    shots = _Shots(out)
    try:
        with tempfile.TemporaryDirectory(prefix="contabilizador-shots-") as temporary:
            folder = Path(temporary)
            _first_run(shots, folder)
            _with_data(shots, folder)
    finally:
        # Quien llamo (por ejemplo las pruebas) recupera su aspecto
        sheet, style, palette, font = previous
        app.setStyleSheet(sheet)
        app.setStyle(style)
        app.setPalette(palette)
        app.setFont(font)
    return shots.written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--out", type=Path, required=True, help="folder for the PNG files")
    arguments = parser.parse_args(argv)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    written = render(arguments.out)
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
