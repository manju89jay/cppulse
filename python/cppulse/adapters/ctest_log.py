"""Parse the reviewed CTest 3.31.6 LastTest.log structure without executing it.

Version 1.0.0 supports complete single-session UTF-8 logs up to 10 MiB. Command
arguments must use CTest's unambiguous double-quoted literal form; embedded quote
encodings and control characters are unsupported. Backslashes and spaces remain
literal. No shell lexer or shell execution is used. Headers are recognized only
outside captured Output blocks, and ambiguous/truncated boundaries fail closed.

These editable logs are imported claims, not authentication. A collector must
bind the exact bytes to observed CTest execution and retained binary identities.
Log outcomes do not replace JUnit: SKIP_RETURN_CODE can say "Test Passed." here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import unicodedata
from typing import Any, Literal

MAX_LOG_BYTES = 10 * 1024 * 1024
MAX_RECORDS = 100_000
_SEPARATOR = "-" * 58
_HEADER = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*) Testing: (.+)")
_ARGUMENT = re.compile(r'"([^"\r\n]*)"(?: |$)')
_VERSION = "1.0.0"
_LIMITS = (
    "Execution-log records are imported claims; observed CTest execution, producer identity and retained binary linkage require separate checks.",
    "CTest may label SKIP_RETURN_CODE as Test Passed; JUnit outcomes remain authoritative for skipped and disabled cases.",
)
Usability = Literal["usable", "malformed", "unsupported", "missing"]
Outcome = Literal["passed", "failed", "notrun"]


class _Unsupported(ValueError):
    """The input requires a different reviewed log dialect."""


@dataclass(frozen=True)
class CTestLogRecord:
    """One structurally delimited record, independent of text printed by its test."""

    name: str
    actual_argv: tuple[str, ...]
    working_directory: str
    outcome: Outcome
    index: int
    total: int


@dataclass(frozen=True)
class CTestLog:
    """Imported trace records and the identity of exactly the parsed raw bytes."""

    records: tuple[CTestLogRecord, ...]
    usability: Usability
    limitations: tuple[str, ...]
    producer: dict[str, Any]
    adapter_version: str
    report_sha256: str | None = None
    size_bytes: int | None = None
    origin: Literal["import"] = "import"

    def as_dict(self) -> dict[str, Any]:
        """Return independent JSON-serializable trace facts."""
        return asdict(self)


def _read_log(path: Path) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("CTest log must be a regular file")
        if info.st_size > MAX_LOG_BYTES:
            raise ValueError(f"CTest log exceeds {MAX_LOG_BYTES} byte limit")
        content = stream.read(MAX_LOG_BYTES + 1)
    if len(content) > MAX_LOG_BYTES:
        raise ValueError(f"CTest log exceeds {MAX_LOG_BYTES} byte limit")
    return content


def _literal(value: str, field: str, *, empty: bool = False) -> str:
    # Unicode space separators inside quoted/structurally delimited fields are
    # literal data, just like ASCII space. Keep line/paragraph separators,
    # controls and formatting characters outside this reviewed profile.
    if (not value and not empty) or any(
        not char.isprintable() and unicodedata.category(char) != "Zs" for char in value
    ):
        raise _Unsupported(f"Unsupported empty/control-character {field}")
    return value


def _argv(value: str) -> tuple[str, ...]:
    # Actual disabled/not-invoked CTest entries use an empty command placeholder.
    if value == '""':
        return ()
    arguments = []
    cursor = 0
    while cursor < len(value):
        token = _ARGUMENT.match(value, cursor)
        if token is None:
            raise _Unsupported(
                "Ambiguous Command encoding; only quoted literal argv is supported"
            )
        arguments.append(_literal(token.group(1), "argument", empty=True))
        cursor = token.end()
    if not arguments or not arguments[0]:
        raise _Unsupported("Log does not identify an invoked executable")
    return tuple(arguments)


def _records(text: str) -> tuple[CTestLogRecord, ...]:
    # Only LF/CRLF delimit records. Unicode output line separators are data.
    lines = [line[:-1] if line.endswith("\r") else line for line in text.split("\n")]
    cursor = 0

    def take() -> str:
        nonlocal cursor
        if cursor >= len(lines):
            raise ValueError("Truncated CTest execution log")
        line = lines[cursor]
        cursor += 1
        return line

    def expect(expected: str) -> None:
        if take() != expected:
            raise ValueError(f"Inconsistent CTest structure; expected {expected!r}")

    def field(prefix: str, *, empty: bool = False) -> str:
        line = take()
        if not line.startswith(prefix):
            raise ValueError(f"Missing structural {prefix!r} field")
        return _literal(line[len(prefix) :], prefix, empty=empty)

    if not field("Start testing: "):
        raise _Unsupported("Expected a complete CTest LastTest.log session")
    expect(_SEPARATOR)
    records = []
    names: set[str] = set()
    indices: set[int] = set()
    session_total: int | None = None
    while True:
        while cursor < len(lines) and lines[cursor] == "":
            cursor += 1
        if cursor < len(lines) and lines[cursor].startswith("End testing: "):
            field("End testing: ")
            if any(lines[cursor:]):
                raise ValueError("Unexpected trailing content after CTest session")
            return tuple(records)
        header = _HEADER.fullmatch(take())
        if header is None:
            raise ValueError("Expected an indexed CTest Testing header or session end")
        index, total, name = int(header[1]), int(header[2]), header[3]
        _literal(name, "test name")
        if '"' in name or name.strip() != name:
            raise _Unsupported(
                "Quoted or padded test names are ambiguous in this log dialect"
            )
        if name in names or index in indices:
            raise ValueError("Duplicate CTest test name or record index is ambiguous")
        if index > total or (session_total is not None and total != session_total):
            raise ValueError("Inconsistent CTest record numbering")
        session_total = total
        expect(f"{index}/{total} Test: {name}")
        arguments = _argv(field("Command: "))
        directory = field("Directory: ")
        if not Path(directory).is_absolute() or directory.strip() != directory:
            raise _Unsupported(
                "CTest Directory must be an unambiguous absolute host path"
            )
        start_time = field(f'"{name}" start time: ', empty=True)
        if bool(arguments) != bool(start_time):
            raise _Unsupported(
                "Command/start-time placeholders do not identify an unambiguous invocation"
            )
        expect("Output:")
        expect(_SEPARATOR)
        # All header-looking text here belongs to the test, never to CTest.
        while take() != "<end of output>":
            pass
        duration = re.fullmatch(r"Test time = +([0-9]+(?:\.[0-9]+)?) sec", take())
        if duration is None or not math.isfinite(float(duration[1])):
            raise ValueError("Malformed or ambiguous captured-output boundary/time")
        expect(_SEPARATOR)
        outcome_line = take()
        outcomes: dict[str, Outcome] = {
            "Test Passed.": "passed",
            "Test Failed.": "failed",
            "Test Not Run.": "notrun",
        }
        if outcome_line not in outcomes:
            raise _Unsupported("Unsupported CTest outcome/footer dialect")
        field(f'"{name}" end time: ')
        elapsed = field(f'"{name}" time elapsed: ')
        if not re.fullmatch(r"[0-9]{2,}:[0-5][0-9]:[0-5][0-9]", elapsed):
            raise ValueError("Malformed CTest elapsed time")
        expect(_SEPARATOR)
        records.append(
            CTestLogRecord(
                name,
                arguments,
                directory,
                outcomes[outcome_line] if arguments else "notrun",
                index,
                total,
            )
        )
        names.add(name)
        indices.add(index)
        if len(records) > MAX_RECORDS:
            raise ValueError(f"CTest log exceeds {MAX_RECORDS} record limit")


def parse_ctest_log(
    path: str | Path,
    adapter_version: str = _VERSION,
    *,
    producer: dict[str, Any],
) -> CTestLog:
    """Read command trace claims from one declared CTest 3.31.6 LastTest.log.

    Args:
        path: Local regular UTF-8 log, bounded to 10 MiB and 100,000 records.
        adapter_version: Exact supported parser contract, currently 1.0.0.
        producer: Caller declaration; only name=ctest/version=3.31.6 is supported.

    Returns:
        Complete records, or unavailable records with actionable limitations.
        Known complete raw reads retain their hash even when malformed. No
        overall test pass is inferred, including for an empty/zero-test trace.
    """
    metadata: dict[str, Any] = {}

    def result(
        usability: Usability, reason: str, records: tuple[CTestLogRecord, ...] = ()
    ) -> CTestLog:
        return CTestLog(
            records,
            usability,
            (*_LIMITS, reason),
            deepcopy(producer),
            adapter_version,
            **metadata,
        )

    if (
        adapter_version != _VERSION
        or not isinstance(producer, dict)
        or producer.get("name") != "ctest"
        or producer.get("version") != "3.31.6"
    ):
        return result(
            "unsupported",
            "This adapter supports only version 1.0.0 and declared producer CTest 3.31.6 (name=ctest).",
        )
    try:
        content = _read_log(Path(path))
    except OSError as error:
        return result("missing", f"CTest execution log is unavailable: {error}")
    except ValueError as error:
        return result("malformed", str(error))
    metadata.update(
        report_sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)
    )
    try:
        records = _records(content.decode("utf-8-sig"))
    except _Unsupported as error:
        return result("unsupported", str(error))
    except (UnicodeError, ValueError) as error:
        return result("malformed", str(error))
    return result(
        "usable",
        (
            "No execution records were present."
            if not records
            else "Commands were parsed only from structural CTest headers."
        ),
        records,
    )
