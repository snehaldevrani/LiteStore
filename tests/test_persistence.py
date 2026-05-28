"""Tests for LiteStore append-only file persistence."""

from pathlib import Path

from src.persistence import AofPersistence
from src.store import MemoryStore
from src.types import CommandName, CommandRequest, PersistRecord


def test_append_writes_readable_json_lines(tmp_path: Path) -> None:
    log_file = tmp_path / "litestore.aof"
    persistence = AofPersistence(log_file)

    record = PersistRecord(
        sequence=0,
        request=CommandRequest(command=CommandName.SET, args=("user:1", "Alice")),
    )
    persistence.append(record)
    persistence.close()

    content = log_file.read_text(encoding="utf-8")
    assert '"sequence": 0' in content
    assert '"command": "SET"' in content
    assert '"args": ["user:1", "Alice"]' in content


def test_replay_preserves_append_order(tmp_path: Path) -> None:
    log_file = tmp_path / "ordered.aof"
    persistence = AofPersistence(log_file)

    persistence.append(PersistRecord(0, CommandRequest(command=CommandName.SET, args=("k1", "v1"))))
    persistence.append(PersistRecord(1, CommandRequest(command=CommandName.SET, args=("k1", "v2"))))
    persistence.append(PersistRecord(2, CommandRequest(command=CommandName.DEL, args=("k1",))))
    persistence.close()

    replay_reader = AofPersistence(log_file)
    replayed = list(replay_reader.replay())
    replay_reader.close()

    assert [item.sequence for item in replayed] == [0, 1, 2]
    assert [item.request.command for item in replayed] == [
        CommandName.SET,
        CommandName.SET,
        CommandName.DEL,
    ]


def test_replay_skips_malformed_lines_safely(tmp_path: Path) -> None:
    log_file = tmp_path / "malformed.aof"
    log_file.write_text(
        "\n".join(
            [
                '{"sequence": 0, "command": "SET", "args": ["k1", "v1"]}',
                "not json at all",
                '{"sequence": "bad", "command": "DEL", "args": ["k1"]}',
                '{"sequence": 1, "command": "DEL", "args": ["k1"]}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    persistence = AofPersistence(log_file)
    replayed = list(persistence.replay())
    persistence.close()

    assert len(replayed) == 2
    assert replayed[0].sequence == 0
    assert replayed[1].sequence == 1


def test_startup_replay_rebuilds_store_state(tmp_path: Path) -> None:
    log_file = tmp_path / "startup.aof"
    writer = AofPersistence(log_file)

    writer.append(PersistRecord(0, CommandRequest(command=CommandName.SET, args=("k1", "v1"))))
    writer.append(PersistRecord(1, CommandRequest(command=CommandName.SET, args=("k1", "v2"))))
    writer.append(PersistRecord(2, CommandRequest(command=CommandName.DEL, args=("k2",))))
    writer.append(PersistRecord(3, CommandRequest(command=CommandName.SET, args=("k3", "v3"))))
    writer.close()

    reader = AofPersistence(log_file)
    recovered_store = MemoryStore()
    for record in reader.replay():
        recovered_store.apply_replay_request(record.request)
    reader.close()

    assert recovered_store.get("k1") == "v2"
    assert recovered_store.get("k2") is None
    assert recovered_store.get("k3") == "v3"


def test_append_request_assigns_monotonic_sequence(tmp_path: Path) -> None:
    log_file = tmp_path / "sequence.aof"
    persistence = AofPersistence(log_file)

    first = persistence.append_request(CommandRequest(command=CommandName.SET, args=("k1", "v1")))
    second = persistence.append_request(CommandRequest(command=CommandName.DEL, args=("k1",)))
    persistence.close()

    assert first.sequence == 0
    assert second.sequence == 1
