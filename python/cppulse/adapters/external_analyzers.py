"""Bounded imports of clang-tidy19.1.7 text and Cppcheck2.17.1 XML2.

No source/tool/network I/O occurs. Locations and tool versions are imported
claims; secondary notes/callstacks remain in original bytes, not confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Literal, Mapping, Sequence
import xml.etree.ElementTree as ET

from cppulse.adapters.gcc_diagnostics import (
    _scope_path,
    _file_identity,
    _Unsupported as _GccUnsupported,
)
from cppulse.errors import ContractError

MAX_REPORT_BYTES = 10 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 64
MAX_DIAGNOSTICS = 10_000
MAX_TEXT_LINES = 100_000
MAX_LINE_BYTES = 64 * 1024
MAX_SCOPE_FILES = 100_000
MAX_SCOPE_BYTES = 16 * 1024 * 1024
VERSION = "1.0.0"
_LIMITS = (
    "Imported diagnostic claims do not prove producer authenticity, completed analysis or a clean scan, including empty diagnostics.",
    "Repeated and overlapping imported occurrences are not independent confirmation and are not merged with native findings.",
    "Coordinates retain reported one-based tool positions; no source-content/display-column conversion is performed.",
)


@dataclass(frozen=True)
class ExternalDiagnostic:
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
class ExternalDiagnostics:
    producer_name: str
    producer_version: str
    usability: Literal["usable", "unsupported", "malformed", "missing"]
    diagnostics: tuple[ExternalDiagnostic, ...]
    limitations: tuple[str, ...]
    report_sha256: str | None
    size_bytes: int | None
    adapter: str
    adapter_version: str = VERSION
    origin: Literal["import"] = "import"


class _Unsupported(ValueError):
    pass


def _unicode(value: str, label: str):
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ContractError(label + " must be valid Unicode") from error


def _prepare(data, source_root, scope_files, producer, name, version, adapter):
    if not isinstance(source_root, str):
        raise ContractError("Source root must be a canonical POSIX string")
    _unicode(source_root, "Source root")
    root = PurePosixPath(source_root)
    if (
        not root.is_absolute()
        or root.as_posix() != source_root
        or ".." in root.parts
        or "\\" in source_root
        or "\0" in source_root
    ):
        raise ContractError("Source root must be canonical and absolute")
    if (
        not isinstance(scope_files, Sequence)
        or isinstance(scope_files, (str, bytes))
        or len(scope_files) > MAX_SCOPE_FILES
    ):
        raise ContractError("Source scope must be a bounded sequence of literal files")
    scope = set()
    metadata = 0
    for value in scope_files:
        path = _scope_path(value)
        metadata += len(path.encode())
        if metadata > MAX_SCOPE_BYTES:
            raise ContractError("Source scope exceeds metadata byte budget")
        if path in scope:
            raise ContractError("Duplicate source scope identity")
        scope.add(path)
    if producer is None:
        claim = {"name": name, "version": "unavailable"}
    elif isinstance(producer, Mapping):
        claim = dict(producer)
    else:
        raise ContractError("Producer must be a name/version mapping")
    if set(claim) != {"name", "version"} or any(
        not isinstance(value, str) or not value for value in claim.values()
    ):
        raise ContractError("Producer requires nonempty name/version strings")
    for value in claim.values():
        _unicode(value, "Producer claim")
    if data is not None and type(data) is not bytes:  # noqa: E721 -- exact raw bytes
        raise ContractError(
            "Report must be exact bytes or missing"
        )  # noqa: E721 -- immutable raw input
    sha = None if data is None else hashlib.sha256(data).hexdigest()
    size = None if data is None else len(data)

    def report(status, rows=(), reason=None, notes=()):
        return ExternalDiagnostics(
            claim["name"],
            claim["version"],
            status,
            tuple(rows),
            (*_LIMITS, *notes, *((reason,) if reason else ())),
            sha,
            size,
            adapter,
        )

    early = None
    if data is None or not data:
        early = report(
            "missing",
            reason="No diagnostic bytes were supplied; missing is not zero findings",
        )
    elif len(data) > MAX_REPORT_BYTES:
        early = report("unsupported", reason="Diagnostic report exceeds byte budget")
    elif claim != {"name": name, "version": version}:
        early = report(
            "unsupported", reason="Unsupported or unavailable declared producer/version"
        )
    return root, scope, report, early


def _position(value, *, zero=False):
    pattern = r"(?:0|[1-9][0-9]*)" if zero else r"[1-9][0-9]*"
    if (
        not isinstance(value, str)
        or len(value) > 19
        or re.fullmatch(pattern, value) is None
    ):
        raise _Unsupported("Location/count must be a bounded decimal integer")
    result = int(value)
    if result > 2**63 - 1:
        raise _Unsupported("Location/count exceeds signed64-bit profile")
    return result


def _secondary(value):
    if (
        not isinstance(value, str)
        or not value
        or "\0" in value
        or "\\" in value
        or PureWindowsPath(value).drive
    ):
        raise _Unsupported("Malformed secondary location")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as error:
        raise _Unsupported("Invalid Unicode secondary location") from error


def _diagnostic(namespace, producer, original, file, line, column, severity, message):
    if not original or original.strip() != original or not message:
        raise _Unsupported("Diagnostic identity/message is unavailable")
    namespaced = namespace + ":" + original
    if (
        re.fullmatch(r"[A-Za-z0-9_.:-]+", original) is None
        or len(namespaced) > 128
        or re.fullmatch(r"option-[0-9a-f]{64}", original)
    ):
        namespaced = (
            namespace + ":option-" + hashlib.sha256(original.encode()).hexdigest()
        )
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "producer": producer,
                "rule": original,
                "file": file,
                "line": line,
                "column": column,
                "message": message,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return ExternalDiagnostic(
        original,
        namespaced,
        producer["version"],
        file,
        line,
        column,
        severity,
        message,
        fingerprint,
    )


_PRIMARY = re.compile(
    r"(.+?):([1-9][0-9]*):([1-9][0-9]*): (warning|error|fatal error): (.+) \[([^\[\]\r\n]+)\]"
)
_NOTE = re.compile(r"(.+?):([1-9][0-9]*):([1-9][0-9]*): note: (.+)")
_EXCERPT = re.compile(r"[ \t]*(?:[0-9]+[ \t]*)?\|.*")
_COUNT = re.compile(r"([0-9]+) (?:warning|warnings|error|errors) generated\.")
_SUPPRESSED = re.compile(r"Suppressed ([0-9]+) warnings? \([^\r\n]+\)\.")
_GUIDANCE = "Use -header-filter=.* to display errors from all non-system headers. Use -system-headers to display errors from system headers as well."


def parse_clang_tidy_text(
    data: bytes | None,
    *,
    source_root: str,
    scope_files: Sequence[str],
    producer: Mapping[str, str] | None = None,
) -> ExternalDiagnostics:
    """Import primary text diagnostics; source excerpts/notes are never findings."""
    root, scope, report, early = _prepare(
        data,
        source_root,
        scope_files,
        producer,
        "clang-tidy",
        "19.1.7",
        "clang-tidy-text",
    )
    if early is not None:
        return early
    try:
        text = data.decode("utf-8-sig", errors="strict")
        if "\0" in text:
            raise ValueError("NUL in diagnostic text")
        text = text.replace("\r\n", "\n")
        if "\r" in text or not text.endswith("\n"):
            raise ValueError("Truncated or unsupported text line ending")
        if text.count("\n") > MAX_TEXT_LINES:
            raise _Unsupported("Diagnostic text line budget exceeded")
        records = []
        notes = False
        context = False
        for line in text.split("\n"):
            if len(line) > MAX_LINE_BYTES or len(line.encode()) > MAX_LINE_BYTES:
                raise _Unsupported("Diagnostic line byte budget exceeded")
            if not line.strip():
                continue
            primary = _PRIMARY.fullmatch(line)
            if primary:
                file = _file_identity(primary[1], root, scope)
                row = _diagnostic(
                    "clang-tidy",
                    {"name": "clang-tidy", "version": "19.1.7"},
                    primary[6],
                    file,
                    _position(primary[2]),
                    _position(primary[3]),
                    "warning" if primary[4] == "warning" else "error",
                    primary[5],
                )
                records.append(row)
                context = True
                if len(records) > MAX_DIAGNOSTICS:
                    raise _Unsupported("Diagnostic occurrence budget exceeded")
                continue
            note = _NOTE.fullmatch(line)
            if note:
                if not context:
                    raise _Unsupported(
                        "Secondary note lacks a preceding primary diagnostic"
                    )
                _secondary(note[1])
                _position(note[2])
                _position(note[3])
                notes = True
                continue
            count = _COUNT.fullmatch(line)
            if count:
                _position(count[1], zero=True)
                context = False
                continue
            suppressed = _SUPPRESSED.fullmatch(line)
            if suppressed:
                _position(suppressed[1], zero=True)
                context = False
                continue
            if line == _GUIDANCE:
                context = False
                continue
            if context and _EXCERPT.fullmatch(line):
                continue
            raise _Unsupported("Unknown/truncated clang-tidy text dialect")
        if not records:
            raise _Unsupported(
                "Summary/missing text does not establish located diagnostics"
            )
        return report(
            "usable",
            records,
            notes=(
                (
                    "Secondary notes remain only in original raw text; no new finding or confirmation is inferred.",
                )
                if notes
                else ()
            ),
        )
    except (UnicodeError, ValueError, _GccUnsupported) as error:
        return report(
            (
                "unsupported"
                if isinstance(error, (_Unsupported, _GccUnsupported))
                else "malformed"
            ),
            reason=str(error),
        )


def _xml(data):
    text = data.decode("utf-8-sig", errors="strict")
    if "\0" in text:
        raise ValueError("NUL in XML input")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise _Unsupported("XML DTD/entity declarations are forbidden")
    if re.search(r"<\?(?!xml(?:\s|\?>))", text, re.I):
        raise _Unsupported("Unreviewed XML processing instruction")
    declaration = re.match(r"<\?xml\s+(.*?)\?>", text, re.S)
    if declaration:
        attributes = re.findall(r"([A-Za-z]+)\s*=\s*([\"'])(.*?)\2", declaration[1])
        values = {name: value for name, _, value in attributes}
        if len(values) != len(attributes) or set(values) - {
            "version",
            "encoding",
            "standalone",
        }:
            raise _Unsupported("Ambiguous XML declaration")
        if (
            values.get("version") != "1.0"
            or values.get("encoding", "UTF-8").upper() not in {"UTF-8", "UTF8"}
            or values.get("standalone", "yes") not in {"yes", "no"}
        ):
            raise _Unsupported("Only XML1.0 UTF-8 reports are supported")
    parser = ET.XMLPullParser(events=("start", "end"))
    root = None
    depth = nodes = 0
    for start in range(0, len(text), 16384):
        parser.feed(text[start : start + 16384])
        for event, element in parser.read_events():
            if event == "start":
                if root is None:
                    root = element
                depth += 1
                nodes += 1
                if nodes > MAX_NODES or depth > MAX_DEPTH:
                    raise _Unsupported("XML node/depth budget exceeded")
            else:
                depth -= 1
    parser.close()
    if root is None:
        raise ValueError("Empty XML document")
    return root


def _space(value):
    if value is not None and value.strip():
        raise _Unsupported("Unexpected XML structural text")


def _location(element, root, scope, *, primary):
    if set(element.attrib) - {"file", "line", "column", "info"} or list(element):
        raise _Unsupported("Unsupported XML location structure")
    _space(element.text)
    _space(element.tail)
    file = element.get("file")
    _secondary(file)
    if primary:
        file = _file_identity(file, root, scope)
    line = _position(element.get("line"))
    column = None if element.get("column") is None else _position(element.get("column"))
    return file, line, column


def parse_cppcheck_xml(
    data: bytes | None,
    *,
    source_root: str,
    scope_files: Sequence[str],
    producer: Mapping[str, str] | None = None,
) -> ExternalDiagnostics:
    """Import XML2 error primary locations; callstack locations remain raw only."""
    root, scope, report, early = _prepare(
        data, source_root, scope_files, producer, "Cppcheck", "2.17.1", "cppcheck-xml"
    )
    if early is not None:
        return early
    try:
        document = _xml(data)
        if (
            document.tag != "results"
            or document.attrib != {"version": "2"}
            or [child.tag for child in document] != ["cppcheck", "errors"]
        ):
            raise _Unsupported("Unsupported Cppcheck XML2 root/tool/error inventory")
        _space(document.text)
        _space(document.tail)
        tool, errors = list(document)
        if tool.attrib != {"version": "2.17.1"} or list(tool) or errors.attrib:
            raise _Unsupported("Unknown embedded Cppcheck version/metadata")
        _space(tool.text)
        _space(tool.tail)
        _space(errors.text)
        _space(errors.tail)
        records = []
        secondary = False
        inconclusive = False
        severity = {
            "error": "error",
            "warning": "warning",
            "style": "info",
            "performance": "info",
            "portability": "info",
            "information": "info",
        }
        for error in errors:
            if error.tag != "error" or set(error.attrib) - {
                "id",
                "severity",
                "msg",
                "verbose",
                "cwe",
                "file0",
                "inconclusive",
            }:
                raise _Unsupported("Unknown Cppcheck error dialect")
            _space(error.text)
            _space(error.tail)
            if error.get("severity") not in severity:
                raise _Unsupported("Unknown Cppcheck diagnostic severity")
            if error.get("inconclusive") not in (None, "true", "false"):
                raise _Unsupported("Invalid Cppcheck inconclusive flag")
            inconclusive |= error.get("inconclusive") == "true"
            if error.get("cwe") is not None:
                _position(error.get("cwe"), zero=True)
            if error.get("file0"):
                _secondary(error.get("file0"))
            locations = []
            for child in error:
                if child.tag == "location":
                    locations.append(child)
                elif child.tag == "symbol":
                    if child.attrib or list(child) or not child.text:
                        raise _Unsupported("Unsupported Cppcheck symbol structure")
                    _space(child.tail)
                else:
                    raise _Unsupported("Unknown Cppcheck diagnostic child")
            if not locations:
                raise _Unsupported(
                    "Unlocated Cppcheck diagnostic cannot be assigned a file"
                )
            file, line, column = _location(locations[0], root, scope, primary=True)
            for location in locations[1:]:
                _location(location, root, scope, primary=False)
                secondary = True
            original = error.get("id")
            message = error.get("msg")
            if not original or not message:
                raise _Unsupported("Cppcheck rule/message is missing")
            records.append(
                _diagnostic(
                    "cppcheck",
                    {"name": "Cppcheck", "version": "2.17.1"},
                    original,
                    file,
                    line,
                    column,
                    severity[error.get("severity")],
                    message,
                )
            )
            if len(records) > MAX_DIAGNOSTICS:
                raise _Unsupported("Diagnostic occurrence budget exceeded")
        notes = []
        if secondary:
            notes.append(
                "Secondary callstack locations remain only in original XML, not extra findings or confirmation."
            )
        if inconclusive:
            notes.append(
                "Inconclusive tool claims remain inconclusive; import does not upgrade certainty."
            )
        return report("usable", records, notes=tuple(notes))
    except (UnicodeError, ValueError, ET.ParseError, _GccUnsupported) as error:
        return report(
            (
                "unsupported"
                if isinstance(error, (_Unsupported, _GccUnsupported))
                else "malformed"
            ),
            reason=str(error),
        )
