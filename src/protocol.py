"""Text protocol parsing and serialization for LiteStore."""

from __future__ import annotations

from .errors import InvalidRequestError, UnknownCommandError, WrongArityError
from .types import CommandName, CommandRequest, CommandResponse, ErrorCode, ResponseKind


def parse_command(raw_command: str, *, request_id: str | None = None, client_id: str | None = None) -> CommandRequest:
	"""Parse a text command into the shared request contract.

	Supported commands:
	- PING
	- SET key value
	- GET key
	- DEL key
	"""
	if not isinstance(raw_command, str):
		raise InvalidRequestError("Command must be text")

	command_line = raw_command.strip()
	if not command_line:
		raise InvalidRequestError("Command cannot be empty")

	verb, args = _split_command(command_line)

	if verb == CommandName.PING.value:
		_ensure_arity(verb, args, expected=0)
		return CommandRequest(command=CommandName.PING, args=(), request_id=request_id, client_id=client_id)

	if verb == CommandName.SET.value:
		_ensure_arity(verb, args, expected=2)
		return CommandRequest(command=CommandName.SET, args=args, request_id=request_id, client_id=client_id)

	if verb == CommandName.GET.value:
		_ensure_arity(verb, args, expected=1)
		return CommandRequest(command=CommandName.GET, args=args, request_id=request_id, client_id=client_id)

	if verb == CommandName.DEL.value:
		_ensure_arity(verb, args, expected=1)
		return CommandRequest(command=CommandName.DEL, args=args, request_id=request_id, client_id=client_id)

	if verb == CommandName.EXPIRE.value:
		_ensure_arity(verb, args, expected=2)
		return CommandRequest(command=CommandName.EXPIRE, args=args, request_id=request_id, client_id=client_id)

	if verb == CommandName.TTL.value:
		_ensure_arity(verb, args, expected=1)
		return CommandRequest(command=CommandName.TTL, args=args, request_id=request_id, client_id=client_id)

	raise UnknownCommandError(f"Unsupported command: {verb}", context={"command": verb})


def serialize_response(response: CommandResponse) -> str:
	"""Serialize a shared response contract into one text line for clients."""
	if response.kind == ResponseKind.SIMPLE_STRING:
		payload = response.message if response.message is not None else ""
		return f"+{payload}\r\n"

	if response.kind == ResponseKind.BULK_STRING:
		if response.value is None:
			raise InvalidRequestError("Bulk string response requires a value")
		return f"${response.value}\r\n"

	if response.kind == ResponseKind.INTEGER:
		if response.integer is None:
			raise InvalidRequestError("Integer response requires an integer value")
		return f":{response.integer}\r\n"

	if response.kind == ResponseKind.NULL:
		return "$-1\r\n"

	if response.kind == ResponseKind.ERROR:
		code = response.error_code.value if response.error_code is not None else ErrorCode.INTERNAL_ERROR.value
		message = response.message if response.message is not None else "Unknown error"
		return f"-ERR {code} {message}\r\n"

	raise InvalidRequestError("Unsupported response kind")


def _split_command(command_line: str) -> tuple[str, tuple[str, ...]]:
	"""Split command preserving a trailing SET value with spaces."""
	first_split = command_line.split(maxsplit=1)
	verb = first_split[0].upper()

	if len(first_split) == 1:
		return verb, ()

	if verb == CommandName.SET.value:
		set_parts = command_line.split(maxsplit=2)
		if len(set_parts) < 3:
			return verb, tuple(set_parts[1:])
		return verb, (set_parts[1], set_parts[2])

	return verb, tuple(first_split[1].split())


def _ensure_arity(command: str, args: tuple[str, ...], *, expected: int) -> None:
	if len(args) != expected:
		raise WrongArityError(
			f"{command} expects {expected} argument(s), received {len(args)}",
			context={"command": command, "expected": str(expected), "received": str(len(args))},
		)
