"""Readiness footer: the one bold element — segmented bar of invoice states fused with
the export call to action.

Counts are keyed by status name (``ready``, ``mismatch``, ``incomplete``, ``blocked``);
``Readiness`` enum members are accepted too (``member.name.lower()``). Exportable =
ready + mismatch (mismatches need confirmation in the export sheet), so the button names
only the ready ones: that is what leaves with the confirmation box unchecked.

With a selection the whole footer describes the selection (caption, bar, legend, hint and
button); without one it describes every invoice.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum
from typing import Any

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from contabilizador.shared import strings
from contabilizador.ui import actions
from contabilizador.ui.theme import PAGE_MARGIN, STATUS_STYLES, TOKENS
from contabilizador.ui.widgets.common import make_label

SEGMENT_ORDER = ("ready", "mismatch", "incomplete", "blocked")
BAR_HEIGHT = 10
SEGMENT_GAP = 2

# Cuentas por estado: la llave es el nombre del estado o un miembro de ``Readiness``
type StatusCounts = Mapping[Any, int]


def normalize_key(key: object) -> str:
    if isinstance(key, Enum):
        return key.name.lower()
    return str(key).lower()


class SegmentedBar(QWidget):
    """Proportional segments in status colors; empty counts draw a hairline track."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts: dict[str, int] = {}
        self.setFixedHeight(BAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_counts(self, counts: Mapping[str, int]) -> None:
        self._counts = {key: int(counts.get(key, 0)) for key in SEGMENT_ORDER}
        self.update()

    def counts(self) -> dict[str, int]:
        return dict(self._counts)

    def segments(self) -> list[tuple[str, float]]:
        """(status, width in px) for every non-empty segment, in display order."""
        total = sum(self._counts.values())
        if total == 0:
            return []
        present = [key for key in SEGMENT_ORDER if self._counts.get(key, 0) > 0]
        usable = self.width() - SEGMENT_GAP * (len(present) - 1)
        return [(key, usable * self._counts[key] / total) for key in present]

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        return QSize(240, BAR_HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = BAR_HEIGHT / 2
        segments = self.segments()
        if not segments:
            painter.setBrush(QColor(TOKENS.hairline))
            painter.drawRoundedRect(QRectF(self.rect()), radius, radius)
            painter.end()
            return
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), radius, radius)
        painter.setClipPath(clip)
        x = 0.0
        for key, width in segments:
            painter.setBrush(QColor(STATUS_STYLES[key].fg))
            painter.drawRect(QRectF(x, 0, width, BAR_HEIGHT))
            x += width + SEGMENT_GAP
        painter.end()


