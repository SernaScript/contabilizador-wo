"""Copy of the Facturas page: import, document tree, detail panel, bulk bar."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contabilizador.shared.strings import common

if TYPE_CHECKING:
    from collections.abc import Sequence

ACTION_IMPORT = "Importar"
ACTION_IMPORT_FILES_MENU = "Archivos XML o zip…"
ACTION_IMPORT_FOLDER_MENU = "Carpeta…"
ACTION_APPLY = "Aplicar"
ACTION_RESTORE_SUGGESTION = "Restablecer sugerencia"
ACTION_CHOOSE_ANOTHER = "Elegir otro"
ACTION_SHOW_XML = "Mostrar XML en carpeta"
ACTION_COPY_CUFE = "Copiar CUFE"

INVOICES_PAGE_TITLE = "Facturas"
STEP_IMPORT = "Importar"
STEP_COMPLETE = "Completar"
STEP_EXPORT = "Exportar"

# --- Importacion / grilla --------------------------------------------------
EMPTY_INVOICES_TITLE = "Aún no hay facturas"
EMPTY_INVOICES_TEXT = "Arrastra aquí los XML de la DIAN o elige los archivos para importarlos."
COLUMN_NIT = "NIT"
COLUMN_SUPPLIER = "Proveedor"
COLUMN_DOCUMENT = "Documento"
COLUMN_ISSUE_DATE = "Fecha"
COLUMN_DUE_DATE = "Vencimiento"
COLUMN_QUANTITY = "Cantidad"
COLUMN_PRODUCT = "Producto"
COLUMN_COST_CENTER = "Centro de costo"
COLUMN_TOTAL = "Total"
COLUMN_STATUS = "Estado"
LABEL_BULK_PRODUCT = "Producto"
LABEL_BULK_COST_CENTER = "Centro de costo"
PLACEHOLDER_NO_CHANGE = "(sin cambio)"
PLACEHOLDER_NONE = "(ninguno)"
FLAG_UNCONFIGURED_SUPPLIER = "Proveedor sin configurar"
FLAG_TOTALS_MISMATCH = "Los totales de las líneas no coinciden con el total del XML"
FLAG_CREDIT_NOTE = "Nota crédito"
FLAG_INVOICE = "Factura"
UNCONFIGURED_SUPPLIER_SINGULAR = "proveedor sin configurar"
UNCONFIGURED_SUPPLIER_PLURAL = "proveedores sin configurar"
FILE_DIALOG_XML_FILTER = "Documentos DIAN (*.xml *.zip);;Todos los archivos (*)"
FILE_DIALOG_IMPORT_TITLE = "Elegir archivos XML o zip"
FILE_DIALOG_FOLDER_TITLE = "Elegir carpeta con XML"
IMPORT_PROGRESS = "Importando facturas…"
IMPORT_CANCELLED = "Importación cancelada. No se guardó ninguna factura."
IMPORT_REPORT_TITLE = "Detalle de la importación"
IMPORT_REPORT_IGNORED = "Archivos ignorados"
IMPORT_REPORT_FAILED = "Archivos con error"
IMPORT_REPORT_ORPHANS = "Notas crédito sin factura original"

# --- Filtros ---------------------------------------------------------------
FILTER_READY = "Listas"
FILTER_INCOMPLETE = "Por completar"
FILTER_UNCONFIGURED = "Proveedor sin configurar"
FILTER_MISMATCH = "Descuadre"
FILTER_SUGGESTED = "Con sugerencias"

# --- Panel de detalle ------------------------------------------------------
DETAIL_SUPPLIER = "Proveedor"
DETAIL_SUPPLIER_CONFIGURED = "Configurado"
DETAIL_SUPPLIER_UNCONFIGURED = "Sin configurar"
DETAIL_CUFE = "CUFE"
DETAIL_ASSIGNMENT = "Asignación"
DETAIL_DATES = "Fechas"
DETAIL_TOTALS = "Totales"
DETAIL_TOTAL_XML = "Total del XML"
DETAIL_TOTAL_COMPUTED = "Total calculado"
DETAIL_DIFFERENCE = "Diferencia"
DETAIL_ORIGINAL_FOUND = "Factura original encontrada"
DETAIL_ORIGINAL_MISSING = "Factura original no encontrada"
DETAIL_PROBLEMS = "Pendientes"
DETAIL_NO_PROBLEMS = "Todo listo para exportar"
ACTION_CONFIGURE_SUPPLIER = "Configurar proveedor"
ACTION_TOGGLE_DETAIL = "Mostrar u ocultar el detalle"
DETAIL_EMPTY = "Selecciona una factura para ver su detalle."
DETAIL_MISMATCH_NOTE = "Se exporta solo si confirmas el descuadre."

# --- Celdas editables ------------------------------------------------------
HINT_CLICK_TO_CHANGE = "Haz clic para cambiar"
HINT_CLICK_TO_CHOOSE = "Haz clic para elegir"

# --- Barra contextual ------------------------------------------------------
PROVENANCE_MEMORY = "Sugerido por facturas anteriores"
PROVENANCE_SUPPLIER_DEFAULT = "Producto por defecto del proveedor"
PROVENANCE_MANUAL = "Asignado a mano"

# --- Arbol de documentos ---------------------------------------------------
ACTION_EXPAND_ALL = "Expandir todo"
ACTION_COLLAPSE_ALL = "Contraer todo"
NO_RESULTS = "Ninguna factura coincide con la búsqueda o el filtro."
CATALOG_EMPTY_PRODUCTS = "No hay productos en el catálogo."
CATALOG_EMPTY_COST_CENTERS = "No hay centros de costo en el catálogo."
ACTION_GO_TO_CATALOGS = "Ir a catálogos"
FILE_NOT_FOUND_TOAST = "El archivo XML ya no está donde se importó."
INVOICE_NOT_FOUND_TITLE = "La factura ya no está en la lista"
INVOICE_NOT_FOUND_HINT = "Se actualizó la lista. Revisa y vuelve a intentarlo."
IMPORT_REPORT_DUPLICATES = "Facturas que ya existían"
IMPORT_REPORT_EMPTY = "Todos los archivos se importaron sin novedades."

# Etiqueta corta de la pastilla por problema principal (clave = ProblemKind.value)
PILL_LABELS = {
    "already_exported": "Ya exportada",
    "document_not_found": "No encontrada",
    "unconfigured_supplier": FLAG_UNCONFIGURED_SUPPLIER,
    "unknown_product": "Producto inexistente",
    "unknown_cost_center": "Centro inexistente",
    "missing_product": "Falta producto",
    "missing_cost_center": "Falta centro de costo",
}

# Frases del detalle por problema (clave = ProblemKind.value)
_LINE_PROBLEM_SENTENCES = {
    "missing_product": "falta el producto",
    "missing_cost_center": "falta el centro de costo",
    "unknown_product": "el producto {detail} ya no existe en el catálogo",
    "unknown_cost_center": "el centro de costo {detail} ya no existe en el catálogo",
}
_DOCUMENT_PROBLEM_SENTENCES = {
    "unconfigured_supplier": "El proveedor no está configurado.",
    "already_exported": "Ya fue exportada. Actualiza la lista.",
    "document_not_found": "Ya no está en la lista. Actualiza la lista.",
}


def readiness_pill_text(readiness: str, problem_kind: str | None) -> str:
    """Text of the status pill: the primary problem when there is one, else the state."""
    if readiness in ("blocked", "incomplete") and problem_kind in PILL_LABELS:
        return PILL_LABELS[problem_kind]
    return common.STATUS_LABELS.get(readiness, readiness)


def problem_message(kind: str, line_number: int | None, detail: str) -> str:
    """One sentence per problem, for the checklist of the detail panel."""
    if line_number is not None and kind in _LINE_PROBLEM_SENTENCES:
        return f"Línea {line_number}: {_LINE_PROBLEM_SENTENCES[kind].format(detail=detail)}."
    if kind in _DOCUMENT_PROBLEM_SENTENCES:
        return _DOCUMENT_PROBLEM_SENTENCES[kind]
    return f"{kind}: {detail}" if detail else kind


def document_tooltip(kind_label: str, due_date: str) -> str:
    return f"{kind_label}, vence el {due_date}"


def editable_cell_tooltip(text: str | None, *, empty: bool = False) -> str:
    """Tooltip of a product / cost center cell: what it holds and that a click changes it."""
    hint = HINT_CLICK_TO_CHOOSE if empty else HINT_CLICK_TO_CHANGE
    return f"{text}\n{hint}" if text else hint


def line_values_sentence(quantity: str, unit_value: str, tax_percent: str) -> str:
    return f"{quantity} a {unit_value}, IVA {tax_percent}"


def various_values_tooltip(values: Sequence[str]) -> str:
    return "Las líneas tienen valores distintos: " + ", ".join(values) + "."


def invoices_updated(count: int) -> str:
    return f"{count} {'factura actualizada' if count == 1 else 'facturas actualizadas'}"


def orphan_credit_note_detail(label: str, reference: str) -> str:
    return f"{label}: la factura original {reference[:12]}… no está importada."


def duplicate_detail(label: str, supplier: str) -> str:
    return f"{label} de {supplier} ya existía."


def unconfigured_suppliers_banner(count: int, blocked: int) -> str:
    """The fact and its consequence: ``blocked`` is how many invoices those suppliers hold."""
    label = UNCONFIGURED_SUPPLIER_SINGULAR if count == 1 else UNCONFIGURED_SUPPLIER_PLURAL
    verb = "bloquea" if count == 1 else "bloquean"
    invoices = "factura" if blocked == 1 else "facturas"
    return f"{count} {label} {verb} {blocked} {invoices}."


def totals_mismatch_tooltip(difference: str) -> str:
    return f"{FLAG_TOTALS_MISMATCH} (diferencia: {difference})"


def import_result_sentence(imported: int, duplicates: int, ignored: int, failed: int) -> str:
    """Toast copy: one sentence per fact, no meta separators."""
    sentences = [f"{imported} {'factura importada' if imported == 1 else 'facturas importadas'}."]
    if duplicates:
        sentences.append(f"{duplicates} ya {'existía' if duplicates == 1 else 'existían'}.")
    if ignored:
        sentences.append(
            f"{ignored} {'archivo no es' if ignored == 1 else 'archivos no son'} una factura DIAN."
        )
    if failed:
        sentences.append(
            f"{failed} {'archivo no se pudo' if failed == 1 else 'archivos no se pudieron'} leer."
        )
    return " ".join(sentences)


def selected_invoices(count: int) -> str:
    return f"{count} {'factura seleccionada' if count == 1 else 'facturas seleccionadas'}"


def lines_count(count: int) -> str:
    return f"{count} {'línea' if count == 1 else 'líneas'}"


def line_label(number: int) -> str:
    """Name of a line row in the Documento column (its description has the wide column)."""
    return f"Línea {number}"


def supplier_tooltip(name: str, nit: str) -> str:
    """Full name (the cell elides it) and NIT of the supplier of an invoice row."""
    return f"{name}\nNIT {nit}"
