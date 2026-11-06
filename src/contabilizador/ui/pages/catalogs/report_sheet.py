"""Import report: what the Excel import did and which rows it skipped (and why)."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QListWidget, QWidget

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared import strings
from contabilizador.ui.pages.catalogs.rows import ImportOutcome
from contabilizador.ui.widgets import Sheet, make_label

LIST_MIN_HEIGHT = 120
LIST_MAX_HEIGHT = 260


class CatalogImportReportSheet(Sheet):
    def __init__(
        self, kind: CatalogKind, outcome: ImportOutcome, parent: QWidget | None = None
    ) -> None:
        super().__init__(
            strings.CATALOG_IMPORT_TITLE, primary_label=strings.ACTION_DONE, parent=parent
        )
        self.cancel_button.hide()
        invalid = outcome.invalid

        sentence = strings.catalog_import_sentence(
            kind, outcome.created, outcome.updated, len(invalid)
        )
        self.summary_label = make_label(sentence, role="section")
        self.summary_label.setWordWrap(True)
        self.body_layout.addWidget(self.summary_label)

        self.invalid_heading = make_label(strings.CATALOG_IMPORT_INVALID_ROWS, role="label")
        self.invalid_list = QListWidget()
        self.invalid_list.setAccessibleName(strings.CATALOG_IMPORT_INVALID_ROWS)
        self.invalid_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.invalid_list.setSpacing(2)
        self.invalid_list.setMinimumHeight(LIST_MIN_HEIGHT)
        self.invalid_list.setMaximumHeight(LIST_MAX_HEIGHT)
        for row_number, reason in invalid:
            self.invalid_list.addItem(strings.catalog_invalid_row(row_number, reason))
        self.fix_hint_label = make_label(strings.CATALOG_IMPORT_FIX_HINT, role="hint")
        self.fix_hint_label.setWordWrap(True)
        for widget in (self.invalid_heading, self.invalid_list, self.fix_hint_label):
            widget.setVisible(bool(invalid))
            self.body_layout.addWidget(widget)
