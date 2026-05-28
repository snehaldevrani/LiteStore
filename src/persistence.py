"""Append-only file persistence for LiteStore."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .interfaces import PersistenceInterface
from .types import CommandName, CommandRequest, PersistRecord


class AofPersistence(PersistenceInterface):
	"""Simple JSONL-based append-only log.

	Each line is a JSON object with sequence, command, and args fields.
	"""

	def __init__(self, file_path: str | Path) -> None:
		self._file_path = Path(file_path)
		self._file_path.parent.mkdir(parents=True, exist_ok=True)
		self._file = self._file_path.open("a+", encoding="utf-8")
		self._next_sequence = self._discover_next_sequence()

	def append(self, record: PersistRecord) -> None:
		"""Append one mutation record to the AOF in write order."""
		payload = {
			"sequence": record.sequence,
			"command": record.request.command.value,
			"args": list(record.request.args),
		}
		self._file.write(json.dumps(payload, ensure_ascii=True) + "\n")
		self._file.flush()

	def append_request(self, request: CommandRequest) -> PersistRecord:
		"""Build and append a new record using local monotonic sequence."""
		record = PersistRecord(sequence=self._next_sequence, request=request)
		self.append(record)
		self._next_sequence += 1
		return record

	def replay(self) -> Iterable[PersistRecord]:
		"""Yield persisted records in file order while skipping malformed lines."""
		with self._file_path.open("r", encoding="utf-8") as source:
			for raw_line in source:
				line = raw_line.strip()
				if not line:
					continue

				parsed = _parse_record_line(line)
				if parsed is None:
					continue

				yield parsed

	def close(self) -> None:
		"""Close file resources."""
		self._file.close()

	def _discover_next_sequence(self) -> int:
		max_sequence = -1
		if not self._file_path.exists():
			return 0

		with self._file_path.open("r", encoding="utf-8") as source:
			for raw_line in source:
				parsed = _parse_record_line(raw_line.strip())
				if parsed is None:
					continue
				if parsed.sequence > max_sequence:
					max_sequence = parsed.sequence
		return max_sequence + 1


def _parse_record_line(line: str) -> PersistRecord | None:
	try:
		data = json.loads(line)
	except json.JSONDecodeError:
		return None

	if not isinstance(data, dict):
		return None

	sequence = data.get("sequence")
	command_raw = data.get("command")
	args_raw = data.get("args")

	if not isinstance(sequence, int):
		return None
	if not isinstance(command_raw, str):
		return None
	if not isinstance(args_raw, list):
		return None
	if not all(isinstance(item, str) for item in args_raw):
		return None

	try:
		command = CommandName(command_raw)
	except ValueError:
		return None

	request = CommandRequest(command=command, args=tuple(args_raw))
	return PersistRecord(sequence=sequence, request=request)
