"""Tests for persistence fsync policy behavior."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from src.persistence import AofPersistence
from src.types import CommandName, CommandRequest, FsyncPolicy, PersistRecord


def _make_record(seq: int) -> PersistRecord:
    return PersistRecord(
        sequence=seq,
        request=CommandRequest(command=CommandName.SET, args=("key", "val")),
    )


def test_fsync_never_does_not_call_fsync(tmp_path: Path) -> None:
    aof = AofPersistence(tmp_path / "test.aof", fsync_policy=FsyncPolicy.NEVER)
    with patch("os.fsync") as mock_fsync:
        for i in range(200):
            aof.append(_make_record(i))
        mock_fsync.assert_not_called()
    aof.close()


def test_fsync_always_calls_fsync_every_write(tmp_path: Path) -> None:
    aof = AofPersistence(tmp_path / "test.aof", fsync_policy=FsyncPolicy.ALWAYS)
    with patch("os.fsync") as mock_fsync:
        for i in range(5):
            aof.append(_make_record(i))
        assert mock_fsync.call_count == 5
    aof.close()


def test_fsync_every_n_calls_fsync_at_threshold(tmp_path: Path) -> None:
    aof = AofPersistence(tmp_path / "test.aof", fsync_policy=FsyncPolicy.EVERY_N, fsync_every_n=10)
    with patch("os.fsync") as mock_fsync:
        for i in range(25):
            aof.append(_make_record(i))
        assert mock_fsync.call_count == 2
    aof.close()


def test_close_fsyncs_remaining_writes(tmp_path: Path) -> None:
    aof = AofPersistence(tmp_path / "test.aof", fsync_policy=FsyncPolicy.EVERY_N, fsync_every_n=100)
    with patch("os.fsync") as mock_fsync:
        for i in range(5):
            aof.append(_make_record(i))
        assert mock_fsync.call_count == 0
        aof.close()
        assert mock_fsync.call_count == 1


def test_force_fsync_immediately_syncs(tmp_path: Path) -> None:
    aof = AofPersistence(tmp_path / "test.aof", fsync_policy=FsyncPolicy.NEVER)
    with patch("os.fsync") as mock_fsync:
        aof.append(_make_record(0))
        mock_fsync.assert_not_called()
        aof.force_fsync()
        assert mock_fsync.call_count == 1
    aof.close()
