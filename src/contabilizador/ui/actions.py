"""Shortcut table as data plus a ``QAction`` factory.

Portable key text (``Ctrl+O``) maps to Cmd on macOS automatically; ``display()`` renders
the platform text for tooltips and the shortcuts dialog.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QKeySequence

from contabilizador.shared import strings

PAGE_ORDER = ("invoices", "suppliers", "catalogs", "batches", "company")


@dataclass(frozen=True, slots=True)
class Shortcut:
    id: str
    label: str
    keys: str
    global_action: bool = True
    display_text: str | None = None

    def sequence(self) -> QKeySequence:
        return QKeySequence(self.keys)

    def display(self) -> str:
        if self.display_text:
            return self.display_text
        return self.sequence().toString(QKeySequence.SequenceFormat.NativeText)


_NAV_LABELS = {
    "invoices": strings.SHORTCUT_NAV_INVOICES,
    "suppliers": strings.SHORTCUT_NAV_SUPPLIERS,
    "catalogs": strings.SHORTCUT_NAV_CATALOGS,
    "batches": strings.SHORTCUT_NAV_BATCHES,
    "company": strings.SHORTCUT_NAV_COMPANY,
}

SHORTCUTS: tuple[Shortcut, ...] = (
    Shortcut("import_files", strings.SHORTCUT_IMPORT_FILES, "Ctrl+O"),
    Shortcut("import_folder", strings.SHORTCUT_IMPORT_FOLDER, "Ctrl+Shift+O"),
    Shortcut("export", strings.SHORTCUT_EXPORT, "Ctrl+E"),
    Shortcut("search", strings.SHORTCUT_SEARCH, "Ctrl+F"),
    *(
        Shortcut(f"nav_{page}", _NAV_LABELS[page], f"Ctrl+{number}")
        for number, page in enumerate(PAGE_ORDER, start=1)
    ),
    Shortcut("show_shortcuts", strings.SHORTCUT_SHOW_SHORTCUTS, "Ctrl+/"),
    # Teclas que gestionan las vistas, no acciones globales
    Shortcut(
        "expand",
        strings.SHORTCUT_EXPAND,
        "Space",
        global_action=False,
        display_text=strings.SHORTCUT_KEY_SPACE,
    ),
    Shortcut(
        "clear_selection",
        strings.SHORTCUT_CLEAR_SELECTION,
        "Esc",
        global_action=False,
        display_text=strings.SHORTCUT_KEY_ESCAPE,
    ),
)

_BY_ID = {item.id: item for item in SHORTCUTS}


def shortcut(shortcut_id: str) -> Shortcut:
    return _BY_ID[shortcut_id]


def with_shortcut(text: str, shortcut_id: str) -> str:
    """Tooltip text with the platform shortcut: ``Buscar (Ctrl+F)``."""
    return f"{text} ({shortcut(shortcut_id).display()})"


def build_actions(parent: QObject) -> dict[str, QAction]:
    """One ``QAction`` per global shortcut, keyed by id; the caller connects them."""
    built: dict[str, QAction] = {}
    for item in SHORTCUTS:
        if not item.global_action:
            continue
        action = QAction(item.label, parent)
        action.setShortcut(item.sequence())
        action.setToolTip(with_shortcut(item.label, item.id))
        built[item.id] = action
    return built
