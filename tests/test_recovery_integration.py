"""Integration tests for restart and persistence recovery."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.config import LiteStoreConfig
from src.server import LiteStoreRuntime


async def _send_tcp_command(host: str, port: int, command: str) -> str:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write((command + "\n").encode("utf-8"))
        await writer.drain()
        response = await reader.readline()
        return response.decode("utf-8")
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_restart_replays_aof_and_restores_state(tmp_path: Path) -> None:
    aof_path = tmp_path / "restart.aof"
    base_config = LiteStoreConfig(
        host="127.0.0.1",
        port=0,
        metrics_host="127.0.0.1",
        metrics_port=0,
        worker_count=2,
        aof_path=aof_path,
        use_multiprocessing=False,
    )

    first = LiteStoreRuntime(base_config)
    await first.start()
    first_port = first.port
    try:
        assert await _send_tcp_command(base_config.host, first_port, "SET account:1 open") == "+OK\r\n"
        assert await _send_tcp_command(base_config.host, first_port, "SET account:2 closed") == "+OK\r\n"
        assert await _send_tcp_command(base_config.host, first_port, "DEL account:2") == ":1\r\n"
    finally:
        await first.close()

    second = LiteStoreRuntime(base_config)
    await second.start()
    second_port = second.port
    try:
        assert await _send_tcp_command(base_config.host, second_port, "GET account:1") == "$open\r\n"
        assert await _send_tcp_command(base_config.host, second_port, "GET account:2") == "$-1\r\n"
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_end_to_end_ttl_flow_over_socket(tmp_path: Path) -> None:
    config = LiteStoreConfig(
        host="127.0.0.1",
        port=0,
        metrics_host="127.0.0.1",
        metrics_port=0,
        worker_count=2,
        aof_path=tmp_path / "ttl_flow.aof",
        use_multiprocessing=False,
    )
    runtime = LiteStoreRuntime(config)
    await runtime.start()

    try:
        assert await _send_tcp_command(config.host, runtime.port, "SET session:1 live") == "+OK\r\n"
        assert await _send_tcp_command(config.host, runtime.port, "EXPIRE session:1 1") == ":1\r\n"
        await asyncio.sleep(1.2)
        assert await _send_tcp_command(config.host, runtime.port, "GET session:1") == "$-1\r\n"
    finally:
        await runtime.close()
