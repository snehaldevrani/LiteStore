# LiteStore Shared Contracts

This document freezes cross-module contracts for LiteStore so implementation can proceed without interface drift.

## 1) Command Request and Response Shapes

Defined in src/types.py:

- CommandRequest
  - command: CommandName
  - args: tuple[str, ...]
  - request_id: str | None
  - client_id: str | None

- CommandResponse
  - kind: ResponseKind
  - message: str | None
  - value: str | None
  - integer: int | None
  - error_code: ErrorCode | None
  - request_id: str | None

- PersistRecord
  - sequence: int
  - request: CommandRequest

Design notes:
- No untyped shared dicts are used as public contract types.
- Shared payloads use frozen dataclasses with explicit typing.

## 2) Store Interface

Defined in src/interfaces.py as StoreInterface:

- set(key: str, value: str) -> None
- get(key: str) -> str | None
- delete(key: str) -> bool
- expire(key: str, ttl_seconds: int) -> bool
- ttl(key: str) -> int
- process_expirations(now: float | None = None) -> int

TTL return semantics are reserved for Redis-like behavior:
- positive seconds remaining
- -1 when key exists with no expiry
- -2 when key does not exist

Expiration processing contract:
- `process_expirations()` proactively removes due keys and returns how many were removed.
- worker-owned stores expose this directly so workers do not depend on `getattr` or hidden methods.

## 3) Persistence Interface

Defined in src/interfaces.py as PersistenceInterface:

- append(record: PersistRecord) -> None
- replay() -> Iterable[PersistRecord]
- close() -> None

Contract invariants:
- append preserves write order.
- replay returns records in durable order.

## 4) Router Interface

Defined in src/interfaces.py as RouterInterface:

- route_key(key: str) -> KeyRoute
- route_request(request: CommandRequest) -> KeyRoute

Contract invariants:
- routing is deterministic for the same input key.
- route_request uses command semantics to choose ownership.

## 5) Worker Interface

Defined in src/interfaces.py as WorkerInterface:

Attributes:
- worker_id: str
- partition_id: int

Methods:
- start() -> None
- stop() -> None
- execute(request: CommandRequest) -> CommandResponse
- stats() -> WorkerStats

## 6) Common Error Types

Defined in src/errors.py with base LiteStoreError:

- InvalidRequestError
- UnknownCommandError
- WrongArityError
- StorageError
- PersistenceError
- RoutingError
- WorkerError

All map to ErrorCode values in src/types.py and expose structured error details via to_details().

## 7) Stability Rules

- Treat src/types.py, src/interfaces.py, and src/errors.py as stable contract surfaces.
- Additive changes are preferred over breaking changes.
- If a breaking change is unavoidable, update this document and bump project contract version in README.
