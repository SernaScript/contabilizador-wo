"""Shortcuts dialog: the table of ``actions.py`` grouped by task, one key cap per key."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from contabilizador.shared import strings
from contabilizador.ui import actions
from contabilizador.ui.dialogs.shortcuts_dialog import ShortcutsDialog, split_keys


@pytest.mark.parametrize(
    ("display", "expected"),
    [
        ("Ctrl+O", ["Ctrl", "O"]),
        ("Ctrl+Shift+O", ["Ctrl", "Shift", "O"]),
        ("Ctrl+/", ["Ctrl", "/"]),
        ("Ctrl++", ["Ctrl", "+"]),
        ("⌘O", ["⌘", "O"]),
        ("⇧⌘O", ["⇧", "⌘", "O"]),
        ("⌘/", ["⌘", "/"]),
        ("Esc", ["Esc"]),
        ("Espacio", ["Espacio"]),
    ],
)
def test_split_keys_gives_one_key_cap_per_key(display: str, expected: list[str]) -> None:
    assert split_keys(display) == expected


def _dialog(qtbot) -> ShortcutsDialog:
    dialog = ShortcutsDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_dialog_has_title_purpose_and_only_a_close_button(qtbot) -> None:
    dialog = _dialog(qtbot)

    assert dialog.windowTitle() == strings.SHORTCUTS_TITLE
    assert dialog.title_label.text() == strings.SHORTCUTS_TITLE
    assert dialog.subtitle_label.text() == strings.SHORTCUTS_PURPOSE
    assert dialog.primary_button.text() == strings.ACTION_CLOSE
    assert dialog.cancel_button.isHidden()


def test_lists_every_shortcut_of_the_table_with_its_platform_text(qtbot) -> None:
    dialog = _dialog(qtbot)

    rows = {row.shortcut_id: row for row in dialog.rows()}

    assert set(rows) == {item.id for item in actions.SHORTCUTS}
    for item in actions.SHORTCUTS:
        assert rows[item.id].label == item.label
        # Windows separa con "+"; macOS pega los simbolos: las teclas suman el mismo texto
        assert "".join(rows[item.id].keys) == item.display().replace("+", "")


def test_shortcuts_are_grouped_by_task_in_reading_order(qtbot) -> None:
    dialog = _dialog(qtbot)

    assert dialog.group_titles() == [
        strings.SHORTCUTS_GROUP_FLOW,
        strings.SHORTCUTS_GROUP_LIST,
        strings.SHORTCUTS_GROUP_NAVIGATION,
    ]
    group_of = {row.shortcut_id: row.group for row in dialog.rows()}
    for shortcut_id in ("import_files", "import_folder", "export"):
        assert group_of[shortcut_id] == strings.SHORTCUTS_GROUP_FLOW
    for shortcut_id in ("search", "expand", "clear_selection"):
        assert group_of[shortcut_id] == strings.SHORTCUTS_GROUP_LIST
    for page in actions.PAGE_ORDER:
        assert group_of[f"nav_{page}"] == strings.SHORTCUTS_GROUP_NAVIGATION
    assert group_of["show_shortcuts"] == strings.SHORTCUTS_GROUP_NAVIGATION


def test_a_shortcut_missing_from_the_groups_still_shows_up_under_other(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = actions.Shortcut("future_action", "Acción futura", "Ctrl+9")
    monkeypatch.setattr(actions, "SHORTCUTS", (*actions.SHORTCUTS, extra))

    dialog = _dialog(qtbot)

    row = next(row for row in dialog.rows() if row.shortcut_id == "future_action")
    assert row.group == strings.SHORTCUTS_GROUP_OTHER
    assert dialog.group_titles()[-1] == strings.SHORTCUTS_GROUP_OTHER


def test_keys_are_drawn_as_one_key_cap_label_each(qtbot) -> None:
    dialog = _dialog(qtbot)

    caps = [
        label.text() for label in dialog.findChildren(QLabel) if label.property("role") == "keycap"
    ]

    expected = [key for row in dialog.rows() for key in row.keys]
    assert sorted(caps) == sorted(expected)


def test_each_key_group_has_the_whole_shortcut_as_accessible_name(qtbot) -> None:
    dialog = _dialog(qtbot)

    for row in dialog.rows():
        item = actions.shortcut(row.shortcut_id)
        assert row.keys_widget.accessibleName() == item.display()


def test_close_button_accepts_the_dialog(qtbot) -> None:
    dialog = _dialog(qtbot)

    with qtbot.waitSignal(dialog.accepted):
        dialog.primary_button.click()


def test_enter_closes_the_dialog(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.show()

    with qtbot.waitSignal(dialog.accepted):
        qtbot.keyClick(dialog, Qt.Key.Key_Return)


def test_escape_closes_the_dialog(qtbot) -> None:
    dialog = _dialog(qtbot)
    dialog.show()

    with qtbot.waitSignal(dialog.rejected):
        qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    assert not dialog.isVisible()
