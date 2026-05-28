"""Concurrency stress tests for threaded worker dispatch."""

from __future__ import annotations

import asyncio

import pytest

from src.router import DeterministicHashRouter
from src.types import CommandName, CommandRequest
from src.worker import StoreWorker


@pytest.mark.asyncio
async def test_threaded_workers_handle_concurrent_dispatch() -> None:
    workers = {
        "w0": StoreWorker("w0", 0, threaded=True),
        "w1": StoreWorker("w1", 1, threaded=True),
        "w2": StoreWorker("w2", 2, threaded=True),
        "w3": StoreWorker("w3", 3, threaded=True),
    }
    router = DeterministicHashRouter(list(workers.keys()))

    for worker in workers.values():
        worker.start()

    try:
        async def set_key(index: int) -> None:
            key = f"stress:{index}"
            request = CommandRequest(command=CommandName.SET, args=(key, f"v{index}"))
            route = router.route_request(request)
            await workers[route.worker_id].execute_async(request)

        await asyncio.gather(*(set_key(index) for index in range(500)))

        async def get_key(index: int) -> str | None:
            key = f"stress:{index}"
            request = CommandRequest(command=CommandName.GET, args=(key,))
            route = router.route_request(request)
            response = await workers[route.worker_id].execute_async(request)
            return response.value

        values = await asyncio.gather(*(get_key(index) for index in range(500)))
        assert all(value is not None for value in values)
    finally:
        for worker in workers.values():
            worker.stop()
