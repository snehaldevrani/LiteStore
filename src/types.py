"""Shared immutable contract types for LiteStore."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class CommandName(str, Enum):
    """Canonical command names supported by the protocol layer."""

    PING = "PING"
    SET = "SET"
    GET = "GET"
    DEL = "DEL"
    EXPIRE = "EXPIRE"
    TTL = "TTL"


class ResponseKind(str, Enum):
    """Response wire-shape category used by protocol serializers."""

    SIMPLE_STRING = "simple_string"
    BULK_STRING = "bulk_string"
    INTEGER = "integer"
    NULL = "null"
    ERROR = "error"


class FsyncPolicy(str, Enum):
    """Persistence fsync strategy."""

    NEVER = "never"
    ALWAYS = "always"
    EVERY_N = "every_n"


class ErrorCode(str, Enum):
    """Stable error code namespace shared across modules."""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
    WRONG_ARITY = "WRONG_ARITY"
    KEY_NOT_FOUND = "KEY_NOT_FOUND"
    EXPIRED_KEY = "EXPIRED_KEY"
    STORAGE_ERROR = "STORAGE_ERROR"
    PERSISTENCE_ERROR = "PERSISTENCE_ERROR"
    ROUTING_ERROR = "ROUTING_ERROR"
    WORKER_ERROR = "WORKER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """Parsed client request shape used by command execution paths."""

    command: CommandName
    args: tuple[str, ...] = field(default_factory=tuple)
    request_id: str | None = None
    client_id: str | None = None


@dataclass(frozen=True, slots=True)
class CommandResponse:
    """Normalized command response shape before protocol serialization."""

    kind: ResponseKind
    message: str | None = None
    value: str | None = None
    integer: int | None = None
    error_code: ErrorCode | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class PersistRecord:
    """Append-only log record representation."""

    sequence: int
    request: CommandRequest


@dataclass(frozen=True, slots=True)
class KeyRoute:
    """Result of routing a key to a specific worker partition."""

    partition_id: int
    worker_id: str


@dataclass(frozen=True, slots=True)
class WorkerStats:
    """Basic worker state metadata for diagnostics and metrics."""

    worker_id: str
    partition_id: int
    in_flight: int
    queued: int


@dataclass(frozen=True, slots=True)
class ErrorDetails:
    """Structured error payload suitable for logs and client surfaces."""

    code: ErrorCode
    message: str
    context: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WorkerRequest:
    """Serializable request sent to worker process via queue."""

    request_id: str
    command: CommandName
    args: tuple[str, ...]
    client_id: str | None = None


@dataclass(frozen=True, slots=True)
class WorkerResponse:
    """Serializable response from worker process via queue."""

    request_id: str
    kind: ResponseKind
    message: str | None = None
    value: str | None = None
    integer: int | None = None
    error_code: ErrorCode | None = None


@dataclass(frozen=True, slots=True)
class WorkerControl:
    """Control messages for worker process lifecycle."""

    action: str
    request_id: str | None = None
