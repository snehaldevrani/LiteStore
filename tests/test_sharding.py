"""Tests for key-space sharding and worker ownership boundaries."""

from src.router import DeterministicHashRouter
from src.types import CommandName, CommandRequest, ResponseKind
from src.worker import StoreWorker


def test_routing_is_deterministic_for_same_key() -> None:
    router = DeterministicHashRouter(["w0", "w1", "w2"])

    route_a = router.route_key("user:42")
    route_b = router.route_key("user:42")

    assert route_a.worker_id == route_b.worker_id
    assert route_a.partition_id == route_b.partition_id


def test_worker_ownership_isolated_between_partitions() -> None:
    router = DeterministicHashRouter(["w0", "w1", "w2"])
    workers = {
        "w0": StoreWorker("w0", 0),
        "w1": StoreWorker("w1", 1),
        "w2": StoreWorker("w2", 2),
    }

    key_a = _find_key_for_worker(router, "w0")
    key_b = _find_key_for_worker(router, "w1")

    workers["w0"].execute(CommandRequest(command=CommandName.SET, args=(key_a, "value-a")))
    workers["w1"].execute(CommandRequest(command=CommandName.SET, args=(key_b, "value-b")))

    assert workers["w0"].store.get(key_a) == "value-a"
    assert workers["w1"].store.get(key_b) == "value-b"
    assert workers["w0"].store.get(key_b) is None
    assert workers["w1"].store.get(key_a) is None


def test_sharded_dispatch_preserves_command_behavior() -> None:
    router = DeterministicHashRouter(["w0", "w1", "w2"])
    workers = {
        "w0": StoreWorker("w0", 0),
        "w1": StoreWorker("w1", 1),
        "w2": StoreWorker("w2", 2),
    }

    set_request = CommandRequest(command=CommandName.SET, args=("order:1", "created"))
    set_response = _dispatch(router, workers, set_request)
    assert set_response.kind == ResponseKind.SIMPLE_STRING
    assert set_response.message == "OK"

    get_response = _dispatch(
        router,
        workers,
        CommandRequest(command=CommandName.GET, args=("order:1",)),
    )
    assert get_response.kind == ResponseKind.BULK_STRING
    assert get_response.value == "created"

    del_response = _dispatch(
        router,
        workers,
        CommandRequest(command=CommandName.DEL, args=("order:1",)),
    )
    assert del_response.kind == ResponseKind.INTEGER
    assert del_response.integer == 1

    get_after_delete = _dispatch(
        router,
        workers,
        CommandRequest(command=CommandName.GET, args=("order:1",)),
    )
    assert get_after_delete.kind == ResponseKind.NULL


def test_non_key_command_routes_to_default_worker() -> None:
    router = DeterministicHashRouter(["w0", "w1", "w2"])

    route = router.route_request(CommandRequest(command=CommandName.PING, args=()))

    assert route.worker_id == "w0"
    assert route.partition_id == 0


def _dispatch(
    router: DeterministicHashRouter,
    workers: dict[str, StoreWorker],
    request: CommandRequest,
):
    route = router.route_request(request)
    worker = workers[route.worker_id]
    return worker.execute(request)


def _find_key_for_worker(router: DeterministicHashRouter, worker_id: str) -> str:
    for index in range(5000):
        candidate = f"key:{index}"
        if router.route_key(candidate).worker_id == worker_id:
            return candidate
    raise AssertionError(f"No key found for worker {worker_id}")
