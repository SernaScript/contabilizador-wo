"""Test doubles of the Catálogos page tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from contabilizador.ui.errors import ErrorPresenter
from contabilizador.ui.tasks import TaskContext, TaskHandle


class RecordingPresenter(ErrorPresenter):
    """Records what would have been shown in a modal message box."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[tuple[BaseException, str | None]] = []

    def show(self, parent, error, *, context=None):  # type: ignore[override]
        self.shown.append((error, context))
        return self.present(error, context=context)


class FakeDialogs:
    """Native file dialogs replaced by canned answers; records the questions."""

    def __init__(self) -> None:
        self.workbook: Path | None = None
        self.destination: Path | None = None
        self.suggested: list[Path] = []
        self.workbook_asked = 0

    def choose_workbook(self, parent: QWidget) -> Path | None:
        self.workbook_asked += 1
        return self.workbook

    def choose_template_destination(self, parent: QWidget, suggested: Path) -> Path | None:
        self.suggested.append(suggested)
        return self.destination


class _Context:
    def report(self, done: int, total: int) -> None:
        return None

    def cancelled(self) -> bool:
        return False


@dataclass
class _Pending:
    job: Callable[[TaskContext], Any]
    on_done: Callable[[Any], None] | None
    on_error: Callable[[BaseException], None] | None


class ManualRunner(QObject):
    """Runner whose jobs wait in a queue until the test decides to run them, so tests can
    interleave refreshes and look at the busy state."""

    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.pending: list[_Pending] = []

    @property
    def is_busy(self) -> bool:
        return bool(self.pending)

    def submit(
        self,
        job: Callable[[TaskContext], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        self.pending.append(_Pending(job, on_done, on_error))
        return TaskHandle()

    def run_next(self) -> None:
        item = self.pending.pop(0)
        try:
            result = item.job(_Context())
        except BaseException as error:
            if item.on_error is None:
                raise
            item.on_error(error)
        else:
            if item.on_done is not None:
                item.on_done(result)

    def run_all(self) -> None:
        while self.pending:
            self.run_next()

    def shutdown(self) -> None:
        return None
