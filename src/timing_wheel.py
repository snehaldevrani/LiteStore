"""Deterministic timing wheel for LiteStore key expiration."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class _ScheduledEntry:
	key: str
	expires_at: float
	scheduled_tick: int


@dataclass(frozen=True, slots=True)
class TimerEntry:
	"""A scheduled key expiration slot entry."""

	key: str
	expires_at: float


class TimingWheel:
	"""Deterministic expiration scheduler using stable time buckets.

	Entries are scheduled into buckets keyed by logical ticks. `pop_due()` drains all
	expirations up to the provided timestamp, ensuring there are no stale keys once a
	worker/store expiration cycle has run for that time horizon.
	"""

	def __init__(self, tick_seconds: float = 0.1, bucket_count: int = 512) -> None:
		if tick_seconds <= 0:
			raise ValueError("tick_seconds must be positive")
		if bucket_count <= 0:
			raise ValueError("bucket_count must be positive")

		self._tick_seconds = tick_seconds
		self._bucket_count = bucket_count
		self._buckets: list[set[str]] = [set() for _ in range(bucket_count)]
		self._entries_by_key: dict[str, _ScheduledEntry] = {}
		self._last_processed_tick = -1
		self._origin_timestamp: float | None = None

	def schedule(self, key: str, expires_at: float) -> None:
		"""Schedule key expiry in the wheel."""
		if self._origin_timestamp is not None and expires_at < self._origin_timestamp:
			self._rebase_origin(expires_at)
		scheduled_tick = self._tick_for_timestamp(expires_at)
		self.cancel(key)
		entry = _ScheduledEntry(key=key, expires_at=expires_at, scheduled_tick=scheduled_tick)
		self._entries_by_key[key] = entry
		self._bucket_for_tick(scheduled_tick).add(key)

	def cancel(self, key: str) -> None:
		"""Cancel key expiry if currently scheduled."""
		entry = self._entries_by_key.pop(key, None)
		if entry is None:
			return
		self._bucket_for_tick(entry.scheduled_tick).discard(key)

	def pop_due(self, now: float) -> list[TimerEntry]:
		"""Return and unschedule entries due at or before `now`."""
		current_tick = self._tick_for_timestamp(now)
		if current_tick <= self._last_processed_tick:
			return []

		due_entries: list[TimerEntry] = []
		for tick in range(self._last_processed_tick + 1, current_tick + 1):
			bucket = self._bucket_for_tick(tick)
			keys = tuple(bucket)
			for key in keys:
				entry = self._entries_by_key.get(key)
				if entry is None:
					bucket.discard(key)
					continue
				if entry.scheduled_tick > tick:
					continue
				bucket.discard(key)
				if entry.expires_at <= now:
					self._entries_by_key.pop(key, None)
					due_entries.append(TimerEntry(key=entry.key, expires_at=entry.expires_at))
				else:
					# Re-queue when the bucket wraps before the absolute expiry tick.
					self._bucket_for_tick(entry.scheduled_tick).add(key)

		self._last_processed_tick = current_tick
		due_entries.sort(key=lambda entry: entry.expires_at)
		return due_entries

	def _tick_for_timestamp(self, timestamp: float) -> int:
		if self._origin_timestamp is None:
			self._origin_timestamp = timestamp
		return math.floor((timestamp - self._origin_timestamp) / self._tick_seconds)

	def _bucket_for_tick(self, tick: int) -> set[str]:
		return self._buckets[tick % self._bucket_count]

	def _rebase_origin(self, new_origin_timestamp: float) -> None:
		old_entries = list(self._entries_by_key.values())
		old_last_processed_tick = self._last_processed_tick
		self._origin_timestamp = new_origin_timestamp
		self._buckets = [set() for _ in range(self._bucket_count)]
		self._entries_by_key = {}
		self._last_processed_tick = -1 if old_last_processed_tick < 0 else self._tick_for_timestamp(
			new_origin_timestamp + (old_last_processed_tick * self._tick_seconds)
		)
		for entry in old_entries:
			scheduled_tick = self._tick_for_timestamp(entry.expires_at)
			updated_entry = _ScheduledEntry(
				key=entry.key,
				expires_at=entry.expires_at,
				scheduled_tick=scheduled_tick,
			)
			self._entries_by_key[entry.key] = updated_entry
			self._bucket_for_tick(scheduled_tick).add(entry.key)
