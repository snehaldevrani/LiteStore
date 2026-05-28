"""Unit tests for LiteStore command execution layer."""

from dataclasses import replace

from src.commands import execute_command
from src.store import MemoryStore
from src.types import CommandName, CommandRequest, ErrorCode, ResponseKind


def test_ping_returns_pong() -> None:
    store = MemoryStore()
    request = CommandRequest(command=CommandName.PING)

    response = execute_command(request, store)

    assert response.kind == ResponseKind.SIMPLE_STRING
    assert response.message == "PONG"


def test_set_returns_ok_and_persists_value() -> None:
    store = MemoryStore()
    request = CommandRequest(command=CommandName.SET, args=("user:1", "Alice"))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.SIMPLE_STRING
    assert response.message == "OK"
    assert store.get("user:1") == "Alice"


def test_get_returns_bulk_string_for_existing_key() -> None:
    store = MemoryStore()
    store.set("user:1", "Alice")
    request = CommandRequest(command=CommandName.GET, args=("user:1",))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.BULK_STRING
    assert response.value == "Alice"


def test_get_returns_null_for_missing_key() -> None:
    store = MemoryStore()
    request = CommandRequest(command=CommandName.GET, args=("missing",))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.NULL


def test_del_returns_one_for_existing_key() -> None:
    store = MemoryStore()
    store.set("session:1", "token")
    request = CommandRequest(command=CommandName.DEL, args=("session:1",))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == 1
    assert store.get("session:1") is None


def test_del_returns_zero_for_missing_key() -> None:
    store = MemoryStore()
    request = CommandRequest(command=CommandName.DEL, args=("missing",))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == 0


def test_wrong_arity_returns_error_response() -> None:
    store = MemoryStore()
    request = CommandRequest(command=CommandName.SET, args=("only-key",))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.ERROR
    assert response.error_code == ErrorCode.WRONG_ARITY


def test_expire_returns_integer_flag() -> None:
    store = MemoryStore()
    store.set("k1", "v1")
    request = CommandRequest(command=CommandName.EXPIRE, args=("k1", "10"))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == 1


def test_ttl_returns_integer_remaining() -> None:
    store = MemoryStore()
    store.set("k1", "v1")
    execute_command(CommandRequest(command=CommandName.EXPIRE, args=("k1", "10")), store)

    response = execute_command(CommandRequest(command=CommandName.TTL, args=("k1",)), store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer is not None
    assert response.integer >= 0


def test_expire_with_non_integer_seconds_returns_error() -> None:
    store = MemoryStore()
    store.set("k1", "v1")
    request = CommandRequest(command=CommandName.EXPIRE, args=("k1", "abc"))

    response = execute_command(request, store)

    assert response.kind == ResponseKind.ERROR
    assert response.error_code == ErrorCode.INVALID_REQUEST


def test_unknown_command_returns_error_response() -> None:
    store = MemoryStore()
    request = replace(CommandRequest(command=CommandName.PING), command="MGET")

    response = execute_command(request, store)

    assert response.kind == ResponseKind.ERROR
    assert response.error_code == ErrorCode.UNKNOWN_COMMAND


def test_request_id_is_propagated_to_response() -> None:
    store = MemoryStore()
    request = CommandRequest(command=CommandName.PING, request_id="req-1")

    response = execute_command(request, store)

    assert response.request_id == "req-1"
