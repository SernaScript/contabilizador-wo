"""Sidebar: brand mark, company switcher slot and navigation items with badges."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from contabilizador.shared import strings
from contabilizador.ui import actions, icons
from contabilizador.ui.branding import mark_pixmap
from contabilizador.ui.theme import TOKENS
from contabilizador.ui.widgets.common import flag, make_label, set_property

LOGO_HEIGHT = 40
NAV_ICON_SIZE = 18


class NavItem(QPushButton):
    """One navigation entry: icon + label, optional count badge, active indicator."""

    def __init__(self, key: str, label: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.key = key
        self._icon_name = icon_name
        self.setProperty("role", "nav")
        self.setProperty("active", flag(False))
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setIconSize(QSize(NAV_ICON_SIZE, NAV_ICON_SIZE))
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())
        self.setMinimumHeight(36)
        self._apply_icon(active=False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.addStretch(1)
        self.badge = make_label("", role="badge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.hide()
        layout.addWidget(self.badge)

    def _apply_icon(self, *, active: bool) -> None:
        color = TOKENS.blue if active else TOKENS.slate
        self.setIcon(icons.icon(self._icon_name, color, NAV_ICON_SIZE))

    @property
    def is_active(self) -> bool:
        return self.property("active") == "true"

    def set_active(self, active: bool) -> None:
        self._apply_icon(active=active)
        set_property(self, "active", flag(active))

    def set_badge(self, count: int, status: str | None = None) -> None:
        if count <= 0:
            self.badge.hide()
            self.badge.setText("")
            return
        self.badge.setText(str(count))
        set_property(self.badge, "status", status)
        self.badge.show()


class Sidebar(QFrame):
    navigated = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.setFixedWidth(232)
        self._items: dict[str, NavItem] = {}
        self._active: str | None = None
        self._company_widget: QWidget | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 16, 0, 12)
        layout.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(16, 0, 16, 8)
        brand.setSpacing(10)
        self.logo = QLabel()
        self.logo.setObjectName("headerLogo")
        self.logo.setPixmap(mark_pixmap(LOGO_HEIGHT))
        self.logo.setToolTip(strings.BRAND_NAME)
        brand.addWidget(self.logo)
        self.app_name = make_label(strings.APP_NAME, role="brand")
        brand.addWidget(self.app_name, 1)
        layout.addLayout(brand)

        self.company_slot = QVBoxLayout()
        self.company_slot.setContentsMargins(12, 4, 12, 12)
        layout.addLayout(self.company_slot)

        self._nav = QVBoxLayout()
        self._nav.setContentsMargins(0, 0, 0, 0)
        self._nav.setSpacing(2)
        layout.addLayout(self._nav)
        layout.addStretch(1)

        self._footer = QVBoxLayout()
        self._footer.setContentsMargins(0, 0, 0, 0)
        self._footer.setSpacing(2)
        layout.addLayout(self._footer)

    # --- empresa -----------------------------------------------------------
    def set_company_widget(self, widget: QWidget) -> None:
        if self._company_widget is not None:
            self.company_slot.removeWidget(self._company_widget)
            self._company_widget.setParent(None)
        self._company_widget = widget
        widget.setParent(self)
        self.company_slot.addWidget(widget)

    # --- navegacion --------------------------------------------------------
    def add_item(
        self,
        key: str,
        label: str,
        icon_name: str,
        *,
        shortcut_id: str | None = None,
        footer: bool = False,
    ) -> NavItem:
        item = NavItem(key, label, icon_name, self)
        tooltip = actions.with_shortcut(label, shortcut_id) if shortcut_id else label
        item.setToolTip(tooltip)
        item.clicked.connect(lambda _checked=False, k=key: self.navigated.emit(k))
        (self._footer if footer else self._nav).addWidget(item)
        self._items[key] = item
        return item

    def item(self, key: str) -> NavItem:
        return self._items[key]

    def items(self) -> list[NavItem]:
        return list(self._items.values())

    @property
    def active_key(self) -> str | None:
        return self._active

    def set_active(self, key: str | None) -> None:
        self._active = key
        for item_key, item in self._items.items():
            item.set_active(item_key == key)

    def set_badge(self, key: str, count: int, status: str | None = None) -> None:
        self._items[key].set_badge(count, status)
