"""Worker process pool manager for LiteStore main process."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from multiprocessing import Process, Queue
from pathlib import Path

from .process_worker import worker_entry
from .types import (
    CommandRequest,
    CommandResponse,
    FsyncPolicy,
    ResponseKind,
    WorkerControl,
    WorkerRequest,
    WorkerResponse,
)


@dataclass
class _WorkerHandle:
    worker_id: str
    partition_id: int
    request_queue: Queue = field(default_factory=Queue)  # type: ignore[type-arg]
    response_queue: Queue = field(default_factory=Queue)  # type: ignore[type-arg]
    process: Process | None = None


class WorkerPool:
    """Manages worker processes and provides async IPC from the main process."""

    def __init__(
        self,
        worker_count: int,
        aof_base_path: Path,
        fsync_policy: FsyncPolicy = FsyncPolicy.EVERY_N,
        fsync_every_n: int = 100,
    ) -> None:
        self._worker_count = worker_count
        self._aof_base_path = aof_base_path
        self._fsync_policy = fsync_policy
        self._fsync_every_n = fsync_every_n
        self._handles: dict[str, _WorkerHandle] = {}
        self._executor_pool: asyncio.AbstractEventLoop | None = None

        for i in range(worker_count):
            worker_id = f"w{i}"
            self._handles[worker_id] = _WorkerHandle(
                worker_id=worker_id,
                partition_id=i,
            )

    @property
    def worker_ids(self) -> list[str]:
        return list(self._handles.keys())

    def start_all(self) -> None:
        """Fork worker processes."""
        for handle in self._handles.values():
            aof_path = self._aof_path_for_worker(handle.worker_id)
            p = Process(
                target=worker_entry,
                args=(
                    handle.worker_id,
                    handle.partition_id,
                    handle.request_queue,
                    handle.response_queue,
                    str(aof_path),
                    self._fsync_policy.value,
                    self._fsync_every_n,
                ),
                name=f"litestore-{handle.worker_id}",
                daemon=True,
            )
            p.start()
            handle.process = p

    async def execute(self, worker_id: str, request: CommandRequest) -> CommandResponse:
        """Send request to worker process and await response asynchronously."""
        handle = self._handles[worker_id]
        req_id = request.request_id or str(uuid.uuid4())

        worker_req = WorkerRequest(
            request_id=req_id,
            command=request.command,
            args=request.args,
            client_id=request.client_id,
        )

        loop = asyncio.get_running_loop()
        handle.request_queue.put(worker_req)
        response: WorkerResponse = await loop.run_in_executor(
            None, handle.response_queue.get
        )

        return CommandResponse(
            kind=response.kind,
            message=response.message,
            value=response.value,
            integer=response.integer,
            error_code=response.error_code,
            request_id=response.request_id,
        )

    def shutdown_all(self) -> None:
        """Send shutdown to all workers and join processes."""
        for handle in self._handles.values():
            handle.request_queue.put(WorkerControl(action="shutdown"))

        for handle in self._handles.values():
            if handle.process is not None:
                handle.process.join(timeout=5)
                if handle.process.is_alive():
                    handle.process.terminate()

    def _aof_path_for_worker(self, worker_id: str) -> Path:
        stem = self._aof_base_path.stem
        suffix = self._aof_base_path.suffix
        return self._aof_base_path.parent / f"{stem}-{worker_id}{suffix}"
