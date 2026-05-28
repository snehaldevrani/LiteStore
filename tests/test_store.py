"""Unit tests for the isolated in-memory LiteStore store."""

import time

from src.store import MemoryStore


def test_set_and_get_value() -> None:
    store = MemoryStore()

    store.set("user:1", "Alice")

    assert store.get("user:1") == "Alice"


def test_set_overwrites_existing_value() -> None:
    store = MemoryStore()

    store.set("user:1", "Alice")
    store.set("user:1", "Bob")

    assert store.get("user:1") == "Bob"


def test_get_missing_key_returns_none() -> None:
    store = MemoryStore()

    assert store.get("missing") is None


def test_delete_existing_key_returns_true() -> None:
    store = MemoryStore()
    store.set("session:1", "token")

    deleted = store.delete("session:1")

    assert deleted is True
    assert store.get("session:1") is None


def test_delete_missing_key_returns_false() -> None:
    store = MemoryStore()

    deleted = store.delete("missing")

    assert deleted is False


def test_delete_cleans_ttl_metadata_for_key() -> None:
    store = MemoryStore()
    store.set("k1", "v1")
    store.expires_at["k1"] = time.time() + 30

    deleted = store.delete("k1")

    assert deleted is True
    assert "k1" not in store.expires_at


def test_ttl_contract_for_missing_and_present_keys() -> None:
    store = MemoryStore()

    assert store.ttl("missing") == -2
    store.set("k1", "v1")
    assert store.ttl("k1") == -1


def test_expire_placeholder_reports_key_existence() -> None:
    store = MemoryStore()

    assert store.expire("missing", 30) is False

    store.set("k1", "v1")
    assert store.expire("k1", 30) is True