class LegendDot(QWidget):
    """Dot in the color of a segment: ties each legend label to the bar above it."""

    SIZE = 8

    def __init__(self, status: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = STATUS_STYLES[status].fg
        self.setFixedSize(self.SIZE, self.SIZE)

    def color(self) -> str:
        return self._color

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawEllipse(self.rect())
        painter.end()


class ReadinessBar(QFrame):
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "readiness")
        self._counts: dict[str, int] = dict.fromkeys(SEGMENT_ORDER, 0)
        self._selection: int | None = None
        self._selected_total: int | None = None
        self._selection_counts: dict[str, int] | None = None
        self._blocked_by_supplier = True
        self._selection_blocked_by_supplier = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(PAGE_MARGIN, 14, PAGE_MARGIN, 14)
        layout.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.caption_label = make_label("", role="section")
        left.addWidget(self.caption_label)
        self.bar = SegmentedBar()
        left.addWidget(self.bar)
        legend = QHBoxLayout()
        legend.setSpacing(16)
        self._segment_labels: dict[str, QLabel] = {}
        self._legend_items: dict[str, QWidget] = {}
        self._legend_dots: dict[str, LegendDot] = {}
        for key in SEGMENT_ORDER:
            item, dot, label = self._build_legend_item(key)
            item.hide()
            self._legend_items[key] = item
            self._legend_dots[key] = dot
            self._segment_labels[key] = label
            legend.addWidget(item)
        legend.addStretch(1)
        left.addLayout(legend)
        self.secondary_label = make_label("", role="caption")
        self.secondary_label.hide()
        left.addWidget(self.secondary_label)
        layout.addLayout(left, 1)

        self.cta_button = QPushButton("")
        self.cta_button.setProperty("variant", "primary")
        self.cta_button.setProperty("size", "large")
        self.cta_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cta_button.clicked.connect(self.export_requested)
        layout.addWidget(self.cta_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._refresh()

    @staticmethod
    def _build_legend_item(key: str) -> tuple[QWidget, LegendDot, QLabel]:
        item = QWidget()
        layout = QHBoxLayout(item)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        dot = LegendDot(key)
        layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)
        label = make_label("", role="caption")
        layout.addWidget(label)
        return item, dot, label

    # --- datos ---------------------------------------------------------------
    @staticmethod
    def _normalized(counts: StatusCounts) -> dict[str, int]:
        normalized = {normalize_key(key): int(value) for key, value in counts.items()}
        return {key: normalized.get(key, 0) for key in SEGMENT_ORDER}

    def set_counts(self, counts: StatusCounts, *, blocked_by_supplier: bool = True) -> None:
        """``blocked_by_supplier=False`` when some blocked invoice is not waiting for a
        supplier: the legend then says only "bloqueadas"."""
        self._counts = self._normalized(counts)
        self._blocked_by_supplier = blocked_by_supplier
        self._refresh()

    def counts(self) -> dict[str, int]:
        """Counts of every invoice (the selection never changes them)."""
        return {key: value for key, value in self._counts.items() if value}

    def set_selection(
        self,
        selected_exportable: int | None,
        selected_total: int | None = None,
        *,
        counts: StatusCounts | None = None,
        blocked_by_supplier: bool = True,
    ) -> None:
        """Makes the footer describe the selection; ``None`` goes back to every invoice.

        ``selected_exportable`` is how many selected invoices can be exported (none: the
        button still exports every ready invoice and the footer stays global).
        ``selected_total`` is how many are selected, exportable or not; without it the caption
        counts only the exportable ones. ``counts`` is the readiness of the selected
        invoices: the bar, the legend and the hint then describe the selection and the
        button names its ready ones ("Exportar 3 seleccionadas"); without it only the caption
        and the button follow the selection. ``blocked_by_supplier`` is the selection's own,
        like in ``set_counts``.
        """
        self._selection = selected_exportable
        self._selected_total = selected_total
        self._selection_counts = self._normalized(counts) if counts is not None else None
        self._selection_blocked_by_supplier = blocked_by_supplier
        self._refresh()

    def segment_label(self, key: str) -> QLabel:
        return self._segment_labels[key]

    def legend_item(self, key: str) -> QWidget:
        return self._legend_items[key]

    def legend_dot(self, key: str) -> LegendDot:
        return self._legend_dots[key]

    # --- presentacion --------------------------------------------------------
    def _refresh(self) -> None:
        selected = self._selection if self._selection is not None and self._selection > 0 else None
        # Sin nada exportable en la seleccion el boton exporta todo lo listo: el pie sigue global
        scoped = self._selection_counts if selected is not None else None
        shown = scoped if scoped is not None else self._counts
        by_supplier = (
            self._selection_blocked_by_supplier if scoped is not None else self._blocked_by_supplier
        )
        ready = shown["ready"]
        mismatch = shown["mismatch"]
        incomplete = shown["incomplete"]
        blocked = shown["blocked"]
        exportable = ready + mismatch
        total = exportable + incomplete + blocked

        self.bar.set_counts(shown)
        for key, label in self._segment_labels.items():
            count = shown[key]
            label.setText(strings.readiness_legend(key, count, by_supplier=by_supplier))
            self._legend_items[key].setVisible(count > 0)

        if selected is not None:
            chosen = self._selected_total if self._selected_total is not None else selected
            self.caption_label.setText(strings.selection_caption(max(chosen, selected), selected))
            self.cta_button.setText(
                strings.export_selected_cta(ready if scoped is not None else selected)
            )
            enabled = True
        else:
            self.caption_label.setText(strings.readiness_caption(exportable, total))
            # Lo que sale con la casilla del descuadre sin marcar: el numero no cambia en la hoja
            self.cta_button.setText(strings.export_cta(ready))
            enabled = exportable > 0
        self.cta_button.setEnabled(enabled)

        reason = strings.export_disabled_reason(blocked, incomplete, by_supplier=by_supplier)
        if enabled:
            self.cta_button.setToolTip(actions.with_shortcut(strings.ACTION_EXPORT_SHORT, "export"))
        else:
            self.cta_button.setToolTip(reason)
        # La linea secundaria dice que sigue: confirmar descuadres o completar lo pendiente
        if mismatch:
            hint = strings.mismatch_needs_confirmation(mismatch)
        elif not enabled and total > 0:
            hint = reason
        else:
            hint = ""
        self.secondary_label.setText(hint)
        self.secondary_label.setVisible(bool(hint))
