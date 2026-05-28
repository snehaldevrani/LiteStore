"""Tests for LiteStore built-in observability."""

from src.metrics import MetricsCollector
from src.server import MetricsHttpEndpoint
from src.types import CommandName, CommandRequest


def test_metrics_collects_throughput_latency_and_hot_keys() -> None:
    collector = MetricsCollector()

    collector.observe_command(CommandRequest(command=CommandName.GET, args=("user:1",)), 0.003)
    collector.observe_command(CommandRequest(command=CommandName.GET, args=("user:1",)), 0.007)
    collector.observe_command(CommandRequest(command=CommandName.SET, args=("session:1", "abc")), 0.020)

    payload = collector.render_prometheus()

    assert "litestore_commands_total 3" in payload
    assert 'litestore_command_requests_total{command="GET"} 2' in payload
    assert 'litestore_command_requests_total{command="SET"} 1' in payload
    assert 'litestore_command_latency_seconds_count{command="GET"} 2' in payload
    assert 'litestore_hot_key_access_total{key="user:1"} 2' in payload
    assert 'litestore_hot_key_access_total{key="session:1"} 1' in payload


def test_hot_keys_returns_ranked_entries() -> None:
    collector = MetricsCollector()

    collector.observe_command(CommandRequest(command=CommandName.GET, args=("k1",)), 0.001)
    collector.observe_command(CommandRequest(command=CommandName.GET, args=("k1",)), 0.001)
    collector.observe_command(CommandRequest(command=CommandName.GET, args=("k2",)), 0.001)

    hot_keys = collector.hot_keys(limit=2)

    assert hot_keys[0].key == "k1"
    assert hot_keys[0].count == 2
    assert hot_keys[1].key == "k2"
    assert hot_keys[1].count == 1


def test_metrics_aggregates_memory_by_key_prefix() -> None:
    collector = MetricsCollector()

    collector.observe_store_snapshot(
        {
            "user:1": "alice",
            "user:2": "bob",
            "session:1": "token",
            "plain": "value",
        }
    )

    payload = collector.render_prometheus()

    assert 'litestore_memory_by_prefix_bytes{prefix="user"}' in payload
    assert 'litestore_memory_by_prefix_bytes{prefix="session"}' in payload
    assert 'litestore_memory_by_prefix_bytes{prefix="default"}' in payload


def test_metrics_endpoint_serves_prometheus_payload() -> None:
    collector = MetricsCollector()
    collector.observe_command(CommandRequest(command=CommandName.PING), 0.0005)
    endpoint = MetricsHttpEndpoint(collector)

    response = endpoint.handle_request("/metrics")

    assert response.status_code == 200
    assert response.content_type == "text/plain; version=0.0.4; charset=utf-8"
    assert "# HELP litestore_commands_total" in response.body
    assert 'litestore_command_requests_total{command="PING"} 1' in response.body


def test_metrics_endpoint_returns_404_for_unknown_path() -> None:
    endpoint = MetricsHttpEndpoint(MetricsCollector())

    response = endpoint.handle_request("/health")

    assert response.status_code == 404
    assert response.body == "not found\n"
