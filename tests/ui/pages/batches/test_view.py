"""BatchesView: master list, detail of the selected batch and the actions that depend on it."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from contabilizador.shared import strings
from contabilizador.ui.pages.batches.rows import batch_rows
from contabilizador.ui.pages.batches.view import BATCH_ROW_HEIGHT, MAX_BATCH_ROWS, BatchesView
from contabilizador.ui.theme import TOKENS, apply_theme
from tests.ui.pages.batches.builders import FC, NC, doc, make_batch

NEWEST = make_batch(
    3,
    doc("c1", FC, 5750, external_number="5750", prefix="FPI"),
    doc("c2", FC, 5751),
    doc("c3", NC, 12),
)
PARTIAL = make_batch(
    2, doc("b1", FC, 5740, released=True), doc("b2", FC, 5741), doc("b3", FC, 5742)
)
VOIDED = make_batch(1, doc("a1", FC, 5731, released=True), voided=True, reused=True)


def make_view(qtbot, batches=(NEWEST, PARTIAL, VOIDED)) -> BatchesView:
    view = BatchesView()
    qtbot.addWidget(view)
    view.resize(1000, 760)
    view.show()
    view.set_batches(batch_rows(list(batches)))
    return view


def doc_cufes(view: BatchesView) -> list[str]:
    model = view.documents_model
    return [model.row_at(row).cufe for row in range(model.rowCount())]  # type: ignore[union-attr]


def click_batch(qtbot, view: BatchesView, row: int) -> None:
    index = view.batches_model.index(row, 0)
    qtbot.mouseClick(
        view.batches_table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=view.batches_table.visualRect(index).center(),
    )


# --- estructura -----------------------------------------------------------------


def test_page_header_names_the_page(qtbot) -> None:
    view = make_view(qtbot)

    assert view.title_label.text() == strings.BATCHES_PAGE_TITLE
    assert view.purpose_label.text() == strings.BATCHES_PAGE_PURPOSE
    assert view.splitter.orientation() == Qt.Orientation.Vertical


def test_the_divider_between_list_and_detail_is_easy_to_grab(qtbot) -> None:
    view = make_view(qtbot)

    assert view.splitter.handle(1).height() >= 8


def test_lists_batches_as_given_and_selects_the_newest(qtbot) -> None:
    view = make_view(qtbot)

    assert view.state() == "list"
    assert view.batches_model.rowCount() == 3
    assert view.selected_batch_id() == 3


def test_detail_describes_the_selected_batch(qtbot) -> None:
    view = make_view(qtbot)

    assert view.detail_title.text() == "Lote 3"
    assert view.detail_pill.status == "archived"
    assert view.detail_pill.text == strings.BATCH_STATUS_EXPORTED
    assert view.detail_summary.text().startswith("Exportado el ")
    assert view.detail_summary.text().endswith("Incluye 2 facturas y 1 nota crédito.")
    # se lee el nombre del archivo; la ruta completa queda en los tooltips
    assert view.detail_file.full_text() == NEWEST.file_path.name
    assert view.detail_file.toolTip() == str(NEWEST.file_path)
    assert view.show_file_button.toolTip() == str(NEWEST.file_path)
    assert doc_cufes(view) == ["c1", "c2", "c3"]


def test_choosing_another_batch_updates_the_detail_and_announces_it(qtbot) -> None:
    view = make_view(qtbot)
    seen: list[object] = []
    view.batch_selected.connect(seen.append)

    click_batch(qtbot, view, 1)

    assert view.selected_batch_id() == 2
    assert view.detail_title.text() == "Lote 2"
    assert view.detail_pill.status == "incomplete"
    assert view.detail_pill.text == strings.BATCH_STATUS_PARTIAL
    assert doc_cufes(view) == ["b1", "b2", "b3"]
    assert seen[-1] == 2


def test_voided_batch_detail_says_so(qtbot) -> None:
    view = make_view(qtbot)

    view.select_batch(1)

    assert view.detail_pill.text == strings.BATCH_STATUS_VOIDED_RETURNED


# --- anular -----------------------------------------------------------------------


def test_void_button_asks_to_void_the_selected_batch(qtbot) -> None:
    view = make_view(qtbot)
    requested: list[int] = []
    view.void_requested.connect(requested.append)

    assert view.void_button.text() == strings.ACTION_VOID_BATCH
    assert view.void_button.isEnabled()
    qtbot.mouseClick(view.void_button, Qt.MouseButton.LeftButton)

    assert requested == [3]


def test_a_voided_batch_cannot_be_voided_again_and_the_tooltip_says_why(qtbot) -> None:
    view = make_view(qtbot)

    view.select_batch(1)

    assert not view.void_button.isEnabled()
    assert view.void_button.toolTip() == strings.BATCH_VOID_DISABLED_HINT


# --- liberar ----------------------------------------------------------------------


def test_release_waits_for_a_selection_and_explains(qtbot) -> None:
    view = make_view(qtbot)

    assert view.release_button.text() == strings.ACTION_RELEASE_SELECTED_INVOICES
    assert not view.release_button.isEnabled()
    assert view.release_button.toolTip() == strings.BATCH_RELEASE_DISABLED_NOTHING
    assert view.selection_label.text() == strings.BATCH_RELEASE_DISABLED_NOTHING

    view.select_cufes(["c2"])

    assert view.release_button.isEnabled()
    assert view.release_button.toolTip() == ""
    assert view.selection_label.text() == "1 factura seleccionada"


def test_release_requests_only_the_selected_unreleased_invoices(qtbot) -> None:
    view = make_view(qtbot)
    requests: list[tuple[int, list[str]]] = []
    view.release_requested.connect(lambda batch_id, cufes: requests.append((batch_id, cufes)))
    view.select_cufes(["c1", "c3"])

    qtbot.mouseClick(view.release_button, Qt.MouseButton.LeftButton)

    assert requests == [(3, ["c1", "c3"])]
    assert view.selection_label.text() == "2 facturas seleccionadas"


def test_escape_clears_the_invoice_selection(qtbot) -> None:
    view = make_view(qtbot)
    view.select_cufes(["c1", "c2"])
    view.documents_table.setFocus()

    qtbot.keyClick(view.documents_table, Qt.Key.Key_Escape)

    assert view.selected_cufes() == []
    assert view.selected_batch_id() == 3  # el lote sigue elegido
    assert not view.release_button.isEnabled()


def test_released_invoices_cannot_be_selected(qtbot) -> None:
    view = make_view(qtbot)
    view.select_batch(2)

    view.documents_table.selectAll()

    assert view.selected_cufes() == ["b2", "b3"]
    view.select_cufes(["b1"])
    assert view.selected_cufes() == []


def test_a_voided_batch_has_nothing_left_to_release(qtbot) -> None:
    view = make_view(qtbot)

    view.select_batch(1)

    assert not view.release_button.isEnabled()
    assert view.release_button.toolTip() == strings.BATCH_RELEASE_DISABLED_VOIDED
    assert view.selection_label.text() == strings.BATCH_RELEASE_DISABLED_VOIDED


def test_the_selection_caption_sits_right_next_to_the_release_button(qtbot) -> None:
    view = make_view(qtbot)
    QApplication.processEvents()
    caption, button = view.selection_label, view.release_button

    gap = button.geometry().left() - caption.geometry().right() - 1

    assert 0 <= gap <= 12
    assert caption.parent() is button.parent()
    # ambos pegados al borde derecho, junto a la tabla: la frase explica el boton
    assert button.geometry().right() >= view.documents_table.geometry().right() - 1


def test_the_status_column_of_the_invoices_only_shows_when_something_was_released(qtbot) -> None:
    view = make_view(qtbot)
    status = view.documents_model.STATUS_COLUMN

    assert view.selected_batch_id() == 3
    assert view.documents_table.isColumnHidden(status)  # todas exportadas: columna vacia

    view.select_batch(2)  # una factura liberada
    assert not view.documents_table.isColumnHidden(status)

    view.select_batch(3)
    assert view.documents_table.isColumnHidden(status)


def test_the_batch_list_is_as_tall_as_its_rows_and_the_detail_gets_the_rest(qtbot) -> None:
    view = make_view(qtbot, batches=(NEWEST, PARTIAL))
    QApplication.processEvents()
    two = view.batches_table.height()

    # justo lo que piden sus filas: sin barra de desplazamiento ni fila a medias
    assert two == view.list_height(2)
    assert not view.batches_table.verticalScrollBar().isVisible()
    assert view.documents_table.height() > two  # el detalle tiene mas espacio que la lista

    view.set_batches(batch_rows([NEWEST, PARTIAL, VOIDED]))
    QApplication.processEvents()
    assert view.batches_table.height() == two + BATCH_ROW_HEIGHT
    assert not view.batches_table.verticalScrollBar().isVisible()

    many = [make_batch(n, doc(f"x{n}", FC, 6000 + n)) for n in range(1, 13)]
    view.set_batches(batch_rows(many))
    QApplication.processEvents()
    # con muchos lotes la lista se detiene en un tope y se desplaza
    assert view.list_height() == view.list_height(MAX_BATCH_ROWS)
    assert view.list_height(3) < view.batches_table.height() <= view.list_height() + 2


def test_a_taller_window_gives_the_extra_height_to_the_detail(qtbot) -> None:
    view = make_view(qtbot, batches=(NEWEST, PARTIAL))
    QApplication.processEvents()
    list_before = view.batches_table.height()
    detail_before = view.documents_table.height()

    view.resize(1000, 960)
    QApplication.processEvents()

    assert view.batches_table.height() == list_before
    assert view.documents_table.height() > detail_before


def test_a_divider_the_person_moved_is_never_recomputed(qtbot) -> None:
    view = make_view(qtbot, batches=(NEWEST, PARTIAL))
    QApplication.processEvents()
    view.splitter.setSizes([300, 300])
    view.splitter.splitterMoved.emit(300, 1)
    QApplication.processEvents()
    chosen = view.batches_table.height()
    assert chosen > view.list_height(3)  # la persona agrando la lista a proposito

    view.set_batches(batch_rows([NEWEST, PARTIAL, VOIDED]))
    QApplication.processEvents()

    assert view.batches_table.height() == chosen


# --- mostrar archivo ----------------------------------------------------------------


def test_show_file_asks_for_the_selected_batch(qtbot) -> None:
    view = make_view(qtbot)
    requested: list[int] = []
    view.show_file_requested.connect(requested.append)

    assert view.show_file_button.text() == strings.ACTION_SHOW_BATCH_FILE
    qtbot.mouseClick(view.show_file_button, Qt.MouseButton.LeftButton)

    assert requested == [3]


def test_show_file_is_available_even_for_a_voided_batch(qtbot) -> None:
    view = make_view(qtbot)

    view.select_batch(1)

    assert view.show_file_button.isEnabled()


# --- seleccion preservada ---------------------------------------------------------


def test_refreshing_keeps_the_batch_and_the_invoices_selected(qtbot) -> None:
    view = make_view(qtbot)
    view.select_batch(2)
    view.select_cufes(["b2", "b3"])

    view.set_batches(batch_rows([NEWEST, PARTIAL, VOIDED]))

    assert view.selected_batch_id() == 2
    assert view.selected_cufes() == ["b2", "b3"]
    assert view.release_button.isEnabled()


def test_after_releasing_the_batch_stays_selected_and_released_invoices_drop_out(qtbot) -> None:
    view = make_view(qtbot)
    view.select_batch(2)
    view.select_cufes(["b2"])

    after = make_batch(
        2,
        doc("b1", FC, 5740, released=True),
        doc("b2", FC, 5741, released=True),
        doc("b3", FC, 5742),
    )
    view.set_batches(batch_rows([NEWEST, after, VOIDED]))

    assert view.selected_batch_id() == 2
    assert view.selected_cufes() == []
    assert view.documents_model.row_at(1).released  # type: ignore[union-attr]


def test_the_selected_batch_stays_selected_after_it_is_voided(qtbot) -> None:
    view = make_view(qtbot)
    view.select_batch(2)

    voided = make_batch(2, doc("b1", FC, 5740, released=True), voided=True, reused=False)
    view.set_batches(batch_rows([NEWEST, voided, VOIDED]))

    assert view.selected_batch_id() == 2
    assert view.detail_pill.text == strings.BATCH_STATUS_VOIDED
    assert not view.void_button.isEnabled()


def test_if_the_selected_batch_disappears_the_newest_is_selected(qtbot) -> None:
    view = make_view(qtbot)
    view.select_batch(1)

    view.set_batches(batch_rows([NEWEST, PARTIAL]))

    assert view.selected_batch_id() == 3


# --- vacio, sin empresa y ocupado -----------------------------------------------------


def test_no_batches_invites_to_export_from_facturas(qtbot) -> None:
    view = make_view(qtbot, batches=())
    requested: list[str] = []
    view.empty_action_requested.connect(lambda: requested.append("go"))

    assert view.state() == "empty"
    assert view.empty.title_label.text() == strings.EMPTY_BATCHES_TITLE
    assert view.empty.text_label.text() == strings.EMPTY_BATCHES_TEXT
    assert view.empty.action_button.text() == strings.BATCH_ACTION_GO_TO_INVOICES
    qtbot.mouseClick(view.empty.action_button, Qt.MouseButton.LeftButton)

    assert requested == ["go"]
    assert view.selected_batch_id() is None


def test_before_the_first_load_nothing_claims_there_are_no_batches(qtbot) -> None:
    view = BatchesView()
    qtbot.addWidget(view)

    assert view.state() == "list"
    assert view.selected_batch_id() is None
    assert not view.void_button.isEnabled()


def test_without_a_company_the_page_asks_for_one(qtbot) -> None:
    view = make_view(qtbot)

    view.set_has_company(False)

    assert view.state() == "no_company"
    assert view.no_company.title_label.text() == strings.BATCH_NO_COMPANY_TITLE

    view.set_has_company(True)
    assert view.state() == "list"


def test_reset_forgets_the_rows(qtbot) -> None:
    view = make_view(qtbot)

    view.reset()

    assert view.batches_model.rowCount() == 0
    assert view.documents_model.rowCount() == 0
    assert view.state() == "list"
    assert view.selected_batch_id() is None


def test_busy_locks_void_and_release_but_not_show_file(qtbot) -> None:
    view = make_view(qtbot)
    view.select_cufes(["c1"])

    view.set_busy(True)

    assert not view.void_button.isEnabled()
    assert not view.release_button.isEnabled()
    assert view.show_file_button.isEnabled()

    view.set_busy(False)

    assert view.void_button.isEnabled()
    assert view.release_button.isEnabled()


# --- aspecto de los botones deshabilitados ---------------------------------------------


@pytest.fixture
def themed(qapp: QApplication):
    """The real stylesheet, restored afterwards so other tests keep the plain style."""
    previous_sheet = qapp.styleSheet()
    previous_style = qapp.style().objectName()
    apply_theme(qapp)
    yield
    qapp.setStyleSheet(previous_sheet)
    qapp.setStyle(previous_style)


def background_of(button) -> str:
    image = button.grab().toImage()
    return QColor(image.pixelColor(6, button.height() // 2)).name().upper()


def test_a_disabled_action_does_not_look_like_an_enabled_one(qtbot, themed) -> None:
    view = make_view(qtbot)
    view.select_batch(3)
    enabled_void = background_of(view.void_button)
    enabled_release = None
    view.select_cufes(["c1"])
    enabled_release = background_of(view.release_button)

    view.select_batch(1)  # anulado: no se puede anular ni liberar
    view.repaint()

    assert not view.void_button.isEnabled()
    assert background_of(view.void_button) == TOKENS.disabled_bg
    assert background_of(view.release_button) == TOKENS.disabled_bg
    assert enabled_void != TOKENS.disabled_bg
    assert enabled_release != TOKENS.disabled_bg
