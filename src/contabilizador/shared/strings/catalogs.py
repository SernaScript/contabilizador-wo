"""Copy of the Catálogos page (products and cost centers).

Functions take the catalog kind as its string value (``"product"`` / ``"cost_center"``,
the values of ``CatalogKind``) so this module never imports from the application layer.
"""

from collections.abc import (
    Sequence as _Sequence,
)  # privado: el paquete reexporta los nombres publicos

# --- Cabecera y barra de herramientas ---------------------------------------
ACTION_IMPORT_EXCEL = "Importar desde Excel"
ACTION_DOWNLOAD_TEMPLATE = "Descargar plantilla"
CATALOGS_PAGE_TITLE = "Catálogos"
CATALOGS_PAGE_PURPOSE = "Productos y centros de costo tal como existen en World Office."
CATALOG_PRODUCTS = "Productos"
CATALOG_COST_CENTERS = "Centros de costo"
CATALOG_SEARCH_PLACEHOLDER = "Buscar por código o nombre"
CATALOG_TEMPLATE_HINT = "Un Excel vacío con los encabezados que espera la importación."
CATALOG_DELETE_DISABLED_HINT = "Selecciona un registro de la lista para eliminarlo."
COLUMN_CODE = "Código"
COLUMN_NAME = "Nombre"

# --- Formulario -------------------------------------------------------------
CATALOG_CODE_REQUIRED = "Escribe el código."
CATALOG_NAME_REQUIRED = "Escribe el nombre."
CATALOG_ENTRY_CODE_HINT = "Tal como aparece en World Office. No se podrá cambiar después."
CATALOG_CODE_IMMUTABLE = "El código no se puede cambiar; crea otro registro si lo necesitas."

# --- Importación y plantilla -------------------------------------------------
CATALOG_IMPORT_HINT = "Primera hoja: fila 1 encabezado, columna A código, columna B nombre."
CATALOG_IMPORT_TITLE = "Importación de catálogo"
CATALOG_IMPORT_INVALID_ROWS = "Filas que no se importaron"
CATALOG_IMPORT_FIX_HINT = (
    "Corrige esas filas en el Excel y vuelve a importarlo. Las filas válidas ya se guardaron."
)
CATALOG_UNREADABLE_FILE = (
    "No se pudo leer el archivo. Guárdalo como libro de Excel (.xlsx) e inténtalo de nuevo."
)
CATALOG_TEMPLATE_SAVED = "Plantilla guardada"
CATALOG_TEMPLATE_DIALOG_TITLE = "Guardar plantilla de Excel"
FILE_DIALOG_EXCEL_FILTER = "Libros de Excel (*.xlsx)"
FILE_DIALOG_EXCEL_TITLE = "Elegir libro de Excel"

# --- Estados vacíos ---------------------------------------------------------
EMPTY_CATALOG_TEXT = "Importa el Excel con códigos y nombres o crea los registros uno a uno."
CATALOG_NO_RESULTS_TITLE = "Sin resultados"
CATALOG_NO_COMPANY_TITLE = "Elige una empresa"
CATALOG_NO_COMPANY_TEXT = "Cada empresa tiene sus propios productos y centros de costo."

# --- Eliminar ---------------------------------------------------------------
CATALOG_PRODUCT_IN_USE = (
    "Algún proveedor usa este producto. Si lo eliminas, sus facturas quedarán bloqueadas."
)
CATALOG_DELETE_NOTE = "Esta acción no se puede deshacer."
CATALOG_COST_CENTER_DELETE_NOTE = (
    "Si alguna factura lo tiene asignado, quedará bloqueada hasta que elijas otro centro de costo."
)

_NOUN = {"product": "producto", "cost_center": "centro de costo"}
_NOUN_PLURAL = {"product": "productos", "cost_center": "centros de costo"}
_TITLE_NOUN = {"product": "Producto", "cost_center": "Centro de costo"}
_IN_USE_LIST_LIMIT = 3


