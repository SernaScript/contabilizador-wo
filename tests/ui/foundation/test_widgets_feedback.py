"""Feedback widgets: StatusPill, Toast, Banner, EmptyState, DropOverlay, BusyOverlay,
ReadinessBar."""

from enum import Enum, auto
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QRect, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui.theme import STATUS_STYLES, TOKENS
from contabilizador.ui.widgets.banner import Banner
from contabilizador.ui.widgets.busy_overlay import BusyOverlay
from contabilizador.ui.widgets.drop_overlay import DropOverlay, paths_from_mime
from contabilizador.ui.widgets.empty_state import EmptyState
from contabilizador.ui.widgets.readiness_bar import ReadinessBar
from contabilizador.ui.widgets.status_pill import (
    StatusPill,
    elide_pill_text,
    paint_status_pill,
    status_pill_size,
)
from contabilizador.ui.widgets.toast import Toast, ToastHost

# --- StatusPill -----------------------------------------------------------------


def test_status_pill_defaults_text_from_status(qtbot) -> None:
    pill = StatusPill("ready")
    qtbot.addWidget(pill)

    assert pill.status == "ready"
    assert pill.text == strings.STATUS_READY
    assert pill.sizeHint().width() > 0
    assert pill.property("status") == "ready"

    pill.set_status("blocked", strings.FLAG_UNCONFIGURED_SUPPLIER)
    assert pill.text == strings.FLAG_UNCONFIGURED_SUPPLIER
    assert pill.toolTip() == strings.FLAG_UNCONFIGURED_SUPPLIER
    assert pill.accessibleName() == strings.FLAG_UNCONFIGURED_SUPPLIER


