"""Thread lifecycle tests for threaded LiteStore workers."""

from __future__ import annotations

from src.types import CommandName, CommandRequest
from src.worker import StoreWorker


def test_threaded_worker_start_and_stop_lifecycle() -> None:
    worker = StoreWorker("w0", 0, threaded=True)

    worker.start()
    assert worker.is_thread_running is True

    response = worker.execute(CommandRequest(command=CommandName.PING, args=()))
    assert response.message == "PONG"

    worker.stop()
    assert worker.is_thread_running is False


def test_threaded_worker_snapshot_isolation() -> None:
    worker = StoreWorker("w1", 1, threaded=True)
    worker.start()

    try:
        worker.execute(CommandRequest(command=CommandName.SET, args=("k1", "v1")))
        snapshot = worker.snapshot()
        assert snapshot == {"k1": "v1"}
    finally:
        worker.stop()