def _noun(kind: str, count: int = 1) -> str:
    return (_NOUN if count == 1 else _NOUN_PLURAL)[kind]


def _quoted_list(names: _Sequence[str]) -> str:
    quoted = [f"«{name}»" for name in names]
    if len(quoted) == 1:
        return quoted[0]
    return f"{', '.join(quoted[:-1])} y {quoted[-1]}"


def catalog_new_title(kind: str) -> str:
    return f"Nuevo {_noun(kind)}"


def catalog_edit_title(kind: str) -> str:
    return f"Editar {_noun(kind)}"


def catalog_count(kind: str, shown: int, total: int) -> str:
    noun = _noun(kind, total)
    return f"{total} {noun}" if shown == total else f"{shown} de {total} {noun}"


def catalog_saved(kind: str) -> str:
    return f"{_TITLE_NOUN[kind]} guardado"


def catalog_deleted(kind: str) -> str:
    return f"{_TITLE_NOUN[kind]} eliminado"


def catalog_code_exists(kind: str, code: str) -> str:
    return (
        f"Ya existe un {_noun(kind)} con el código «{code}». "
        "Selecciónalo en la lista para editarlo."
    )


def catalog_empty_title(kind: str) -> str:
    return f"Aún no hay {_noun(kind, 2)}"


def catalog_no_results(kind: str, query: str) -> str:
    return f"Ningún {_noun(kind)} coincide con «{query}»."


def catalog_template_filename(kind: str) -> str:
    return f"plantilla-{_noun(kind, 2).replace(' ', '-')}.xlsx"


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


def catalog_import_sentence(kind: str, created: int, updated: int, invalid: int) -> str:
    """Result of an Excel import as plain sentences (no ``A · B · C`` summaries)."""
    made = f"{created} {_noun(kind, created)} {_plural(created, 'creado', 'creados')}"
    changed = f"{updated} {_plural(updated, 'actualizado', 'actualizados')}"
    if created and updated:
        head = f"{made} y {changed}."
    elif created:
        head = f"{made}."
    elif updated:
        head = (
            f"{updated} {_noun(kind, updated)} {_plural(updated, 'actualizado', 'actualizados')}."
        )
    elif invalid:
        head = "No se importó ninguna fila."
    else:
        return "El archivo no tiene filas para importar."
    if not invalid:
        return head
    if created or updated:
        tail = _plural(invalid, "fila no se importó", "filas no se importaron")
    else:
        tail = _plural(invalid, "fila tiene un error", "filas tienen errores")
    return f"{head} {invalid} {tail}."


def catalog_product_in_use(supplier_names: _Sequence[str]) -> str:
    """Warning shown before deleting a product some supplier is configured with."""
    if not supplier_names:
        return CATALOG_PRODUCT_IN_USE
    count = len(supplier_names)
    if count == 1:
        who = f"Lo usa el proveedor {_quoted_list(supplier_names)}."
        consequence = "las facturas de ese proveedor"
    else:
        if count <= _IN_USE_LIST_LIMIT:
            who = f"Lo usan los proveedores {_quoted_list(supplier_names)}."
        else:
            listed = _quoted_list(supplier_names[:_IN_USE_LIST_LIMIT])
            who = f"Lo usan {count} proveedores, entre ellos {listed}."
        consequence = "las facturas de esos proveedores"
    return (
        f"{who} Si lo eliminas, {consequence} quedarán bloqueadas hasta que elijas otro producto."
    )


# --- Primera interfaz (se retira con la integración) -------------------------
def catalog_import_summary(created: int, updated: int, invalid: int) -> str:
    return f"Creados: {created} · Actualizados: {updated} · Filas inválidas: {invalid}"


def catalog_invalid_row(row_number: int, reason: str) -> str:
    reasons = {
        "code is required": "falta el código",
        "name is required": "falta el nombre",
        "duplicate code in file": "código repetido en el archivo",
    }
    return f"Fila {row_number}: {reasons.get(reason, reason)}"
