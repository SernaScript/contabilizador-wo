"""Background work for containers: one worker thread, results delivered on the GUI thread.

``QtTaskRunner`` owns a private ``QThreadPool`` with one thread, so every use case that
touches the database runs serialized. Callbacks are skipped when ``owner`` (the widget
that asked) was deleted meanwhile. On ``shutdown`` the queued jobs still run (an edit the
screen already shows must reach the database) without callbacks, and jobs that poll
``ctx.cancelled()`` stop early. ``SyncTaskRunner`` runs jobs inline for widget tests.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

import shiboken6
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal, Slot

T = TypeVar("T")
log = logging.getLogger(__name__)


class TaskCancelledError(Exception):
    """Raised by a job that noticed ``ctx.cancelled()``, or by the runner for jobs that were
    cancelled before they started."""


class TaskContext(Protocol):
    def report(self, done: int, total: int) -> None:
        """Progress; delivered to ``on_progress`` on the GUI thread."""

    def cancelled(self) -> bool:
        """True once ``TaskHandle.cancel()`` was called or the runner is shutting down;
        jobs poll it between steps."""
        ...


class TaskHandle:
    """Cancellation token returned by ``submit``; safe to call from the GUI thread."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._finished = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    @property
    def is_finished(self) -> bool:
        return self._finished.is_set()

    def _mark_finished(self) -> None:
        self._finished.set()


