"""Built-in observability primitives for LiteStore."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from threading import Lock
from typing import Mapping, Sequence

from .countmin import TopKTracker
from .types import CommandRequest


@dataclass(frozen=True, slots=True)
class HotKeyEntry:
	"""Hot key ranking entry."""

	key: str
	count: int


class MetricsCollector:
	"""Collects Prometheus-friendly LiteStore metrics."""

	_LATENCY_BUCKETS: Sequence[float] = (0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0)

	def __init__(self) -> None:
		self._lock = Lock()
		self._throughput_total = 0
		self._throughput_by_command: Counter[str] = Counter()
		self._latency_sum_by_command: Counter[str] = Counter()
		self._latency_count_by_command: Counter[str] = Counter()
		self._latency_bucket_counts: dict[str, Counter[float]] = {}
		self._hot_key_tracker = TopKTracker(k=100, sketch_width=2048, sketch_depth=4)
		self._memory_by_prefix_bytes: Counter[str] = Counter()

	def observe_command(self, request: CommandRequest, duration_seconds: float) -> None:
		"""Record one executed command for throughput, latency, and hot-key tracking."""
		command_name = request.command.value
		with self._lock:
			self._throughput_total += 1
			self._throughput_by_command[command_name] += 1
			self._latency_sum_by_command[command_name] += duration_seconds
			self._latency_count_by_command[command_name] += 1
			self._observe_latency_bucket(command_name, duration_seconds)

			if request.args:
				key = request.args[0]
				self._hot_key_tracker.record(key)

	def observe_store_snapshot(self, data: Mapping[str, str]) -> None:
		"""Recompute approximate memory usage grouped by key prefix."""
		prefix_totals: Counter[str] = Counter()
		for key, value in data.items():
			prefix = _key_prefix(key)
			prefix_totals[prefix] += len(key.encode("utf-8")) + len(value.encode("utf-8"))

		with self._lock:
			self._memory_by_prefix_bytes = prefix_totals

	def hot_keys(self, limit: int = 10) -> list[HotKeyEntry]:
		"""Return current hot keys in descending access order."""
		with self._lock:
			top = self._hot_key_tracker.top_k()[:limit]
			return [HotKeyEntry(key=key, count=count) for key, count in top]

	def render_prometheus(self) -> str:
		"""Render metrics in Prometheus exposition format."""
		with self._lock:
			lines: list[str] = [
				"# HELP litestore_commands_total Total number of executed commands.",
				"# TYPE litestore_commands_total counter",
				f"litestore_commands_total {self._throughput_total}",
				"# HELP litestore_command_requests_total Total requests by command.",
				"# TYPE litestore_command_requests_total counter",
			]

			for command_name in sorted(self._throughput_by_command):
				count = self._throughput_by_command[command_name]
				lines.append(
					f'litestore_command_requests_total{{command="{command_name}"}} {count}'
				)

			lines.extend(
				[
					"# HELP litestore_command_latency_seconds Command latency by command.",
					"# TYPE litestore_command_latency_seconds histogram",
				]
			)

			for command_name in sorted(self._latency_count_by_command):
				cumulative = 0
				bucket_counts = self._latency_bucket_counts.get(command_name, Counter())
				for bucket in self._LATENCY_BUCKETS:
					cumulative += bucket_counts.get(bucket, 0)
					lines.append(
						"litestore_command_latency_seconds_bucket"
						f'{{command="{command_name}",le="{bucket}"}} {cumulative}'
					)
				total_count = self._latency_count_by_command[command_name]
				lines.append(
					"litestore_command_latency_seconds_bucket"
					f'{{command="{command_name}",le="+Inf"}} {total_count}'
				)
				lines.append(
					f'litestore_command_latency_seconds_count{{command="{command_name}"}} {total_count}'
				)
				lines.append(
					"litestore_command_latency_seconds_sum"
					f'{{command="{command_name}"}} {self._latency_sum_by_command[command_name]}'
				)

			lines.extend(
				[
					"# HELP litestore_hot_key_access_total Access count by key.",
					"# TYPE litestore_hot_key_access_total gauge",
				]
			)
			for key, count in self._hot_key_tracker.top_k():
				lines.append(f'litestore_hot_key_access_total{{key="{_escape_label_value(key)}"}} {count}')

			lines.extend(
				[
					"# HELP litestore_memory_by_prefix_bytes Approximate memory used by key prefix.",
					"# TYPE litestore_memory_by_prefix_bytes gauge",
				]
			)
			for prefix in sorted(self._memory_by_prefix_bytes):
				lines.append(
					"litestore_memory_by_prefix_bytes"
					f'{{prefix="{_escape_label_value(prefix)}"}} {self._memory_by_prefix_bytes[prefix]}'
				)

		return "\n".join(lines) + "\n"

	def _observe_latency_bucket(self, command_name: str, duration_seconds: float) -> None:
		bucket_counts = self._latency_bucket_counts.setdefault(command_name, Counter())
		for bucket in self._LATENCY_BUCKETS:
			if duration_seconds <= bucket:
				bucket_counts[bucket] += 1
				return


def _key_prefix(key: str) -> str:
	prefix, separator, _ = key.partition(":")
	if separator:
		return prefix
	return "default"


def _escape_label_value(value: str) -> str:
	return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
