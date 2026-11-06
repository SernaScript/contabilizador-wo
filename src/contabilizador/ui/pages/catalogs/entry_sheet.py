"""Entry sheet: create a product or cost center, or rename one (its code never changes)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from contabilizador.catalog.application.import_catalog import CatalogKind
from contabilizador.shared import strings
from contabilizador.ui.widgets import Sheet, make_label
from contabilizador.ui.widgets.common import flag, set_property


class CatalogEntrySheet(Sheet):
    """Form with code and name. ``submitted`` fires once the values are valid; the
    container saves and then calls :meth:`close_saved` or :meth:`show_error`."""

    submitted = Signal(str, str)  # (codigo, nombre)

    def __init__(
        self,
        kind: CatalogKind,
        *,
        code: str | None = None,
        name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        editing = code is not None
        title = strings.catalog_edit_title(kind) if editing else strings.catalog_new_title(kind)
        super().__init__(title, primary_label=strings.ACTION_SAVE, parent=parent)
        self.kind = kind
        self._original_code = code
        self.code_edit: QLineEdit | None = None
        self.code_value_label: QLabel | None = None

        self.body_layout.setSpacing(4)
        code_label = make_label(strings.COLUMN_CODE, role="label")
        self.body_layout.addWidget(code_label)
        if code is None:
            self.code_edit = QLineEdit()
            self.code_edit.setAccessibleName(strings.COLUMN_CODE)
            self.code_edit.textChanged.connect(self._clear_invalid)
            code_label.setBuddy(self.code_edit)
            self.body_layout.addWidget(self.code_edit)
        else:
            # El codigo no cambia: se muestra como texto, sin apariencia de campo editable
            self.code_value_label = make_label(code, role="value")
            self.code_value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self.body_layout.addWidget(self.code_value_label)
        hint = strings.CATALOG_CODE_IMMUTABLE if editing else strings.CATALOG_ENTRY_CODE_HINT
        self.hint_label = make_label(hint, role="hint")
        self.hint_label.setWordWrap(True)
        self.body_layout.addWidget(self.hint_label)
        self.body_layout.addSpacing(12)

        name_label = make_label(strings.COLUMN_NAME, role="label")
        self.body_layout.addWidget(name_label)
        self.name_edit = QLineEdit(name)
        self.name_edit.setAccessibleName(strings.COLUMN_NAME)
        self.name_edit.textChanged.connect(self._clear_invalid)
        name_label.setBuddy(self.name_edit)
        self.body_layout.addWidget(self.name_edit)

    # --- envio ---------------------------------------------------------------
    def accept(self) -> None:
        """Validates and announces the values; the dialog closes in :meth:`close_saved`."""
        code = self._original_code if self.code_edit is None else self.code_edit.text().strip()
        name = self.name_edit.text().strip()
        if not code:
            self.show_error(strings.CATALOG_CODE_REQUIRED, field="code")
        elif not name:
            self.show_error(strings.CATALOG_NAME_REQUIRED, field="name")
        else:
            self.submitted.emit(code, name)

    def close_saved(self) -> None:
        super().accept()

    def set_saving(self, saving: bool) -> None:
        self.set_busy(saving)
        self.name_edit.setEnabled(not saving)
        if self.code_edit is not None:
            self.code_edit.setEnabled(not saving)

    def show_error(self, text: str, *, field: str | None = None) -> None:
        """Footer message plus the offending field marked and focused."""
        self.set_error(text)
        target = self.code_edit if field == "code" else self.name_edit if field == "name" else None
        if target is not None:
            set_property(target, "invalid", flag(True))
            target.setFocus(Qt.FocusReason.OtherFocusReason)

    def _clear_invalid(self) -> None:
        self.set_error(None)
        for edit in (self.code_edit, self.name_edit):
            if edit is not None and edit.property("invalid") != flag(False):
                set_property(edit, "invalid", flag(False))

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        # Sheet enfoca el boton primario; un formulario empieza en su primer campo
        (self.code_edit or self.name_edit).setFocus(Qt.FocusReason.OtherFocusReason)
