"""Bounded whole-document JSON validation with provisional array element bytes.

The caller owns the input stream and must finish iteration before committing any
derived records. This module neither validates a report schema nor authenticates
its source. Ignored containers are parsed without materializing their contents.
"""

from __future__ import annotations

from contextlib import closing
import hashlib
import json
import re
from typing import BinaryIO, Iterator

from cppulse.contracts.json_stream import JsonStreamLimits
from cppulse.errors import ContractError, IntegrityError

_SPACE = re.compile(rb"[ \t\r\n]*")
_SPECIAL = re.compile(rb'["\\\x00-\x1f]')
_DELIMITERS = b" \t\r\n,]}"


class _Reader:
    def __init__(self, stream: BinaryIO, size: int, limits: JsonStreamLimits) -> None:
        self.stream, self.size, self.limits = stream, size, limits
        self.buffer, self.position = b"", 0
        self.read_bytes = self.offset = 0
        self.ended = False
        self.digest = hashlib.sha256()

    def peek(self) -> int | None:
        if self.position == len(self.buffer):
            if self.ended:
                return None
            # A single extra byte is the necessary EOF/oversize probe. Never
            # retain it as accepted body data or issue an unbounded read.
            requested = min(self.limits.chunk_bytes, self.size - self.read_bytes + 1)
            try:
                block = self.stream.read(requested)
            except Exception as error:
                raise IntegrityError("JSON binary stream read failed") from error
            if not isinstance(block, bytes) or len(block) > requested:
                raise IntegrityError(
                    "JSON binary stream violated bounded read contract"
                )
            if not block:
                self.ended = True
                return None
            if len(block) > self.size - self.read_bytes:
                raise IntegrityError("JSON stream exceeds expected size/byte budget")
            self.read_bytes += len(block)
            self.digest.update(block)
            self.buffer, self.position = block, 0
        return self.buffer[self.position]

    def take(self) -> int:
        value = self.peek()
        if value is None:
            raise ContractError("Truncated JSON input")
        self.position += 1
        self.offset += 1
        return value

    def advance(self, end: int) -> bytes:
        raw = self.buffer[self.position : end]
        self.offset += end - self.position
        self.position = end
        return raw

    def space(self) -> None:
        while self.peek() is not None:
            end = _SPACE.match(self.buffer, self.position).end()
            if end == self.position:
                return
            self.advance(end)


