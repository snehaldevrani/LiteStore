"""TTL behavior tests for LiteStore."""

import time

from src.commands import execute_command
from src.store import MemoryStore
from src.types import CommandName, CommandRequest, ErrorCode, ResponseKind


def test_expired_keys_are_not_returned_by_get() -> None:
    store = MemoryStore()
    store.set("k1", "v1")
    store.expire("k1", 1)

    time.sleep(1.1)

    response = execute_command(CommandRequest(command=CommandName.GET, args=("k1",)), store)

    assert response.kind == ResponseKind.NULL


def test_ttl_reports_minus_one_for_key_without_expiry() -> None:
    store = MemoryStore()
    store.set("k1", "v1")

    response = execute_command(CommandRequest(command=CommandName.TTL, args=("k1",)), store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == -1


def test_ttl_reports_minus_two_for_missing_key() -> None:
    store = MemoryStore()

    response = execute_command(CommandRequest(command=CommandName.TTL, args=("missing",)), store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == -2


def test_expire_missing_key_returns_zero() -> None:
    store = MemoryStore()

    response = execute_command(CommandRequest(command=CommandName.EXPIRE, args=("missing", "10")), store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == 0


def test_expire_non_integer_seconds_returns_error() -> None:
    store = MemoryStore()
    store.set("k1", "v1")

    response = execute_command(CommandRequest(command=CommandName.EXPIRE, args=("k1", "1.5")), store)

    assert response.kind == ResponseKind.ERROR
    assert response.error_code == ErrorCode.INVALID_REQUEST


def test_expire_zero_or_negative_deletes_key() -> None:
    store = MemoryStore()
    store.set("k1", "v1")

    response = execute_command(CommandRequest(command=CommandName.EXPIRE, args=("k1", "0")), store)

    assert response.kind == ResponseKind.INTEGER
    assert response.integer == 1

    get_response = execute_command(CommandRequest(command=CommandName.GET, args=("k1",)), store)
    assert get_response.kind == ResponseKind.NULL
