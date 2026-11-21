"""Bounded canonical JSON ingestion for private runtime declarations."""

from __future__ import annotations
import json
from typing import Any
from cppulse.errors import ContractError
from cppulse.contracts.runtime_input import validate_runtime_manifest

_MAX_BYTES = 8 * 1024**2


def _bounded_structure(text: str) -> None:
    depth = 0
    collections = 0
    members = 0
    quoted = False
    escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            collections += 1
            if depth > 64 or collections > 20000:
                raise ValueError("Runtime JSON structural boundary exceeded")
        elif character in "]}":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced runtime JSON")
        elif character == ",":
            members += 1
            if members > 20000:
                raise ValueError("Runtime JSON member boundary exceeded")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        key.encode("utf-8", errors="strict")
        if key in result:
            raise ValueError("Duplicate runtime JSON key")
        result[key] = value
    return result


def _integer(token: str) -> int:
    if len(token) > 128:
        raise ValueError("Runtime integer token too long")
    return int(token)


def _reject_number(token: str) -> Any:
    raise ValueError("Runtime declarations require finite exact integer tokens")


def _strings(value: Any) -> None:
    if isinstance(value, str):
        value.encode("utf-8", errors="strict")
    elif isinstance(value, dict):
        for child in value.values():
            _strings(child)
    elif isinstance(value, list):
        for child in value:
            _strings(child)


def load_runtime_manifest(raw: bytes) -> dict[str, Any]:
    """Reject ambiguous encodings and resource-heavy structure before validation."""
    if not isinstance(raw, bytes) or len(raw) > _MAX_BYTES:
        raise ContractError("Runtime JSON exceeds byte boundary or is not bytes")
    try:
        text = raw.decode("utf-8", errors="strict")
        _bounded_structure(text)
        document = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_int=_integer,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        _strings(document)
        validate_runtime_manifest(document)
        return document
    except (ValueError, UnicodeError, RecursionError, TypeError) as error:
        raise ContractError("Invalid bounded runtime JSON") from error
