"""Multiprocessing worker process for LiteStore partitions."""

from __future__ import annotations

import time
from multiprocessing import Queue
from pathlib import Path
from queue import Empty

from .commands import execute_command
from .persistence import AofPersistence
from .store import MemoryStore
from .types import (
    CommandName,
    CommandRequest,
    CommandResponse,
    FsyncPolicy,
    ResponseKind,
    WorkerControl,
    WorkerRequest,
    WorkerResponse,
)


class WorkerProcess:
    """Runs in a child process, owns one partition's state entirely."""

    def __init__(
        self,
        worker_id: str,
        partition_id: int,
        request_queue: Queue,  # type: ignore[type-arg]
        response_queue: Queue,  # type: ignore[type-arg]
        aof_path: Path | None = None,
        fsync_policy: FsyncPolicy = FsyncPolicy.EVERY_N,
        fsync_every_n: int = 100,
    ) -> None:
        self._worker_id = worker_id
        self._partition_id = partition_id
        self._request_queue = request_queue
        self._response_queue = response_queue
        self._store = MemoryStore()
        self._persistence: AofPersistence | None = None
        if aof_path is not None:
            self._persistence = AofPersistence(
                aof_path,
                fsync_policy=fsync_policy,
                fsync_every_n=fsync_every_n,
            )
        self._running = True

    def run(self) -> None:
        """Main loop: pull requests, execute, respond."""
        if self._persistence:
            for record in self._persistence.replay():
                self._store.apply_replay_request(record.request)

        last_expiration = time.time()

        while self._running:
            try:
                msg = self._request_queue.get(timeout=0.05)
            except Empty:
                now = time.time()
                if now - last_expiration > 0.1:
                    self._store.process_expirations()
                    last_expiration = now
                continue

            if isinstance(msg, WorkerControl):
                self._handle_control(msg)
            elif isinstance(msg, WorkerRequest):
                self._handle_request(msg)

            now = time.time()
            if now - last_expiration > 0.1:
                self._store.process_expirations()
                last_expiration = now

    def _handle_request(self, msg: WorkerRequest) -> None:
        request = CommandRequest(
            command=msg.command,
            args=msg.args,
            request_id=msg.request_id,
            client_id=msg.client_id,
        )
        response = execute_command(request, self._store)

        if self._persistence and _is_write(request, response):
            self._persistence.append_request(request)

        self._response_queue.put(WorkerResponse(
            request_id=msg.request_id,
            kind=response.kind,
            message=response.message,
            value=response.value,
            integer=response.integer,
            error_code=response.error_code,
        ))

    def _handle_control(self, msg: WorkerControl) -> None:
        if msg.action == "shutdown":
            self._running = False
            if self._persistence:
                self._persistence.close()
        elif msg.action == "snapshot":
            snapshot = self._store.snapshot()
            self._response_queue.put(WorkerResponse(
                request_id=msg.request_id or "__snapshot__",
                kind=ResponseKind.BULK_STRING,
                value=str(snapshot),
                message="__snapshot__",
            ))


def _is_write(request: CommandRequest, response: CommandResponse) -> bool:
    if response.kind == ResponseKind.ERROR:
        return False
    if request.command == CommandName.SET:
        return True
    if request.command == CommandName.DEL:
        return True
    if request.command == CommandName.EXPIRE and response.integer == 1:
        return True
    return False


def worker_entry(
    worker_id: str,
    partition_id: int,
    request_queue: Queue,  # type: ignore[type-arg]
    response_queue: Queue,  # type: ignore[type-arg]
    aof_path: str | None,
    fsync_policy: str,
    fsync_every_n: int,
) -> None:
    """Entry point for multiprocessing.Process target."""
    aof = Path(aof_path) if aof_path else None
    policy = FsyncPolicy(fsync_policy)
    worker = WorkerProcess(
        worker_id=worker_id,
        partition_id=partition_id,
        request_queue=request_queue,
        response_queue=response_queue,
        aof_path=aof,
        fsync_policy=policy,
        fsync_every_n=fsync_every_n,
    )
    worker.run()
