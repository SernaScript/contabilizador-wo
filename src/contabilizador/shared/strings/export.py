"""Copy of the export sheet and the readiness footer."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from contabilizador.exports.domain.errors import (
        ExportProblem,
    )

ACTION_EXPORT_SHORT = "Exportar"
EXPORT_DIALOG_TITLE = "Exportar a World Office"
EXPORT_SHEET_SUBTITLE = "Se genera un libro de Excel listo para importar en World Office."
EXPORT_DESTINATION = "Archivo de salida"
EXPORT_START_NUMBER = "Consecutivo inicial"
EXPORT_RANGE_PREVIEW = "Se usarán"
EXPORT_CONFIRM_MISMATCH = "Exportar también las facturas con descuadre"
EXPORT_CONFIRM_MISMATCH_ONE = "Exportar también la factura con descuadre"
EXPORT_NOTHING_READY = "Ninguna factura está lista para exportar."
EXPORT_COLLISION_TITLE = "Los consecutivos se cruzan con un lote anterior"
DOCUMENT_TYPE_LABELS = {"FC": "Facturas de compra (FC)", "NC": "Notas crédito (NC)"}
# Un nombre por estado: la leyenda, los chips y el motivo del boton deshabilitado lo comparten
READINESS_LEGEND = {
    "ready": "listas",
    "incomplete": "por completar",
    "blocked": "con proveedor sin configurar",
    "mismatch": "con descuadre",
}
READINESS_BLOCKED_ANY = "bloqueadas"


def readiness_legend(status: str, count: int, *, by_supplier: bool = True) -> str:
    """Legend entry of the footer: "8 listas", "1 lista", "3 por completar".

    The blocked ones name their supplier. When one of them is blocked by something else (a
    code that left the catalog) ``by_supplier=False`` says only "bloqueadas": the legend
    never blames a supplier for what it did not do.
    """
    if status == "blocked" and not by_supplier:
        label = "bloqueada" if count == 1 else READINESS_BLOCKED_ANY
    elif status == "ready" and count == 1:
        label = "lista"
    else:
        label = READINESS_LEGEND[status]
    return f"{count} {label}"


def export_default_filename(moment: datetime) -> str:
    # Con fecha y hora: aceptar el nombre sugerido nunca sobrescribe un lote anterior
    return f"world-office-compras-{moment:%Y%m%d-%H%M%S}.xlsx"


# --- Pie de preparacion (pagina Facturas) --------------------------------------


def export_cta(count: int) -> str:
    """Sin nada que exportar el boton dice solo la accion: "Exportar 0 facturas" es un
    numero que nadie puede usar (el boton va deshabilitado y su motivo se lee en el pie)."""
    if count == 0:
        return ACTION_EXPORT_SHORT
    return f"{ACTION_EXPORT_SHORT} {count} {'factura' if count == 1 else 'facturas'}"


def export_selected_cta(count: int) -> str:
    """Como ``export_cta``: sin ninguna lista en la seleccion el boton dice solo la accion."""
    if count == 0:
        return ACTION_EXPORT_SHORT
    return f"{ACTION_EXPORT_SHORT} {count} {'seleccionada' if count == 1 else 'seleccionadas'}"


def readiness_caption(exportable: int, total: int) -> str:
    """Una sola palabra para "se puede exportar": listas y con descuadre cuentan igual
    (las leyendas de la barra las separan)."""
    if total == 0:
        return "Sin facturas pendientes"
    if exportable == 0:
        if total == 1:
            return "La factura todavía no se puede exportar"
        return f"Ninguna de las {total} facturas se puede exportar todavía"
    noun = "factura" if total == 1 else "facturas"
    verb = "se puede" if exportable == 1 else "se pueden"
    return f"{exportable} de {total} {noun} {verb} exportar"


def selection_caption(selected: int, exportable: int) -> str:
    """Pie con una seleccion activa: cuantas hay y cuantas de ellas saldrian."""
    head = f"{selected} {'seleccionada' if selected == 1 else 'seleccionadas'}"
    if selected == 1:
        return f"{head}, se puede exportar"
    verb = "se puede" if exportable == 1 else "se pueden"
    return f"{head}, {exportable} {verb} exportar"


def mismatch_needs_confirmation(count: int) -> str:
    if count == 1:
        return "1 con descuadre requiere confirmación"
    return f"{count} con descuadre requieren confirmación"


def export_disabled_reason(blocked: int, incomplete: int, *, by_supplier: bool = True) -> str:
    """Why the button is off, in the same words as the legend (one name per state)."""
    if blocked == 0 and incomplete == 0:
        return "No hay facturas listas para exportar."
    parts = []
    if incomplete:
        parts.append(readiness_legend("incomplete", incomplete))
    if blocked:
        parts.append(readiness_legend("blocked", blocked, by_supplier=by_supplier))
    return "Completa las facturas pendientes para exportar: " + " y ".join(parts) + "."


def invoices_exported(count: int) -> str:
    return f"{count} {'factura exportada' if count == 1 else 'facturas exportadas'}"


# --- Hoja de exportacion -------------------------------------------------------
# Las facturas se nombran por su etiqueta (FPI-5731 · Proveedor), nunca por su CUFE.
EXPORT_COLUMN_TYPE = "Documento"
EXPORT_COLUMN_COUNT = "Cantidad"
EXPORT_NEEDS_DESTINATION = "Elige dónde guardar el archivo."
# Las facturas con descuadre son opcionales: sin la casilla, el lote sale sin ellas. Este es
# el unico caso en que la casilla es lo que falta para poder exportar.
EXPORT_ONLY_MISMATCHED = "Solo hay facturas con descuadre. Marca la casilla para exportarlas."
EXPORT_CONFIRM_COLLISION = "Usar estos consecutivos aunque se crucen"
EXPORT_NEEDS_COLLISION_CONFIRMATION = (
    "Cambia el consecutivo inicial o confirma que quieres usarlo aunque se cruce."
)
# Una factura pedida que ya no esta guardada
EXPORT_UNKNOWN_DOCUMENT = "Factura que ya no está en la lista"
EXPORT_DOCUMENT_GONE = "Una de las facturas ya no está guardada."
EXPORT_SUCCESS_NEXT_STEP = "Ya puedes importarlo en World Office."
EXPORT_OPEN_FILE_FAILED = "No se pudo abrir el archivo. Ábrelo desde Mostrar en carpeta."
EXPORT_OPEN_FOLDER_FAILED = "No se pudo abrir la carpeta. Búscala en la ruta que aparece arriba."
EXPORT_FILE_DIALOG_TITLE = "Guardar el archivo para World Office"
EXPORT_FILE_FILTER = "Libros de Excel (*.xlsx)"


def export_skipped(count: int) -> str:
    if count == 1:
        return "1 factura no está lista y queda pendiente."
    return f"{count} facturas no están listas y quedan pendientes."


def mismatch_title(count: int) -> str:
    if count == 1:
        return "1 factura tiene descuadre"
    return f"{count} facturas tienen descuadre"


def mismatch_explanation(count: int) -> str:
    """Why they are listed and what happens when the box stays unchecked."""
    if count == 1:
        left_out = "Queda fuera del lote si no la incluyes."
    else:
        left_out = "Quedan fuera del lote si no las incluyes."
    return f"El total de sus líneas no coincide con el total del XML. {left_out}"


def export_include_mismatch(count: int) -> str:
    return EXPORT_CONFIRM_MISMATCH_ONE if count == 1 else EXPORT_CONFIRM_MISMATCH


def mismatch_item(label: str, amount: str, *, lines_exceed: bool) -> str:
    """``amount`` already formatted as money (always positive)."""
    direction = "más" if lines_exceed else "menos"
    return f"{label}: las líneas suman {amount} {direction} que el XML."


def more_items(count: int) -> str:
    return f"Y {count} más."


def collision_sentence(proposed: str, batch_id: int, existing: str) -> str:
    """``proposed`` / ``existing``: ranges already written as ``FC 5731 a 5748``."""
    return f"{proposed} se cruza con el lote {batch_id}, que ya usó {existing}."


def collision_fix(starts: Sequence[int]) -> str:
    if len(starts) == 1:
        return f"Empezar en {starts[0]}"
    return "Usar consecutivos libres"


def document_problem(label: str, problem: ExportProblem) -> str:
    """Why one document blocks the export, named by its label."""
    line = problem.line_number
    match problem.kind.value:
        case "document_not_found":
            return EXPORT_DOCUMENT_GONE
        case "already_exported":
            return f"{label}: ya se exportó en otro lote."
        case "unconfigured_supplier":
            return f"{label}: el proveedor no está configurado."
        case "missing_product":
            return f"{label}: falta el producto en la línea {line}."
        case "missing_cost_center":
            return f"{label}: falta el centro de costo en la línea {line}."
        case "unknown_product":
            return (
                f"{label}: el producto {problem.detail} de la línea {line} ya no está en el "
                "catálogo."
            )
        case "unknown_cost_center":
            return (
                f"{label}: el centro de costo {problem.detail} de la línea {line} ya no está "
                "en el catálogo."
            )
        case other:
            return f"{label}: {problem_kind_message(other)}."


def exporting(count: int) -> str:
    return f"Exportando {count} {'factura' if count == 1 else 'facturas'}…"


def export_saved_in(file_name: str, folder: str) -> str:
    return f"Se guardó {file_name} en {folder}."


def export_ranges_used(ranges: Sequence[str]) -> str:
    """``ranges`` already written as ``FC 5731 a 5748``."""
    listed = ranges[0] if len(ranges) == 1 else f"{', '.join(ranges[:-1])} y {ranges[-1]}"
    return f"Consecutivos usados: {listed}."


# --- Problemas por tipo ---------------------------------------------------------
# Sin nombrar el documento: quien conoce la etiqueta (la hoja de exportacion) la agrega.

_PROBLEM_MESSAGES = {
    "document_not_found": "documento no encontrado",
    "already_exported": "ya fue exportado",
    "unconfigured_supplier": "proveedor sin configurar",
    "missing_product": "falta el producto",
    "missing_cost_center": "falta el centro de costo",
    "unknown_cost_center": "centro de costo inexistente",
    "unknown_product": "producto inexistente en el catálogo",
}


def problem_kind_message(kind: str) -> str:
    return _PROBLEM_MESSAGES.get(kind, kind)


def export_problem_message(problem: ExportProblem) -> str:
    """One problem as a sentence, never with the CUFE: ``Línea 2: falta el producto.``"""
    where = f"Línea {problem.line_number}: " if problem.line_number is not None else ""
    detail = f" ({problem.detail})" if problem.detail else ""
    sentence = f"{where}{problem_kind_message(problem.kind.value)}{detail}"
    return f"{sentence[:1].upper()}{sentence[1:]}."
