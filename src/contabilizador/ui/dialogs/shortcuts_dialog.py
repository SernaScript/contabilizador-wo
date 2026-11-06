"""Shortcuts dialog (Ctrl/Cmd+/): the table of ``actions.py`` grouped by task.

Presentational: it only reads the shortcut table, so a shortcut added there shows up here
(under "Otros atajos" until it gets a group).
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QWidget

from contabilizador.shared import strings
from contabilizador.ui import actions
from contabilizador.ui.widgets.common import make_label
from contabilizador.ui.widgets.sheet import Sheet

# Grupos por tarea en orden de lectura; dentro de cada uno se respeta este orden
_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (strings.SHORTCUTS_GROUP_FLOW, ("import_files", "import_folder", "export")),
    (strings.SHORTCUTS_GROUP_LIST, ("search", "expand", "clear_selection")),
    (
        strings.SHORTCUTS_GROUP_NAVIGATION,
        (*(f"nav_{page}" for page in actions.PAGE_ORDER), "show_shortcuts"),
    ),
)

_MAC_MODIFIERS = "⌃⌥⇧⌘"


def split_keys(display: str) -> list[str]:
    """One entry per key of a platform shortcut text: ``Ctrl+Shift+O`` or ``⇧⌘O``."""
    if display.endswith("++"):
        # La tecla "+" va despues del separador
        return [*split_keys(display[:-2]), "+"]
    if "+" in display:
        return [part for part in display.split("+") if part] or [display]
    keys: list[str] = []
    rest = display
    while rest and rest[0] in _MAC_MODIFIERS:
        keys.append(rest[0])
        rest = rest[1:]
    if rest:
        keys.append(rest)
    return keys


@dataclass(frozen=True, slots=True)
class ShortcutRow:
    group: str
    shortcut_id: str
    label: str
    keys: tuple[str, ...]
    keys_widget: QWidget


def _grouped_shortcuts() -> list[tuple[str, list[actions.Shortcut]]]:
    by_id = {item.id: item for item in actions.SHORTCUTS}
    grouped: list[tuple[str, list[actions.Shortcut]]] = []
    placed: set[str] = set()
    for title, ids in _GROUPS:
        members = [by_id[shortcut_id] for shortcut_id in ids if shortcut_id in by_id]
        placed.update(item.id for item in members)
        if members:
            grouped.append((title, members))
    leftovers = [item for item in actions.SHORTCUTS if item.id not in placed]
    if leftovers:
        grouped.append((strings.SHORTCUTS_GROUP_OTHER, leftovers))
    return grouped


class ShortcutsDialog(Sheet):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            strings.SHORTCUTS_TITLE,
            subtitle=strings.SHORTCUTS_PURPOSE,
            primary_label=strings.ACTION_CLOSE,
            parent=parent,
        )
        # Dialogo informativo: un solo boton; Esc tambien cierra
        self.cancel_button.hide()
        self._rows: list[ShortcutRow] = []
        for position, (title, members) in enumerate(_grouped_shortcuts()):
            if position:
                self.body_layout.addSpacing(8)
            self.body_layout.addWidget(make_label(title, role="section"))
            self.body_layout.addLayout(self._build_group(title, members))

    def rows(self) -> list[ShortcutRow]:
        return list(self._rows)

    def group_titles(self) -> list[str]:
        titles: list[str] = []
        for row in self._rows:
            if row.group not in titles:
                titles.append(row.group)
        return titles

    def _build_group(self, title: str, members: list[actions.Shortcut]) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(0, 1)
        for index, item in enumerate(members):
            grid.addWidget(make_label(item.label), index, 0)
            keys = tuple(split_keys(item.display()))
            keys_widget = self._build_keys(keys, item.display())
            grid.addWidget(keys_widget, index, 1, Qt.AlignmentFlag.AlignRight)
            self._rows.append(ShortcutRow(title, item.id, item.label, keys, keys_widget))
        return grid

    @staticmethod
    def _build_keys(keys: tuple[str, ...], whole: str) -> QWidget:
        container = QWidget()
        container.setAccessibleName(whole)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        for key in keys:
            cap: QLabel = make_label(key, role="keycap")
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(cap)
        return container
