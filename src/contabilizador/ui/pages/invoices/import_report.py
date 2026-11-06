"""Import report: what was not imported and why (presentational dialog)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from contabilizador.invoices.application.import_invoice_files import ImportReport
from contabilizador.shared import strings
from contabilizador.ui.formatting import document_label
from contabilizador.ui.widgets.common import make_label
from contabilizador.ui.widgets.sheet import Sheet


def has_details(report: ImportReport) -> bool:
    """True when the toast should offer "Ver detalle"."""
    return bool(
        report.duplicates or report.ignored or report.failed or report.credit_notes_without_original
    )


def _sections(report: ImportReport) -> list[tuple[str, list[str]]]:
    sections: list[tuple[str, list[str]]] = []
    if report.duplicates:
        sections.append(
            (
                strings.IMPORT_REPORT_DUPLICATES,
                [
                    strings.duplicate_detail(
                        document_label(d.supplier_prefix, d.supplier_number), d.supplier_name
                    )
                    for d in report.duplicates
                ],
            )
        )
    if report.ignored:
        sections.append(
            (strings.IMPORT_REPORT_IGNORED, [f"{f.source}: {f.reason}" for f in report.ignored])
        )
    if report.failed:
        sections.append(
            (strings.IMPORT_REPORT_FAILED, [f"{f.source}: {f.reason}" for f in report.failed])
        )
    if report.credit_notes_without_original:
        sections.append(
            (
                strings.IMPORT_REPORT_ORPHANS,
                [
                    strings.orphan_credit_note_detail(
                        document_label(d.supplier_prefix, d.supplier_number),
                        d.billing_reference_cufe or "",
                    )
                    for d in report.credit_notes_without_original
                ],
            )
        )
    return sections


class ImportReportDialog(Sheet):
    def __init__(self, report: ImportReport, parent: QWidget | None = None) -> None:
        super().__init__(
            strings.IMPORT_REPORT_TITLE, primary_label=strings.ACTION_CLOSE, parent=parent
        )
        self.cancel_button.hide()
        self.sections: dict[str, QLabel] = {}
        self.summary_label = make_label(
            strings.import_result_sentence(
                len(report.imported),
                len(report.duplicates),
                len(report.ignored),
                len(report.failed),
            ),
            role="value",
        )
        self.summary_label.setWordWrap(True)
        self.body_layout.addWidget(self.summary_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(6)
        self.empty_label = make_label(strings.IMPORT_REPORT_EMPTY, role="muted")
        self.empty_label.setWordWrap(True)
        inner_layout.addWidget(self.empty_label)
        for title, lines in _sections(report):
            inner_layout.addSpacing(6)
            inner_layout.addWidget(make_label(title, role="section"))
            label = QLabel("\n".join(lines))
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            inner_layout.addWidget(label)
            self.sections[title] = label
        self.empty_label.setVisible(not self.sections)
        inner_layout.addStretch(1)
        scroll.setWidget(inner)
        scroll.setMinimumHeight(160)
        self.body_layout.addWidget(scroll, 1)
