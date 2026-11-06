"""Shortcut table as data plus the QAction factory (Ctrl on Windows, Cmd on macOS)."""

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QWidget

from contabilizador.shared import strings
from contabilizador.ui import actions


def test_shortcut_table_covers_the_plan() -> None:
    by_id = {shortcut.id: shortcut for shortcut in actions.SHORTCUTS}

    assert by_id["import_files"].sequence() == QKeySequence("Ctrl+O")
    assert by_id["import_folder"].sequence() == QKeySequence("Ctrl+Shift+O")
    assert by_id["export"].sequence() == QKeySequence("Ctrl+E")
    assert by_id["search"].sequence() == QKeySequence("Ctrl+F")
    for number, page in enumerate(actions.PAGE_ORDER, start=1):
        assert by_id[f"nav_{page}"].sequence() == QKeySequence(f"Ctrl+{number}")
    assert by_id["show_shortcuts"].sequence() == QKeySequence("Ctrl+/")
    assert by_id["clear_selection"].sequence() == QKeySequence("Esc")
    assert by_id["expand"].sequence() == QKeySequence("Space")


def test_every_shortcut_has_spanish_label() -> None:
    labels = {shortcut.label for shortcut in actions.SHORTCUTS}

    assert strings.SHORTCUT_IMPORT_FILES in labels
    assert strings.SHORTCUT_EXPORT in labels
    assert all(shortcut.label for shortcut in actions.SHORTCUTS)


def test_build_actions_creates_global_actions_only(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)

    built = actions.build_actions(parent)

    assert set(built) == {s.id for s in actions.SHORTCUTS if s.global_action}
    assert "clear_selection" not in built
    assert "expand" not in built
    export = built["export"]
    assert isinstance(export, QAction)
    assert export.shortcut() == QKeySequence("Ctrl+E")
    assert export.text() == strings.SHORTCUT_EXPORT
    assert export.parent() is parent


def test_display_text_is_platform_native() -> None:
    shortcut = actions.shortcut("import_files")

    assert shortcut.display() == QKeySequence("Ctrl+O").toString(
        QKeySequence.SequenceFormat.NativeText
    )


def test_with_shortcut_appends_hint_to_tooltips() -> None:
    hint = actions.shortcut("search").display()

    assert actions.with_shortcut("Buscar", "search") == f"Buscar ({hint})"
