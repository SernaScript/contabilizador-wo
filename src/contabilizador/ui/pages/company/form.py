"""Company fields: World Office data and defaults.

Presentational and shared by the Empresa page and the new company dialog. It knows nothing
about use cases: the owner loads values with ``set_values`` and reads them back with
``values``.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from contabilizador.companies.application.use_cases import DEFAULT_UNIT, DEFAULT_WAREHOUSE
from contabilizador.companies.domain.company import DEFAULT_PAYMENT_FORM
from contabilizador.shared import strings
from contabilizador.ui.widgets.common import flag, make_label, set_property

SECTION_GAP = 36
FIELD_GAP = 14
TITLE_GAP = 12


@dataclass(frozen=True, slots=True)
class CompanyValues:
    name: str
    internal_third_party_id: str
    warehouse: str
    unit: str
    payment_form: str

    @classmethod
    def defaults(cls) -> CompanyValues:
        """Blank name and third party plus the usual World Office defaults."""
        return cls("", "", DEFAULT_WAREHOUSE, DEFAULT_UNIT, DEFAULT_PAYMENT_FORM)


class CompanyForm(QWidget):
    edited = Signal()
    submitted = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._loading = False
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(strings.COMPANY_NAME_PLACEHOLDER)
        self.third_party_edit = QLineEdit()
        self.warehouse_edit = QLineEdit()
        self.unit_edit = QLineEdit()
        self.payment_edit = QLineEdit()
        self.name_error_label: QLabel = make_label("", role="error")
        self.name_error_label.setWordWrap(True)
        # El mensaje tiene su fila reservada: al aparecer no mueve los campos ni aprieta un
        # dialogo que ya esta abierto
        policy = self.name_error_label.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.name_error_label.setSizePolicy(policy)
        self.name_error_label.setMinimumHeight(self.name_error_label.fontMetrics().height())
        self.name_error_label.hide()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(make_label(strings.SECTION_WORLD_OFFICE, role="section"))
        root.addSpacing(TITLE_GAP)
        root.addWidget(self._field(strings.FIELD_COMPANY_NAME, self.name_edit))
        root.addSpacing(3)
        root.addWidget(self.name_error_label)
        root.addSpacing(6)
        root.addWidget(self._field(strings.FIELD_INTERNAL_THIRD_PARTY, self.third_party_edit))
        root.addSpacing(SECTION_GAP)
        root.addWidget(make_label(strings.SECTION_DEFAULTS, role="section"))
        root.addSpacing(TITLE_GAP)
        root.addLayout(self._defaults_row())

        # Una empresa nueva arranca con los valores habituales de World Office
        self._baseline = CompanyValues.defaults()
        self.set_values(self._baseline)
        for edit in self._edits():
            edit.textChanged.connect(self._on_text_changed)
            edit.returnPressed.connect(self.submitted)
        self.name_edit.textChanged.connect(self._on_name_changed)

    # --- construccion -------------------------------------------------------
    def _edits(self) -> tuple[QLineEdit, ...]:
        return (
            self.name_edit,
            self.third_party_edit,
            self.warehouse_edit,
            self.unit_edit,
            self.payment_edit,
        )

    @staticmethod
    def _field(label_text: str, edit: QLineEdit) -> QWidget:
        """Label above its input, bound together for keyboard and screen readers."""
        label = make_label(label_text, role="label")
        label.setBuddy(edit)
        edit.setAccessibleName(label_text)
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(label)
        layout.addWidget(edit)
        return field

    def _defaults_row(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(FIELD_GAP)
        fields = (
            (strings.FIELD_WAREHOUSE, self.warehouse_edit),
            (strings.FIELD_UNIT, self.unit_edit),
            (strings.FIELD_PAYMENT_FORM, self.payment_edit),
        )
        for column, (text, edit) in enumerate(fields):
            grid.addWidget(self._field(text, edit), 0, column)
            grid.setColumnStretch(column, 1)
        return grid

    # --- valores ------------------------------------------------------------
    def values(self) -> CompanyValues:
        return CompanyValues(
            name=self.name_edit.text().strip(),
            internal_third_party_id=self.third_party_edit.text().strip(),
            warehouse=self.warehouse_edit.text().strip(),
            unit=self.unit_edit.text().strip(),
            payment_form=self.payment_edit.text().strip(),
        )

    def set_values(self, values: CompanyValues) -> None:
        """Loads the fields; the loaded values become the baseline of ``is_dirty``."""
        self._loading = True
        try:
            self.name_edit.setText(values.name)
            self.third_party_edit.setText(values.internal_third_party_id)
            self.warehouse_edit.setText(values.warehouse)
            self.unit_edit.setText(values.unit)
            self.payment_edit.setText(values.payment_form)
        finally:
            self._loading = False
        self._baseline = self.values()
        self.set_name_error(None)

    def mark_saved(self, values: CompanyValues) -> None:
        """The saved values become the baseline; fields are not touched, so anything typed
        after the save request still counts as an unsaved change."""
        self._baseline = values

    def is_dirty(self) -> bool:
        return self.values() != self._baseline

    def focus_name(self) -> None:
        self.name_edit.setFocus()

    # --- validacion ---------------------------------------------------------
    def validate(self) -> bool:
        """Marks what is wrong next to its field; only the name is required."""
        if not self.name_edit.text().strip():
            self.set_name_error(strings.COMPANY_NAME_REQUIRED)
            self.focus_name()
            return False
        self.set_name_error(None)
        return True

    def set_name_error(self, text: str | None) -> None:
        shown = bool(text)
        self.name_error_label.setText(text or "")
        self.name_error_label.setVisible(shown)
        self.name_edit.setAccessibleDescription(text or "")
        set_property(self.name_edit, "invalid", flag(shown))

    # --- eventos ------------------------------------------------------------
    def _on_text_changed(self, _text: str) -> None:
        if not self._loading:
            self.edited.emit()

    def _on_name_changed(self, _text: str) -> None:
        # El error del nombre desaparece al corregirlo, no al tocar otros campos
        if not self.name_error_label.isHidden():
            self.set_name_error(None)
