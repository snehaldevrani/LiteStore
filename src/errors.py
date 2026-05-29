"""Common error types for LiteStore contracts."""

from __future__ import annotations

from typing import Mapping

from .types import ErrorCode, ErrorDetails


class LiteStoreError(Exception):
    """Base exception carrying stable, typed error metadata."""

    def __init__(self, code: ErrorCode, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context: Mapping[str, str] = context or {}

    def to_details(self) -> ErrorDetails:
        """Return a serializable structured error payload."""
        return ErrorDetails(code=self.code, message=self.message, context=self.context)


class InvalidRequestError(LiteStoreError):
    """Raised when request shape or protocol framing is invalid."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.INVALID_REQUEST, message, context)


class UnknownCommandError(LiteStoreError):
    """Raised when the command verb is not supported."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.UNKNOWN_COMMAND, message, context)


class WrongArityError(LiteStoreError):
    """Raised when command argument count does not match contract."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.WRONG_ARITY, message, context)


class StorageError(LiteStoreError):
    """Raised for store-layer failures."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.STORAGE_ERROR, message, context)


class PersistenceError(LiteStoreError):
    """Raised for persistence append/replay failures."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.PERSISTENCE_ERROR, message, context)


class RoutingError(LiteStoreError):
    """Raised when routing cannot resolve ownership."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.ROUTING_ERROR, message, context)


class WorkerError(LiteStoreError):
    """Raised when worker execution or lifecycle fails."""

    def __init__(self, message: str, context: Mapping[str, str] | None = None) -> None:
        super().__init__(ErrorCode.WORKER_ERROR, message, context)
