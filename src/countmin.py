"""Count-Min Sketch and Top-K tracker for bounded hot-key detection."""

from __future__ import annotations

import hashlib
import heapq


class CountMinSketch:
    """Fixed-memory approximate frequency counter using multiple hash functions."""

    def __init__(self, width: int = 2048, depth: int = 4) -> None:
        self._width = width
        self._depth = depth
        self._table: list[list[int]] = [[0] * width for _ in range(depth)]

    def increment(self, key: str) -> None:
        """Increment estimated count for key across all hash rows."""
        key_bytes = key.encode("utf-8")
        for row in range(self._depth):
            col = self._hash(key_bytes, row)
            self._table[row][col] += 1

    def estimate(self, key: str) -> int:
        """Return minimum count across all hash rows (conservative estimate)."""
        key_bytes = key.encode("utf-8")
        return min(
            self._table[row][self._hash(key_bytes, row)]
            for row in range(self._depth)
        )

    def _hash(self, key_bytes: bytes, seed: int) -> int:
        digest = hashlib.sha256(bytes([seed]) + key_bytes).digest()
        value = int.from_bytes(digest[:4], byteorder="big", signed=False)
        return value % self._width


class TopKTracker:
    """Track top-K frequent keys using Count-Min Sketch + min-heap."""

    def __init__(self, k: int = 100, sketch_width: int = 2048, sketch_depth: int = 4) -> None:
        self._k = k
        self._sketch = CountMinSketch(width=sketch_width, depth=sketch_depth)
        self._heap: list[tuple[int, str]] = []
        self._tracked: dict[str, int] = {}

    def record(self, key: str) -> None:
        """Record an access to key and update top-K if necessary."""
        self._sketch.increment(key)
        estimated = self._sketch.estimate(key)

        if key in self._tracked:
            self._tracked[key] = estimated
            self._rebuild_heap()
        elif len(self._heap) < self._k:
            self._tracked[key] = estimated
            heapq.heappush(self._heap, (estimated, key))
        else:
            min_count, min_key = self._heap[0]
            if estimated > min_count:
                heapq.heapreplace(self._heap, (estimated, key))
                del self._tracked[min_key]
                self._tracked[key] = estimated

    def top_k(self) -> list[tuple[str, int]]:
        """Return top K keys with approximate counts, descending by count."""
        return sorted(
            ((key, count) for key, count in self._tracked.items()),
            key=lambda item: item[1],
            reverse=True,
        )

    def _rebuild_heap(self) -> None:
        self._heap = [(count, key) for key, count in self._tracked.items()]
        heapq.heapify(self._heap)
