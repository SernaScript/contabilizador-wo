"""Task runners: threaded (results delivered on the GUI thread) and synchronous (tests)."""

import threading

import pytest
import shiboken6
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QApplication, QWidget

from contabilizador.ui.tasks import (
    QtTaskRunner,
    SyncTaskRunner,
    TaskCancelledError,
    TaskContext,
    TaskHandle,
    TaskRunner,
)


@pytest.fixture
def runner(qapp: QApplication):
    runner = QtTaskRunner()
    yield runner
    runner.shutdown()


def test_qt_runner_delivers_result_on_gui_thread(qapp: QApplication, runner: QtTaskRunner, qtbot):
    results: list[object] = []
    threads: list[QThread] = []

    def job(ctx: TaskContext) -> int:
        return sum(range(10))

    def done(value: int) -> None:
        threads.append(QThread.currentThread())
        results.append(value)

    handle = runner.submit(job, on_done=done)

    assert isinstance(handle, TaskHandle)
    qtbot.waitUntil(lambda: results == [45], timeout=5000)
    assert threads == [qapp.thread()]


def test_qt_runner_reports_progress_and_busy(qapp: QApplication, runner: QtTaskRunner, qtbot):
    progress: list[tuple[int, int]] = []
    busy: list[bool] = []
    runner.busy_changed.connect(busy.append)

    def job(ctx: TaskContext) -> str:
        for done in range(1, 4):
            ctx.report(done, 3)
        return "ok"

    runner.submit(job, on_progress=lambda d, t: progress.append((d, t)))

    qtbot.waitUntil(lambda: busy == [True, False], timeout=5000)
    assert progress == [(1, 3), (2, 3), (3, 3)]
    assert runner.is_busy is False


def test_qt_runner_routes_exceptions_to_on_error(runner: QtTaskRunner, qtbot):
    errors: list[BaseException] = []

    def job(ctx: TaskContext) -> None:
        raise ValueError("boom")

    runner.submit(job, on_error=errors.append)

    qtbot.waitUntil(lambda: len(errors) == 1, timeout=5000)
    assert isinstance(errors[0], ValueError)
    assert str(errors[0]) == "boom"


def test_qt_runner_cancel_is_visible_to_the_job(runner: QtTaskRunner, qtbot):
    started = threading.Event()
    errors: list[BaseException] = []

    def job(ctx: TaskContext) -> None:
        started.set()
        while not ctx.cancelled():
            threading.Event().wait(0.01)
        raise TaskCancelledError()

    handle = runner.submit(job, on_error=errors.append)
    assert started.wait(5)
    handle.cancel()

    qtbot.waitUntil(lambda: len(errors) == 1, timeout=5000)
    assert isinstance(errors[0], TaskCancelledError)
    assert handle.is_cancelled


def test_qt_runner_skips_callbacks_when_owner_was_deleted(
    qapp: QApplication, runner: QtTaskRunner, qtbot
):
    release = threading.Event()
    calls: list[object] = []
    owner = QWidget()

    def job(ctx: TaskContext) -> str:
        release.wait(5)
        return "late"

    runner.submit(job, on_done=calls.append, on_error=calls.append, owner=owner)
    shiboken6.delete(owner)
    release.set()

    qtbot.waitUntil(lambda: not runner.is_busy, timeout=5000)
    qapp.processEvents()
    assert calls == []


def test_qt_runner_serializes_jobs_on_one_worker_thread(runner: QtTaskRunner, qtbot):
    threads: list[QThread] = []
    order: list[int] = []

    def make_job(number: int):
        def job(ctx: TaskContext) -> int:
            threads.append(QThread.currentThread())
            order.append(number)
            return number

        return job

    for number in range(3):
        runner.submit(make_job(number))

    qtbot.waitUntil(lambda: order == [0, 1, 2], timeout=5000)
    assert len(set(threads)) == 1


