"""Test doubles for the Proveedores container: a runner the test advances by hand and a
presenter that records errors instead of opening a message box."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from contabilizador.ui.errors import ErrorPresentation, ErrorPresenter
from contabilizador.ui.tasks import TaskContext, TaskHandle


class RecordingPresenter(ErrorPresenter):
    def __init__(self) -> None:
        super().__init__()
        self.shown: list[BaseException] = []

    def show(
        self, parent: QWidget | None, error: BaseException, *, context: str | None = None
    ) -> ErrorPresentation:
        self.shown.append(error)
        return self.present(error, context=context)


class _Context:
    def __init__(self, handle: TaskHandle) -> None:
        self._handle = handle

    def report(self, done: int, total: int) -> None:
        return None

    def cancelled(self) -> bool:
        return self._handle.is_cancelled


@dataclass
class _Queued:
    job: Callable[[TaskContext], Any]
    on_done: Callable[[Any], None] | None
    on_error: Callable[[BaseException], None] | None
    handle: TaskHandle = field(default_factory=TaskHandle)


class ManualRunner(QObject):
    """Queues jobs; the test decides when each one runs, to exercise stale results."""

    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.queue: list[_Queued] = []

    @property
    def is_busy(self) -> bool:
        return bool(self.queue)

    def submit(
        self,
        job: Callable[[TaskContext], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        queued = _Queued(job, on_done, on_error)
        self.queue.append(queued)
        return queued.handle

    def run_next(self) -> None:
        """Runs the oldest job and delivers its result, like the Qt runner would."""
        queued = self.queue.pop(0)
        try:
            result = queued.job(_Context(queued.handle))
        except BaseException as error:
            if queued.on_error is not None:
                queued.on_error(error)
            return
        if queued.on_done is not None:
            queued.on_done(result)

    def shutdown(self) -> None:
        return None
