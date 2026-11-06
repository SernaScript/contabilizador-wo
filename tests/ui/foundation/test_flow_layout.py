"""Flow layout: one row while it fits, more rows when narrow, items centered in their row."""

from PySide6.QtWidgets import QLabel, QPushButton, QWidget

from contabilizador.ui.widgets.flow_layout import FlowLayout


def _host(qtbot) -> tuple[QWidget, FlowLayout, list[QWidget]]:
    host = QWidget()
    qtbot.addWidget(host)
    layout = FlowLayout(host, spacing=10, row_spacing=8)
    items: list[QWidget] = [QLabel("3 facturas seleccionadas"), QPushButton("Aplicar")]
    items[1].setFixedHeight(36)
    for item in items:
        layout.addWidget(item)
    return host, layout, items


def test_items_share_a_row_and_are_vertically_centered(qtbot) -> None:
    host, layout, (label, button) = _host(qtbot)
    host.resize(layout.sizeHint().width() + 50, 60)
    host.show()
    layout.activate()

    assert label.geometry().top() > button.geometry().top()
    assert abs(label.geometry().center().y() - button.geometry().center().y()) <= 1
    assert label.geometry().right() < button.geometry().left()


def test_narrow_width_moves_items_to_a_new_row(qtbot) -> None:
    host, layout, (label, button) = _host(qtbot)
    narrow = max(label.sizeHint().width(), button.sizeHint().width()) + 4
    host.resize(narrow, layout.heightForWidth(narrow))
    host.show()
    layout.activate()

    assert button.geometry().top() >= label.geometry().bottom()
    assert button.geometry().left() == 0
    assert layout.heightForWidth(narrow) > layout.heightForWidth(narrow * 3)
