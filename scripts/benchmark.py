"""In-process benchmark for LiteStore command execution."""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.commands import execute_command
from src.store import MemoryStore
from src.types import CommandName, CommandRequest


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
	name: str
	operations: int
	elapsed_seconds: float
	throughput_ops_per_second: float
	average_latency_ms: float
	p50_latency_ms: float
	p95_latency_ms: float


def build_workload(key_count: int) -> list[CommandRequest]:
	requests: list[CommandRequest] = []
	for index in range(key_count):
		key = f"bench:{index}"
		value = f"value-{index}"
		requests.append(CommandRequest(command=CommandName.SET, args=(key, value)))
		requests.append(CommandRequest(command=CommandName.GET, args=(key,)))
		requests.append(CommandRequest(command=CommandName.DEL, args=(key,)))
	return requests


def run_benchmark(key_count: int) -> BenchmarkResult:
	store = MemoryStore()
	workload = build_workload(key_count)
	latencies_ms: list[float] = []

	start = time.perf_counter()
	for request in workload:
		op_start = time.perf_counter()
		execute_command(request, store)
		latencies_ms.append((time.perf_counter() - op_start) * 1000.0)
	elapsed = time.perf_counter() - start

	return BenchmarkResult(
		name="single-store-command-layer",
		operations=len(workload),
		elapsed_seconds=elapsed,
		throughput_ops_per_second=len(workload) / elapsed if elapsed > 0 else 0.0,
		average_latency_ms=statistics.fmean(latencies_ms),
		p50_latency_ms=_percentile(latencies_ms, 50),
		p95_latency_ms=_percentile(latencies_ms, 95),
	)


def render_table(result: BenchmarkResult) -> str:
	return "\n".join(
		[
			"| workload | operations | elapsed_s | throughput_ops_s | avg_ms | p50_ms | p95_ms |",
			"| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
			(
				f"| {result.name} | {result.operations} | {result.elapsed_seconds:.4f} | "
				f"{result.throughput_ops_per_second:.2f} | {result.average_latency_ms:.4f} | "
				f"{result.p50_latency_ms:.4f} | {result.p95_latency_ms:.4f} |"
			),
		]
	)


def _percentile(values: list[float], percentile: int) -> float:
	ordered = sorted(values)
	if not ordered:
		return 0.0
	rank = (len(ordered) - 1) * (percentile / 100)
	lower = int(rank)
	upper = min(lower + 1, len(ordered) - 1)
	weight = rank - lower
	return ordered[lower] * (1 - weight) + ordered[upper] * weight


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="Run the LiteStore in-process benchmark.")
	parser.add_argument("--keys", type=int, default=5000, help="Number of keys to exercise in the workload.")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	result = run_benchmark(args.keys)
	print(render_table(result))


if __name__ == "__main__":
	main()
