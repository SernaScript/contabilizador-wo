"""Copy of the Lotes exportados page."""

from collections.abc import (
    Sequence as _Sequence,
)  # privado: el paquete reexporta los nombres publicos

# --- Acciones y cabecera -----------------------------------------------------
ACTION_VOID_BATCH = "Anular lote"
ACTION_RELEASE_SELECTED_INVOICES = "Liberar facturas seleccionadas"
ACTION_RELEASE_INVOICES = "Liberar facturas"
ACTION_SHOW_BATCH_FILE = "Mostrar archivo"
BATCH_ACTION_SEE_INVOICES = "Ver facturas"
BATCH_ACTION_GO_TO_INVOICES = "Ir a Facturas"
BATCHES_PAGE_TITLE = "Lotes exportados"
BATCHES_PAGE_PURPOSE = "Cada exportación queda registrada con sus consecutivos."

# --- Tablas -----------------------------------------------------------------
COLUMN_BATCH_ID = "Lote"
COLUMN_BATCH_DATE = "Fecha"
COLUMN_BATCH_RANGES = "Consecutivos"
COLUMN_BATCH_STATUS = "Estado"
COLUMN_BATCH_DOCUMENTS = "Facturas"
COLUMN_BATCH_CONSECUTIVE = "Consecutivo"
COLUMN_BATCH_DOCUMENT = "Documento"

# --- Estados (siempre icono + texto) ----------------------------------------
BATCH_STATUS_EXPORTED = "Exportado"
BATCH_STATUS_VOIDED = "Anulado"
BATCH_STATUS_VOIDED_REUSED = "Anulado (consecutivos devueltos)"
BATCH_STATUS_VOIDED_RETURNED = "Anulado con consecutivos devueltos"
BATCH_STATUS_PARTIAL = "Parcial"
BATCH_DOCUMENT_RELEASED = "Liberada"
BATCH_EXPORTED_TOOLTIP = "Todas las facturas del lote siguen exportadas."
BATCH_VOIDED_RETURNED_TOOLTIP = "El lote se anuló y sus consecutivos quedaron disponibles otra vez."
BATCH_VOIDED_KEPT_TOOLTIP = "El lote se anuló, pero sus consecutivos siguen usados."

# --- Estados vacíos y avisos --------------------------------------------------
NO_BATCHES_HINT = "Aún no hay lotes exportados."
EMPTY_BATCHES_TITLE = "Aún no hay lotes exportados"
EMPTY_BATCHES_TEXT = "Cuando exportes facturas, cada lote aparecerá aquí con sus consecutivos."
BATCH_DETAIL_PLACEHOLDER = "Elige un lote para ver sus facturas."
BATCH_NO_COMPANY_TITLE = "Elige una empresa"
BATCH_NO_COMPANY_TEXT = "Los lotes exportados son propios de cada empresa."
BATCH_FILE_MISSING = "No se encontró el archivo. Puede que lo hayas movido o eliminado."
BATCH_VOID_DISABLED_HINT = "Este lote ya está anulado."
BATCH_RELEASE_DISABLED_NOTHING = "Selecciona las facturas que quieres liberar."
BATCH_RELEASE_DISABLED_VOIDED = "Las facturas de un lote anulado ya están liberadas."

# --- Confirmaciones -----------------------------------------------------------
CONFIRM_VOID_BATCH = (
    "Se liberarán todos los documentos del lote. Los consecutivos solo se devuelven si es "
    "el último lote. ¿Continuar?"
)
CONFIRM_RELEASE_DOCUMENTS = (
    "Los documentos seleccionados volverán a estar pendientes; sus consecutivos quedan usados. "
    "¿Continuar?"
)
CONFIRM_RELEASE_NOTE = "Sus consecutivos quedan usados y no se pueden reutilizar."
BATCH_ALREADY_VOIDED = "El lote ya está anulado."


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def batch_title(batch_id: int) -> str:
    return f"Lote {batch_id}"


def batch_documents_count(invoices: int, credit_notes: int) -> str:
    parts = []
    if invoices:
        parts.append(f"{invoices} {_plural(invoices, 'factura', 'facturas')}")
    if credit_notes:
        parts.append(f"{credit_notes} {_plural(credit_notes, 'nota crédito', 'notas crédito')}")
    return " y ".join(parts)


def batch_summary(
    date_text: str,
    time_text: str,
    invoices: int,
    credit_notes: int,
    *,
    released: int = 0,
    total: int = 0,
) -> str:
    counts = batch_documents_count(invoices, credit_notes)
    summary = f"Exportado el {date_text} a las {time_text}. Incluye {counts}."
    if released:
        summary += f" {batch_released_summary(released, total)}."
    return summary


def batch_ranges_sentence(parts: _Sequence[str]) -> str:
    """``A``, ``A y B`` or ``A, B y C``."""
    if len(parts) < 2:
        return "".join(parts)
    return f"{', '.join(parts[:-1])} y {parts[-1]}"


def batch_released_summary(released: int, total: int) -> str:
    return f"{released} de {total} {_plural(total, 'factura liberada', 'facturas liberadas')}"


def batch_partial_tooltip(released: int, total: int) -> str:
    return f"{batch_released_summary(released, total)}; las demás siguen exportadas."


def confirm_void_title(batch_id: int) -> str:
    return f"¿Anular el lote {batch_id}?"


def confirm_void_documents(count: int) -> str:
    if count == 0:
        return "Todas las facturas del lote ya estaban liberadas."
    if count == 1:
        return "La factura del lote volverá a estar pendiente."
    return f"Las {count} facturas del lote volverán a estar pendientes."


def confirm_void_returns(ranges: str, numbers: int) -> str:
    """The consecutives of the voided batch go back to the pool."""
    if numbers == 1:
        return f"El consecutivo {ranges} quedará disponible otra vez."
    return f"Los consecutivos {ranges} quedarán disponibles otra vez."


def confirm_void_keeps(ranges: str, numbers: int, later_batch_id: int) -> str:
    """A later batch holds consecutives, so these stay burned."""
    reason = f"porque el lote {later_batch_id} es posterior"
    if numbers == 1:
        return f"El consecutivo {ranges} queda usado {reason}."
    return f"Los consecutivos {ranges} quedan usados {reason}."


def confirm_release_title(count: int) -> str:
    return f"¿Liberar {count} {_plural(count, 'factura', 'facturas')}?"


def confirm_release_message(count: int) -> str:
    if count == 1:
        return "La factura volverá a estar pendiente en Facturas."
    return f"Las {count} facturas volverán a estar pendientes en Facturas."


def batch_voided(batch_id: int, *, returned: bool) -> str:
    consecutives = "están disponibles otra vez" if returned else "quedan usados"
    return f"Lote {batch_id} anulado. Los consecutivos {consecutives}."


def documents_released(count: int) -> str:
    return f"{count} {_plural(count, 'factura liberada', 'facturas liberadas')}"


def release_selection_caption(count: int) -> str:
    if count == 0:
        return BATCH_RELEASE_DISABLED_NOTHING
    return f"{count} {_plural(count, 'factura seleccionada', 'facturas seleccionadas')}"
