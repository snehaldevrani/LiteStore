"""Stable interfaces for LiteStore components."""

from __future__ import annotations

from typing import Iterable, Protocol

from .types import CommandRequest, CommandResponse, KeyRoute, PersistRecord, WorkerStats


class StoreInterface(Protocol):
    """Contract for in-memory key-value state operations."""

    def set(self, key: str, value: str) -> None:
        """Create or overwrite a key with a string value."""

    def get(self, key: str) -> str | None:
        """Return key value when present, else None."""

    def delete(self, key: str) -> bool:
        """Delete key if present and return whether deletion occurred."""

    def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL on key and return whether key existed."""

    def ttl(self, key: str) -> int:
        """Return TTL contract value (seconds, -1, or -2)."""

    def process_expirations(self, now: float | None = None) -> int:
        """Remove keys whose TTL deadline has passed and return count removed."""

    def keys(self, pattern: str) -> list[str]:
        """Return all live key names matching a glob pattern ('*' matches all)."""

    def flush(self) -> int:
        """Delete all keys and return the count of keys removed."""

    def snapshot(self) -> dict[str, str]:
        """Return a copy of the current key-value state for aggregation or metrics."""


class PersistenceInterface(Protocol):
    """Contract for append-only persistence and replay."""

    def append(self, record: PersistRecord) -> None:
        """Persist one mutation record in order."""

    def replay(self) -> Iterable[PersistRecord]:
        """Yield persisted mutation records in durable order."""

    def close(self) -> None:
        """Release resources owned by persistence backend."""


class RouterInterface(Protocol):
    """Contract for deterministic request routing to worker ownership."""

    def route_key(self, key: str) -> KeyRoute:
        """Resolve a key to a partition and worker."""

    def route_request(self, request: CommandRequest) -> KeyRoute:
        """Resolve request ownership from command semantics."""


class WorkerInterface(Protocol):
    """Contract for worker lifecycle and command execution."""

    worker_id: str
    partition_id: int

    def start(self) -> None:
        """Start worker processing resources."""

    def stop(self) -> None:
        """Stop worker processing resources."""

    def execute(self, request: CommandRequest) -> CommandResponse:
        """Execute one request against worker-owned state."""

    async def execute_async(self, request: CommandRequest) -> CommandResponse:
        """Async execution hook used by asyncio runtime integration."""

    def run_expiration_cycle(self, now: float | None = None) -> int:
        """Run due expiration processing for this worker partition."""

    async def run_expiration_cycle_async(self, now: float | None = None) -> int:
        """Async variant of expiration cycle processing."""

    def snapshot(self) -> dict[str, str]:
        """Return current partition state snapshot."""

    async def snapshot_async(self) -> dict[str, str]:
        """Async variant of partition snapshot retrieval."""

    def stats(self) -> WorkerStats:
        """Return lightweight worker diagnostics."""
