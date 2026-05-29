"""Integration tests for LiteStore runtime networking and command flow."""

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


async def _http_get_metrics(host: str, port: int) -> str:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(b"GET /metrics HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        await writer.drain()
        chunks: list[bytes] = []
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            chunks.append(chunk)
        payload = b"".join(chunks).decode("utf-8")
        return payload
    finally:
        writer.close()
        await writer.wait_closed()


@pytest.mark.asyncio
async def test_tcp_command_flow_and_metrics_endpoint(tmp_path: Path) -> None:
    config = LiteStoreConfig(
        host="127.0.0.1",
        port=0,
        metrics_host="127.0.0.1",
        metrics_port=0,
        worker_count=2,
        aof_path=tmp_path / "runtime.aof",
        use_multiprocessing=False,
    )
    runtime = LiteStoreRuntime(config)
    await runtime.start()

    try:
        assert await _send_tcp_command(config.host, runtime.port, "PING") == "+PONG\r\n"
        assert await _send_tcp_command(config.host, runtime.port, "SET user:1 alice") == "+OK\r\n"
        assert await _send_tcp_command(config.host, runtime.port, "GET user:1") == "$alice\r\n"
        assert await _send_tcp_command(config.host, runtime.port, "DEL user:1") == ":1\r\n"
        assert await _send_tcp_command(config.host, runtime.port, "GET user:1") == "$-1\r\n"

        metrics_payload = await _http_get_metrics(config.metrics_host, runtime.metrics_port)
        assert "HTTP/1.1 200 OK" in metrics_payload
        assert "litestore_commands_total" in metrics_payload
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_invalid_command_returns_protocol_error(tmp_path: Path) -> None:
    config = LiteStoreConfig(
        host="127.0.0.1",
        port=0,
        metrics_host="127.0.0.1",
        metrics_port=0,
        worker_count=2,
        aof_path=tmp_path / "invalid.aof",
        use_multiprocessing=False,
    )
    runtime = LiteStoreRuntime(config)
    await runtime.start()

    try:
        response = await _send_tcp_command(config.host, runtime.port, "MGET key:1")
        assert response.startswith("-ERR UNKNOWN_COMMAND")
    finally:
        await runtime.close()
