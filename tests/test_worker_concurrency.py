"""Concurrency tests for worker dispatch (in-process mode)."""

from __future__ import annotations

from src.router import DeterministicHashRouter
from src.types import CommandName, CommandRequest
from src.worker import StoreWorker


def test_workers_handle_sequential_dispatch() -> None:
    workers = {
        "w0": StoreWorker("w0", 0),
        "w1": StoreWorker("w1", 1),
        "w2": StoreWorker("w2", 2),
        "w3": StoreWorker("w3", 3),
    }
    router = DeterministicHashRouter(list(workers.keys()))

    for worker in workers.values():
        worker.start()

    try:
        for index in range(500):
            key = f"stress:{index}"
            request = CommandRequest(command=CommandName.SET, args=(key, f"v{index}"))
            route = router.route_request(request)
            workers[route.worker_id].execute(request)

        for index in range(500):
            key = f"stress:{index}"
            request = CommandRequest(command=CommandName.GET, args=(key,))
            route = router.route_request(request)
            response = workers[route.worker_id].execute(request)
            assert response.value == f"v{index}"
    finally:
        for worker in workers.values():
            worker.stop()
