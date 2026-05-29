"""LiteStore runtime entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import multiprocessing
from pathlib import Path

try:
    from src.config import LiteStoreConfig
    from src.server import LiteStoreRuntime
except ImportError:  # pragma: no cover - fallback for module execution contexts
    from .config import LiteStoreConfig
    from .server import LiteStoreRuntime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the LiteStore server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6379)
    parser.add_argument("--metrics-host", default="127.0.0.1")
    parser.add_argument("--metrics-port", type=int, default=9100)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--aof-path", default="data/litestore.aof")
    parser.add_argument("--no-multiprocessing", action="store_true", help="Run in single-process mode")
    return parser.parse_args()


async def run_runtime(config: LiteStoreConfig) -> None:
    runtime = LiteStoreRuntime(config)
    await runtime.start()
    try:
        await asyncio.Event().wait()
    finally:
        await runtime.close()


def main() -> None:
    multiprocessing.set_start_method("spawn", force=True)
    args = parse_args()
    config = LiteStoreConfig(
        host=args.host,
        port=args.port,
        metrics_host=args.metrics_host,
        metrics_port=args.metrics_port,
        worker_count=args.workers,
        aof_path=Path(args.aof_path),
        use_multiprocessing=not args.no_multiprocessing,
    )
    try:
        asyncio.run(run_runtime(config))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
