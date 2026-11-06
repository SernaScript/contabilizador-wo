"""Primeros pasos page: the first-run checklist (company, catalogs, first import).

Presentational: the container tells which steps are done or locked with ``set_steps``
and reacts to ``step_triggered``. The three steps are a real sequence, so they are the one
place besides the invoices stepper that numbers things.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui.theme import (
    FORM_PAGE_GAP,
    PAGE_MARGIN,
    PAGE_MARGIN_BOTTOM,
    PAGE_MARGIN_TOP,
    TOKENS,
)
from contabilizador.ui.widgets.common import flag, hairline, make_label, set_property
from contabilizador.ui.widgets.status_pill import StatusPill

STEP_COMPANY = "company"
STEP_CATALOG = "catalog"
STEP_IMPORT = "import"

COLUMN_WIDTH = 640

# El titulo de un paso bloqueado baja de tono; el tema no tiene este caso
_LOCKED_QSS = f"""
QLabel[role="section"][locked="true"] {{ color: {TOKENS.slate}; }}
"""


@dataclass(frozen=True, slots=True)
class StepStatus:
    """What one step looks like.

    Attributes:
        done: the step is complete.
        locked: it needs a company that does not exist yet, so its button is disabled.
        detail: one line of partial progress ("Faltan centros de costo.").
    """

    done: bool = False
    locked: bool = False
    detail: str = ""


FIRST_RUN = (StepStatus(), StepStatus(locked=True), StepStatus(locked=True))


class StepRow(QWidget):
    """One checklist row: indicator, title, explanation, and the action or the done mark."""

    def __init__(
        self,
        key: str,
        number: int,
        title: str,
        text: str,
        action_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.state = "todo"
        self.locked = False
        self._number = number

        self.indicator: QLabel = make_label(str(number), role="step-number")
        self.indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label = make_label(title, role="section")
        self.text_label = make_label(text, role="muted")
        self.text_label.setWordWrap(True)
        self.detail_label = make_label("", role="hint")
        self.detail_label.setWordWrap(True)
        self.detail_label.hide()
        self.action_button = QPushButton(action_label)
        # Enter tambien activa el boton enfocado (fuera de un dialogo no lo hace por defecto)
        self.action_button.setAutoDefault(True)
        self.done_pill = StatusPill("ready", strings.STEP_DONE)
        self.done_pill.hide()

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        texts.addWidget(self.title_label)
        texts.addWidget(self.text_label)
        texts.addWidget(self.detail_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(16)
        layout.addWidget(self.indicator, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(texts, 1)
        layout.addWidget(self.action_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.done_pill, 0, Qt.AlignmentFlag.AlignVCenter)

    def apply(self, status: StepStatus, *, current: bool) -> None:
        self.locked = status.locked and not status.done
        self.state = "done" if status.done else ("current" if current else "todo")
        # La secuencia 1-2-3 siempre se ve; el estado lo da el indicador y la etiqueta "Hecho"
        set_property(self.indicator, "state", self.state)
        set_property(self.title_label, "locked", flag(self.locked))
        # Bloqueado: la razon queda a la vista, no solo en un tooltip
        detail = strings.ONBOARDING_NEEDS_COMPANY if self.locked else status.detail
        self.detail_label.setText(detail)
        self.detail_label.setVisible(bool(detail))
        self.action_button.setVisible(not status.done)
        self.action_button.setEnabled(not self.locked)
        # "secondary" no tiene aspecto deshabilitado en el tema; el estilo neutro si
        if self.locked:
            variant = "neutral"
        else:
            variant = "primary" if current and not status.done else "secondary"
        set_property(self.action_button, "variant", variant)
        self.done_pill.setVisible(status.done)


class OnboardingView(QWidget):
    step_triggered = Signal(str)  # STEP_COMPANY, STEP_CATALOG or STEP_IMPORT
    finish_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_LOCKED_QSS)
        self.title_label = make_label(strings.ONBOARDING_TITLE, role="page-title")
        self.purpose_label = make_label(strings.ONBOARDING_PURPOSE, role="purpose")
        definitions = (
            (
                STEP_COMPANY,
                strings.ONBOARDING_STEP_COMPANY,
                strings.ONBOARDING_STEP_COMPANY_TEXT,
                strings.ONBOARDING_ACTION_COMPANY,
            ),
            (
                STEP_CATALOG,
                strings.ONBOARDING_STEP_CATALOG,
                strings.ONBOARDING_STEP_CATALOG_TEXT,
                strings.ONBOARDING_ACTION_CATALOG,
            ),
            (
                STEP_IMPORT,
                strings.ONBOARDING_STEP_IMPORT,
                strings.ONBOARDING_STEP_IMPORT_TEXT,
                strings.ONBOARDING_ACTION_IMPORT,
            ),
        )
        self._rows = [
            StepRow(key, number, title, text, action)
            for number, (key, title, text, action) in enumerate(definitions, start=1)
        ]
        self._all_done = False

        root = QVBoxLayout(self)
        root.setContentsMargins(PAGE_MARGIN, PAGE_MARGIN_TOP, PAGE_MARGIN, PAGE_MARGIN_BOTTOM)
        root.setSpacing(FORM_PAGE_GAP)
        header = QFrame()
        header.setProperty("role", "page-header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.purpose_label)
        root.addWidget(header)

        column = QWidget()
        column.setMaximumWidth(COLUMN_WIDTH)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(0)
        for position, row in enumerate(self._rows):
            if position:
                column_layout.addWidget(hairline())
            column_layout.addWidget(row)
            row.action_button.clicked.connect(lambda _checked=False, k=row.key: self._trigger(k))
        column_layout.addWidget(hairline())
        column_layout.addSpacing(8)
        self.finish_panel = self._build_finish_panel()
        column_layout.addWidget(self.finish_panel)
        column_layout.addStretch(1)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(column, 100, Qt.AlignmentFlag.AlignTop)
        body.addStretch(1)
        root.addLayout(body, 1)

        self.set_steps(FIRST_RUN)

    def _build_finish_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(4)
        self.finish_title_label = make_label(strings.ONBOARDING_ALL_DONE_TITLE, role="section")
        self.finish_text_label = make_label(strings.ONBOARDING_ALL_DONE_TEXT, role="muted")
        self.finish_text_label.setWordWrap(True)
        self.finish_button = QPushButton(strings.ONBOARDING_ACTION_FINISH)
        self.finish_button.setProperty("variant", "primary")
        self.finish_button.setAutoDefault(True)
        self.finish_button.clicked.connect(self.finish_requested)
        layout.addWidget(self.finish_title_label)
        layout.addWidget(self.finish_text_label)
        layout.addSpacing(12)
        layout.addWidget(self.finish_button, 0, Qt.AlignmentFlag.AlignLeft)
        panel.hide()
        return panel

    # --- consulta -----------------------------------------------------------
    def steps(self) -> list[StepRow]:
        return list(self._rows)

    def step(self, key: str) -> StepRow:
        return next(row for row in self._rows if row.key == key)

    @property
    def all_done(self) -> bool:
        return self._all_done

    # --- estado -------------------------------------------------------------
    def set_steps(self, statuses: Sequence[StepStatus]) -> None:
        """One status per step, in order; the first step not done becomes the current one."""
        if len(statuses) != len(self._rows):
            raise ValueError(f"{len(self._rows)} step statuses are required")
        current = next((i for i, status in enumerate(statuses) if not status.done), None)
        for position, (row, status) in enumerate(zip(self._rows, statuses, strict=True)):
            row.apply(status, current=position == current)
        self._all_done = current is None
        self.finish_panel.setVisible(self._all_done)

    def _trigger(self, key: str) -> None:
        self.step_triggered.emit(key)
