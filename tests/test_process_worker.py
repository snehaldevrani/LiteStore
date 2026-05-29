"""Tests for multiprocessing worker process lifecycle."""

from __future__ import annotations

import multiprocessing
import time
from pathlib import Path
from queue import Empty

import pytest

from src.process_worker import worker_entry
from src.types import (
    CommandName,
    FsyncPolicy,
    WorkerControl,
    WorkerRequest,
    WorkerResponse,
)


@pytest.fixture(autouse=True)
def _set_spawn_method() -> None:
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        pass


def test_worker_process_handles_set_get_del(tmp_path: Path) -> None:
    req_q: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    res_q: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]

    p = multiprocessing.Process(
        target=worker_entry,
        args=("w0", 0, req_q, res_q, str(tmp_path / "w0.aof"), "never", 100),
    )
    p.start()
    time.sleep(0.3)

    req_q.put(WorkerRequest(request_id="r1", command=CommandName.SET, args=("key1", "hello")))
    resp: WorkerResponse = res_q.get(timeout=2)
    assert resp.request_id == "r1"
    assert resp.message == "OK"

    req_q.put(WorkerRequest(request_id="r2", command=CommandName.GET, args=("key1",)))
    resp = res_q.get(timeout=2)
    assert resp.request_id == "r2"
    assert resp.value == "hello"

    req_q.put(WorkerRequest(request_id="r3", command=CommandName.DEL, args=("key1",)))
    resp = res_q.get(timeout=2)
    assert resp.request_id == "r3"
    assert resp.integer == 1

    req_q.put(WorkerControl(action="shutdown"))
    p.join(timeout=3)
    assert not p.is_alive()


def test_worker_process_persists_writes(tmp_path: Path) -> None:
    aof_path = tmp_path / "w0.aof"
    req_q: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    res_q: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]

    p = multiprocessing.Process(
        target=worker_entry,
        args=("w0", 0, req_q, res_q, str(aof_path), "always", 1),
    )
    p.start()
    time.sleep(0.3)

    req_q.put(WorkerRequest(request_id="r1", command=CommandName.SET, args=("persist-key", "data")))
    res_q.get(timeout=2)

    req_q.put(WorkerControl(action="shutdown"))
    p.join(timeout=3)

    assert aof_path.exists()
    content = aof_path.read_text()
    assert "persist-key" in content


def test_worker_process_replays_aof_on_start(tmp_path: Path) -> None:
    aof_path = tmp_path / "w0.aof"
    req_q: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    res_q: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]

    # First process: write data
    p1 = multiprocessing.Process(
        target=worker_entry,
        args=("w0", 0, req_q, res_q, str(aof_path), "always", 1),
    )
    p1.start()
    time.sleep(0.3)
    req_q.put(WorkerRequest(request_id="r1", command=CommandName.SET, args=("replay-key", "replayed")))
    res_q.get(timeout=2)
    req_q.put(WorkerControl(action="shutdown"))
    p1.join(timeout=3)

    # Second process: should replay and have the key
    req_q2: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    res_q2: multiprocessing.Queue = multiprocessing.Queue()  # type: ignore[type-arg]
    p2 = multiprocessing.Process(
        target=worker_entry,
        args=("w0", 0, req_q2, res_q2, str(aof_path), "always", 1),
    )
    p2.start()
    time.sleep(0.3)
    req_q2.put(WorkerRequest(request_id="r2", command=CommandName.GET, args=("replay-key",)))
    resp = res_q2.get(timeout=2)
    assert resp.value == "replayed"

    req_q2.put(WorkerControl(action="shutdown"))
    p2.join(timeout=3)