def test_qt_runner_shutdown_lets_queued_jobs_finish_without_callbacks(qapp: QApplication):
    runner = QtTaskRunner()
    started = threading.Event()
    release = threading.Event()
    written: list[str] = []
    import_saw_cancel: list[bool] = []
    callbacks: list[object] = []

    def slow_refresh(ctx: TaskContext) -> str:
        started.set()
        release.wait(5)
        return "read"

    def importing(ctx: TaskContext) -> str:
        import_saw_cancel.append(ctx.cancelled())
        return "imported"

    def save_edit(ctx: TaskContext) -> str:
        written.append("saved")
        return "saved"

    runner.submit(slow_refresh, on_done=callbacks.append)
    runner.submit(importing, on_done=callbacks.append)
    runner.submit(save_edit, on_done=callbacks.append, on_error=callbacks.append)
    assert started.wait(5)
    # la tarea en curso termina despues de que la ventana se cerro
    threading.Timer(0.2, release.set).start()

    finished = runner.shutdown()

    assert written == ["saved"]  # una edicion en cola nunca se pierde al salir
    assert import_saw_cancel == [True]  # lo cancelable se entera y no hace nada
    assert finished is True
    qapp.processEvents()
    assert callbacks == []  # ninguna pantalla recibe resultados despues de cerrar
    assert runner.is_busy is False


def test_qt_runner_shutdown_asks_the_running_job_to_stop(qapp: QApplication):
    runner = QtTaskRunner()
    started = threading.Event()
    noticed: list[bool] = []

    def importing(ctx: TaskContext) -> None:
        started.set()
        while not ctx.cancelled():
            threading.Event().wait(0.01)
        noticed.append(True)
        raise TaskCancelledError()

    runner.submit(importing)
    assert started.wait(5)

    assert runner.shutdown() is True
    assert noticed == [True]


def test_qt_runner_shutdown_reports_a_job_that_is_still_running(qapp: QApplication):
    runner = QtTaskRunner()
    started = threading.Event()
    release = threading.Event()

    def stuck(ctx: TaskContext) -> None:
        started.set()
        release.wait(5)

    runner.submit(stuck)
    assert started.wait(5)

    assert runner.shutdown(timeout_ms=50) is False
    release.set()
    assert runner.shutdown() is True  # esperar otra vez es seguro


def test_qt_runner_skips_a_job_cancelled_before_it_started(runner: QtTaskRunner, qtbot):
    release = threading.Event()
    ran: list[str] = []
    errors: list[BaseException] = []

    runner.submit(lambda ctx: release.wait(5))
    queued = runner.submit(lambda ctx: ran.append("ran"), on_error=errors.append)
    queued.cancel()
    release.set()

    qtbot.waitUntil(lambda: len(errors) == 1, timeout=5000)
    assert ran == []
    assert isinstance(errors[0], TaskCancelledError)


def test_qt_runner_refuses_jobs_after_shutdown(qapp: QApplication):
    runner = QtTaskRunner()
    runner.shutdown()
    ran: list[str] = []

    handle = runner.submit(lambda ctx: ran.append("late"))

    assert handle.is_cancelled and handle.is_finished
    assert ran == []


def test_sync_runner_runs_inline_and_implements_the_protocol():
    runner = SyncTaskRunner()
    results: list[int] = []
    progress: list[tuple[int, int]] = []
    busy: list[bool] = []
    runner.busy_changed.connect(busy.append)

    def job(ctx: TaskContext) -> int:
        ctx.report(1, 1)
        return 7

    handle = runner.submit(
        job, on_done=results.append, on_progress=lambda d, t: progress.append((d, t))
    )

    assert isinstance(runner, TaskRunner)
    assert results == [7]
    assert progress == [(1, 1)]
    assert busy == [True, False]
    assert handle.is_finished


def test_sync_runner_routes_errors_or_raises_without_handler():
    runner = SyncTaskRunner()
    errors: list[BaseException] = []

    def failing(ctx: TaskContext) -> None:
        raise KeyError("missing")

    runner.submit(failing, on_error=errors.append)
    assert isinstance(errors[0], KeyError)

    with pytest.raises(KeyError):
        runner.submit(failing)


def test_sync_runner_skips_callbacks_of_a_deleted_owner():
    runner = SyncTaskRunner()
    owner = QObject()
    shiboken6.delete(owner)
    calls: list[object] = []

    runner.submit(lambda ctx: 1, on_done=calls.append, owner=owner)

    assert calls == []
