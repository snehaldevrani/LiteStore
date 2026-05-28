"""Smoke tests for throughput comparison benchmark script."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_benchmark_compare_includes_threaded_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "benchmark_compare.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--keys",
            "50",
            "--workers",
            "2",
            "--concurrency",
            "20",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output = result.stdout
    assert "threaded-sharded-2-workers" in output
    assert "single-store" in output
