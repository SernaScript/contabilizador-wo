"""Copy of the Empresa page, the company switcher and the company form."""

LABEL_COMPANY = "Empresa"
NO_COMPANIES_HINT = "Crea una empresa para empezar."
COMPANY_PAGE_TITLE = "Empresa"
COMPANY_PAGE_PURPOSE = "Datos que World Office espera en cada importación."
FIELD_COMPANY_NAME = "Nombre (tal como lo espera World Office)"
FIELD_INTERNAL_THIRD_PARTY = "Tercero interno (quien registra las facturas)"
FIELD_WAREHOUSE = "Bodega"
FIELD_UNIT = "Unidad de medida"
FIELD_PAYMENT_FORM = "Forma de pago"
COMPANY_NAME_PLACEHOLDER = "Ej. EMPRESA DEMO S.A.S"
COMPANY_NAME_REQUIRED = "Escribe el nombre de la empresa."
COMPANY_NAME_DUPLICATED = "Ya existe una empresa con ese nombre. Usa otro nombre."
ACTION_NEW_COMPANY = "Nueva empresa"
COMPANY_SWITCHER_PLACEHOLDER = "Sin empresa"
COMPANY_SWITCHER_LOCKED_HINT = "Espera a que termine la tarea en curso para cambiar de empresa."
SECTION_WORLD_OFFICE = "Datos World Office"
SECTION_DEFAULTS = "Valores por defecto"
SECTION_CONSECUTIVES = "Consecutivos"
LABEL_LAST_FC = "Última factura de compra (FC)"
LABEL_LAST_NC = "Última nota crédito (NC)"
COMPANY_SAVED = "Empresa guardada"
COMPANY_UNSAVED_CHANGES = "Hay cambios sin guardar."
COMPANY_CONSECUTIVE_NONE = "Ninguna todavía"
COMPANY_CONSECUTIVES_HINT = (
    "Se actualizan solos con cada exportación. Al exportar puedes elegir otro número inicial."
)
COMPANY_EMPTY_TITLE = "Todavía no tienes una empresa"
COMPANY_EMPTY_TEXT = "Crea una para guardar los datos que World Office espera en cada importación."
NEW_COMPANY_PURPOSE = (
    "Escribe el nombre tal como aparece en World Office. "
    "Podrás cambiar estos datos después en Empresa."
)
NEW_COMPANY_SUBMIT = "Crear empresa"


def company_created(name: str) -> str:
    return f"Empresa «{name}» creada"
