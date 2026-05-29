"""Command execution layer for LiteStore."""

from __future__ import annotations

from .interfaces import StoreInterface
from .types import CommandName, CommandRequest, CommandResponse, ErrorCode, ResponseKind


def execute_command(request: CommandRequest, store: StoreInterface) -> CommandResponse:
	"""Execute a parsed command against store state.

	Command logic is intentionally isolated from protocol parsing and transport concerns.
	"""
	command_value = request.command.value if isinstance(request.command, CommandName) else str(request.command)

	if request.command == CommandName.PING:
		if not _has_arity(request, expected=0):
			return _wrong_arity_response(request, expected=0)
		return CommandResponse(kind=ResponseKind.SIMPLE_STRING, message="PONG", request_id=request.request_id)

	if request.command == CommandName.SET:
		if not _has_arity(request, expected=2):
			return _wrong_arity_response(request, expected=2)
		key, value = request.args
		store.set(key, value)
		return CommandResponse(kind=ResponseKind.SIMPLE_STRING, message="OK", request_id=request.request_id)

	if request.command == CommandName.GET:
		if not _has_arity(request, expected=1):
			return _wrong_arity_response(request, expected=1)
		(key,) = request.args
		result = store.get(key)
		if result is None:
			return CommandResponse(kind=ResponseKind.NULL, request_id=request.request_id)
		return CommandResponse(kind=ResponseKind.BULK_STRING, value=result, request_id=request.request_id)

	if request.command == CommandName.DEL:
		if not _has_arity(request, expected=1):
			return _wrong_arity_response(request, expected=1)
		(key,) = request.args
		deleted = store.delete(key)
		return CommandResponse(kind=ResponseKind.INTEGER, integer=1 if deleted else 0, request_id=request.request_id)

	if request.command == CommandName.EXPIRE:
		if not _has_arity(request, expected=2):
			return _wrong_arity_response(request, expected=2)
		key, seconds_raw = request.args
		seconds = _parse_ttl_seconds(seconds_raw)
		if seconds is None:
			return CommandResponse(
				kind=ResponseKind.ERROR,
				error_code=ErrorCode.INVALID_REQUEST,
				message="EXPIRE seconds must be an integer",
				request_id=request.request_id,
			)
		expired_set = store.expire(key, seconds)
		return CommandResponse(
			kind=ResponseKind.INTEGER,
			integer=1 if expired_set else 0,
			request_id=request.request_id,
		)

	if request.command == CommandName.TTL:
		if not _has_arity(request, expected=1):
			return _wrong_arity_response(request, expected=1)
		(key,) = request.args
		remaining = store.ttl(key)
		return CommandResponse(kind=ResponseKind.INTEGER, integer=remaining, request_id=request.request_id)

	return CommandResponse(
		kind=ResponseKind.ERROR,
		error_code=ErrorCode.UNKNOWN_COMMAND,
		message=f"Unsupported command: {command_value}",
		request_id=request.request_id,
	)


def _has_arity(request: CommandRequest, *, expected: int) -> bool:
	return len(request.args) == expected


def _wrong_arity_response(request: CommandRequest, *, expected: int) -> CommandResponse:
	command_value = request.command.value if isinstance(request.command, CommandName) else str(request.command)
	return CommandResponse(
		kind=ResponseKind.ERROR,
		error_code=ErrorCode.WRONG_ARITY,
		message=(
			f"{command_value} expects {expected} argument(s), "
			f"received {len(request.args)}"
		),
		request_id=request.request_id,
	)


def _parse_ttl_seconds(seconds_raw: str) -> int | None:
	try:
		return int(seconds_raw)
	except ValueError:
		return None
