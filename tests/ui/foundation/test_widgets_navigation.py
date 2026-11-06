"""Navigation widgets: Sidebar, CompanySwitcher, Stepper, Segmented, FilterChips."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QToolButton

from contabilizador.shared import strings
from contabilizador.ui import actions
from contabilizador.ui.widgets.company_switcher import CompanySwitcher
from contabilizador.ui.widgets.filter_chips import FilterChips
from contabilizador.ui.widgets.segmented import Segmented
from contabilizador.ui.widgets.sidebar import NavItem, Sidebar
from contabilizador.ui.widgets.stepper import Stepper

# --- Sidebar -------------------------------------------------------------------


def _sidebar(qtbot) -> Sidebar:
    sidebar = Sidebar()
    qtbot.addWidget(sidebar)
    sidebar.add_item("invoices", strings.NAV_INVOICES, "invoices", shortcut_id="nav_invoices")
    sidebar.add_item("suppliers", strings.NAV_SUPPLIERS, "suppliers", shortcut_id="nav_suppliers")
    sidebar.add_item("shortcuts", strings.NAV_SHORTCUTS, "keyboard", shortcut_id="show_shortcuts")
    sidebar.show()
    return sidebar


def test_sidebar_has_logo_mark_and_app_name(qtbot) -> None:
    sidebar = _sidebar(qtbot)

    logo = sidebar.findChild(QLabel, "headerLogo")
    assert logo is not None
    assert not logo.pixmap().isNull()
    assert 36 <= logo.pixmap().height() <= 44
    assert sidebar.app_name.text() == strings.APP_NAME
    assert sidebar.property("role") == "sidebar"


def test_sidebar_items_emit_navigated_and_track_active(qtbot) -> None:
    sidebar = _sidebar(qtbot)
    item = sidebar.item("suppliers")

    with qtbot.waitSignal(sidebar.navigated) as blocker:
        qtbot.mouseClick(item, Qt.MouseButton.LeftButton)

    assert blocker.args == ["suppliers"]
    sidebar.set_active("suppliers")
    assert sidebar.active_key == "suppliers"
    assert sidebar.item("suppliers").is_active is True
    assert sidebar.item("invoices").is_active is False
    assert item.property("active") == "true"


def test_sidebar_item_shows_icon_text_shortcut_and_badge(qtbot) -> None:
    sidebar = _sidebar(qtbot)
    item = sidebar.item("invoices")

    assert isinstance(item, NavItem)
    assert item.text() == strings.NAV_INVOICES
    assert not item.icon().isNull()
    assert actions.shortcut("nav_invoices").display() in item.toolTip()
    assert item.badge.isHidden()

    sidebar.set_badge("invoices", 8)
    assert item.badge.text() == "8"
    assert not item.badge.isHidden()
    sidebar.set_badge("suppliers", 3, status="blocked")
    assert sidebar.item("suppliers").badge.property("status") == "blocked"
    sidebar.set_badge("invoices", 0)
    assert item.badge.isHidden()


def test_sidebar_hosts_the_company_widget_in_its_slot(qtbot) -> None:
    sidebar = _sidebar(qtbot)
    switcher = QComboBox()

    sidebar.set_company_widget(switcher)

    assert switcher.parent() is sidebar
    assert sidebar.company_slot.indexOf(switcher) >= 0
    replacement = QComboBox()
    sidebar.set_company_widget(replacement)
    assert sidebar.company_slot.indexOf(replacement) >= 0
    assert sidebar.company_slot.indexOf(switcher) == -1


def test_sidebar_items_are_keyboard_focusable(qtbot) -> None:
    sidebar = _sidebar(qtbot)

    assert sidebar.item("invoices").focusPolicy() & Qt.FocusPolicy.TabFocus


# --- CompanySwitcher ------------------------------------------------------------


def test_company_switcher_lists_companies_and_keeps_current(qtbot) -> None:
    switcher = CompanySwitcher()
    qtbot.addWidget(switcher)

    switcher.set_companies([(1, "WEARE DEV"), (2, "While Corp")], current=2)

    assert switcher.current_company_id() == 2
    assert switcher.combo.count() == 2
    assert switcher.new_button.text() == strings.ACTION_NEW_COMPANY
    switcher.set_companies([(1, "WEARE DEV"), (2, "While Corp"), (3, "Otra")])
    assert switcher.current_company_id() == 2


def test_company_switcher_emits_changes_and_new_company(qtbot) -> None:
    switcher = CompanySwitcher()
    qtbot.addWidget(switcher)
    switcher.set_companies([(1, "A"), (2, "B")], current=2)

    with qtbot.waitSignal(switcher.company_changed) as blocker:
        switcher.combo.setCurrentIndex(0)
    assert blocker.args == [1]

    with qtbot.waitSignal(switcher.new_company_requested):
        switcher.new_button.click()


def test_company_switcher_without_companies_and_locked(qtbot) -> None:
    switcher = CompanySwitcher()
    qtbot.addWidget(switcher)

    switcher.set_companies([])
    assert switcher.current_company_id() is None
    assert switcher.combo.placeholderText() == strings.COMPANY_SWITCHER_PLACEHOLDER
    assert switcher.combo.isEnabled() is False

    switcher.set_companies([(1, "A")])
    switcher.set_locked(True)
    assert switcher.combo.isEnabled() is False
    assert switcher.combo.toolTip() == strings.COMPANY_SWITCHER_LOCKED_HINT
    switcher.set_locked(False)
    assert switcher.combo.isEnabled() is True


def test_company_switcher_set_current_emits_only_on_change(qtbot) -> None:
    switcher = CompanySwitcher()
    qtbot.addWidget(switcher)
    switcher.set_companies([(1, "A"), (2, "B")], current=1)
    seen: list[object] = []
    switcher.company_changed.connect(seen.append)

    switcher.set_current(1)
    switcher.set_current(2)

    assert seen == [2]


# --- Stepper --------------------------------------------------------------------


def test_stepper_has_three_numbered_steps_and_states(qtbot) -> None:
    stepper = Stepper()
    qtbot.addWidget(stepper)

    assert [stepper.button(i).text() for i in range(3)] == [
        strings.STEP_IMPORT,
        strings.STEP_COMPLETE,
        strings.STEP_EXPORT,
    ]
    assert [stepper.number(i).text() for i in range(3)] == ["1", "2", "3"]

    stepper.set_current(1)
    assert [stepper.state(i) for i in range(3)] == ["done", "current", "todo"]
    assert stepper.button(1).property("state") == "current"
    stepper.set_state(2, "done")
    assert stepper.state(2) == "done"


def test_stepper_steps_are_clickable(qtbot) -> None:
    stepper = Stepper()
    qtbot.addWidget(stepper)
    stepper.show()

    with qtbot.waitSignal(stepper.step_clicked) as blocker:
        qtbot.mouseClick(stepper.button(2), Qt.MouseButton.LeftButton)

    assert blocker.args == [2]


# --- Segmented ------------------------------------------------------------------


def test_segmented_control_is_exclusive_and_emits(qtbot) -> None:
    segmented = Segmented()
    qtbot.addWidget(segmented)
    segmented.set_options([("products", "Productos"), ("cost_centers", "Centros de costo")])
    segmented.show()

    assert segmented.current() == "products"
    assert segmented.button("products").property("position") == "first"
    assert segmented.button("cost_centers").property("position") == "last"

    with qtbot.waitSignal(segmented.changed) as blocker:
        qtbot.mouseClick(segmented.button("cost_centers"), Qt.MouseButton.LeftButton)

    assert blocker.args == ["cost_centers"]
    assert segmented.current() == "cost_centers"
    assert segmented.button("products").isChecked() is False
    assert isinstance(segmented.button("products"), QToolButton)


# --- FilterChips ----------------------------------------------------------------


def test_filter_chips_show_counts_and_emit(qtbot) -> None:
    chips = FilterChips()
    qtbot.addWidget(chips)
    chips.set_chips([("all", strings.FILTER_ALL), ("ready", strings.FILTER_READY)])
    chips.show()

    assert chips.current() == "all"
    chips.set_counts({"all": 26, "ready": 18})
    assert chips.chip("ready").text() == f"{strings.FILTER_READY} (18)"
    assert chips.chip("ready").property("role") == "chip"

    with qtbot.waitSignal(chips.filter_changed) as blocker:
        qtbot.mouseClick(chips.chip("ready"), Qt.MouseButton.LeftButton)

    assert blocker.args == ["ready"]
    assert chips.current() == "ready"
    chips.set_current("all")
    assert chips.chip("all").isChecked() is True
    assert chips.chip("ready").isChecked() is False


SIX_CHIPS = [
    ("all", strings.FILTER_ALL),
    ("ready", strings.FILTER_READY),
    ("incomplete", strings.FILTER_INCOMPLETE),
    ("unconfigured", strings.FILTER_UNCONFIGURED),
    ("mismatch", strings.FILTER_MISMATCH),
    ("suggested", strings.FILTER_SUGGESTED),
]


def test_filter_chips_wrap_onto_another_row_instead_of_widening_the_window(qtbot) -> None:
    chips = FilterChips()
    qtbot.addWidget(chips)
    chips.set_chips(SIX_CHIPS)
    chips.set_counts({key: 128 for key, _label in SIX_CHIPS})
    one_row = sum(chips.chip(key).sizeHint().width() for key, _label in SIX_CHIPS)

    widest = max(chips.chip(key).sizeHint().width() for key, _label in SIX_CHIPS)
    assert chips.minimumSizeHint().width() <= widest
    assert chips.sizeHint().width() >= one_row
    assert chips.hasHeightForWidth()
    row = chips.chip("all").sizeHint().height()
    assert chips.heightForWidth(one_row + 200) == row
    assert chips.heightForWidth(one_row // 2) > row

    chips.resize(one_row // 2, chips.heightForWidth(one_row // 2))
    chips.show()
    tops = sorted({chips.chip(key).geometry().top() for key, _label in SIX_CHIPS})
    lefts = [chips.chip(key).geometry().left() for key, _label in SIX_CHIPS]
    assert len(tops) >= 2
    assert lefts[0] == 0  # cada fila empieza en el borde izquierdo


def test_segmented_control_stays_on_one_row(qtbot) -> None:
    segmented = Segmented()
    qtbot.addWidget(segmented)
    segmented.set_options([("products", "Productos"), ("cost_centers", "Centros de costo")])

    assert not segmented.hasHeightForWidth()
