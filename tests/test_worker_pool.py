"""Tests for WorkerPool lifecycle and async dispatch."""

from __future__ import annotations

import asyncio
import multiprocessing
from pathlib import Path

import pytest

from src.types import CommandName, CommandRequest, ResponseKind
from src.worker_pool import WorkerPool


@pytest.fixture(autouse=True)
def _set_spawn_method() -> None:
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass


@pytest.mark.asyncio
async def test_pool_start_execute_shutdown(tmp_path: Path) -> None:
    pool = WorkerPool(worker_count=2, aof_base_path=tmp_path / "pool.aof")
    pool.start_all()
    await asyncio.sleep(0.3)

    request = CommandRequest(
        command=CommandName.SET,
        args=("test-key", "test-val"),
        request_id="pool-r1",
    )
    response = await pool.execute("w0", request)
    assert response.kind == ResponseKind.SIMPLE_STRING
    assert response.message == "OK"

    get_req = CommandRequest(
        command=CommandName.GET,
        args=("test-key",),
        request_id="pool-r2",
    )
    get_resp = await pool.execute("w0", get_req)
    assert get_resp.kind == ResponseKind.BULK_STRING
    assert get_resp.value == "test-val"

    pool.shutdown_all()


@pytest.mark.asyncio
async def test_pool_concurrent_requests(tmp_path: Path) -> None:
    pool = WorkerPool(worker_count=4, aof_base_path=tmp_path / "concurrent.aof")
    pool.start_all()
    await asyncio.sleep(0.3)

    async def set_key(worker_id: str, key: str, value: str) -> None:
        req = CommandRequest(command=CommandName.SET, args=(key, value), request_id=f"c-{key}")
        resp = await pool.execute(worker_id, req)
        assert resp.kind == ResponseKind.SIMPLE_STRING

    tasks = []
    for i in range(50):
        worker_id = f"w{i % 4}"
        tasks.append(set_key(worker_id, f"key:{i}", f"val:{i}"))

    await asyncio.gather(*tasks)
    pool.shutdown_all()


@pytest.mark.asyncio
async def test_pool_isolation_between_workers(tmp_path: Path) -> None:
    pool = WorkerPool(worker_count=2, aof_base_path=tmp_path / "isolation.aof")
    pool.start_all()
    await asyncio.sleep(0.3)

    await pool.execute("w0", CommandRequest(command=CommandName.SET, args=("only-w0", "yes"), request_id="i1"))

    get_resp = await pool.execute("w1", CommandRequest(command=CommandName.GET, args=("only-w0",), request_id="i2"))
    assert get_resp.kind == ResponseKind.NULL

    pool.shutdown_all()
