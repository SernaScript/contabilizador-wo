"""Presentational widgets: they receive data, emit signals and never call use cases."""

from contabilizador.ui.widgets.banner import Banner
from contabilizador.ui.widgets.busy_overlay import BusyOverlay
from contabilizador.ui.widgets.code_combo import CodeCombo, CodeItem
from contabilizador.ui.widgets.common import (
    IconButton,
    hairline,
    icon_label,
    make_label,
    paint_row_action,
)
from contabilizador.ui.widgets.company_switcher import CompanySwitcher
from contabilizador.ui.widgets.confirm_sheet import ConfirmSheet
from contabilizador.ui.widgets.drop_overlay import DropOverlay, paths_from_mime
from contabilizador.ui.widgets.empty_state import EmptyState
from contabilizador.ui.widgets.filter_chips import FilterChips
from contabilizador.ui.widgets.readiness_bar import ReadinessBar, SegmentedBar
from contabilizador.ui.widgets.search_field import SearchField
from contabilizador.ui.widgets.segmented import Segmented
from contabilizador.ui.widgets.sheet import Sheet
from contabilizador.ui.widgets.sidebar import NavItem, Sidebar
from contabilizador.ui.widgets.split_button import SplitButton
from contabilizador.ui.widgets.status_pill import StatusPill, paint_status_pill, status_pill_size
from contabilizador.ui.widgets.stepper import Stepper
from contabilizador.ui.widgets.toast import Toast, ToastHost

__all__ = [
    "Banner",
    "BusyOverlay",
    "CodeCombo",
    "CodeItem",
    "CompanySwitcher",
    "ConfirmSheet",
    "DropOverlay",
    "EmptyState",
    "FilterChips",
    "IconButton",
    "NavItem",
    "ReadinessBar",
    "SearchField",
    "Segmented",
    "SegmentedBar",
    "Sheet",
    "Sidebar",
    "SplitButton",
    "StatusPill",
    "Stepper",
    "Toast",
    "ToastHost",
    "hairline",
    "icon_label",
    "make_label",
    "paint_row_action",
    "paint_status_pill",
    "paths_from_mime",
    "status_pill_size",
]
