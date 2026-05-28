"""Worker ownership boundary for sharded LiteStore execution."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from threading import Event, Thread

from .commands import execute_command
from .interfaces import StoreInterface
from .store import MemoryStore
from .types import CommandRequest, CommandResponse, WorkerStats


class StoreWorker:
	"""Single worker owning one key partition and one store instance."""

	def __init__(
		self,
		worker_id: str,
		partition_id: int,
		store: StoreInterface | None = None,
		*,
		threaded: bool = False,
	) -> None:
		self.worker_id = worker_id
		self.partition_id = partition_id
		self._store = store if store is not None else MemoryStore()
		self._threaded = threaded
		self._running = False
		self._in_flight = 0
		self._loop: asyncio.AbstractEventLoop | None = None
		self._thread: Thread | None = None
		self._loop_ready = Event()

	@property
	def store(self) -> StoreInterface:
		"""Expose worker-owned store for integration wiring and tests."""
		return self._store

	@property
	def is_thread_running(self) -> bool:
		"""Return whether worker thread is currently active."""
		return bool(self._thread and self._thread.is_alive())

	def start(self) -> None:
		"""Mark worker as available for request processing."""
		if self._running:
			return

		if self._threaded:
			self._loop_ready.clear()
			self._thread = Thread(target=self._run_event_loop_thread, name=f"litestore-worker-{self.worker_id}", daemon=True)
			self._thread.start()
			if not self._loop_ready.wait(timeout=5):
				raise RuntimeError(f"Worker {self.worker_id} failed to start thread event loop")

		self._running = True

	def stop(self) -> None:
		"""Mark worker as unavailable for request processing."""
		if not self._running:
			return

		if self._threaded and self._loop is not None:
			self._loop.call_soon_threadsafe(self._loop.stop)
			if self._thread is not None:
				self._thread.join(timeout=5)

		self._loop = None
		self._thread = None
		self._running = False

	def execute(self, request: CommandRequest) -> CommandResponse:
		"""Execute request against this worker's owned store."""
		if self._threaded:
			self._ensure_started()
			future = self._submit_coroutine(self._execute_on_worker(request))
			return future.result()

		return self._execute_local(request)

	async def execute_async(self, request: CommandRequest) -> CommandResponse:
		"""Execute request and return response in async runtimes."""
		if self._threaded:
			self._ensure_started()
			future = self._submit_coroutine(self._execute_on_worker(request))
			return await asyncio.wrap_future(future)

		return self._execute_local(request)

	def run_expiration_cycle(self, now: float | None = None) -> int:
		"""Process due expirations for this worker."""
		if self._threaded:
			self._ensure_started()
			future = self._submit_coroutine(self._process_expirations_on_worker(now))
			return future.result()

		return self._store.process_expirations(now)

	async def run_expiration_cycle_async(self, now: float | None = None) -> int:
		"""Async variant of expiration cycle for runtime integration."""
		if self._threaded:
			self._ensure_started()
			future = self._submit_coroutine(self._process_expirations_on_worker(now))
			return await asyncio.wrap_future(future)

		return self._store.process_expirations(now)

	def snapshot(self) -> dict[str, str]:
		"""Return a safe snapshot of this worker-owned store."""
		if self._threaded:
			self._ensure_started()
			future = self._submit_coroutine(self._snapshot_on_worker())
			return future.result()

		return self._store.snapshot()

	async def snapshot_async(self) -> dict[str, str]:
		"""Async variant for snapshot retrieval."""
		if self._threaded:
			self._ensure_started()
			future = self._submit_coroutine(self._snapshot_on_worker())
			return await asyncio.wrap_future(future)

		return self._store.snapshot()

	def stats(self) -> WorkerStats:
		"""Return worker diagnostics required by interfaces."""
		return WorkerStats(
			worker_id=self.worker_id,
			partition_id=self.partition_id,
			in_flight=self._in_flight,
			queued=0,
		)

	def _execute_local(self, request: CommandRequest) -> CommandResponse:
		self._in_flight += 1
		try:
			self.run_expiration_cycle()
			return execute_command(request, self._store)
		finally:
			self._in_flight -= 1

	async def _execute_on_worker(self, request: CommandRequest) -> CommandResponse:
		self._in_flight += 1
		try:
			self._store.process_expirations()
			return execute_command(request, self._store)
		finally:
			self._in_flight -= 1

	async def _process_expirations_on_worker(self, now: float | None) -> int:
		return self._store.process_expirations(now)

	async def _snapshot_on_worker(self) -> dict[str, str]:
		return self._store.snapshot()

	def _submit_coroutine(self, coroutine: asyncio.Future | asyncio.coroutines) -> Future:
		if self._loop is None:
			raise RuntimeError(f"Worker {self.worker_id} event loop is not initialized")
		return asyncio.run_coroutine_threadsafe(coroutine, self._loop)

	def _ensure_started(self) -> None:
		if not self._running:
			raise RuntimeError(f"Worker {self.worker_id} is not running")

	def _run_event_loop_thread(self) -> None:
		loop = asyncio.new_event_loop()
		self._loop = loop
		asyncio.set_event_loop(loop)
		self._loop_ready.set()
		try:
			loop.run_forever()
		finally:
			pending = asyncio.all_tasks(loop)
			for task in pending:
				task.cancel()
			if pending:
				loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
			loop.close()
