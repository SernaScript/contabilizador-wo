"""Copy of the Facturas page: pills, problem sentences, tooltips (Spanish, sentence case)."""

from contabilizador.shared import strings
from contabilizador.shared.strings import invoices as copy


def test_readiness_pill_text_prefers_the_primary_problem() -> None:
    assert copy.readiness_pill_text("ready", None) == strings.STATUS_READY
    assert copy.readiness_pill_text("mismatch", None) == strings.STATUS_MISMATCH
    assert copy.readiness_pill_text("incomplete", "missing_product") == "Falta producto"
    assert copy.readiness_pill_text("incomplete", "missing_cost_center") == "Falta centro de costo"
    assert copy.readiness_pill_text("blocked", "unconfigured_supplier") == (
        "Proveedor sin configurar"
    )
    assert copy.readiness_pill_text("blocked", "unknown_product") == "Producto inexistente"
    # al lado de la columna "Centro de costo" se entiende sin repetirla; la frase completa
    # vive en el detalle. Asi "Proveedor sin configurar" sigue siendo la pastilla mas ancha.
    assert copy.readiness_pill_text("blocked", "unknown_cost_center") == "Centro inexistente"
    assert copy.readiness_pill_text("blocked", "already_exported") == "Ya exportada"
    assert copy.readiness_pill_text("blocked", "document_not_found") == "No encontrada"
    # sin problema conocido se usa la etiqueta generica del estado
    assert copy.readiness_pill_text("blocked", None) == strings.STATUS_BLOCKED


def test_problem_message_is_a_sentence_with_the_line_and_the_code() -> None:
    assert copy.problem_message("missing_product", 2, "") == "Línea 2: falta el producto."
    assert copy.problem_message("missing_cost_center", 1, "") == (
        "Línea 1: falta el centro de costo."
    )
    assert copy.problem_message("unknown_product", 3, "P-9") == (
        "Línea 3: el producto P-9 ya no existe en el catálogo."
    )
    assert copy.problem_message("unknown_cost_center", 3, "CC-9") == (
        "Línea 3: el centro de costo CC-9 ya no existe en el catálogo."
    )
    assert copy.problem_message("unconfigured_supplier", None, "900") == (
        "El proveedor no está configurado."
    )
    assert copy.problem_message("already_exported", None, "") == (
        "Ya fue exportada. Actualiza la lista."
    )
    assert copy.problem_message("document_not_found", None, "") == (
        "Ya no está en la lista. Actualiza la lista."
    )


def test_line_values_and_various_values_are_sentences() -> None:
    assert copy.line_values_sentence("2,5", "$ 83.333", "19 %") == "2,5 a $ 83.333, IVA 19 %"
    assert copy.various_values_tooltip(["1001 - Papelería", "2001 - Servicios"]) == (
        "Las líneas tienen valores distintos: 1001 - Papelería, 2001 - Servicios."
    )


def test_counts_and_report_copy() -> None:
    assert copy.invoices_updated(1) == "1 factura actualizada"
    assert copy.invoices_updated(3) == "3 facturas actualizadas"
    assert copy.orphan_credit_note_detail("NC-125", "718b2e03aaaa") == (
        "NC-125: la factura original 718b2e03aaaa… no está importada."
    )
    assert copy.duplicate_detail("FEV-1001", "COMERCIALIZADORA") == (
        "FEV-1001 de COMERCIALIZADORA ya existía."
    )
    assert strings.IMPORT_REPORT_DUPLICATES == "Facturas que ya existían"
    assert strings.IMPORT_REPORT_EMPTY == "Todos los archivos se importaron sin novedades."
    assert strings.NO_RESULTS == "Ninguna factura coincide con la búsqueda o el filtro."
    assert strings.DETAIL_EMPTY == "Selecciona una factura para ver su detalle."
    assert strings.DETAIL_MISMATCH_NOTE == "Se exporta solo si confirmas el descuadre."
    assert strings.CATALOG_EMPTY_PRODUCTS == "No hay productos en el catálogo."
    assert strings.CATALOG_EMPTY_COST_CENTERS == "No hay centros de costo en el catálogo."
    assert strings.ACTION_GO_TO_CATALOGS == "Ir a catálogos"
    assert strings.ACTION_EXPAND_ALL == "Expandir todo"
    assert strings.ACTION_COLLAPSE_ALL == "Contraer todo"
    assert strings.INVOICE_NOT_FOUND_TITLE == "La factura ya no está en la lista"
    assert strings.INVOICE_NOT_FOUND_HINT == "Se actualizó la lista. Revisa y vuelve a intentarlo."
    assert strings.FILE_NOT_FOUND_TOAST == "El archivo XML ya no está donde se importó."


def test_copy_has_no_all_caps_labels_nor_arrows() -> None:
    public = {
        name: value
        for name, value in vars(copy).items()
        if not name.startswith("_") and isinstance(value, str)
    }
    for name, value in public.items():
        assert "→" not in value, name
        # Etiquetas en sentence case: nunca todo en mayusculas (los acronimos quedan fuera)
        if len(value) > 4 and value.isalpha():
            assert not value.isupper(), name


def test_document_tooltip_mentions_the_due_date() -> None:
    assert copy.document_tooltip("Factura", "30/09/2026") == "Factura, vence el 30/09/2026"