class _Parser:
    def __init__(self, reader: _Reader, member: str) -> None:
        self.reader, self.member, self.limits = reader, member, reader.limits
        self.compact = self.array_items = self.records = self.live_keys = 0
        self.item_starts: list[int] = []

    def emit(self, raw: bytes, capture: bytearray | None) -> None:
        self.compact += len(raw)
        # All active elements share the same cap; the earliest start always
        # dominates. This avoids one counter update per nested active element.
        if (
            self.item_starts
            and self.compact - self.item_starts[0] > self.limits.max_item_bytes
        ):
            raise ContractError("JSON array element exceeds compact byte budget")
        if capture is not None:
            capture.extend(raw)

    def punctuation(self, expected: int, capture: bytearray | None) -> None:
        if self.reader.take() != expected:
            raise ContractError("Unexpected JSON delimiter")
        self.emit(bytes((expected,)), capture)

    def depth(self, value: int) -> None:
        if value > self.limits.max_depth:
            raise ContractError("JSON container depth exceeds budget")

    def string(self, capture: bytearray | None) -> str:
        token = bytearray()

        def append(raw: bytes) -> None:
            if len(token) + len(raw) > self.limits.max_token_bytes:
                raise ContractError("JSON string token exceeds byte budget")
            self.emit(raw, capture)
            token.extend(raw)

        if self.reader.take() != 34:
            raise ContractError("JSON object key/string must start with a quote")
        append(b'"')
        while True:
            if self.reader.peek() is None:
                raise ContractError("Truncated JSON string")
            match = _SPECIAL.search(self.reader.buffer, self.reader.position)
            if match is None:
                append(self.reader.advance(len(self.reader.buffer)))
                continue
            value = self.reader.buffer[match.start()]
            append(self.reader.advance(match.end()))
            if value == 34:
                break
            if value < 32:
                raise ContractError("Unescaped JSON string control character")
            escaped = self.reader.take()
            append(bytes((escaped,)))
            if escaped < 32:
                raise ContractError("Invalid JSON string escape")
        try:
            decoded = json.loads(token.decode("utf-8", errors="strict"))
            decoded.encode("utf-8", errors="strict")
        except (ValueError, UnicodeError) as error:
            raise ContractError(
                "Invalid JSON UTF-8, escape or Unicode surrogate"
            ) from error
        return decoded

    def scalar(self, capture: bytearray | None) -> None:
        token_bytes = 0

        def consume() -> int:
            nonlocal token_bytes
            value = self.reader.take()
            token_bytes += 1
            if token_bytes > self.limits.max_token_bytes:
                raise ContractError("JSON scalar token exceeds byte budget")
            self.emit(bytes((value,)), capture)
            return value

        current = self.reader.peek()
        words = {116: b"true", 102: b"false", 110: b"null"}
        if current in words:
            for value in words[current]:
                if consume() != value:
                    raise ContractError("Invalid JSON literal")
        else:
            if current == 45:
                consume()
                current = self.reader.peek()
            if current == 48:
                consume()
            elif current is not None and 49 <= current <= 57:
                while (
                    current := self.reader.peek()
                ) is not None and 48 <= current <= 57:
                    consume()
            else:
                raise ContractError("Invalid JSON value or number")
            if self.reader.peek() == 46:
                consume()
                current = self.reader.peek()
                if current is None or not 48 <= current <= 57:
                    raise ContractError("JSON fraction needs digits")
                while (
                    current := self.reader.peek()
                ) is not None and 48 <= current <= 57:
                    consume()
            if self.reader.peek() in (69, 101):
                consume()
                if self.reader.peek() in (43, 45):
                    consume()
                current = self.reader.peek()
                if current is None or not 48 <= current <= 57:
                    raise ContractError("JSON exponent needs digits")
                while (
                    current := self.reader.peek()
                ) is not None and 48 <= current <= 57:
                    consume()
        current = self.reader.peek()
        if current is not None and current not in _DELIMITERS:
            raise ContractError("Invalid JSON scalar terminator")

    def object_keys(self, depth: int, capture: bytearray | None) -> Iterator[str]:
        self.depth(depth)
        self.punctuation(123, capture)
        keys, held = set(), 0
        try:
            self.reader.space()
            if self.reader.peek() == 125:
                self.punctuation(125, capture)
                return
            while True:
                key = self.string(capture)
                if key in keys:
                    raise ContractError("Duplicate decoded JSON object key")
                size = len(key.encode("utf-8"))
                if size > self.limits.max_key_bytes:
                    raise ContractError("JSON decoded key exceeds byte budget")
                if len(keys) >= self.limits.max_object_members:
                    raise ContractError("JSON object member budget exceeded")
                if self.live_keys + size > self.limits.max_live_key_bytes:
                    raise ContractError("Simultaneous JSON object key budget exceeded")
                keys.add(key)
                held += size
                self.live_keys += size
                self.reader.space()
                self.punctuation(58, capture)
                self.reader.space()
                yield key
                self.reader.space()
                if self.reader.peek() == 125:
                    self.punctuation(125, capture)
                    return
                self.punctuation(44, capture)
                self.reader.space()
        finally:
            self.live_keys -= held

    def start_item(self, *, selected: bool = False) -> None:
        self.array_items += 1
        if self.array_items > self.limits.max_array_items:
            raise ContractError("Global JSON array item budget exceeded")
        if selected:
            self.records += 1
            if self.records > self.limits.max_records:
                raise ContractError("Selected JSON record budget exceeded")
        self.item_starts.append(self.compact)

    def array(self, depth: int, capture: bytearray | None) -> None:
        self.depth(depth)
        self.punctuation(91, capture)
        self.reader.space()
        if self.reader.peek() == 93:
            self.punctuation(93, capture)
            return
        while True:
            self.start_item()
            try:
                self.value(depth + 1, capture)
            finally:
                self.item_starts.pop()
            self.reader.space()
            if self.reader.peek() == 93:
                self.punctuation(93, capture)
                return
            self.punctuation(44, capture)
            self.reader.space()

    def value(self, depth: int, capture: bytearray | None) -> None:
        current = self.reader.peek()
        if current == 123:
            with closing(self.object_keys(depth, capture)) as keys:
                for _ in keys:
                    self.value(depth + 1, capture)
        elif current == 91:
            self.array(depth, capture)
        elif current == 34:
            self.string(capture)
        else:
            self.scalar(capture)

    def selected(self, depth: int) -> Iterator[bytes]:
        self.depth(depth)
        self.punctuation(91, None)
        self.reader.space()
        if self.reader.peek() == 93:
            self.punctuation(93, None)
            return
        while True:
            self.start_item(selected=True)
            buffer = bytearray()
            try:
                self.value(depth + 1, buffer)
            finally:
                self.item_starts.pop()
            self.reader.space()
            delimiter = self.reader.peek()
            if delimiter not in (44, 93):
                raise ContractError(
                    "Selected JSON array lacks a complete element delimiter"
                )
            self.punctuation(delimiter, None)
            item = bytes(buffer)
            del buffer
            yield item
            if delimiter == 93:
                return
            self.reader.space()

    def root(self) -> Iterator[bytes]:
        found = False
        self.reader.space()
        with closing(self.object_keys(1, None)) as keys:
            for key in keys:
                if key == self.member:
                    if self.reader.peek() != 91:
                        raise ContractError("Selected JSON member is not an array")
                    found = True
                    yield from self.selected(2)
                else:
                    self.value(2, None)
        self.reader.space()
        if self.reader.peek() is not None:
            raise ContractError("Trailing material after JSON root object")
        if self.reader.read_bytes != self.reader.size:
            raise IntegrityError("JSON stream size differs from expected identity")
        if not found:
            raise ContractError("Selected JSON array member is missing")


