"""In-memory key-value store implementation for LiteStore."""

from __future__ import annotations

import fnmatch
import time
from typing import Callable, Dict

from .timing_wheel import TimingWheel
from .types import CommandName, CommandRequest


class MemoryStore:
	"""Isolated in-memory key-value store.

	This store intentionally contains no networking, persistence, or sharding logic.
	"""

	def __init__(
		self,
		*,
		time_source: Callable[[], float] | None = None,
		timing_wheel: TimingWheel | None = None,
	) -> None:
		self._time_source = time_source if time_source is not None else time.time
		self._data: Dict[str, str] = {}
		self._expires_at: Dict[str, float] = {}
		self._timing_wheel = timing_wheel if timing_wheel is not None else TimingWheel()

	def set(self, key: str, value: str) -> None:
		"""Create or overwrite a key with a value."""
		self.process_expirations()
		self._data[key] = value
		self._clear_expiry(key)

	def get(self, key: str) -> str | None:
		"""Return key value when present, otherwise None."""
		self.process_expirations()
		return self._data.get(key)

	def delete(self, key: str) -> bool:
		"""Delete key and return whether deletion occurred."""
		self.process_expirations()
		if key not in self._data:
			return False

		del self._data[key]
		self._clear_expiry(key)
		return True

	def expire(self, key: str, ttl_seconds: int) -> bool:
		"""Set expiry in seconds for an existing key."""
		self.process_expirations()
		if key not in self._data:
			return False

		if ttl_seconds <= 0:
			self.delete(key)
			return True

		expires_at = self._time_source() + ttl_seconds
		self._expires_at[key] = expires_at
		self._timing_wheel.schedule(key, expires_at)
		return True

	def ttl(self, key: str) -> int:
		"""Return TTL contract value (seconds, -1, -2)."""
		self.process_expirations()
		if key not in self._data:
			return -2

		expires_at = self._expires_at.get(key)
		if expires_at is None:
			return -1

		remaining = int(expires_at - self._time_source())
		if remaining < 0:
			self.delete(key)
			return -2
		return remaining

	@property
	def expires_at(self) -> Dict[str, float]:
		"""Expose TTL metadata mapping for upcoming expiration logic integration."""
		return self._expires_at

	def snapshot(self) -> dict[str, str]:
		"""Return a shallow copy of current store state."""
		self.process_expirations()
		return dict(self._data)

	def apply_replay_request(self, request: CommandRequest) -> None:
		"""Apply a persisted write command during startup recovery."""
		self.process_expirations()
		if request.command == CommandName.SET and len(request.args) == 2:
			key, value = request.args
			self.set(key, value)
			return

		if request.command == CommandName.DEL and len(request.args) == 1:
			(key,) = request.args
			self.delete(key)
			return

		if request.command == CommandName.EXPIRE and len(request.args) == 2:
			key, seconds_raw = request.args
			try:
				seconds = int(seconds_raw)
			except ValueError:
				return
			self.expire(key, seconds)

		if request.command == CommandName.FLUSHALL and len(request.args) == 0:
			self.flush()

	def process_expirations(self, now: float | None = None) -> int:
		"""Drain due expirations from the timing wheel and remove expired keys."""
		current_time = self._time_source() if now is None else now
		expired_count = 0
		for entry in self._timing_wheel.pop_due(current_time):
			expires_at = self._expires_at.get(entry.key)
			if expires_at is None:
				continue
			if expires_at > current_time:
				continue
			if entry.key in self._data:
				del self._data[entry.key]
				expired_count += 1
			self._expires_at.pop(entry.key, None)
		return expired_count

	def _clear_expiry(self, key: str) -> None:
		self._expires_at.pop(key, None)
		self._timing_wheel.cancel(key)

	def keys(self, pattern: str) -> list[str]:
		"""Return all live key names matching a glob pattern ('*' matches all)."""
		self.process_expirations()
		return [k for k in self._data if fnmatch.fnmatch(k, pattern)]

	def flush(self) -> int:
		"""Delete all keys and return the count removed."""
		self.process_expirations()
		count = len(self._data)
		self._data.clear()
		self._expires_at.clear()
		self._timing_wheel = TimingWheel()
		return count
