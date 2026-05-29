"""In-process worker for sharded LiteStore execution (single-process mode)."""

from __future__ import annotations

from .commands import execute_command
from .interfaces import StoreInterface
from .store import MemoryStore
from .types import CommandRequest, CommandResponse, WorkerStats


class StoreWorker:
    """Single worker owning one key partition and one store instance.

    Used for in-process (non-multiprocessing) mode and unit tests.
    For production multi-process parallelism, see process_worker.py and worker_pool.py.
    """

    def __init__(
        self,
        worker_id: str,
        partition_id: int,
        store: StoreInterface | None = None,
    ) -> None:
        self.worker_id = worker_id
        self.partition_id = partition_id
        self._store = store if store is not None else MemoryStore()
        self._running = False
        self._in_flight = 0

    @property
    def store(self) -> StoreInterface:
        return self._store

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def execute(self, request: CommandRequest) -> CommandResponse:
        """Execute request against this worker's owned store."""
        self._ensure_started()
        self._in_flight += 1
        try:
            self._store.process_expirations()
            return execute_command(request, self._store)
        finally:
            self._in_flight -= 1

    async def execute_async(self, request: CommandRequest) -> CommandResponse:
        """Async wrapper — executes synchronously since there's no thread boundary."""
        return self.execute(request)

    def run_expiration_cycle(self, now: float | None = None) -> int:
        return self._store.process_expirations(now)

    async def run_expiration_cycle_async(self, now: float | None = None) -> int:
        return self._store.process_expirations(now)

    def snapshot(self) -> dict[str, str]:
        return self._store.snapshot()

    async def snapshot_async(self) -> dict[str, str]:
        return self._store.snapshot()

    def stats(self) -> WorkerStats:
        return WorkerStats(
            worker_id=self.worker_id,
            partition_id=self.partition_id,
            in_flight=self._in_flight,
            queued=0,
        )

    def _ensure_started(self) -> None:
        if not self._running:
            raise RuntimeError(f"Worker {self.worker_id} is not running")
