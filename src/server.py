"""Runtime server integration for LiteStore network surfaces."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import perf_counter

from .config import LiteStoreConfig
from .errors import LiteStoreError, PersistenceError
from .metrics import MetricsCollector
from .persistence import AofPersistence
from .protocol import parse_command, serialize_response
from .router import DeterministicHashRouter
from .types import CommandName, CommandRequest, CommandResponse, ErrorCode, ResponseKind
from .worker import StoreWorker


@dataclass(frozen=True, slots=True)
class HttpResponse:
	"""Minimal HTTP response shape for lightweight endpoints."""

	status_code: int
	content_type: str
	body: str


class MetricsHttpEndpoint:
	"""Tiny HTTP surface that exposes Prometheus metrics at /metrics."""

	def __init__(self, metrics: MetricsCollector) -> None:
		self._metrics = metrics

	def handle_request(self, path: str) -> HttpResponse:
		"""Return a text response for a simple HTTP path."""
		if path != "/metrics":
			return HttpResponse(status_code=404, content_type="text/plain; charset=utf-8", body="not found\n")

		return HttpResponse(
			status_code=200,
			content_type="text/plain; version=0.0.4; charset=utf-8",
			body=self._metrics.render_prometheus(),
		)


class LiteStoreRuntime:
	"""Runnable LiteStore integration layer for TCP commands and metrics."""

	def __init__(self, config: LiteStoreConfig) -> None:
		self._config = config
		worker_ids = [f"w{index}" for index in range(config.worker_count)]
		self._router = DeterministicHashRouter(worker_ids)
		self._workers = {
			worker_id: StoreWorker(worker_id=worker_id, partition_id=index, threaded=True)
			for index, worker_id in enumerate(worker_ids)
		}
		self._metrics = MetricsCollector()
		self._metrics_endpoint = MetricsHttpEndpoint(self._metrics)
		self._persistence = AofPersistence(config.aof_path)
		self._tcp_server: asyncio.AbstractServer | None = None
		self._metrics_server: asyncio.AbstractServer | None = None
		self._connection_sequence = 0

	@property
	def port(self) -> int:
		return _bound_port(self._tcp_server)

	@property
	def metrics_port(self) -> int:
		return _bound_port(self._metrics_server)

	async def start(self) -> None:
		"""Start worker-owned runtime surfaces and replay persisted state."""
		for worker in self._workers.values():
			worker.start()

		self._replay_persistence()
		await self._refresh_metrics_snapshot()

		self._tcp_server = await asyncio.start_server(
			self._handle_client,
			host=self._config.host,
			port=self._config.port,
		)
		self._metrics_server = await asyncio.start_server(
			self._handle_metrics_http,
			host=self._config.metrics_host,
			port=self._config.metrics_port,
		)

	async def close(self) -> None:
		"""Gracefully shut down network listeners and owned resources."""
		if self._tcp_server is not None:
			self._tcp_server.close()
			await self._tcp_server.wait_closed()
			self._tcp_server = None

		if self._metrics_server is not None:
			self._metrics_server.close()
			await self._metrics_server.wait_closed()
			self._metrics_server = None

		for worker in self._workers.values():
			worker.stop()

		self._persistence.close()

	async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
		connection_id = self._next_connection_id(writer)
		request_index = 0
		try:
			while not reader.at_eof():
				raw = await reader.readline()
				if not raw:
					break

				request_index += 1
				request_id = f"{connection_id}:{request_index}"
				response = await self._process_command_bytes(raw, connection_id=connection_id, request_id=request_id)
				writer.write(serialize_response(response).encode("utf-8"))
				await writer.drain()
		finally:
			writer.close()
			await writer.wait_closed()

	async def _handle_metrics_http(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
		request_line = await reader.readline()
		path = "/"
		if request_line:
			decoded = request_line.decode("utf-8", errors="replace").strip()
			parts = decoded.split()
			if len(parts) >= 2:
				path = parts[1]

		while True:
			line = await reader.readline()
			if not line or line in {b"\r\n", b"\n"}:
				break

		response = self._metrics_endpoint.handle_request(path)
		payload = response.body.encode("utf-8")
		headers = [
			f"HTTP/1.1 {response.status_code} {_reason_phrase(response.status_code)}",
			f"Content-Type: {response.content_type}",
			f"Content-Length: {len(payload)}",
			"Connection: close",
			"",
			"",
		]
		writer.write("\r\n".join(headers).encode("utf-8") + payload)
		await writer.drain()
		writer.close()
		await writer.wait_closed()

	async def _process_command_bytes(self, raw: bytes, *, connection_id: str, request_id: str) -> CommandResponse:
		decoded = raw.decode("utf-8", errors="replace")
		try:
			request = parse_command(decoded, request_id=request_id, client_id=connection_id)
		except LiteStoreError as exc:
			return _error_response(exc.code, exc.message, request_id=request_id)

		started_at = perf_counter()
		response = await self._dispatch_request(request)
		duration = perf_counter() - started_at
		self._metrics.observe_command(request, duration)
		return response

	async def _dispatch_request(self, request: CommandRequest) -> CommandResponse:
		route = self._router.route_request(request)
		worker = self._workers[route.worker_id]
		response = await worker.execute_async(request)

		if _is_persisted_write(request, response):
			try:
				self._persistence.append_request(request)
			except OSError as exc:
				return _error_response(ErrorCode.PERSISTENCE_ERROR, f"Persistence append failed: {exc}", request.request_id)
			await self._refresh_metrics_snapshot()
		elif request.command in {CommandName.GET, CommandName.TTL}:
			await self._refresh_metrics_snapshot()

		return response

	def _replay_persistence(self) -> None:
		for record in self._persistence.replay():
			route = self._router.route_request(record.request)
			worker = self._workers[route.worker_id]
			worker.execute(record.request)

	async def _refresh_metrics_snapshot(self) -> None:
		aggregated: dict[str, str] = {}
		for worker in self._workers.values():
			aggregated.update(await worker.snapshot_async())
		self._metrics.observe_store_snapshot(aggregated)

	def _next_connection_id(self, writer: asyncio.StreamWriter) -> str:
		self._connection_sequence += 1
		peer = writer.get_extra_info("peername")
		if isinstance(peer, tuple) and len(peer) >= 2:
			return f"{peer[0]}:{peer[1]}:{self._connection_sequence}"
		return f"connection:{self._connection_sequence}"


def _is_persisted_write(request: CommandRequest, response: CommandResponse) -> bool:
	if response.kind == ResponseKind.ERROR:
		return False
	if request.command == CommandName.SET:
		return True
	if request.command == CommandName.DEL:
		return True
	if request.command == CommandName.EXPIRE and response.integer == 1:
		return True
	return False


def _error_response(code: ErrorCode, message: str, request_id: str | None) -> CommandResponse:
	return CommandResponse(
		kind=ResponseKind.ERROR,
		error_code=code,
		message=message,
		request_id=request_id,
	)


def _bound_port(server: asyncio.AbstractServer | None) -> int:
	if server is None or server.sockets is None or not server.sockets:
		return 0
	return int(server.sockets[0].getsockname()[1])


def _reason_phrase(status_code: int) -> str:
	if status_code == 200:
		return "OK"
	if status_code == 404:
		return "Not Found"
	return "Error"
