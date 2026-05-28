"""Compare direct command execution with sharded worker dispatch."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
	sys.path.insert(0, str(ROOT))

from src.commands import execute_command
from src.router import DeterministicHashRouter
from src.store import MemoryStore
from src.types import CommandName, CommandRequest
from src.worker import StoreWorker


@dataclass(frozen=True, slots=True)
class ComparisonResult:
	mode: str
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


def run_single_store(key_count: int) -> ComparisonResult:
	store = MemoryStore()
	workload = build_workload(key_count)
	latencies_ms: list[float] = []

	start = time.perf_counter()
	for request in workload:
		op_start = time.perf_counter()
		execute_command(request, store)
		latencies_ms.append((time.perf_counter() - op_start) * 1000.0)
	elapsed = time.perf_counter() - start
	return _build_result("single-store", workload, latencies_ms, elapsed)


def run_sharded(key_count: int, worker_count: int) -> ComparisonResult:
	workload = build_workload(key_count)
	worker_ids = [f"w{index}" for index in range(worker_count)]
	router = DeterministicHashRouter(worker_ids)
	workers = {
		worker_id: StoreWorker(worker_id=worker_id, partition_id=index)
		for index, worker_id in enumerate(worker_ids)
	}
	latencies_ms: list[float] = []

	start = time.perf_counter()
	for request in workload:
		route = router.route_request(request)
		worker = workers[route.worker_id]
		op_start = time.perf_counter()
		worker.execute(request)
		latencies_ms.append((time.perf_counter() - op_start) * 1000.0)
	elapsed = time.perf_counter() - start
	return _build_result(f"sharded-{worker_count}-workers", workload, latencies_ms, elapsed)


def run_threaded_sharded(key_count: int, worker_count: int, concurrency: int) -> ComparisonResult:
	return asyncio.run(_run_threaded_sharded_async(key_count, worker_count, concurrency))


async def _run_threaded_sharded_async(key_count: int, worker_count: int, concurrency: int) -> ComparisonResult:
	workload = build_workload(key_count)
	worker_ids = [f"w{index}" for index in range(worker_count)]
	router = DeterministicHashRouter(worker_ids)
	workers = {
		worker_id: StoreWorker(worker_id=worker_id, partition_id=index, threaded=True)
		for index, worker_id in enumerate(worker_ids)
	}
	for worker in workers.values():
		worker.start()

	semaphore = asyncio.Semaphore(concurrency)
	latencies_ms: list[float] = []

	async def run_request(request: CommandRequest) -> None:
		route = router.route_request(request)
		worker = workers[route.worker_id]
		async with semaphore:
			op_start = time.perf_counter()
			await worker.execute_async(request)
			latencies_ms.append((time.perf_counter() - op_start) * 1000.0)

	start = time.perf_counter()
	await asyncio.gather(*(run_request(request) for request in workload))
	elapsed = time.perf_counter() - start

	for worker in workers.values():
		worker.stop()

	return _build_result(f"threaded-sharded-{worker_count}-workers", workload, latencies_ms, elapsed)


def render_table(results: list[ComparisonResult]) -> str:
	lines = [
		"| mode | operations | elapsed_s | throughput_ops_s | avg_ms | p50_ms | p95_ms |",
		"| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
	]
	for result in results:
		lines.append(
			f"| {result.mode} | {result.operations} | {result.elapsed_seconds:.4f} | "
			f"{result.throughput_ops_per_second:.2f} | {result.average_latency_ms:.4f} | "
			f"{result.p50_latency_ms:.4f} | {result.p95_latency_ms:.4f} |"
		)
	return "\n".join(lines)


def _build_result(mode: str, workload: list[CommandRequest], latencies_ms: list[float], elapsed: float) -> ComparisonResult:
	return ComparisonResult(
		mode=mode,
		operations=len(workload),
		elapsed_seconds=elapsed,
		throughput_ops_per_second=len(workload) / elapsed if elapsed > 0 else 0.0,
		average_latency_ms=statistics.fmean(latencies_ms),
		p50_latency_ms=_percentile(latencies_ms, 50),
		p95_latency_ms=_percentile(latencies_ms, 95),
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
	parser = argparse.ArgumentParser(description="Compare LiteStore execution modes.")
	parser.add_argument("--keys", type=int, default=5000, help="Number of keys to exercise in the workload.")
	parser.add_argument("--workers", type=int, default=4, help="Worker count for sharded execution.")
	parser.add_argument("--concurrency", type=int, default=100, help="Concurrent requests for threaded mode.")
	return parser.parse_args()


def main() -> None:
	args = parse_args()
	results = [
		run_single_store(args.keys),
		run_sharded(args.keys, args.workers),
		run_threaded_sharded(args.keys, args.workers, args.concurrency),
	]
	print(render_table(results))


if __name__ == "__main__":
	main()
