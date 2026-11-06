"""Detail panel of the selected invoice (presentational).

The top is what can be acted on: document, status and the checklist of every problem with
its direct action. Reference data follows (supplier, CUFE, dates, totals XML vs computed,
the credit-note original). It only emits signals.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from contabilizador.exports.domain.errors import ExportProblem, ProblemKind
from contabilizador.exports.domain.readiness import STALE_PROBLEMS, Readiness
from contabilizador.invoices.domain.document import DocumentKind
from contabilizador.shared import strings
from contabilizador.ui.formatting import format_date, format_money, short_cufe
from contabilizador.ui.pages.invoices.rows import (
    FIELD_COST_CENTER,
    FIELD_PRODUCT,
    InvoiceRow,
    difference_text,
)
from contabilizador.ui.theme import STATUS_STYLES
from contabilizador.ui.widgets.common import (
    IconButton,
    hairline,
    icon_label,
    make_label,
    set_property,
)
from contabilizador.ui.widgets.status_pill import StatusPill

PANEL_MIN_WIDTH = 280
PANEL_MAX_WIDTH = 440
# Cada grupo (encabezado + sus filas) va junto; los grupos se separan mas entre si
BLOCK_GAP = 14
BLOCK_INNER_GAP = 4

PRODUCT_KINDS = frozenset({ProblemKind.MISSING_PRODUCT, ProblemKind.UNKNOWN_PRODUCT})
MISSING_KINDS = frozenset({ProblemKind.MISSING_PRODUCT, ProblemKind.MISSING_COST_CENTER})
UNKNOWN_KINDS = frozenset({ProblemKind.UNKNOWN_PRODUCT, ProblemKind.UNKNOWN_COST_CENTER})


class ProblemRow(QWidget):
    """One checklist line: status icon, sentence and (optionally) its direct action."""

    def __init__(
        self,
        status: str,
        text: str,
        action_label: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        style = STATUS_STYLES[status]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(icon_label(style.icon, style.fg, 16), 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.button: QPushButton | None = None
        if action_label:
            self.button = QPushButton(action_label)
            self.button.setProperty("variant", "ghost")
            self.button.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(self.button, 0, Qt.AlignmentFlag.AlignTop)


class DetailPanel(QFrame):
    configure_supplier_requested = Signal(str, str)  # nit, nombre
    copy_cufe_requested = Signal(str)
    show_in_folder_requested = Signal(object)  # Path del XML
    edit_line_requested = Signal(int, str)  # line_id, campo
    restore_suggestion_requested = Signal(list)  # ids de linea
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "detail")
        self.setMinimumWidth(PANEL_MIN_WIDTH)
        self.setMaximumWidth(PANEL_MAX_WIDTH)
        self._invoice: InvoiceRow | None = None
        self._problem_rows: list[ProblemRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.empty_label = make_label(strings.DETAIL_EMPTY, role="muted")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setContentsMargins(16, 32, 16, 32)
        outer.addWidget(self.empty_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.scroll_area.setWidget(self.content)
        outer.addWidget(self.scroll_area, 1)
        self._build_content()
        self.show_invoice(None)

    # --- construccion --------------------------------------------------------
    @staticmethod
    def _block(parent: QVBoxLayout, spacing: int = BLOCK_INNER_GAP) -> QVBoxLayout:
        """A group of related rows: tight inside, ``BLOCK_GAP`` away from the next group."""
        block = QVBoxLayout()
        block.setContentsMargins(0, 0, 0, 0)
        block.setSpacing(spacing)
        parent.addLayout(block)
        return block

    def _build_content(self) -> None:
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(BLOCK_GAP)

        # Documento, cuantas lineas trae y estado; el proveedor tiene su propio bloque
        heading = self._block(layout, 2)
        self.title_label = make_label("", role="section")
        self.title_label.setWordWrap(True)
        heading.addWidget(self.title_label)
        self.lines_label = make_label("", role="caption")
        heading.addWidget(self.lines_label)
        heading.addSpacing(6)
        self.pill = StatusPill("ready")
        heading.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignLeft)

        # Pendientes: lo unico accionable va primero, sin bajar con la barra
        pending = self._block(layout, 6)
        self.problems_title = make_label(strings.DETAIL_PROBLEMS, role="label")
        pending.addWidget(self.problems_title)
        self.problems_box = QWidget()
        self.problems_layout = QVBoxLayout(self.problems_box)
        self.problems_layout.setContentsMargins(0, 0, 0, 0)
        self.problems_layout.setSpacing(8)
        pending.addWidget(self.problems_box)
        layout.addWidget(hairline())

        # Proveedor
        supplier = self._block(layout)
        supplier.addWidget(make_label(strings.DETAIL_SUPPLIER, role="label"))
        self.supplier_name_label = make_label("", role="value")
        self.supplier_name_label.setWordWrap(True)
        supplier.addWidget(self.supplier_name_label)
        supplier_row = QHBoxLayout()
        supplier_row.setSpacing(8)
        self.supplier_nit_label = make_label("", role="caption")
        supplier_row.addWidget(self.supplier_nit_label)
        # Icono + texto, como todo estado de la app (una nota gris no se distingue)
        self.supplier_pill = StatusPill("ready", strings.DETAIL_SUPPLIER_CONFIGURED)
        supplier_row.addWidget(self.supplier_pill)
        supplier_row.addStretch(1)
        supplier.addLayout(supplier_row)
        self.configure_button = QPushButton(strings.ACTION_CONFIGURE_SUPPLIER)
        self.configure_button.setProperty("variant", "secondary")
        self.configure_button.clicked.connect(self._on_configure)
        supplier.addWidget(self.configure_button, 0, Qt.AlignmentFlag.AlignLeft)

        # Fechas
        dates_block = self._block(layout)
        dates_block.addWidget(make_label(strings.DETAIL_DATES, role="label"))
        dates = QGridLayout()
        dates.setHorizontalSpacing(12)
        dates.setVerticalSpacing(4)
        self.issue_label = self._value_cell(dates, 0, strings.COLUMN_ISSUE_DATE)
        self.due_label = self._value_cell(dates, 1, strings.COLUMN_DUE_DATE)
        dates_block.addLayout(dates)

        # Totales: lo que explica un descuadre se lee antes que el CUFE
        totals_block = self._block(layout)
        totals_block.addWidget(make_label(strings.DETAIL_TOTALS, role="label"))
        totals = QGridLayout()
        totals.setHorizontalSpacing(12)
        totals.setVerticalSpacing(4)
        self.total_xml_label = self._value_cell(totals, 0, strings.DETAIL_TOTAL_XML, money=True)
        self.total_computed_label = self._value_cell(
            totals, 1, strings.DETAIL_TOTAL_COMPUTED, money=True
        )
        self.difference_label = self._value_cell(totals, 2, strings.DETAIL_DIFFERENCE, money=True)
        totals_block.addLayout(totals)
        self.mismatch_note = make_label(strings.DETAIL_MISMATCH_NOTE, role="caption")
        self.mismatch_note.setWordWrap(True)
        totals_block.addWidget(self.mismatch_note)
        self.original_label = make_label("", role="caption")
        self.original_label.setWordWrap(True)
        totals_block.addWidget(self.original_label)

        # Asignacion: restablecer actua sobre lo asignado a mano, no es un pendiente
        self.assignment_box = QWidget()
        assignment = QVBoxLayout(self.assignment_box)
        assignment.setContentsMargins(0, 0, 0, 0)
        assignment.setSpacing(BLOCK_INNER_GAP)
        self.assignment_title = make_label(strings.DETAIL_ASSIGNMENT, role="label")
        assignment.addWidget(self.assignment_title)
        self.assignment_label = make_label(strings.PROVENANCE_MANUAL, role="caption")
        assignment.addWidget(self.assignment_label)
        self.restore_button = QPushButton(strings.ACTION_RESTORE_SUGGESTION)
        self.restore_button.setProperty("variant", "secondary")
        self.restore_button.clicked.connect(self._on_restore)
        assignment.addWidget(self.restore_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.assignment_box)

        # CUFE: solo sirve para copiarlo
        cufe_block = self._block(layout)
        cufe_block.addWidget(make_label(strings.DETAIL_CUFE, role="label"))
        cufe_row = QHBoxLayout()
        cufe_row.setSpacing(6)
        self.cufe_label = make_label("", role="value")
        self.cufe_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cufe_row.addWidget(self.cufe_label, 1)
        self.copy_button = IconButton("copy", strings.ACTION_COPY_CUFE)
        self.copy_button.clicked.connect(self._on_copy)
        cufe_row.addWidget(self.copy_button)
        cufe_block.addLayout(cufe_row)

        layout.addStretch(1)
        self.show_xml_button = QPushButton(strings.ACTION_SHOW_XML)
        self.show_xml_button.setProperty("variant", "secondary")
        self.show_xml_button.clicked.connect(self._on_show_xml)
        layout.addWidget(self.show_xml_button, 0, Qt.AlignmentFlag.AlignLeft)

    @staticmethod
    def _value_cell(grid: QGridLayout, row: int, caption: str, *, money: bool = False) -> QLabel:
        grid.addWidget(make_label(caption, role="label"), row, 0)
        value = make_label("", role="money" if money else "value")
        value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        value.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            if money
            else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        grid.addWidget(value, row, 1)
        return value

    # --- datos ---------------------------------------------------------------
    def invoice(self) -> InvoiceRow | None:
        return self._invoice

    def show_invoice(self, row: InvoiceRow | None) -> None:
        self._invoice = row
        self.empty_label.setVisible(row is None)
        self.scroll_area.setVisible(row is not None)
        if row is None:
            return
        self.title_label.setText(row.label)
        self.lines_label.setText(strings.lines_count(row.line_count))
        self.pill.set_status(row.pill_status, row.pill_text)
        self.supplier_name_label.setText(row.supplier_name)
        self.supplier_nit_label.setText(row.supplier_nit)
        if row.supplier_configured:
            self.supplier_pill.set_status("ready", strings.DETAIL_SUPPLIER_CONFIGURED)
        else:
            self.supplier_pill.set_status("blocked", strings.DETAIL_SUPPLIER_UNCONFIGURED)
        self.configure_button.setVisible(not row.supplier_configured)
        self.cufe_label.setText(short_cufe(row.cufe))
        self.cufe_label.setToolTip(row.cufe)
        self.issue_label.setText(format_date(row.issue_date))
        self.due_label.setText(format_date(row.due_date))
        totals = row.totals
        self.total_xml_label.setText(format_money(totals.expected))
        self.total_computed_label.setText(format_money(totals.computed))
        self.difference_label.setText(difference_text(totals))
        set_property(self.difference_label, "status", None if totals.matches else "mismatch")
        self.mismatch_note.setVisible(row.readiness is Readiness.MISMATCH)
        is_credit_note = row.kind is DocumentKind.CREDIT_NOTE
        self.original_label.setVisible(is_credit_note)
        if is_credit_note:
            self.original_label.setText(
                strings.DETAIL_ORIGINAL_FOUND
                if row.original_found
                else strings.DETAIL_ORIGINAL_MISSING
            )
        self.assignment_box.setVisible(row.has_manual)
        self._rebuild_problems(row)

    def problem_rows(self) -> list[ProblemRow]:
        return list(self._problem_rows)

    # --- pendientes ----------------------------------------------------------
    def _rebuild_problems(self, row: InvoiceRow) -> None:
        for old in self._problem_rows:
            self.problems_layout.removeWidget(old)
            old.deleteLater()
        self._problem_rows = []
        if not row.problems:
            # Un descuadre no es un problema del dominio, pero tampoco esta "todo listo"
            if row.readiness is Readiness.MISMATCH:
                self._add_problem("mismatch", strings.FLAG_TOTALS_MISMATCH)
            else:
                self._add_problem("ready", strings.DETAIL_NO_PROBLEMS)
            return
        for problem in row.problems:
            action = self._action_for(row, problem)
            status = "incomplete" if problem.kind in MISSING_KINDS else "blocked"
            text = strings.problem_message(problem.kind.value, problem.line_number, problem.detail)
            widget = self._add_problem(status, text, action[0] if action else None)
            if action and widget.button is not None:
                widget.button.clicked.connect(action[1])

    def _add_problem(self, status: str, text: str, action_label: str | None = None) -> ProblemRow:
        widget = ProblemRow(status, text, action_label)
        self.problems_layout.addWidget(widget)
        self._problem_rows.append(widget)
        return widget

    def _action_for(
        self, row: InvoiceRow, problem: ExportProblem
    ) -> tuple[str, Callable[[], None]] | None:
        kind = problem.kind
        if kind is ProblemKind.UNCONFIGURED_SUPPLIER:
            return strings.ACTION_CONFIGURE_SUPPLIER, self._on_configure
        if kind in STALE_PROBLEMS:
            return strings.ACTION_REFRESH, self.refresh_requested.emit
        if problem.line_number is None or problem.line_number > len(row.lines):
            return None
        line_id = row.lines[problem.line_number - 1].line_id
        field = FIELD_PRODUCT if kind in PRODUCT_KINDS else FIELD_COST_CENTER
        label = strings.ACTION_CHOOSE_ANOTHER if kind in UNKNOWN_KINDS else strings.ACTION_CHOOSE
        return label, lambda: self.edit_line_requested.emit(line_id, field)

    # --- acciones ------------------------------------------------------------
    def _on_configure(self) -> None:
        if self._invoice is not None:
            self.configure_supplier_requested.emit(
                self._invoice.supplier_nit, self._invoice.supplier_name
            )

    def _on_copy(self) -> None:
        if self._invoice is not None:
            self.copy_cufe_requested.emit(self._invoice.cufe)

    def _on_show_xml(self) -> None:
        if self._invoice is not None:
            self.show_in_folder_requested.emit(self._invoice.source_file)

    def _on_restore(self) -> None:
        if self._invoice is not None:
            ids = [line.line_id for line in self._invoice.lines if line.is_manual]
            if ids:
                self.restore_suggestion_requested.emit(ids)