def iter_json_array(
    binary_stream: BinaryIO,
    member: str,
    *,
    expected_sha256: str,
    expected_size: int,
    limits: JsonStreamLimits = JsonStreamLimits(),
) -> Iterator[bytes]:
    """Yield provisional compact UTF-8 rows, validating every input byte at EOF.

    Record limits count selected rows; array limits count all elements globally.
    Every array element, including ignored elements, has the same compact-byte
    cap. Caller streams are never closed here. Abandoning iteration proves nothing.
    """
    if type(limits) is not JsonStreamLimits:  # noqa: E721 -- closed private budget profile
        raise ContractError("JSON stream limits require the frozen budget dataclass")
    limits.validate()
    if type(expected_size) is not int or not 0 <= expected_size <= limits.max_bytes:  # noqa: E721 -- exact size pin, no coercion
        raise ContractError("JSON stream needs an exact bounded expected size")
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
    ):
        raise ContractError("JSON stream needs an exact lowercase SHA256 pin")
    if not isinstance(member, str) or not member or "\x00" in member:
        raise ContractError(
            "Selected JSON member must be a nonempty Unicode name without NUL"
        )
    try:
        if (
            len(member) > limits.max_key_bytes
            or len(member.encode("utf-8", errors="strict")) > limits.max_key_bytes
        ):
            raise ContractError("Selected member exceeds decoded key budget")
    except UnicodeError as error:
        raise ContractError("Selected JSON member is not valid Unicode") from error
    reader = _Reader(binary_stream, expected_size, limits)
    try:
        yield from _Parser(reader, member).root()
    except (RecursionError, MemoryError) as error:
        raise ContractError("JSON parser local capacity exhausted") from error
    if reader.digest.hexdigest() != expected_sha256:
        raise IntegrityError("JSON stream SHA256 differs from expected identity")
