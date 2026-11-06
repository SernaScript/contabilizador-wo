"""Company switcher for the sidebar: combo of companies plus "Nueva empresa"."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QPushButton, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui import icons
from contabilizador.ui.theme import TOKENS


class CompanySwitcher(QWidget):
    company_changed = Signal(object)  # int | None
    new_company_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current: int | None = None
        self._locked = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.combo = QComboBox()
        self.combo.setPlaceholderText(strings.COMPANY_SWITCHER_PLACEHOLDER)
        self.combo.setAccessibleName(strings.LABEL_COMPANY)
        self.combo.setToolTip(strings.LABEL_COMPANY)
        layout.addWidget(self.combo)
        self.new_button = QPushButton(strings.ACTION_NEW_COMPANY)
        self.new_button.setProperty("variant", "ghost")
        self.new_button.setIcon(icons.icon("plus", TOKENS.blue_hover))
        layout.addWidget(self.new_button)
        self.combo.currentIndexChanged.connect(self._on_index_changed)
        self.new_button.clicked.connect(self.new_company_requested)
        self._sync_enabled()

    def set_companies(
        self, companies: Sequence[tuple[int, str]], current: int | None = None
    ) -> None:
        wanted = current if current is not None else self._current
        ids = [company_id for company_id, _name in companies]
        if wanted not in ids:
            wanted = ids[0] if ids else None
        self.combo.blockSignals(True)
        self.combo.clear()
        for company_id, name in companies:
            self.combo.addItem(name, company_id)
        self.combo.setCurrentIndex(self.combo.findData(wanted) if wanted is not None else -1)
        self.combo.blockSignals(False)
        self._sync_enabled()
        self._update_current()

    def current_company_id(self) -> int | None:
        return self._current

    def set_current(self, company_id: int | None) -> None:
        position = self.combo.findData(company_id) if company_id is not None else -1
        if position == self.combo.currentIndex():
            self._update_current()
            return
        self.combo.setCurrentIndex(position)

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self._sync_enabled()

    def _sync_enabled(self) -> None:
        has_companies = self.combo.count() > 0
        self.combo.setEnabled(has_companies and not self._locked)
        self.new_button.setEnabled(not self._locked)
        if self._locked:
            self.combo.setToolTip(strings.COMPANY_SWITCHER_LOCKED_HINT)
        elif not has_companies:
            self.combo.setToolTip(strings.NO_COMPANIES_HINT)
        else:
            self.combo.setToolTip(strings.LABEL_COMPANY)

    def _on_index_changed(self, _index: int) -> None:
        self._update_current()

    def _update_current(self) -> None:
        data = self.combo.currentData()
        value = int(data) if data is not None else None
        if value != self._current:
            self._current = value
            self.company_changed.emit(value)
