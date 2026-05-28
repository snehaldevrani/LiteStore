"""Deterministic key-space routing for LiteStore workers."""

from __future__ import annotations

import hashlib

from .types import CommandName, CommandRequest, KeyRoute


class DeterministicHashRouter:
	"""Routes keys to worker partitions using stable hash partitioning."""

	def __init__(self, worker_ids: list[str]) -> None:
		if not worker_ids:
			raise ValueError("At least one worker is required")

		self._worker_ids = tuple(worker_ids)
		self._partition_count = len(self._worker_ids)
		self._default_worker = self._worker_ids[0]

	def route_key(self, key: str) -> KeyRoute:
		"""Resolve key ownership using deterministic hashing."""
		partition_id = _stable_partition_for_key(key, self._partition_count)
		worker_id = self._worker_ids[partition_id]
		return KeyRoute(partition_id=partition_id, worker_id=worker_id)

	def route_request(self, request: CommandRequest) -> KeyRoute:
		"""Resolve ownership from command semantics and key presence."""
		key = _extract_key_from_request(request)
		if key is None:
			return KeyRoute(partition_id=0, worker_id=self._default_worker)
		return self.route_key(key)


def _stable_partition_for_key(key: str, partition_count: int) -> int:
	digest = hashlib.sha256(key.encode("utf-8")).digest()
	hash_value = int.from_bytes(digest[:8], byteorder="big", signed=False)
	return hash_value % partition_count


def _extract_key_from_request(request: CommandRequest) -> str | None:
	command = request.command
	if command in {
		CommandName.SET,
		CommandName.GET,
		CommandName.DEL,
		CommandName.EXPIRE,
		CommandName.TTL,
	} and request.args:
		return request.args[0]

	return None
