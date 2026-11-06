"""Copy of the Catálogos page: sentences, plurals and kind-specific nouns."""

import pytest

from contabilizador.shared import strings

PRODUCT = "product"
COST_CENTER = "cost_center"


def test_titles_name_the_kind_being_created_or_edited() -> None:
    assert strings.catalog_new_title(PRODUCT) == "Nuevo producto"
    assert strings.catalog_new_title(COST_CENTER) == "Nuevo centro de costo"
    assert strings.catalog_edit_title(PRODUCT) == "Editar producto"
    assert strings.catalog_edit_title(COST_CENTER) == "Editar centro de costo"


@pytest.mark.parametrize(
    ("kind", "shown", "total", "expected"),
    [
        (PRODUCT, 14, 14, "14 productos"),
        (PRODUCT, 1, 1, "1 producto"),
        (PRODUCT, 0, 0, "0 productos"),
        (PRODUCT, 3, 14, "3 de 14 productos"),
        (PRODUCT, 0, 14, "0 de 14 productos"),
        (COST_CENTER, 1, 1, "1 centro de costo"),
        (COST_CENTER, 2, 9, "2 de 9 centros de costo"),
    ],
)
def test_count_caption_says_how_many_rows_match(
    kind: str, shown: int, total: int, expected: str
) -> None:
    assert strings.catalog_count(kind, shown, total) == expected


def test_toasts_say_what_was_saved_or_deleted() -> None:
    assert strings.catalog_saved(PRODUCT) == "Producto guardado"
    assert strings.catalog_saved(COST_CENTER) == "Centro de costo guardado"
    assert strings.catalog_deleted(PRODUCT) == "Producto eliminado"
    assert strings.catalog_deleted(COST_CENTER) == "Centro de costo eliminado"


def test_duplicate_code_tells_where_to_edit_it() -> None:
    message = strings.catalog_code_exists(PRODUCT, "1001")

    assert "producto" in message
    assert "«1001»" in message
    assert "lista" in message


def test_empty_states_invite_to_act_per_kind() -> None:
    assert strings.catalog_empty_title(PRODUCT) == "Aún no hay productos"
    assert strings.catalog_empty_title(COST_CENTER) == "Aún no hay centros de costo"
    assert "Excel" in strings.EMPTY_CATALOG_TEXT


def test_no_results_quotes_the_query() -> None:
    assert strings.catalog_no_results(PRODUCT, "papel") == "Ningún producto coincide con «papel»."
    assert "centro de costo" in strings.catalog_no_results(COST_CENTER, "x")


@pytest.mark.parametrize(
    ("kind", "created", "updated", "invalid", "expected"),
    [
        (PRODUCT, 12, 3, 0, "12 productos creados y 3 actualizados."),
        (PRODUCT, 12, 0, 0, "12 productos creados."),
        (PRODUCT, 0, 3, 0, "3 productos actualizados."),
        (PRODUCT, 1, 1, 0, "1 producto creado y 1 actualizado."),
        (COST_CENTER, 2, 0, 1, "2 centros de costo creados. 1 fila no se importó."),
        (PRODUCT, 5, 0, 2, "5 productos creados. 2 filas no se importaron."),
        (PRODUCT, 0, 0, 3, "No se importó ninguna fila. 3 filas tienen errores."),
        (PRODUCT, 0, 0, 1, "No se importó ninguna fila. 1 fila tiene un error."),
        (PRODUCT, 0, 0, 0, "El archivo no tiene filas para importar."),
    ],
)
def test_import_result_is_written_as_sentences(
    kind: str, created: int, updated: int, invalid: int, expected: str
) -> None:
    assert strings.catalog_import_sentence(kind, created, updated, invalid) == expected


def test_import_result_has_no_meta_separators() -> None:
    sentence = strings.catalog_import_sentence(PRODUCT, 4, 2, 1)

    assert "·" not in sentence
    assert ":" not in sentence


@pytest.mark.parametrize(
    ("names", "expected_start"),
    [
        (["ACME"], "Lo usa el proveedor «ACME»."),
        (["A", "B"], "Lo usan los proveedores «A» y «B»."),
        (["A", "B", "C"], "Lo usan los proveedores «A», «B» y «C»."),
        (["A", "B", "C", "D", "E"], "Lo usan 5 proveedores, entre ellos «A», «B» y «C»."),
    ],
)
def test_product_in_use_names_the_suppliers(names: list[str], expected_start: str) -> None:
    message = strings.catalog_product_in_use(names)

    assert message.startswith(expected_start)
    assert "bloqueadas" in message
    assert "elijas otro producto" in message


def test_template_filenames_are_distinct_per_kind() -> None:
    assert strings.catalog_template_filename(PRODUCT) == "plantilla-productos.xlsx"
    assert strings.catalog_template_filename(COST_CENTER) == "plantilla-centros-de-costo.xlsx"


def test_legacy_names_used_by_the_first_ui_survive() -> None:
    assert strings.ACTION_IMPORT_EXCEL == "Importar desde Excel"
    assert strings.FILE_DIALOG_EXCEL_FILTER == "Libros de Excel (*.xlsx)"
    assert strings.catalog_invalid_row(4, "code is required") == "Fila 4: falta el código"
    assert strings.CATALOG_UNREADABLE_FILE
    assert strings.catalog_import_summary(1, 2, 3)
