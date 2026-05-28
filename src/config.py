"""Runtime configuration for LiteStore."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LiteStoreConfig:
	"""Configuration for the LiteStore runtime."""

	host: str = "127.0.0.1"
	port: int = 6379
	metrics_host: str = "127.0.0.1"
	metrics_port: int = 9100
	worker_count: int = 4
	aof_path: Path = Path("data/litestore.aof")
