"""Bounded import of GNU G++ 14.2.0 JSON diagnostics, adapter 1.0.0.

This imports compiler diagnostic claims, not completed-analysis proof. Raw JSON
and producer identity remain attributable. No files, tools or network are read.
GCC byte columns are kept separately from display columns; an unavailable byte
column stays unknown. Unsupported unlocated records are never assigned a file.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any, Literal, Mapping, Sequence

from cppulse.errors import ContractError

MAX_REPORT_BYTES = 10 * 1024 * 1024
MAX_JSON_NODES = 100_000
MAX_JSON_DEPTH = 64
MAX_DIAGNOSTICS = 10_000
_PRODUCER = {"name": "GNU-G++", "version": "14.2.0"}
_LIMIT = (
    "Imported GCC diagnostic claims do not establish complete analysis, source "
    "execution or producer authenticity; an empty array is not a clean scan."
)
Usability = Literal["usable", "unsupported", "malformed", "missing"]


@dataclass(frozen=True)
class GccDiagnostic:
    """One retained diagnostic occurrence, with its original rule identity."""

    original_rule_id: str
    namespaced_rule_id: str
    rule_version: str
    file: str
    line: int
    column: int | None
    severity: str
    message: str
    fingerprint: str


@dataclass(frozen=True)
class GccDiagnostics:
    """Parsed import claims; unavailable reports carry no invented zero result."""

    producer_name: str
    producer_version: str
    usability: Usability
    diagnostics: tuple[GccDiagnostic, ...]
    limitations: tuple[str, ...]
    report_sha256: str
    size_bytes: int
    adapter: str = "gcc-json"
    adapter_version: str = "1.0.0"
    origin: Literal["import"] = "import"


class _Unsupported(ValueError):
    pass


def _unicode_metadata(value: str, label: str) -> None:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ContractError(label + " must contain valid Unicode") from error


def _scope_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\\" in value
        or PureWindowsPath(value).drive
        or PurePosixPath(value).is_absolute()
        or ".." in PurePosixPath(value).parts
        or PurePosixPath(value).as_posix() != value
        or value == "."
    ):
        raise ContractError("Diagnostic scope needs canonical relative POSIX files")
    _unicode_metadata(value, "Diagnostic scope")
    return value


def _file_identity(value: Any, root: PurePosixPath, scope: set[str]) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\x00" in value
        or "\\" in value
        or PureWindowsPath(value).drive
    ):
        raise _Unsupported("Unsupported diagnostic file identity")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise _Unsupported("Diagnostic path traversal is unsupported")
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError as error:
            raise _Unsupported(
                "Diagnostic lies outside the declared source root"
            ) from error
    relative = path.as_posix()
    if relative not in scope:
        raise _Unsupported("Diagnostic is outside the declared source scope")
    return relative


def _finite_json(value: str) -> None:
    raise ValueError(f"Nonfinite JSON value is unsupported: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field is ambiguous")
        result[key] = value
    return result


def _check_tree(value: Any) -> None:
    pending = [(value, 0)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise _Unsupported("Diagnostic JSON node/depth limit exceeded")
        if isinstance(current, str):
            try:
                current.encode("utf-8", errors="strict")
            except UnicodeError as error:
                raise _Unsupported(
                    "Diagnostic JSON contains invalid Unicode"
                ) from error
        elif isinstance(current, float) and not math.isfinite(current):
            raise _Unsupported("Diagnostic JSON number exceeds finite numeric profile")
        elif isinstance(current, dict):
            for key in current:
                try:
                    key.encode("utf-8", errors="strict")
                except UnicodeError as error:
                    raise _Unsupported(
                        "Diagnostic JSON key contains invalid Unicode"
                    ) from error
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)


def _read_diagnostics(
    records: list[Any], root: PurePosixPath, scope: set[str]
) -> tuple[GccDiagnostic, ...]:
    pending = list(reversed(records))
    result = []
    severities = {
        "error": "error",
        "fatal error": "error",
        "warning": "warning",
        "note": "info",
    }
    while pending:
        record = pending.pop()
        if len(result) >= MAX_DIAGNOSTICS:
            raise _Unsupported("Diagnostic occurrence limit exceeded")
        if (
            not isinstance(record, dict)
            or not isinstance(record.get("kind"), str)
            or record["kind"] not in severities
        ):
            raise _Unsupported("Unsupported GCC diagnostic category/shape")
        message = record.get("message")
        if not isinstance(message, str) or not message:
            raise _Unsupported("Diagnostic message is unavailable")
        locations = record.get("locations")
        if (
            not isinstance(locations, list)
            or not locations
            or not isinstance(locations[0], dict)
        ):
            raise _Unsupported("Unlocated diagnostic retained only in the raw report")
        caret = locations[0].get("caret")
        if not isinstance(caret, dict):
            raise _Unsupported("Primary diagnostic caret is unavailable")
        file = _file_identity(caret.get("file"), root, scope)
        line = caret.get("line")
        column = caret.get("byte-column")
        if not isinstance(line, int) or isinstance(line, bool) or line <= 0:
            raise _Unsupported("Diagnostic source line is unavailable")
        if column is not None and (
            not isinstance(column, int) or isinstance(column, bool) or column <= 0
        ):
            raise _Unsupported("Only positive one-based byte columns are supported")
        original = record.get(
            "option", "diagnostic-" + record["kind"].replace(" ", "-")
        )
        if not isinstance(original, str) or not original:
            raise _Unsupported("Diagnostic rule identity is unavailable")
        namespaced = "gcc:" + original
        if (
            not re.fullmatch(r"[A-Za-z0-9_.:-]+", original)
            or len(namespaced) > 128
            or re.fullmatch(r"option-[0-9a-f]{64}", original)
        ):
            # Reserve this representation for hashed originals. Otherwise an
            # accepted literal rule can impersonate another rule's hash slot.
            namespaced = "gcc:option-" + hashlib.sha256(original.encode()).hexdigest()
        identity = {
            "producer": _PRODUCER,
            "rule": original,
            "file": file,
            "line": line,
            "column": column,
            "message": message,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
        ).hexdigest()
        result.append(
            GccDiagnostic(
                original,
                namespaced,
                _PRODUCER["version"],
                file,
                line,
                column,
                severities[record["kind"]],
                message,
                fingerprint,
            )
        )
        children = record.get("children", [])
        if not isinstance(children, list):
            raise _Unsupported("Diagnostic children must be an array")
        pending.extend(reversed(children))
    return tuple(result)


def parse_gcc_json(
    content: bytes,
    *,
    source_root: str,
    scope_files: Sequence[str],
    producer: Mapping[str, str] | None = None,
) -> GccDiagnostics:
    """Parse one imported translation-unit report without inspecting a project.

    Args:
        content: Exact raw UTF-8 JSON bytes, retained by the caller.
        source_root: Explicit original absolute POSIX source root, not a guessed basename.
        scope_files: Declared repository-relative source identities.
        producer: Explicit imported claim; omission stays unavailable, not guessed.
            Only GNU-G++ 14.2.0 is currently supported.

    Returns:
        Located observations or explicit unavailable status with raw byte identity.

    Raises:
        ContractError: Invalid caller-selected root/scope/producer metadata.
    """
    if not isinstance(source_root, str):
        raise ContractError("Diagnostic source_root must be a POSIX string")
    _unicode_metadata(source_root, "Diagnostic source_root")
    root = PurePosixPath(source_root)
    if (
        not root.is_absolute()
        or ".." in root.parts
        or root.as_posix() != source_root
        or "\\" in source_root
        or "\x00" in source_root
    ):
        raise ContractError(
            "Diagnostic source_root must be a canonical absolute POSIX path"
        )
    scope = {_scope_path(path) for path in scope_files}
    if len(scope) != len(scope_files):
        raise ContractError("Diagnostic scope contains duplicate identities")
    claim = dict(
        {"name": "GNU-G++", "version": "unavailable"} if producer is None else producer
    )
    if set(claim) != {"name", "version"} or any(
        not isinstance(v, str) or not v for v in claim.values()
    ):
        raise ContractError("Producer claim requires nonempty name/version strings")
    for value in claim.values():
        _unicode_metadata(value, "Diagnostic producer claim")
    if not isinstance(content, bytes):
        raise ContractError("Diagnostic report must contain exact bytes")
    sha = hashlib.sha256(content).hexdigest()

    def report(
        status: Usability,
        diagnostics: tuple[GccDiagnostic, ...] = (),
        reason: str | None = None,
    ) -> GccDiagnostics:
        return GccDiagnostics(
            claim["name"],
            claim["version"],
            status,
            diagnostics,
            (_LIMIT, *([reason] if reason else [])),
            sha,
            len(content),
        )

    if len(content) > MAX_REPORT_BYTES:
        return report("unsupported", reason="Diagnostic report byte limit exceeded")
    if not content:
        return report("missing", reason="Empty log is not a JSON diagnostic array")
    if claim != _PRODUCER:
        return report("unsupported", reason="Unsupported imported GCC producer/version")
    try:
        value = json.loads(
            content.decode("utf-8"),
            parse_constant=_finite_json,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeError, ValueError, RecursionError):
        return report("malformed", reason="Invalid UTF-8 finite JSON diagnostic report")
    if not isinstance(value, list):
        return report(
            "malformed", reason="GCC JSON requires a top-level diagnostic array"
        )
    try:
        _check_tree(value)
        return report("usable", _read_diagnostics(value, root, scope))
    except _Unsupported as error:
        return report("unsupported", reason=str(error))
