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


_HEAP_CLEANUP_RATIO = 3  # compact heap when stale entries exceed k * this factor


class TopKTracker:
    """Track top-K frequent keys using Count-Min Sketch + min-heap.

    Uses lazy deletion to avoid O(k) heap rebuilds on every update to a tracked
    key.  Stale entries (where the stored count no longer matches _tracked) are
    skipped when inspecting the minimum.  A periodic compact is triggered when
    the heap grows beyond k * _HEAP_CLEANUP_RATIO to bound memory overhead.
    """

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
            # Lazy update: push a fresh entry; the old (stale) entry remains in
            # the heap but will be skipped by _peek_min / _compact_heap.
            self._tracked[key] = estimated
            heapq.heappush(self._heap, (estimated, key))
            if len(self._heap) > self._k * _HEAP_CLEANUP_RATIO:
                self._compact_heap()
            return

        if len(self._tracked) < self._k:
            self._tracked[key] = estimated
            heapq.heappush(self._heap, (estimated, key))
            return

        # Heap is at capacity — compare against the current (non-stale) minimum.
        min_entry = self._peek_min()
        if min_entry is not None and estimated > min_entry[0]:
            _, evicted = heapq.heappop(self._heap)  # _peek_min guarantees current
            del self._tracked[evicted]
            self._tracked[key] = estimated
            heapq.heappush(self._heap, (estimated, key))

    def top_k(self) -> list[tuple[str, int]]:
        """Return top K keys with approximate counts, descending by count."""
        return sorted(
            ((key, count) for key, count in self._tracked.items()),
            key=lambda item: item[1],
            reverse=True,
        )

    def _peek_min(self) -> tuple[int, str] | None:
        """Return the current minimum heap entry, discarding stale entries."""
        while self._heap:
            count, key = self._heap[0]
            if self._tracked.get(key) == count:
                return count, key
            heapq.heappop(self._heap)  # stale — discard
        return None

    def _compact_heap(self) -> None:
        """Rebuild heap from _tracked to remove accumulated stale entries."""
        self._heap = [(count, key) for key, count in self._tracked.items()]
        heapq.heapify(self._heap)
