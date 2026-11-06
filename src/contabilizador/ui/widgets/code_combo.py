"""Searchable code combo: one list with the preferred codes first, a separator, then the
rest of the catalog. Free text is rejected; ``committed(code)`` fires on user choice.

Usable directly or as an item-delegate editor (read ``current_code()`` in ``setModelData``
and connect ``committed`` to commit/close the editor).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QComboBox, QCompleter, QWidget

from contabilizador.shared import strings
from contabilizador.ui.formatting import code_and_name

SEPARATOR_MARK = "separator"


@dataclass(frozen=True, slots=True)
class CodeItem:
    code: str
    name: str = ""

    @property
    def display(self) -> str:
        return code_and_name(self.code, self.name)


class CodeCombo(QComboBox):
    committed = Signal(object)  # str | None

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        allow_empty: bool = False,
        empty_label: str = strings.PLACEHOLDER_NONE,
    ) -> None:
        super().__init__(parent)
        self._allow_empty = allow_empty
        self._empty_label = empty_label
        self._current_code: str | None = None
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(18)
        self._completer = QCompleter(self.model(), self)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompleter(self._completer)
        self.activated.connect(self._on_activated)
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.editingFinished.connect(self._on_editing_finished)
            line_edit.installEventFilter(self)
        self.setCurrentIndex(-1)

    # --- datos ---------------------------------------------------------------
    def set_items(self, preferred: Sequence[CodeItem], rest: Sequence[CodeItem] = ()) -> None:
        self.blockSignals(True)
        self.clear()
        if self._allow_empty:
            self.addItem(self._empty_label, None)
        for item in preferred:
            self.addItem(item.display, item.code)
        if preferred and rest:
            self.insertSeparator(self.count())
        for item in rest:
            self.addItem(item.display, item.code)
        self.setCurrentIndex(-1)
        self.blockSignals(False)
        self._current_code = None
        self._show_current()

    def codes(self) -> list[str]:
        return [
            self.itemData(index)
            for index in range(self.count())
            if not self.is_separator(index) and self.itemData(index) is not None
        ]

    def is_separator(self, index: int) -> bool:
        return self.itemData(index, Qt.ItemDataRole.AccessibleDescriptionRole) == SEPARATOR_MARK

    def row_for_code(self, code: str | None) -> int:
        for index in range(self.count()):
            if not self.is_separator(index) and self.itemData(index) == code:
                return index
        return -1

    def current_code(self) -> str | None:
        return self._current_code

    def set_current_code(self, code: str | None) -> bool:
        """Selects ``code`` without emitting ``committed``; unknown codes clear the combo."""
        row = self.row_for_code(code)
        if code is None and not self._allow_empty:
            row = -1
        known = row >= 0 or code is None
        self._current_code = code if row >= 0 else None
        self.blockSignals(True)
        self.setCurrentIndex(row)
        self.blockSignals(False)
        self._show_current()
        return known

    # --- interaccion ---------------------------------------------------------
    def _show_current(self) -> None:
        line_edit = self.lineEdit()
        if line_edit is None:
            return
        row = (
            self.row_for_code(self._current_code)
            if (self._current_code is not None or self._allow_empty)
            else -1
        )
        line_edit.setText(self.itemText(row) if row >= 0 else "")

    def _commit(self, row: int) -> None:
        if row < 0 or self.is_separator(row):
            return
        code = self.itemData(row)
        if self.currentIndex() != row:
            self.blockSignals(True)
            self.setCurrentIndex(row)
            self.blockSignals(False)
        changed = code != self._current_code
        self._current_code = code
        self._show_current()
        if changed:
            self.committed.emit(code)

    def _on_activated(self, row: int) -> None:
        self._commit(row)

    def _resolve_text(self, text: str) -> int:
        wanted = text.strip().casefold()
        if not wanted:
            return 0 if self._allow_empty else -1
        for index in range(self.count()):
            if self.is_separator(index):
                continue
            if self.itemText(index).casefold() == wanted or (
                self.itemData(index) is not None and str(self.itemData(index)).casefold() == wanted
            ):
                return index
        return -1

    def _on_editing_finished(self) -> None:
        line_edit = self.lineEdit()
        if line_edit is None:
            return
        row = self._resolve_text(line_edit.text())
        if row >= 0:
            self._commit(row)
        else:
            self._show_current()  # texto libre: se descarta

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API
        if watched is self.lineEdit() and event.type() == QEvent.Type.FocusOut:
            self._on_editing_finished()
        return super().eventFilter(watched, event)