@runtime_checkable
class TaskRunner(Protocol):
    def submit(
        self,
        job: Callable[[TaskContext], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle: ...

    def shutdown(self) -> bool | None:
        """Stops taking jobs; ``False`` when a job is still running after the wait."""
        ...

    @property
    def is_busy(self) -> bool: ...


def _owner_alive(owner: QObject | None) -> bool:
    return owner is None or shiboken6.isValid(owner)


class _Context:
    def __init__(
        self,
        handle: TaskHandle,
        report: Callable[[int, int], None],
        stopping: threading.Event | None = None,
    ) -> None:
        self._handle = handle
        self._report = report
        self._stopping = stopping

    def report(self, done: int, total: int) -> None:
        self._report(done, total)

    def cancelled(self) -> bool:
        stopping = self._stopping is not None and self._stopping.is_set()
        return self._handle.is_cancelled or stopping


class _TaskSignals(QObject):
    """Lives on the GUI thread; the worker emits, queued connections deliver here."""

    done = Signal(object)
    failed = Signal(object)
    progress = Signal(int, int)
    finished = Signal(object)

    def __init__(
        self,
        handle: TaskHandle,
        on_done: Callable[[Any], None] | None,
        on_error: Callable[[BaseException], None] | None,
        on_progress: Callable[[int, int], None] | None,
        owner: QObject | None,
    ) -> None:
        super().__init__()
        self._handle = handle
        self._on_done = on_done
        self._on_error = on_error
        self._on_progress = on_progress
        self._owner = owner
        self.closed = False
        self.done.connect(self._deliver_done, Qt.ConnectionType.QueuedConnection)
        self.failed.connect(self._deliver_failed, Qt.ConnectionType.QueuedConnection)
        self.progress.connect(self._deliver_progress, Qt.ConnectionType.QueuedConnection)

    def _callbacks_allowed(self) -> bool:
        return not self.closed and _owner_alive(self._owner)

    @Slot(object)
    def _deliver_done(self, result: object) -> None:
        if self._callbacks_allowed() and self._on_done is not None:
            self._on_done(result)
        self._finish()

    @Slot(object)
    def _deliver_failed(self, error: object) -> None:
        if self._callbacks_allowed():
            if self._on_error is not None:
                self._on_error(error)  # type: ignore[arg-type]
            else:
                log.error("task failed without on_error", exc_info=error)  # type: ignore[arg-type]
        self._finish()

    @Slot(int, int)
    def _deliver_progress(self, done: int, total: int) -> None:
        if self._callbacks_allowed() and self._on_progress is not None:
            self._on_progress(done, total)

    def _finish(self) -> None:
        self._handle._mark_finished()
        self.finished.emit(self)


class _Runnable(QRunnable):
    def __init__(
        self,
        job: Callable[[TaskContext], Any],
        handle: TaskHandle,
        signals: _TaskSignals,
        stopping: threading.Event,
    ) -> None:
        super().__init__()
        self._job = job
        self._handle = handle
        self._signals = signals
        self._stopping = stopping
        self.setAutoDelete(True)

    def run(self) -> None:
        # Solo lo que el usuario cancelo se salta; al cerrar la app lo encolado igual corre
        if self._handle.is_cancelled:
            self._signals.failed.emit(TaskCancelledError())
            return
        try:
            context = _Context(self._handle, self._signals.progress.emit, self._stopping)
            result = self._job(context)
        except BaseException as error:
            self._signals.failed.emit(error)
        else:
            self._signals.done.emit(result)


class QtTaskRunner(QObject):
    """Serialized background runner; ``busy_changed(bool)`` flips on first/last task."""

    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._active: dict[int, tuple[TaskHandle, _TaskSignals]] = {}
        self._closed = False
        self._stopping = threading.Event()

    @property
    def is_busy(self) -> bool:
        return bool(self._active)

    def submit(
        self,
        job: Callable[[TaskContext], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        handle = TaskHandle()
        if self._closed:
            handle.cancel()
            handle._mark_finished()
            return handle
        signals = _TaskSignals(handle, on_done, on_error, on_progress, owner)
        signals.finished.connect(self._on_task_finished)
        was_busy = self.is_busy
        self._active[id(signals)] = (handle, signals)
        self._pool.start(_Runnable(job, handle, signals, self._stopping))
        if not was_busy:
            self.busy_changed.emit(True)
        return handle

    @Slot(object)
    def _on_task_finished(self, signals: object) -> None:
        # Tras ``shutdown`` la tarea ya no esta en la lista: no se avisa dos veces
        if self._active.pop(id(signals), None) is not None and not self._active:
            self.busy_changed.emit(False)

    def shutdown(self, timeout_ms: int = 10_000) -> bool:
        """Stops taking jobs and waits for the queued ones; no callback runs any more.

        Queued jobs are not dropped: an edit or a void the screen already shows must reach
        the database. Jobs that poll ``ctx.cancelled()`` (the import) see True and stop
        without storing anything. Returns False when a job is still running after
        ``timeout_ms``; calling it again waits again.
        """
        self._closed = True
        self._stopping.set()
        for _handle, signals in self._active.values():
            signals.closed = True
        if not self._pool.waitForDone(timeout_ms):
            return False
        was_busy = self.is_busy
        for handle, _signals in self._active.values():
            handle._mark_finished()
        self._active.clear()
        if was_busy:
            self.busy_changed.emit(False)
        return True


class SyncTaskRunner(QObject):
    """Runs jobs inline on the calling thread; without ``on_error`` the exception propagates
    so widget tests see it."""

    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.handles: list[TaskHandle] = []

    @property
    def is_busy(self) -> bool:
        return False

    def submit(
        self,
        job: Callable[[TaskContext], Any],
        *,
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        owner: QObject | None = None,
    ) -> TaskHandle:
        handle = TaskHandle()
        self.handles.append(handle)
        self.busy_changed.emit(True)
        try:
            result = job(_Context(handle, on_progress or (lambda done, total: None)))
        except BaseException as error:
            if on_error is None:
                raise
            if _owner_alive(owner):
                on_error(error)
        else:
            if on_done is not None and _owner_alive(owner):
                on_done(result)
        finally:
            handle._mark_finished()
            self.busy_changed.emit(False)
        return handle

    def shutdown(self) -> bool:
        return True  # nada queda en cola: cada tarea ya corrio al enviarla
