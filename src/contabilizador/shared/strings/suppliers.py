"""Copy of the Proveedores page, the supplier wizard and the product picker."""

ACTION_CONFIGURE = "Configurar"
ACTION_SAVE_AND_NEXT = "Guardar y siguiente"
ACTION_SKIP = "Omitir"
SUPPLIER_DIALOG_TITLE = "Configurar proveedor"
SUPPLIERS_PAGE_TITLE = "Proveedores"
SUPPLIERS_PAGE_PURPOSE = "Define qué productos puede traer cada proveedor."
FIELD_SUPPLIER_PRODUCTS = "Productos permitidos"
NO_PRODUCTS_HINT = "No hay productos en el catálogo. Impórtalos primero en Catálogos."
SUPPLIERS_UNCONFIGURED_TITLE = "Sin configurar"
COLUMN_SUPPLIER_DEFAULT = "Producto por defecto"
COLUMN_SUPPLIER_PRODUCTS = "Productos"
COLUMN_SUPPLIER_PENDING = "Facturas pendientes"
EMPTY_SUPPLIERS_TITLE = "Aún no hay proveedores"
EMPTY_SUPPLIERS_TEXT = "Los proveedores aparecen al importar facturas. Configúralos desde aquí."
SUPPLIER_SAVED = "Proveedor guardado"
SUPPLIER_DELETED = "Proveedor eliminado"

# --- Pagina ----------------------------------------------------------------
SUPPLIERS_SEARCH_PLACEHOLDER = "Buscar por NIT o nombre"
COLUMN_SUPPLIER_NIT = "NIT"
COLUMN_SUPPLIER_NAME = "Proveedor"
SUPPLIER_PRODUCT_MISSING_PILL = "Producto inexistente"
ACTION_SUPPLIERS_GO_TO_INVOICES = "Ir a Facturas"
SUPPLIERS_NO_COMPANY_TITLE = "Elige una empresa"
SUPPLIERS_NO_COMPANY_TEXT = "Los proveedores se configuran por empresa."
SUPPLIER_DELETE_DETAIL = (
    "Sus facturas pendientes quedarán bloqueadas hasta que lo configures otra vez."
)

# --- Hojas de edicion y asistente ------------------------------------------
SUPPLIER_EDIT_TITLE = "Editar proveedor"
WIZARD_CONTEXT_TITLE = "Líneas pendientes de este proveedor"
SUPPLIER_PRODUCTS_NONE = "Selecciona al menos un producto."
SUPPLIER_PRODUCTS_MISSING = "Quita los productos que ya no están en el catálogo."
SUPPLIER_SAVE_FAILED = "No se pudo guardar el proveedor. Inténtalo de nuevo."

# --- Selector de productos -------------------------------------------------
PICKER_SEARCH_PLACEHOLDER = "Buscar producto"
# La estrella solo aparece en los productos marcados: antes de marcar uno, la pista pide marcar
PICKER_NO_DEFAULT_HINT = "Marca los productos que este proveedor puede traer."
PICKER_STAR_SET = "Usar como producto por defecto"
PICKER_STAR_IS_DEFAULT = "Producto por defecto"
PICKER_DEFAULT_BADGE = "Por defecto"
PICKER_MISSING_BADGE = "Ya no está en el catálogo"
ACTION_PICKER_GO_TO_CATALOGS = "Ir a Catálogos"


def supplier_dialog_subtitle(index: int, total: int) -> str:
    return f"Proveedor {index} de {total}"


def configure_pending_action(count: int) -> str:
    return "Configurar proveedor" if count == 1 else "Configurar proveedores"


def suppliers_configured(count: int) -> str:
    return f"{count} {'proveedor configurado' if count == 1 else 'proveedores configurados'}"


def suppliers_no_match(query: str) -> str:
    return f"Ningún proveedor coincide con «{query}»."


def supplier_missing_products_tooltip(codes: list[str]) -> str:
    verb = "Ya no está" if len(codes) == 1 else "Ya no están"
    return f"{verb} en el catálogo: {', '.join(codes)}."


def picker_selected_count(count: int) -> str:
    if count == 0:
        return "Ninguno seleccionado"
    return f"{count} {'seleccionado' if count == 1 else 'seleccionados'}"


def picker_default_summary(label: str, *, can_change: bool = False) -> str:
    """The star is only worth mentioning once there is another checked product to choose."""
    summary = f"Por defecto: {label}."
    return f"{summary} Cámbialo con la estrella." if can_change else summary


def picker_no_match(query: str) -> str:
    return f"Ningún producto coincide con «{query}»."


def wizard_context_lines(count: int) -> str:
    return f"{count} {'línea' if count == 1 else 'líneas'}"


def supplier_products_count(count: int) -> str:
    return f"{count} {'producto' if count == 1 else 'productos'}"
