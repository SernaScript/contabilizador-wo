"""Copy of the Lotes exportados page: sentences that state exactly what will happen."""

import pytest

from contabilizador.shared import strings


def test_batch_title_and_document_counts() -> None:
    assert strings.batch_title(12) == "Lote 12"
    assert strings.batch_documents_count(18, 2) == "18 facturas y 2 notas crédito"
    assert strings.batch_documents_count(1, 0) == "1 factura"
    assert strings.batch_documents_count(0, 1) == "1 nota crédito"
    assert strings.batch_documents_count(1, 1) == "1 factura y 1 nota crédito"
    assert strings.batch_documents_count(0, 3) == "3 notas crédito"


def test_summary_is_a_sentence_without_separators() -> None:
    summary = strings.batch_summary("03/09/2026", "14:05", 18, 2)

    assert summary == "Exportado el 03/09/2026 a las 14:05. Incluye 18 facturas y 2 notas crédito."
    assert "·" not in summary


def test_summary_mentions_released_invoices_when_there_are_some() -> None:
    summary = strings.batch_summary("03/09/2026", "14:05", 18, 2, released=2, total=20)

    assert summary == (
        "Exportado el 03/09/2026 a las 14:05. Incluye 18 facturas y 2 notas crédito. "
        "2 de 20 facturas liberadas."
    )


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        ([], ""),
        (["FC 5731"], "FC 5731"),
        (["FC 5731 a 5748", "NC 12"], "FC 5731 a 5748 y NC 12"),
        (["A", "B", "C"], "A, B y C"),
    ],
)
def test_ranges_sentence_joins_with_y(parts: list[str], expected: str) -> None:
    assert strings.batch_ranges_sentence(parts) == expected


def test_released_summary() -> None:
    assert strings.batch_released_summary(2, 20) == "2 de 20 facturas liberadas"
    assert strings.batch_released_summary(1, 1) == "1 de 1 factura liberada"


@pytest.mark.parametrize(
    ("count", "expected"),
    [
        (18, "Las 18 facturas del lote volverán a estar pendientes."),
        (1, "La factura del lote volverá a estar pendiente."),
        (0, "Todas las facturas del lote ya estaban liberadas."),
    ],
)
def test_void_confirmation_states_what_happens_to_the_invoices(count: int, expected: str) -> None:
    assert strings.confirm_void_documents(count) == expected


def test_void_title_names_the_batch() -> None:
    assert strings.confirm_void_title(12) == "¿Anular el lote 12?"


def test_void_confirmation_says_the_consecutives_come_back() -> None:
    assert strings.confirm_void_returns("FC 5731 a 5748 y NC 12 a 14", 20) == (
        "Los consecutivos FC 5731 a 5748 y NC 12 a 14 quedarán disponibles otra vez."
    )
    assert strings.confirm_void_returns("FC 5731", 1) == (
        "El consecutivo FC 5731 quedará disponible otra vez."
    )


def test_void_confirmation_says_the_consecutives_stay_used_and_why() -> None:
    assert strings.confirm_void_keeps("FC 5731 a 5748", 18, 13) == (
        "Los consecutivos FC 5731 a 5748 quedan usados porque el lote 13 es posterior."
    )
    assert strings.confirm_void_keeps("FC 5731", 1, 13) == (
        "El consecutivo FC 5731 queda usado porque el lote 13 es posterior."
    )


def test_release_confirmation_counts_and_warns_numbers_stay_used() -> None:
    assert strings.confirm_release_title(3) == "¿Liberar 3 facturas?"
    assert strings.confirm_release_title(1) == "¿Liberar 1 factura?"
    assert strings.confirm_release_message(3) == (
        "Las 3 facturas volverán a estar pendientes en Facturas."
    )
    assert strings.confirm_release_message(1) == (
        "La factura volverá a estar pendiente en Facturas."
    )
    assert "consecutivos quedan usados" in strings.CONFIRM_RELEASE_NOTE


def test_success_toasts_use_the_same_word_as_the_action() -> None:
    assert strings.batch_voided(12, returned=True) == (
        "Lote 12 anulado. Los consecutivos están disponibles otra vez."
    )
    assert strings.batch_voided(12, returned=False) == (
        "Lote 12 anulado. Los consecutivos quedan usados."
    )
    assert strings.documents_released(3) == "3 facturas liberadas"
    assert strings.documents_released(1) == "1 factura liberada"


def test_selection_caption() -> None:
    # sin seleccion el pie dice que hacer, no solo que no hay nada
    assert strings.release_selection_caption(0) == "Selecciona las facturas que quieres liberar."
    assert strings.release_selection_caption(1) == "1 factura seleccionada"
    assert strings.release_selection_caption(3) == "3 facturas seleccionadas"


def test_status_pill_texts_match_the_plan() -> None:
    assert strings.BATCH_STATUS_EXPORTED == "Exportado"
    assert strings.BATCH_STATUS_VOIDED == "Anulado"
    assert strings.BATCH_STATUS_VOIDED_RETURNED == "Anulado con consecutivos devueltos"
    assert strings.BATCH_STATUS_PARTIAL == "Parcial"


def test_status_tooltips_explain_each_state() -> None:
    assert "liberad" in strings.batch_partial_tooltip(2, 20)
    assert "2 de 20" in strings.batch_partial_tooltip(2, 20)
    assert strings.BATCH_VOIDED_RETURNED_TOOLTIP
    assert strings.BATCH_VOIDED_KEPT_TOOLTIP
    assert strings.BATCH_EXPORTED_TOOLTIP


def test_legacy_names_used_by_the_first_ui_survive() -> None:
    assert strings.COLUMN_BATCH_ID == "Lote"
    assert strings.COLUMN_BATCH_RANGES == "Consecutivos"
    assert strings.BATCH_STATUS_VOIDED_REUSED
    assert strings.CONFIRM_VOID_BATCH
    assert strings.CONFIRM_RELEASE_DOCUMENTS
    assert strings.BATCH_ALREADY_VOIDED == "El lote ya está anulado."
    assert strings.EMPTY_BATCHES_TITLE == "Aún no hay lotes exportados"
    assert strings.NO_BATCHES_HINT
    assert strings.ACTION_VOID_BATCH == "Anular lote"
    assert strings.ACTION_RELEASE_SELECTED_INVOICES == "Liberar facturas seleccionadas"
    assert strings.ACTION_SHOW_BATCH_FILE == "Mostrar archivo"
