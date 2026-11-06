"""The UI test plumbing (tests/ui/conftest.py) keeps the widgets of a test alive until its
teardown and copes with widgets whose C++ object is already gone."""

import gc
import weakref

import shiboken6
from PySide6.QtWidgets import QWidget


def test_a_widget_deleted_during_the_test_does_not_break_the_teardown(qtbot) -> None:
    widget = QWidget()
    qtbot.addWidget(widget)

    shiboken6.delete(widget)  # el objeto C++ desaparece; Python conserva el envoltorio

    assert not shiboken6.isValid(widget)


def test_added_widgets_stay_alive_until_the_test_ends(qtbot) -> None:
    def build() -> QWidget:
        widget = QWidget()
        qtbot.addWidget(widget)
        return widget

    added = weakref.ref(build())  # ninguna otra referencia de Python
    gc.collect()

    widget = added()
    assert widget is not None
    assert shiboken6.isValid(widget)
