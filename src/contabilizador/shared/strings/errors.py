"""Copy of error dialogs: what happened plus how to fix it, never raw English.

Documents are never named by their CUFE here: without labels at hand the copy counts them.
"""

from __future__ import annotations

from collections.abc import Sequence

ERROR_GENERIC_TITLE = "Algo no salió como se esperaba"
ERROR_GENERIC_MESSAGE = "La acción no se completó."
ERROR_GENERIC_HINT = "Inténtalo de nuevo. Si vuelve a pasar, copia los detalles técnicos."
ERROR_FILE_LOCKED_TITLE = "No se pudo guardar el archivo"
ERROR_FILE_LOCKED_MESSAGE = "El archivo está en uso o la carpeta no permite escribir."
ERROR_FILE_LOCKED_HINT = "Cierra el archivo en Excel e inténtalo de nuevo."
ERROR_FILE_READ_TITLE = "No se pudo leer el archivo"
ERROR_FILE_READ_MESSAGE = "El archivo no existe o no se tiene permiso para abrirlo."
ERROR_FILE_READ_HINT = "Comprueba que el archivo sigue en su carpeta e inténtalo de nuevo."
ERROR_FILE_NOT_FOUND_MESSAGE = "El archivo ya no está donde se esperaba."
ERROR_EXPORT_BLOCKED_TITLE = "No se puede exportar"
ERROR_EXPORT_BLOCKED_MESSAGE = "Algunas facturas no están listas."
ERROR_EXPORT_BLOCKED_HINT = "Completa los pendientes marcados en cada factura y vuelve a exportar."
ERROR_EXPORT_COLLISION_TITLE = "Los consecutivos se cruzan con un lote anterior"
ERROR_EXPORT_COLLISION_HINT = (
    "Cambia el consecutivo inicial para que empiece después del último lote."
)
ERROR_EXPORT_TOTALS_TITLE = "Totales que no coinciden"
ERROR_EXPORT_TOTALS_HINT = "Revisa cada factura con descuadre y confirma la exportación."
ERROR_NOTHING_TO_EXPORT_TITLE = "Nada para exportar"
ERROR_NOTHING_TO_EXPORT_MESSAGE = "No se seleccionó ninguna factura lista."
ERROR_NOTHING_TO_EXPORT_HINT = "Elige facturas con estado Lista e inténtalo de nuevo."
ERROR_COMPANY_NOT_FOUND_TITLE = "La empresa ya no existe"
ERROR_COMPANY_NOT_FOUND_HINT = "Elige otra empresa o crea una nueva."
ERROR_BATCH_NOT_FOUND_TITLE = "El lote ya no existe"
ERROR_BATCH_NOT_FOUND_HINT = "Actualiza la lista de lotes."
ERROR_BATCH_VOIDED_TITLE = "El lote ya está anulado"
ERROR_BATCH_VOIDED_HINT = "No hay nada más que hacer con este lote."
ERROR_DOCUMENT_NOT_IN_BATCH_TITLE = "El documento no pertenece al lote"
ERROR_DOCUMENT_RELEASED_TITLE = "El documento ya estaba liberado"
ERROR_DOCUMENT_RELEASED_HINT = "Actualiza la lista para ver el estado actual."
ERROR_DOCUMENT_NOT_EDITABLE_TITLE = "La factura ya fue exportada"
ERROR_DOCUMENT_NOT_EDITABLE_HINT = "Libera la factura desde Lotes exportados para editarla."
ERROR_LINE_NOT_FOUND_TITLE = "La línea ya no existe"
ERROR_LINE_NOT_FOUND_HINT = "Actualiza la lista de facturas."
ERROR_INVALID_DOCUMENT_TITLE = "El archivo no es una factura DIAN válida"
ERROR_INVALID_DOCUMENT_HINT = "Comprueba que el XML venga de la DIAN sin modificaciones."
ERROR_UNSUPPORTED_DOCUMENT_TITLE = "Tipo de documento no soportado"
ERROR_UNSUPPORTED_DOCUMENT_HINT = "Solo se importan facturas de venta y notas crédito."
ERROR_CATALOG_UNREADABLE_TITLE = "No se pudo leer el catálogo"
ERROR_CATALOG_UNREADABLE_HINT = (
    "Guárdalo como libro de Excel (.xlsx) con código en la columna A y nombre en la B."
)
ERROR_DUPLICATE_COMPANY_TITLE = "Ya existe una empresa con ese nombre"
ERROR_DUPLICATE_COMPANY_HINT = "Usa otro nombre o edita la empresa existente."
ERROR_IMPORT_CANCELLED_TITLE = "Importación cancelada"
ERROR_IMPORT_CANCELLED_MESSAGE = "No se guardó ninguna factura."
ERROR_TASK_CANCELLED_TITLE = "Tarea cancelada"
ERROR_TASK_CANCELLED_MESSAGE = "La tarea se canceló antes de empezar."


def _join(items: Sequence[str]) -> str:
    """``a``, ``a y b``, ``a, b y c``."""
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} y {items[-1]}"


def company_name_taken(name: str) -> str:
    return f"Ya existe una empresa llamada «{name}»."


def export_blocked_message(documents: int, reasons: Sequence[str]) -> str:
    """Why an export was refused when the documents have no labels at hand."""
    if documents == 1:
        subject = "1 factura no está lista"
    else:
        subject = f"{documents} facturas no están listas"
    return f"{subject}: {_join(reasons)}." if reasons else f"{subject}."


def totals_mismatch_count(count: int) -> str:
    if count == 1:
        return "1 factura tiene un total que no coincide con el del XML."
    return f"{count} facturas tienen un total que no coincide con el del XML."


def documents_not_in_batch(count: int) -> str:
    if count == 1:
        return "1 factura no pertenece a este lote."
    return f"{count} facturas no pertenecen a este lote."


def documents_already_released(count: int) -> str:
    if count == 1:
        return "1 factura ya estaba liberada."
    return f"{count} facturas ya estaban liberadas."
