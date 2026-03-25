"""Threading utilities for PyQt6 GUI."""

from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal


class WorkerSignals(QObject):
    """Standard signals for worker threads."""

    progress = pyqtSignal(int, int, str)  # current, total, message
    finished = pyqtSignal(object)  # result
    error = pyqtSignal(Exception)  # exception


class WorkerThread(QThread):
    """Generic worker thread for background tasks."""

    def __init__(self, task_func, parent=None):
        """
        Initialize worker thread.

        Args:
            task_func: Function to execute (receives signals object for progress updates)
            parent: Parent widget
        """
        super().__init__(parent)
        self.task_func = task_func
        self.signals = WorkerSignals()

    def run(self) -> None:
        """Execute the task function and emit results."""
        try:
            result = self.task_func(self.signals)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(e)


def run_in_background(
    parent,
    task_func,
    on_success,
    on_error,
    on_progress=None,
    busy_callback=None,
):
    """
    Run a task in background thread.

    Args:
        parent: Parent widget
        task_func: Function to execute (receives signals object for progress updates)
        on_success: Slot for success(result)
        on_error: Slot for error(Exception)
        on_progress: Optional slot for progress(current, total, message)
        busy_callback: Optional callback(busy: bool) when task starts/ends

    Returns:
        The created WorkerThread instance
    """
    if busy_callback:
        busy_callback(True)

    thread = WorkerThread(task_func, parent)
    thread.signals.finished.connect(on_success)
    thread.signals.error.connect(on_error)

    if on_progress:
        thread.signals.progress.connect(on_progress)

    if busy_callback:

        def on_finished():
            busy_callback(False)

        thread.signals.finished.connect(on_finished)
        thread.signals.error.connect(on_finished)

    thread.start()
    return thread
