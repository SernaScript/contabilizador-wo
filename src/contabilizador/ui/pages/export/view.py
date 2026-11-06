"""Export sheet (presentational): consecutives per type, confirmations, destination and
the success state. It receives view-model values and emits what the user asks for; the
container runs the use cases."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from contabilizador.exports.domain.world_office import DocumentType
from contabilizador.shared import strings
from contabilizador.ui.errors import ErrorPresentation
from contabilizador.ui.formatting import format_range
from contabilizador.ui.pages.export.model import (
    CollisionNotice,
    ExportSheetState,
    MismatchNotice,
    SuccessSummary,
    TypeRow,
)
from contabilizador.ui.pages.export.notice import Notice
from contabilizador.ui.theme import STATUS_STYLES
from contabilizador.ui.widgets import BusyOverlay, Sheet, icon_label, make_label

MAX_CONSECUTIVE = 2_000_000_000
SUCCESS_ICON_SIZE = 24
# Cabe en 1024 px de ancho (Qt limita las ventanas a 2/3 de la pantalla: 682 px)
SHEET_WIDTH = 600
MAX_SCREEN_SHARE = 0.85
_RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
_LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def _height_for(widget: QWidget, width: int) -> int:
    if widget.hasHeightForWidth():
        return widget.heightForWidth(width)
    return widget.sizeHint().height()


def _drop_size_caches(root: QWidget) -> None:
    """Layouts keep their size hints until the event loop lays them out again; measuring
    right after a change (a notice that appears, a longer text) needs fresh values."""
    for widget in reversed(root.findChildren(QWidget)):
        widget.updateGeometry()
    for layout in root.findChildren(QLayout):
        layout.invalidate()


@dataclass(frozen=True, slots=True)
class TypeRowWidgets:
    label: QLabel
    count: QLabel
    start: QSpinBox
    range: QLabel


class ExportSheet(Sheet):
    start_numbers_changed = Signal(object)  # dict[DocumentType, int]
    mismatch_inclusion_changed = Signal(bool)  # la persona marco / desmarco la casilla
    export_requested = Signal()
    browse_requested = Signal()
    open_file_requested = Signal()
    show_in_folder_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            strings.EXPORT_DIALOG_TITLE,
            subtitle=strings.EXPORT_SHEET_SUBTITLE,
            primary_label=strings.ACTION_EXPORT_SHORT,
            parent=parent,
        )
        self.rows: dict[DocumentType, TypeRowWidgets] = {}
        self._counts: dict[DocumentType, int] = {}
        self._exportable_count = 0
        self._destination: Path | None = None

        self._form = self._build_form()
        self._success = False
        self._success_page = self._build_success_page()

        # Ancho fijo y alto segun el contenido; en pantallas bajas el cuerpo se desplaza
        self.setFixedWidth(SHEET_WIDTH)
        self._content = QWidget()
        self._content.setAutoFillBackground(False)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self._form)
        content_layout.addWidget(self._success_page)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.viewport().setAutoFillBackground(False)
        self._scroll.setWidget(self._content)
        self.body_layout.addWidget(self._scroll)

        self.open_file_button = self.add_button(strings.ACTION_OPEN_FILE)
        self.open_file_button.clicked.connect(self.open_file_requested)
        self.open_file_button.hide()
        self.show_in_folder_button = self.add_button(strings.ACTION_SHOW_IN_FOLDER)
        self.show_in_folder_button.clicked.connect(self.show_in_folder_requested)
        self.show_in_folder_button.hide()

        self.busy_overlay = BusyOverlay(self)
        self._exporting = False

    # --- construccion ------------------------------------------------------------------
    def _build_form(self) -> QWidget:
        form = QWidget()
        layout = QVBoxLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.skipped_label = make_label("", role="muted")
        self.skipped_label.setWordWrap(True)
        self.skipped_label.hide()
        layout.addWidget(self.skipped_label)
        layout.addLayout(self._build_grid())

        self.collision_notice = Notice("blocked", confirm_label=strings.EXPORT_CONFIRM_COLLISION)
        self.collision_notice.confirmed_changed.connect(self._sync_primary)
        self.collision_notice.action_triggered.connect(self._use_free_consecutives)
        self.collision_notice.hide()
        layout.addWidget(self.collision_notice)
        self._collisions: CollisionNotice | None = None

        # Opcional: sin marcarla, el lote sale con las facturas que cuadran. Se avisa solo
        # cuando la persona la toca (``clicked``); si la hoja la limpia no se avisa a nadie.
        self.mismatch_notice = Notice("mismatch", confirm_label=strings.EXPORT_CONFIRM_MISMATCH)
        self.mismatch_notice.checkbox.clicked.connect(self.mismatch_inclusion_changed)
        self.mismatch_notice.hide()
        layout.addWidget(self.mismatch_notice)
        self._mismatches: MismatchNotice | None = None

        layout.addLayout(self._build_destination())
        # cerca del pie: el error aparece junto al boton que lo provoco
        self.error_notice = Notice("blocked")
        self.error_notice.hide()
        layout.addWidget(self.error_notice)
        return form

    def _build_grid(self) -> QGridLayout:
        self._grid = QGridLayout()
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(8)
        self._grid.setColumnStretch(0, 1)
        self._headers: list[QLabel] = []
        headers = (
            (strings.EXPORT_COLUMN_TYPE, _LEFT),
            (strings.EXPORT_COLUMN_COUNT, _RIGHT),
            (strings.EXPORT_START_NUMBER, _LEFT),
            (strings.EXPORT_RANGE_PREVIEW, _LEFT),
        )
        for column, (text, alignment) in enumerate(headers):
            header = make_label(text, role="caption")
            self._headers.append(header)
            self._grid.addWidget(header, 0, column, alignment)
        return self._grid

    def _build_destination(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(2)
        layout.addWidget(make_label(strings.EXPORT_DESTINATION, role="label"))
        name_row = QHBoxLayout()
        name_row.setSpacing(12)
        self.destination_name = make_label("", role="value")
        # nombres largos se parten en guiones en vez de ensanchar la hoja
        self.destination_name.setWordWrap(True)
        self.destination_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        name_row.addWidget(self.destination_name, 1)
        self.browse_button = QPushButton(strings.ACTION_BROWSE)
        self.browse_button.clicked.connect(self.browse_requested)
        name_row.addWidget(self.browse_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(name_row)
        self.destination_folder = make_label("", role="caption")
        self.destination_folder.setWordWrap(True)
        layout.addWidget(self.destination_folder)
        return layout

    def _build_success_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        ready = STATUS_STYLES["ready"]
        layout.addWidget(
            icon_label(ready.icon, ready.fg, SUCCESS_ICON_SIZE), 0, Qt.AlignmentFlag.AlignTop
        )
        text = QVBoxLayout()
        text.setSpacing(6)
        self.success_saved_label = make_label("")
        self.success_saved_label.setWordWrap(True)
        self.success_saved_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        text.addWidget(self.success_saved_label)
        self.success_ranges_label = make_label("", role="muted")
        self.success_ranges_label.setWordWrap(True)
        text.addWidget(self.success_ranges_label)
        layout.addLayout(text, 1)
        page.hide()
        return page

    # --- datos -----------------------------------------------------------------
    def set_state(self, state: ExportSheetState) -> None:
        """Shows a (new) preview. Start numbers already on screen are kept: a preview
        never overwrites what the user typed."""
        present = {row.document_type for row in state.rows}
        added = False
        for row in state.rows:
            widgets = self.rows.get(row.document_type)
            if widgets is None:
                widgets = self._add_row(row)
                added = True
            self._counts[row.document_type] = row.count
            widgets.count.setText(str(row.count))
            self._refresh_range(row.document_type)
        if added:
            self._sync_tab_order()
        for document_type, widgets in self.rows.items():
            for widget in (widgets.label, widgets.count, widgets.start, widgets.range):
                widget.setVisible(document_type in present)
        for header in self._headers:
            header.setVisible(bool(present))  # sin filas, las cabeceras no encabezan nada
        self.skipped_label.setText(state.skipped_text)
        self.skipped_label.setVisible(bool(state.skipped_text))
        self._set_collisions(state.collisions)
        self._set_mismatches(state.mismatches)
        self._exportable_count = state.exportable_count
        self.set_primary_label(strings.export_cta(state.exportable_count))
        self._sync_primary()
        self._fit_to_content()

    def start_numbers(self) -> dict[DocumentType, int]:
        return {
            document_type: widgets.start.value()
            for document_type, widgets in self.rows.items()
            if not widgets.start.isHidden()
        }

    def set_destination(self, path: Path) -> None:
        self._destination = path
        self.destination_name.setText(path.name)
        self.destination_folder.setText(str(path.parent))
        self._sync_primary()
        self._fit_to_content()

    def destination(self) -> Path | None:
        return self._destination

    def mismatch_confirmed(self) -> bool:
        """The person chose to export the invoices with a totals mismatch too."""
        return self._mismatches is not None and self.mismatch_notice.confirmed

    def collision_confirmed(self) -> bool:
        return self._collisions is not None and self.collision_notice.confirmed

    # --- avisos --------------------------------------------------------------------
    def _set_collisions(self, notice: CollisionNotice | None) -> None:
        # otros cruces (otros numeros u otro lote) piden confirmar de nuevo
        if notice != self._collisions:
            self.collision_notice.reset_confirmation()
        self._collisions = notice
        if notice is not None:
            self.collision_notice.set_content(notice.title, notice.items)
            self.collision_notice.set_action(notice.action_label)
        self.collision_notice.setVisible(notice is not None)

    def _use_free_consecutives(self) -> None:
        if self._collisions is None:
            return
        for document_type, start in self._collisions.suggested_starts.items():
            widgets = self.rows.get(document_type)
            if widgets is not None and not widgets.start.isHidden():
                widgets.start.setValue(start)

    def _set_mismatches(self, notice: MismatchNotice | None) -> None:
        # una confirmacion vale solo para la lista que el usuario vio
        if notice != self._mismatches:
            self.mismatch_notice.reset_confirmation()
        self._mismatches = notice
        if notice is not None:
            self.mismatch_notice.set_content(notice.title, (notice.explanation, *notice.items))
            self.mismatch_notice.checkbox.setText(notice.include_label)
        self.mismatch_notice.setVisible(notice is not None)

    # --- filas -------------------------------------------------------------------
    def _add_row(self, row: TypeRow) -> TypeRowWidgets:
        line = self._grid.rowCount()
        start = QSpinBox()
        start.setRange(1, MAX_CONSECUTIVE)
        start.setValue(row.start)
        start.setAlignment(_RIGHT)
        start.setMinimumWidth(120)
        start.setAccessibleName(f"{strings.EXPORT_START_NUMBER}, {row.label}")
        widgets = TypeRowWidgets(
            label=make_label(row.label),
            count=make_label(str(row.count), role="value"),
            start=start,
            range=make_label("", role="value"),
        )
        widgets.count.setAlignment(_RIGHT)
        self._grid.addWidget(widgets.label, line, 0)
        self._grid.addWidget(widgets.count, line, 1)
        self._grid.addWidget(widgets.start, line, 2)
        self._grid.addWidget(widgets.range, line, 3)
        self.rows[row.document_type] = widgets
        start.valueChanged.connect(lambda _value, t=row.document_type: self._on_start_changed(t))
        return widgets

    def _sync_tab_order(self) -> None:
        """Reading order; the rows are created after the footer, so Qt's default (creation
        order) would visit Cancelar before the consecutives."""
        chain: list[QWidget] = [
            *(self.rows[t].start for t in DocumentType if t in self.rows),
            self.collision_notice.action_button,
            self.collision_notice.checkbox,
            self.mismatch_notice.checkbox,
            self.browse_button,
            self.open_file_button,
            self.show_in_folder_button,
            self.cancel_button,
            self.primary_button,
        ]
        for first, second in itertools.pairwise(chain):
            QWidget.setTabOrder(first, second)

    def _on_start_changed(self, document_type: DocumentType) -> None:
        self._refresh_range(document_type)
        self.start_numbers_changed.emit(self.start_numbers())

    def _refresh_range(self, document_type: DocumentType) -> None:
        widgets = self.rows[document_type]
        first = widgets.start.value()
        last = first + max(self._counts.get(document_type, 1), 1) - 1
        widgets.range.setText(format_range(first, last))

    def show_error(self, presentation: ErrorPresentation | None) -> None:
        """What happened and how to fix it; the technical text only in the tooltip."""
        if presentation is None:
            self.error_notice.hide()
        else:
            lines = [text for text in (presentation.message, presentation.hint) if text]
            self.error_notice.set_content(presentation.title, lines)
            self.error_notice.setToolTip(presentation.details)
            self.error_notice.show()
        self._fit_to_content()

    # --- exito ----------------------------------------------------------------------
    def show_success(self, summary: SuccessSummary) -> None:
        self._success = True
        self.title_label.setText(summary.title)
        self.subtitle_label.setText(strings.EXPORT_SUCCESS_NEXT_STEP)
        self.subtitle_label.show()
        self.success_saved_label.setText(summary.saved_text)
        self.success_ranges_label.setText(summary.ranges_text)
        self._form.hide()
        self._success_page.show()
        self.cancel_button.hide()
        self.open_file_button.show()
        self.show_in_folder_button.show()
        self.set_primary_label(strings.ACTION_DONE)
        self._sync_primary()
        self._fit_to_content()
        self.primary_button.setFocus(Qt.FocusReason.OtherFocusReason)

    @property
    def is_success(self) -> bool:
        return self._success

    # --- tamano y foco --------------------------------------------------------------
    def _fit_to_content(self) -> None:
        """Height that shows every wrapped notice whole (Qt's own sizing ignores
        height-for-width and caps windows to 2/3 of the screen), capped to the screen."""
        self.ensurePolished()
        _drop_size_caches(self)
        margins = self.body_layout.contentsMargins()
        content_width = SHEET_WIDTH - margins.left() - margins.right()
        needed = (
            _height_for(self.header, SHEET_WIDTH)
            + margins.top()
            + _height_for(self._content, content_width)
            + margins.bottom()
            + _height_for(self.footer, SHEET_WIDTH)
        )
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            needed = min(needed, int(screen.availableGeometry().height() * MAX_SCREEN_SHARE))
        self.resize(SHEET_WIDTH, needed)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        # ya en su pantalla: el tope de alto usa la pantalla real
        self._fit_to_content()
        if not self.primary_button.isEnabled():
            # nunca en Cancelar (Enter cerraria la hoja): al primer consecutivo
            first = next((w.start for w in self.rows.values() if not w.start.isHidden()), None)
            if first is not None:
                first.setFocus(Qt.FocusReason.OtherFocusReason)

    # --- exportacion en curso -------------------------------------------------------
    def set_exporting(self, exporting: bool, message: str = "") -> None:
        """Locks the sheet (footer, Esc, close, fields) while the workbook is written."""
        self._exporting = exporting
        self.set_busy(exporting)
        self._form.setEnabled(not exporting)
        if exporting:
            self.busy_overlay.start(message or strings.BUSY_DEFAULT_MESSAGE)
        else:
            self.busy_overlay.finish()

    @property
    def is_exporting(self) -> bool:
        return self._exporting

    # --- pie -------------------------------------------------------------------
    def can_export(self) -> bool:
        return not (self._exporting or self._success) and self._blocking_reason() is None

    def accept(self) -> None:
        """Primary button and Enter: ask for the export (the sheet stays open); after a
        successful export, Listo closes it."""
        if self._success:
            super().accept()
        elif self.can_export():
            self.export_requested.emit()

    def reject(self) -> None:
        # a medio escribir el archivo no se puede cerrar: el lote quedaria a medias
        if not self._exporting:
            super().reject()

    def _blocking_reason(self) -> str | None:
        """Why Exportar is disabled (its tooltip), or ``None`` when it can run."""
        if self._success:
            return None
        if self._exportable_count == 0:
            if self._mismatches is not None:
                return strings.EXPORT_ONLY_MISMATCHED
            return strings.EXPORT_NOTHING_READY
        if self._destination is None:
            return strings.EXPORT_NEEDS_DESTINATION
        if self._collisions is not None and not self.collision_notice.confirmed:
            return strings.EXPORT_NEEDS_COLLISION_CONFIRMATION
        return None

    def _sync_primary(self) -> None:
        reason = self._blocking_reason()
        self.set_primary_enabled(reason is None)
        self.primary_button.setToolTip(reason or "")
