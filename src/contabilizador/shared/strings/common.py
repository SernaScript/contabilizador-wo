"""Copy shared by every page: app identity, generic actions, navigation, widgets."""

APP_TITLE = "Contabilizador WO"
APP_NAME = "Contabilizador"
BRAND_NAME = "While Corp - Software Development"

# --- Acciones genericas ----------------------------------------------------
ACTION_SAVE = "Guardar"
ACTION_CANCEL = "Cancelar"
ACTION_DELETE = "Eliminar"
ACTION_NEW = "Nuevo"
ACTION_BROWSE = "Examinar…"
ACTION_REFRESH = "Actualizar"
ACTION_CLOSE = "Cerrar"
ACTION_DONE = "Listo"
ACTION_RETRY = "Reintentar"
ACTION_EDIT = "Editar"
ACTION_CLEAR_SEARCH = "Borrar búsqueda"
ACTION_CLEAR_SELECTION = "Quitar selección"
ACTION_SHOW_DETAILS = "Ver detalle"
ACTION_SHOW_IN_FOLDER = "Mostrar en carpeta"
ACTION_OPEN_FILE = "Abrir archivo"
ACTION_CHOOSE_FILES = "Elegir archivos"
ACTION_CHOOSE = "Elegir…"
COPIED = "Copiado"

# --- Navegacion (barra lateral) --------------------------------------------
NAV_INVOICES = "Facturas"
NAV_SUPPLIERS = "Proveedores"
NAV_CATALOGS = "Catálogos"
NAV_BATCHES = "Lotes exportados"
NAV_COMPANY = "Empresa"
NAV_SHORTCUTS = "Atajos"
# Pestaña de la UI anterior: se conserva porque las pruebas de compatibilidad la fijan
TAB_CATALOGS = "Catálogos"

# --- Estados (siempre icono + texto) ---------------------------------------
STATUS_READY = "Lista"
STATUS_INCOMPLETE = "Por completar"
STATUS_BLOCKED = "Bloqueada"
STATUS_MISMATCH = "Descuadre"
STATUS_ARCHIVED = "Archivada"
STATUS_LABELS = {
    "ready": STATUS_READY,
    "incomplete": STATUS_INCOMPLETE,
    "blocked": STATUS_BLOCKED,
    "mismatch": STATUS_MISMATCH,
    "archived": STATUS_ARCHIVED,
}

# --- Widgets compartidos ---------------------------------------------------
SEARCH_PLACEHOLDER = "Buscar"
BUSY_DEFAULT_MESSAGE = "Trabajando…"
BUSY_CANCELLING = "Cancelando…"
DROP_OVERLAY_TEXT = "Suelta aquí los archivos XML, carpetas o zips"
TOAST_CLOSE = "Cerrar aviso"
FILTER_ALL = "Todas"
STEP_DONE = "Hecho"
STEP_CURRENT = "Paso actual"
VARIOUS = "Varios"
LOADING = "Cargando…"


def confirm_delete(label: str) -> str:
    return f"¿Eliminar «{label}»?"


def busy_progress(done: int, total: int) -> str:
    return f"{done} de {total}"


def count_label(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"
