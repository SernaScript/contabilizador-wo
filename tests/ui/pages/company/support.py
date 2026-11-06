"""Test doubles shared by the Empresa, new company and Primeros pasos tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import shiboken6
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget

from contabilizador.ui.errors import ErrorPresentation, ErrorPresenter
from contabilizador.ui.tasks import TaskHandle


class RecordingPresenter(ErrorPresenter):
    """Remembers the errors it was asked to show instead of opening a modal box."""

    def __init__(self) -> None:
        super().__init__()
        self.shown: list[BaseException] = []

    def show(
        self, parent: QWidget | None, error: BaseException, *, context: str | None = None
    ) -> ErrorPresentation:
        self.shown.append(error)
        return self.present(error, context=context)


@dataclass(slots=True)
class PendingJob:
    job: Callable[..., Any]
    on_done: Callable[[Any], None] | None
    on_error: Callable[[BaseException], None] | None
    handle: TaskHandle
    owner: QObject | None


class DeferredRunner(QObject):
    """TaskRunner that holds every job until the test runs it, to reproduce races. Like the
    real runner, it skips the callbacks of an ``owner`` that was deleted meanwhile."""

    busy_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.pending: list[PendingJob] = []

    @property
    def is_busy(self) -> bool:
        return bool(self.pending)

    def submit(
        self,
        job: Callable[..., Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        handle = TaskHandle()
        self.pending.append(PendingJob(job, on_done, on_error, handle, owner))
        return handle

    def run(self, index: int = 0) -> None:
        """Runs the pending job at ``index`` now and delivers its result like a runner would."""
        pending = self.pending.pop(index)
        context = SimpleNamespace(report=lambda done, total: None, cancelled=lambda: False)
        alive = pending.owner is None or shiboken6.isValid(pending.owner)
        try:
            result = pending.job(context)
        except BaseException as error:
            if pending.on_error is None:
                raise
            if alive:
                pending.on_error(error)
        else:
            if pending.on_done is not None and alive:
                pending.on_done(result)
        finally:
            pending.handle._mark_finished()

    def shutdown(self) -> None:
        return None