def test_paint_status_pill_draws_background_and_fits_size(qapp) -> None:
    font = QFont()
    size = status_pill_size("mismatch", "Descuadre", font)
    image = QImage(size.width() + 10, size.height() + 10, QImage.Format.Format_ARGB32)
    image.fill(QColor(TOKENS.paper))
    painter = QPainter(image)
    painted = paint_status_pill(
        painter, QRect(5, 5, size.width(), size.height()), "mismatch", "Descuadre", font
    )
    painter.end()

    assert painted.width() == size.width()
    assert (
        image.pixelColor(8, 5 + size.height() // 2).name().upper() == STATUS_STYLES["mismatch"].bg
    )
    assert image.pixelColor(1, 1).name().upper() == TOKENS.paper


def _pill_text_width(font: QFont, text: str) -> float:
    medium = QFont(font)
    medium.setWeight(QFont.Weight.Medium)
    return QFontMetricsF(medium).horizontalAdvance(text)


def test_a_pill_that_does_not_fit_is_elided_at_a_word_not_in_the_middle_of_one(qapp) -> None:
    font = QFont(qapp.font())
    full = "Falta centro de costo"
    room = _pill_text_width(font, full) - 25

    shown = elide_pill_text(font, full, int(room))

    # palabras enteras y la elipsis pegada: "Falta centro…", nunca "Falta centro d…" ni "sin …"
    assert shown.endswith("…")
    words = shown.removesuffix("…").split(" ")
    assert words == full.split(" ")[: len(words)]
    assert not shown.removesuffix("…").endswith(" ")
    assert _pill_text_width(font, shown) <= room

    # si cabe entero no se toca; si no cabe ni la primera palabra se corta por caracteres
    assert elide_pill_text(font, full, int(_pill_text_width(font, full)) + 1) == full
    tiny = elide_pill_text(font, "Proveedor sin configurar", int(_pill_text_width(font, "Prov")))
    assert tiny.endswith("…") and "Proveedor".startswith(tiny.removesuffix("…"))
    assert _pill_text_width(font, tiny) <= _pill_text_width(font, "Prov")


def test_paint_status_pill_right_aligned_stays_inside_rect(qapp) -> None:
    font = QFont()
    size = status_pill_size("ready", "Lista", font)
    rect = QRect(0, 0, size.width() + 100, size.height())
    image = QImage(rect.size(), QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painted = paint_status_pill(
        painter, rect, "ready", "Lista", font, align=Qt.AlignmentFlag.AlignRight
    )
    painter.end()

    assert painted.right() <= rect.right()
    assert painted.left() >= 100


# --- Toast ----------------------------------------------------------------------


def test_toast_host_shows_bottom_right_with_action(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(800, 600)
    window.show()
    host = ToastHost(window)
    clicks: list[int] = []

    toast = host.show_toast(
        strings.invoices_exported(18),
        kind="success",
        action_label=strings.ACTION_SHOW_DETAILS,
        on_action=lambda: clicks.append(1),
        timeout_ms=0,
    )

    assert isinstance(toast, Toast)
    assert toast.isVisible()
    assert toast.message() == "18 facturas exportadas"
    assert toast.property("role") == "toast"
    assert toast.property("status") == "ready"
    assert toast.geometry().right() <= window.width() - ToastHost.MARGIN + 1
    assert toast.geometry().bottom() <= window.height() - ToastHost.MARGIN + 1
    assert host.toasts() == [toast]

    toast.action_button.click()
    assert clicks == [1]


def test_toast_dismisses_by_button_and_by_timeout(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(600, 400)
    window.show()
    host = ToastHost(window)

    sticky = host.show_toast("Copiado", timeout_ms=0)
    with qtbot.waitSignal(sticky.dismissed, timeout=3000):
        sticky.close_button.click()
    assert host.toasts() == []

    short = host.show_toast("Guardado", timeout_ms=30)
    with qtbot.waitSignal(short.dismissed, timeout=3000):
        pass
    assert host.toasts() == []


def test_toasts_stack_upwards(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(600, 400)
    window.show()
    host = ToastHost(window)

    first = host.show_toast("Uno", timeout_ms=0)
    second = host.show_toast("Dos", timeout_ms=0)

    assert second.geometry().bottom() < first.geometry().top()


# --- Banner ---------------------------------------------------------------------


def test_banner_text_status_and_action(qtbot) -> None:
    banner = Banner(
        strings.unconfigured_suppliers_banner(3, 5),
        status="blocked",
        action_label=strings.configure_pending_action(3),
    )
    qtbot.addWidget(banner)
    banner.show()

    assert banner.text() == "3 proveedores sin configurar bloquean 5 facturas."
    assert banner.property("status") == "blocked"
    assert banner.action_button.text() == "Configurar proveedores"
    assert not banner.icon_label.pixmap().isNull()

    with qtbot.waitSignal(banner.action_triggered):
        banner.action_button.click()

    # la etiqueta sigue a lo que queda por configurar (un proveedor: en singular)
    banner.set_action(strings.configure_pending_action(1))
    assert banner.action_button.text() == "Configurar proveedor"
    assert banner.action_button.isVisible()

    banner.set_action(None)
    assert banner.action_button.isHidden()
    banner.set_status("incomplete")
    assert banner.property("status") == "incomplete"


# --- EmptyState -----------------------------------------------------------------


def test_empty_state_invites_action(qtbot) -> None:
    empty = EmptyState(
        "import",
        strings.EMPTY_INVOICES_TITLE,
        strings.EMPTY_INVOICES_TEXT,
        action_label=strings.ACTION_CHOOSE_FILES,
    )
    qtbot.addWidget(empty)
    empty.show()

    assert empty.title_label.text() == strings.EMPTY_INVOICES_TITLE
    assert empty.text_label.text() == strings.EMPTY_INVOICES_TEXT
    assert empty.action_button.text() == strings.ACTION_CHOOSE_FILES
    assert empty.action_button.property("variant") == "primary"
    assert not empty.icon_label.pixmap().isNull()

    with qtbot.waitSignal(empty.action_triggered):
        empty.action_button.click()

    empty.set_active(True)
    assert empty.property("active") == "true"


def test_empty_state_without_action_hides_button(qtbot) -> None:
    empty = EmptyState("batches", strings.EMPTY_BATCHES_TITLE)
    qtbot.addWidget(empty)
    empty.show()

    assert empty.action_button.isHidden()
    assert empty.text_label.isHidden()


@pytest.mark.parametrize("width", [900, 1200])
def test_empty_state_never_clips_its_wrapped_text(qtbot, width: int) -> None:
    # En un layout sin estiramiento el estado vacio recibe solo la altura que pide: esa
    # altura tiene que alcanzar para el texto partido en lineas al ancho real de la etiqueta
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    empty = EmptyState(
        "import",
        strings.EMPTY_INVOICES_TITLE,
        "Arrastra aquí los XML de la DIAN, una carpeta o un zip. También puedes elegirlos "
        "desde tu equipo para empezar a completar las facturas del mes.",
        action_label=strings.ACTION_CHOOSE_FILES,
    )
    layout.addWidget(empty)
    layout.addStretch(1)
    host.resize(width, 600)
    host.show()
    layout.activate()

    label = empty.text_label
    assert label.height() >= label.heightForWidth(label.width())
    # el texto se lee en una columna, no a todo el ancho de la ventana
    assert label.width() < width // 2


# --- DropOverlay ----------------------------------------------------------------


def test_drop_overlay_covers_parent_and_tracks_resize(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(500, 300)
    window.show()
    overlay = DropOverlay(window)

    assert overlay.isHidden()
    overlay.show_overlay()
    assert overlay.isVisible()
    assert overlay.geometry() == window.rect()
    assert overlay.label.text() == strings.DROP_OVERLAY_TEXT
    assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    window.resize(700, 500)
    qtbot.waitUntil(lambda: overlay.geometry() == window.rect(), timeout=2000)
    overlay.hide_overlay()
    assert overlay.isHidden()


def test_overlays_follow_resizes_without_their_python_state(qtbot) -> None:
    # El recolector de ciclos vacia el __dict__ antes de que muera el objeto C++ y Qt puede
    # seguir llamando eventFilter mientras tanto: el filtro solo usa estado de C++
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(300, 200)
    drop = DropOverlay(host)
    busy = BusyOverlay(host)
    host.show()
    drop.show_overlay()
    busy.start()
    drop.__dict__.clear()
    busy.__dict__.clear()

    host.resize(420, 260)

    assert drop.geometry() == host.rect()
    assert busy.geometry() == host.rect()


def test_toast_host_survives_resizes_without_its_python_state(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(400, 300)
    window.show()
    host = ToastHost(window)
    host.__dict__.clear()

    window.resize(500, 320)  # sin AttributeError dentro del filtro de eventos

    assert window.width() == 500


def test_paths_from_mime_keeps_local_files_only(tmp_path: Path) -> None:
    mime = QMimeData()
    local = tmp_path / "factura.xml"
    mime.setUrls([QUrl.fromLocalFile(str(local)), QUrl("https://example.com/x.xml")])

    assert paths_from_mime(mime) == [local]
    assert paths_from_mime(QMimeData()) == []


# --- BusyOverlay ----------------------------------------------------------------


def test_busy_overlay_progress_and_cancel(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.resize(500, 300)
    window.show()
    overlay = BusyOverlay(window)

    overlay.start(strings.IMPORT_PROGRESS, cancellable=True)
    assert overlay.isVisible()
    assert overlay.is_running
    assert overlay.message_label.text() == strings.IMPORT_PROGRESS
    assert overlay.cancel_button.isVisible()
    assert overlay.progress_bar.maximum() == 0  # indeterminado hasta el primer reporte

    overlay.set_progress(2, 10)
    assert (overlay.progress_bar.value(), overlay.progress_bar.maximum()) == (2, 10)
    assert overlay.progress_label.text() == strings.busy_progress(2, 10)

    with qtbot.waitSignal(overlay.cancel_requested):
        overlay.cancel_button.click()
    assert overlay.cancel_button.isEnabled() is False
    assert overlay.message_label.text() == strings.BUSY_CANCELLING

    overlay.finish()
    assert overlay.isHidden()
    assert overlay.is_running is False


def test_busy_overlay_without_cancel_hides_button(qtbot) -> None:
    window = QWidget()
    qtbot.addWidget(window)
    window.show()
    overlay = BusyOverlay(window)

    overlay.start()

    assert overlay.message_label.text() == strings.BUSY_DEFAULT_MESSAGE
    assert overlay.cancel_button.isHidden()
    assert not overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


# --- ReadinessBar ---------------------------------------------------------------


class Readiness(Enum):
    BLOCKED = auto()
    INCOMPLETE = auto()
    MISMATCH = auto()
    READY = auto()


def test_readiness_bar_counts_caption_and_cta(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.show()

    bar.set_counts(
        {Readiness.READY: 17, Readiness.MISMATCH: 1, Readiness.INCOMPLETE: 6, Readiness.BLOCKED: 2}
    )

    assert bar.counts() == {"ready": 17, "mismatch": 1, "incomplete": 6, "blocked": 2}
    # una sola palabra para "se puede exportar": 18 = 17 listas + 1 con descuadre
    assert bar.caption_label.text() == "18 de 26 facturas se pueden exportar"
    assert bar.secondary_label.text() == "1 con descuadre requiere confirmación"
    # el boton promete lo que sale sin confirmar: la hoja abre con la casilla del descuadre
    # sin marcar, asi que el numero no cambia en la pantalla siguiente
    assert bar.cta_button.text() == "Exportar 17 facturas"
    assert bar.cta_button.isEnabled()
    assert bar.cta_button.property("variant") == "primary"
    assert bar.segment_label("ready").text() == "17 listas"
    assert bar.segment_label("incomplete").text() == "6 por completar"

    with qtbot.waitSignal(bar.export_requested):
        bar.cta_button.click()


def test_the_cta_names_the_default_export_and_a_mismatch_only_list_keeps_it_enabled(
    qtbot,
) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)

    bar.set_counts({"ready": 8, "mismatch": 1, "incomplete": 3, "blocked": 2})
    assert bar.caption_label.text() == "9 de 14 facturas se pueden exportar"
    assert bar.cta_button.text() == "Exportar 8 facturas"
    assert bar.secondary_label.text() == "1 con descuadre requiere confirmación"
    assert bar.cta_button.isEnabled()

    # solo hay descuadres: el boton sigue activo y no promete un numero (la hoja lo explica)
    bar.set_counts({"mismatch": 2, "incomplete": 1})
    assert bar.cta_button.text() == "Exportar"
    assert bar.cta_button.isEnabled()
    assert bar.caption_label.text() == "2 de 3 facturas se pueden exportar"


def test_readiness_caption_reads_in_singular_and_plural() -> None:
    assert strings.readiness_caption(9, 14) == "9 de 14 facturas se pueden exportar"
    assert strings.readiness_caption(1, 14) == "1 de 14 facturas se puede exportar"
    assert strings.readiness_caption(1, 1) == "1 de 1 factura se puede exportar"
    assert strings.readiness_caption(0, 5) == "Ninguna de las 5 facturas se puede exportar todavía"
    assert strings.readiness_caption(0, 1) == "La factura todavía no se puede exportar"
    assert strings.readiness_caption(0, 0) == "Sin facturas pendientes"


def test_selection_caption_names_what_is_selected_and_what_can_leave() -> None:
    assert strings.selection_caption(3, 3) == "3 seleccionadas, 3 se pueden exportar"
    assert strings.selection_caption(3, 1) == "3 seleccionadas, 1 se puede exportar"
    assert strings.selection_caption(1, 1) == "1 seleccionada, se puede exportar"


def test_readiness_bar_legend_ties_each_label_to_its_segment_color(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.resize(900, 120)
    bar.show()
    bar.set_counts({"ready": 8, "mismatch": 1, "incomplete": 3})

    for key in ("ready", "mismatch", "incomplete"):
        dot = bar.legend_dot(key)
        assert dot.color() == STATUS_STYLES[key].fg
        assert (dot.width(), dot.height()) == (8, 8)
        assert bar.legend_item(key).isVisibleTo(bar)
        image = dot.grab().toImage()
        assert image.pixelColor(4, 4).name().upper() == STATUS_STYLES[key].fg
    # sin facturas bloqueadas la leyenda no las menciona
    assert not bar.legend_item("blocked").isVisibleTo(bar)
    # la etiqueta sigue siendo texto: el color solo enlaza con la barra
    assert bar.segment_label("mismatch").text() == "1 con descuadre"


def test_readiness_bar_selection_and_disabled_reason(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)

    bar.set_counts({"ready": 4, "incomplete": 2})
    bar.set_selection(3)
    assert bar.cta_button.text() == "Exportar 3 seleccionadas"
    bar.set_selection(None)
    assert bar.cta_button.text() == "Exportar 4 facturas"

    bar.set_counts({"incomplete": 5, "blocked": 1})
    assert bar.cta_button.isEnabled() is False
    assert bar.cta_button.toolTip() == strings.export_disabled_reason(1, 5)
    assert bar.caption_label.text() == "Ninguna de las 6 facturas se puede exportar todavía"
    assert bar.secondary_label.text() == strings.export_disabled_reason(1, 5)

    bar.set_counts({})
    assert bar.secondary_label.isHidden()
    assert bar.caption_label.text() == strings.readiness_caption(0, 0)


def test_the_caption_follows_a_selection_that_can_be_exported(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.set_counts({"ready": 6, "mismatch": 1, "incomplete": 5, "blocked": 2})
    assert bar.caption_label.text() == "7 de 14 facturas se pueden exportar"

    bar.set_selection(3)
    assert bar.caption_label.text() == "3 seleccionadas, 3 se pueden exportar"

    bar.set_selection(2, 4)
    assert bar.cta_button.text() == "Exportar 2 seleccionadas"
    assert bar.caption_label.text() == "4 seleccionadas, 2 se pueden exportar"

    # nada exportable en la seleccion: el boton exporta todo lo listo y el pie lo dice igual
    # (7 se pueden exportar; 6 salen sin confirmar el descuadre)
    bar.set_selection(0, 2)
    assert bar.cta_button.text() == "Exportar 6 facturas"
    assert bar.caption_label.text() == "7 de 14 facturas se pueden exportar"

    bar.set_selection(None)
    assert bar.caption_label.text() == "7 de 14 facturas se pueden exportar"


def test_a_selection_scopes_the_bar_the_legend_and_the_hint(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.resize(900, 120)
    bar.show()
    bar.set_counts({"ready": 8, "mismatch": 1, "incomplete": 3, "blocked": 2})

    bar.set_selection(3, 3, counts={"ready": 3})

    # nada de lo que el pie dice describe las otras facturas
    assert bar.bar.counts() == {"ready": 3, "mismatch": 0, "incomplete": 0, "blocked": 0}
    assert bar.segment_label("ready").text() == "3 listas"
    for key in ("mismatch", "incomplete", "blocked"):
        assert not bar.legend_item(key).isVisibleTo(bar)
    assert bar.secondary_label.isHidden()
    assert bar.caption_label.text() == "3 seleccionadas, 3 se pueden exportar"
    assert bar.cta_button.text() == "Exportar 3 seleccionadas"
    # el estado global sigue intacto para cuando se quite la seleccion
    assert bar.counts() == {"ready": 8, "mismatch": 1, "incomplete": 3, "blocked": 2}

    bar.set_selection(None)
    assert bar.bar.counts() == {"ready": 8, "mismatch": 1, "incomplete": 3, "blocked": 2}
    assert bar.segment_label("ready").text() == "8 listas"
    assert bar.segment_label("blocked").text() == "2 con proveedor sin configurar"
    assert bar.secondary_label.text() == "1 con descuadre requiere confirmación"
    assert bar.cta_button.text() == "Exportar 8 facturas"


def test_a_selection_with_a_mismatch_says_so_and_the_cta_counts_only_what_is_ready(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.resize(900, 120)
    bar.show()
    bar.set_counts({"ready": 8, "mismatch": 1, "incomplete": 3, "blocked": 2})

    # llaves de enum tambien: la vista pasa Readiness
    selected = {Readiness.READY: 2, Readiness.MISMATCH: 1, Readiness.BLOCKED: 1}
    bar.set_selection(3, 4, counts=selected)

    assert bar.caption_label.text() == "4 seleccionadas, 3 se pueden exportar"
    assert bar.cta_button.text() == "Exportar 2 seleccionadas"
    assert bar.secondary_label.text() == "1 con descuadre requiere confirmación"
    assert bar.segment_label("blocked").text() == "1 con proveedor sin configurar"
    assert not bar.legend_item("incomplete").isVisibleTo(bar)

    # solo descuadres seleccionados: el boton no promete un numero
    bar.set_selection(2, 2, counts={"mismatch": 2})
    assert bar.cta_button.text() == "Exportar"
    assert bar.cta_button.isEnabled()
    assert bar.secondary_label.text() == "2 con descuadre requieren confirmación"


def test_a_selection_with_nothing_exportable_keeps_the_footer_global(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.resize(900, 120)
    bar.show()
    bar.set_counts({"ready": 6, "mismatch": 1, "incomplete": 5, "blocked": 2})

    # el boton exporta todo lo listo cuando la seleccion no aporta nada: el pie lo cuenta igual
    bar.set_selection(0, 2, counts={"incomplete": 2})

    assert bar.bar.counts() == {"ready": 6, "mismatch": 1, "incomplete": 5, "blocked": 2}
    assert bar.cta_button.text() == "Exportar 6 facturas"
    assert bar.caption_label.text() == "7 de 14 facturas se pueden exportar"


def test_with_nothing_to_export_the_footer_says_what_to_do_next(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.show()

    bar.set_counts({"incomplete": 3, "blocked": 2})

    assert bar.caption_label.text() == "Ninguna de las 5 facturas se puede exportar todavía"
    # sin "Exportar 0 facturas": un numero que nadie puede usar
    assert bar.cta_button.text() == "Exportar"
    assert not bar.cta_button.isEnabled()
    assert bar.cta_button.toolTip() == strings.export_disabled_reason(2, 3)
    # lo que sigue se lee sin pasar el puntero por el boton
    assert bar.secondary_label.isVisibleTo(bar)
    assert bar.secondary_label.text() == strings.export_disabled_reason(2, 3)
    # la barra y la leyenda cuentan la historia
    assert bar.bar.segments()
    assert bar.segment_label("incomplete").text() == "3 por completar"
    assert bar.segment_label("blocked").text() == "2 con proveedor sin configurar"


def test_the_cta_reads_in_singular_and_plural_and_never_promises_zero() -> None:
    assert strings.export_cta(8) == "Exportar 8 facturas"
    assert strings.export_cta(1) == "Exportar 1 factura"
    assert strings.export_cta(0) == "Exportar"
    assert strings.export_selected_cta(3) == "Exportar 3 seleccionadas"
    assert strings.export_selected_cta(1) == "Exportar 1 seleccionada"
    assert strings.export_selected_cta(0) == "Exportar"


def test_the_legend_reads_in_singular_and_plural() -> None:
    assert strings.readiness_legend("ready", 8) == "8 listas"
    assert strings.readiness_legend("ready", 1) == "1 lista"
    assert strings.readiness_legend("mismatch", 1) == "1 con descuadre"
    assert strings.readiness_legend("incomplete", 3) == "3 por completar"
    assert strings.readiness_legend("blocked", 2) == "2 con proveedor sin configurar"
    # si alguna esta bloqueada por otra causa (un codigo que ya no esta en el catalogo) la
    # leyenda no puede decir que todas esperan un proveedor
    assert strings.readiness_legend("blocked", 3, by_supplier=False) == "3 bloqueadas"
    assert strings.readiness_legend("blocked", 1, by_supplier=False) == "1 bloqueada"


def test_the_disabled_reason_names_the_cause_it_can_prove() -> None:
    assert strings.export_disabled_reason(2, 3) == (
        "Completa las facturas pendientes para exportar: 3 por completar y "
        "2 con proveedor sin configurar."
    )
    assert strings.export_disabled_reason(2, 3, by_supplier=False) == (
        "Completa las facturas pendientes para exportar: 3 por completar y 2 bloqueadas."
    )
    assert strings.export_disabled_reason(0, 0) == "No hay facturas listas para exportar."


def test_the_blocked_state_has_one_name_in_the_legend_the_reason_and_the_chip(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.set_counts({"incomplete": 3, "blocked": 2})

    legend = bar.segment_label("blocked").text()

    # la leyenda, el motivo del boton y el chip dicen lo mismo (no "bloqueadas" en un sitio
    # y "con proveedor sin configurar" en otro)
    assert legend in strings.export_disabled_reason(2, 3)
    assert strings.FILTER_UNCONFIGURED.casefold() in legend
    assert "bloqueada" not in legend


def test_the_blocked_name_follows_what_blocks_the_invoices(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.resize(900, 120)
    bar.show()

    bar.set_counts({"incomplete": 3, "blocked": 2})
    assert bar.segment_label("blocked").text() == "2 con proveedor sin configurar"
    assert "2 con proveedor sin configurar" in bar.cta_button.toolTip()

    # una bloqueada por un codigo inexistente: ya no todas esperan un proveedor
    bar.set_counts({"incomplete": 3, "blocked": 2}, blocked_by_supplier=False)
    assert bar.segment_label("blocked").text() == "2 bloqueadas"
    assert bar.secondary_label.text() == strings.export_disabled_reason(2, 3, by_supplier=False)
    assert bar.cta_button.toolTip() == strings.export_disabled_reason(2, 3, by_supplier=False)

    # la seleccion lleva su propio criterio: aqui ninguna de las elegidas esta bloqueada por otra
    bar.set_selection(1, 2, counts={"ready": 1, "blocked": 1}, blocked_by_supplier=True)
    assert bar.segment_label("blocked").text() == "1 con proveedor sin configurar"
    bar.set_selection(1, 2, counts={"ready": 1, "blocked": 1}, blocked_by_supplier=False)
    assert bar.segment_label("blocked").text() == "1 bloqueada"
    bar.set_selection(None)
    assert bar.segment_label("blocked").text() == "2 bloqueadas"


def test_readiness_segments_follow_counts(qtbot) -> None:
    bar = ReadinessBar()
    qtbot.addWidget(bar)
    bar.resize(600, 90)
    bar.show()
    bar.set_counts({"ready": 3, "blocked": 1})

    segments = bar.bar.segments()

    assert [key for key, _width in segments] == ["ready", "blocked"]
    assert segments[0][1] > segments[1][1] > 0
