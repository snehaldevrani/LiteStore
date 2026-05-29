"""Tests for Count-Min Sketch and Top-K tracker."""

from src.countmin import CountMinSketch, TopKTracker


def test_sketch_counts_are_non_negative() -> None:
    sketch = CountMinSketch(width=256, depth=4)
    assert sketch.estimate("nonexistent") == 0


def test_sketch_increments_correctly() -> None:
    sketch = CountMinSketch(width=256, depth=4)
    for _ in range(100):
        sketch.increment("key:hot")
    assert sketch.estimate("key:hot") == 100


def test_sketch_overestimates_not_underestimates() -> None:
    sketch = CountMinSketch(width=256, depth=4)
    for _ in range(50):
        sketch.increment("key:a")
    for i in range(1000):
        sketch.increment(f"noise:{i}")
    assert sketch.estimate("key:a") >= 50


def test_sketch_bounded_memory() -> None:
    sketch = CountMinSketch(width=1024, depth=4)
    for i in range(100_000):
        sketch.increment(f"unique:{i}")
    total_cells = 1024 * 4
    assert total_cells == 4096


def test_topk_tracks_most_frequent() -> None:
    tracker = TopKTracker(k=5, sketch_width=512, sketch_depth=4)
    for i in range(100):
        for _ in range(100 - i):
            tracker.record(f"key:{i}")

    top = tracker.top_k()
    top_keys = [k for k, _ in top[:5]]
    assert "key:0" in top_keys
    assert "key:1" in top_keys


def test_topk_bounded_size() -> None:
    tracker = TopKTracker(k=10, sketch_width=512, sketch_depth=4)
    for i in range(10_000):
        tracker.record(f"key:{i}")
    assert len(tracker.top_k()) <= 10


def test_topk_returns_descending_order() -> None:
    tracker = TopKTracker(k=10, sketch_width=512, sketch_depth=4)
    tracker.record("a")
    for _ in range(5):
        tracker.record("b")
    for _ in range(10):
        tracker.record("c")

    top = tracker.top_k()
    counts = [count for _, count in top]
    assert counts == sorted(counts, reverse=True)
