"""Protocol contract tests for LiteStore text protocol."""

from src.errors import InvalidRequestError, UnknownCommandError, WrongArityError
from src.protocol import parse_command, serialize_response
from src.types import CommandName, CommandResponse, ErrorCode, ResponseKind


def test_parse_ping_command() -> None:
    request = parse_command("PING")

    assert request.command == CommandName.PING
    assert request.args == ()


def test_parse_set_command_with_spaces_in_value() -> None:
    request = parse_command("SET user:1 hello world")

    assert request.command == CommandName.SET
    assert request.args == ("user:1", "hello world")


def test_parse_get_command() -> None:
    request = parse_command("GET user:1")

    assert request.command == CommandName.GET
    assert request.args == ("user:1",)


def test_parse_del_command() -> None:
    request = parse_command("DEL user:1")

    assert request.command == CommandName.DEL
    assert request.args == ("user:1",)


def test_parse_expire_command() -> None:
    request = parse_command("EXPIRE session:1 30")

    assert request.command == CommandName.EXPIRE
    assert request.args == ("session:1", "30")


def test_parse_ttl_command() -> None:
    request = parse_command("TTL session:1")

    assert request.command == CommandName.TTL
    assert request.args == ("session:1",)


def test_parse_rejects_empty_input() -> None:
    try:
        parse_command("   \r\n")
        assert False, "Expected InvalidRequestError"
    except InvalidRequestError as exc:
        assert exc.code == ErrorCode.INVALID_REQUEST


def test_parse_rejects_unknown_command() -> None:
    try:
        parse_command("ZADD myset 1 member")
        assert False, "Expected UnknownCommandError"
    except UnknownCommandError as exc:
        assert exc.code == ErrorCode.UNKNOWN_COMMAND


def test_parse_rejects_wrong_arity() -> None:
    try:
        parse_command("SET user:1")
        assert False, "Expected WrongArityError"
    except WrongArityError as exc:
        assert exc.code == ErrorCode.WRONG_ARITY


def test_serialize_simple_string_response() -> None:
    response = CommandResponse(kind=ResponseKind.SIMPLE_STRING, message="PONG")

    assert serialize_response(response) == "+PONG\r\n"


def test_serialize_bulk_string_response() -> None:
    response = CommandResponse(kind=ResponseKind.BULK_STRING, value="value-1")

    assert serialize_response(response) == "$value-1\r\n"


def test_serialize_integer_response() -> None:
    response = CommandResponse(kind=ResponseKind.INTEGER, integer=1)

    assert serialize_response(response) == ":1\r\n"


def test_serialize_null_response() -> None:
    response = CommandResponse(kind=ResponseKind.NULL)

    assert serialize_response(response) == "$-1\r\n"


def test_serialize_error_response() -> None:
    response = CommandResponse(
        kind=ResponseKind.ERROR,
        error_code=ErrorCode.UNKNOWN_COMMAND,
        message="Unsupported command: MGET",
    )

    assert serialize_response(response) == "-ERR UNKNOWN_COMMAND Unsupported command: MGET\r\n"


def test_serialize_rejects_invalid_bulk_response_shape() -> None:
    response = CommandResponse(kind=ResponseKind.BULK_STRING)

    try:
        serialize_response(response)
        assert False, "Expected InvalidRequestError"
    except InvalidRequestError as exc:
        assert exc.code == ErrorCode.INVALID_REQUEST
