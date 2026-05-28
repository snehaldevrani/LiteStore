"""Deterministic TTL and timing-wheel behavior tests for LiteStore."""

from src.store import MemoryStore
from src.timing_wheel import TimingWheel
from src.types import CommandName, CommandRequest
from src.worker import StoreWorker


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_timing_wheel_returns_due_entries_in_deadline_order() -> None:
    wheel = TimingWheel(tick_seconds=0.1, bucket_count=32)
    wheel.schedule("k2", 1.2)
    wheel.schedule("k1", 1.1)

    due = wheel.pop_due(1.2)

    assert [entry.key for entry in due] == ["k1", "k2"]


def test_store_process_expirations_removes_keys_without_read_access() -> None:
    clock = FakeClock()
    store = MemoryStore(time_source=clock.now, timing_wheel=TimingWheel(tick_seconds=0.1, bucket_count=32))
    store.set("session:1", "token")
    store.expire("session:1", 5)

    clock.advance(5.0)
    expired_count = store.process_expirations()

    assert expired_count == 1
    assert store.get("session:1") is None
    assert "session:1" not in store.expires_at


def test_worker_cycle_prevents_lingering_stale_keys_beyond_deadline() -> None:
    clock = FakeClock()
    store = MemoryStore(time_source=clock.now, timing_wheel=TimingWheel(tick_seconds=0.1, bucket_count=32))
    worker = StoreWorker("w0", 0, store=store)

    worker.execute(CommandRequest(command=CommandName.SET, args=("job:1", "queued")))
    worker.execute(CommandRequest(command=CommandName.EXPIRE, args=("job:1", "3")))

    clock.advance(3.0)
    expired_count = worker.run_expiration_cycle()

    assert expired_count == 1
    assert store.get("job:1") is None


def test_rescheduling_key_keeps_only_latest_deadline() -> None:
    clock = FakeClock()
    store = MemoryStore(time_source=clock.now, timing_wheel=TimingWheel(tick_seconds=0.1, bucket_count=32))
    store.set("k1", "v1")
    store.expire("k1", 10)
    store.expire("k1", 20)

    clock.advance(10.0)
    store.process_expirations()
    assert store.get("k1") == "v1"

    clock.advance(10.0)
    store.process_expirations()
    assert store.get("k1") is None


def test_deterministic_expiration_differs_from_earlier_lazy_behavior() -> None:
    clock = FakeClock()
    store = MemoryStore(time_source=clock.now, timing_wheel=TimingWheel(tick_seconds=0.1, bucket_count=32))
    store.set("k1", "v1")
    store.expire("k1", 4)

    clock.advance(4.0)

    # Earlier lazy TTL removed the key only when GET/TTL/DEL touched it.
    # The new behavior removes it proactively once the expiration cycle runs.
    assert store.process_expirations() == 1
    assert store.get("k1") is None
