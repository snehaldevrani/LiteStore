"""Lifecycle tests for LiteStore workers (in-process mode)."""

from __future__ import annotations

from src.types import CommandName, CommandRequest
from src.worker import StoreWorker


def test_worker_start_and_stop_lifecycle() -> None:
    worker = StoreWorker("w0", 0)

    worker.start()
    response = worker.execute(CommandRequest(command=CommandName.PING, args=()))
    assert response.message == "PONG"

    worker.stop()


def test_worker_snapshot_isolation() -> None:
    worker = StoreWorker("w1", 1)
    worker.start()

    try:
        worker.execute(CommandRequest(command=CommandName.SET, args=("k1", "v1")))
        snapshot = worker.snapshot()
        assert snapshot == {"k1": "v1"}
    finally:
        worker.stop()


def test_worker_execute_without_start_raises() -> None:
    worker = StoreWorker("w2", 2)
    try:
        worker.execute(CommandRequest(command=CommandName.PING, args=()))
        assert False, "Should have raised"
    except RuntimeError:
        pass
