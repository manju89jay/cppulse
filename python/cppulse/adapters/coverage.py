"""Bounded LCOV/Cobertura claim parsers; parsing never proves execution.

Version 1.0.0 supports LCOV 1.x count records and gcovr-style Cobertura 0.4 XML.
Line, branch and function units remain distinct. Cobertura branch ratios retain
per-line groups, and method line rates are not invented function-entry counts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
from xml.etree.ElementTree import Element, TreeBuilder
from xml.parsers import expat

MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_XML_NODES = 100_000
MAX_XML_DEPTH = 64
MAX_COUNTER = 2**64 - 1
LCOV_LINE_METHOD = "lcov-da-v1"
LCOV_BRANCH_METHOD = "lcov-brda-v1"
LCOV_FUNCTION_METHOD = "lcov-fnda-v1"
COBERTURA_LINE_METHOD = "cobertura-lines-v1"
COBERTURA_BRANCH_METHOD = "cobertura-condition-counts-v1"
_IMPORT = "Parsing observes imported coverage claims only; it does not establish source, instrumentation, binary execution or producer authenticity."


@dataclass(frozen=True)
class CoverageUnit:
    """One reported unit or explicit group, with an optional source location."""

    id: str
    covered: int
    total: int
    line: int | None = None


@dataclass(frozen=True)
class CoverageMeasurement:
    """Exact sums of disjoint units for one named measurement method."""

    kind: str
    method: str
    covered: int
    total: int
    units: tuple[CoverageUnit, ...]


@dataclass(frozen=True)
class CoverageFile:
    """Raw report filename; source hashing belongs to a checked normalizer."""

    file: str
    measurements: tuple[CoverageMeasurement, ...]
    source_sha256: str | None = None


@dataclass(frozen=True)
class CoverageReport:
    """Immutable parsed claims with exact consumed-byte identity, never a gate."""

    adapter: str
    adapter_version: str
    producer: dict[str, Any]
    usability: str
    files: tuple[CoverageFile, ...]
    sources: tuple[str, ...]
    limitations: tuple[str, ...]
    origin: str = "import"
    report_sha256: str | None = None
    size_bytes: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return independent JSON-compatible diagnostic data."""
        return asdict(self)


class _Unsupported(ValueError):
    pass


def _counter(value: str, label: str, *, positive: bool = False) -> int:
    if not re.fullmatch(r"[0-9]{1,20}", value):
        raise ValueError(f"{label} must be a nonnegative bounded integer")
    number = int(value)
    if number > MAX_COUNTER or (positive and number == 0):
        raise ValueError(f"{label} exceeds its supported count range")
    return number


def _identity(*parts: Any) -> str:
    return (
        "unit-"
        + hashlib.sha256(
            json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _measurement(
    kind: str, method: str, units: list[CoverageUnit]
) -> CoverageMeasurement:
    if len({unit.id for unit in units}) != len(units):
        raise ValueError("Duplicate measurement unit identity")
    if any(unit.covered < 0 or unit.total < unit.covered for unit in units):
        raise ValueError("Invalid measurement unit counts")
    return CoverageMeasurement(
        kind,
        method,
        sum(unit.covered for unit in units),
        sum(unit.total for unit in units),
        tuple(units),
    )


def _read(path: Path) -> bytes:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Coverage report must be a regular file")
        if before.st_size > MAX_REPORT_BYTES:
            raise _Unsupported(f"Coverage report exceeds {MAX_REPORT_BYTES} bytes")
        content = stream.read(MAX_REPORT_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(content) > MAX_REPORT_BYTES:
        raise _Unsupported("Coverage report exceeded the byte bound while reading")
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("Coverage report changed while being parsed")
    return content


def _name(value: str, label: str) -> str:
    if not value or any(
        ord(character) < 32 or 127 <= ord(character) <= 159 for character in value
    ):
        raise ValueError(f"{label} must be nonempty without control characters")
    return value


def _lcov(text: str) -> tuple[CoverageFile, ...]:
    files = []
    seen = set()
    active: dict[str, Any] | None = None
    for raw in text.splitlines():
        if not raw or raw.startswith("#"):
            continue
        if raw == "end_of_record":
            if active is None:
                raise ValueError("LCOV end_of_record has no source record")
            measurements = []
            lines, branches, functions, hits, summary = (
                active[key]
                for key in ("lines", "branches", "functions", "hits", "summary")
            )
            if lines or any(key in summary for key in ("LF", "LH")):
                measurements.append(
                    _measurement(
                        "line",
                        LCOV_LINE_METHOD,
                        [
                            CoverageUnit(
                                _identity("line", line), int(count > 0), 1, line
                            )
                            for line, count in sorted(lines.items())
                        ],
                    )
                )
            if branches or any(key in summary for key in ("BRF", "BRH")):
                measurements.append(
                    _measurement(
                        "branch",
                        LCOV_BRANCH_METHOD,
                        [
                            CoverageUnit(
                                _identity("branch", *key), int(count > 0), 1, key[0]
                            )
                            for key, count in sorted(branches.items())
                        ],
                    )
                )
            if functions or hits or any(key in summary for key in ("FNF", "FNH")):
                if set(functions) != set(hits):
                    raise ValueError(
                        "LCOV function definitions and exact hit records differ"
                    )
                measurements.append(
                    _measurement(
                        "function",
                        LCOV_FUNCTION_METHOD,
                        [
                            CoverageUnit(
                                _identity("function", line, name),
                                int(hits[name] > 0),
                                1,
                                line,
                            )
                            for name, line in sorted(functions.items())
                        ],
                    )
                )
            if not measurements:
                raise ValueError(
                    "LCOV source record has no explicit measurement inventory"
                )
            values = {row.kind: row for row in measurements}
            for key, kind, field in [
                ("LF", "line", "total"),
                ("LH", "line", "covered"),
                ("BRF", "branch", "total"),
                ("BRH", "branch", "covered"),
                ("FNF", "function", "total"),
                ("FNH", "function", "covered"),
            ]:
                if key in summary and summary[key] != getattr(values[kind], field):
                    raise ValueError(f"LCOV {key} disagrees with exact reported units")
            files.append(CoverageFile(active["file"], tuple(measurements)))
            active = None
            continue
        if ":" not in raw:
            raise ValueError("LCOV record is truncated or malformed")
        tag, value = raw.split(":", 1)
        if tag == "TN":
            continue
        if tag == "SF":
            if active is not None:
                raise ValueError("LCOV source record lacks end_of_record")
            name = _name(value, "LCOV source filename")
            if name in seen:
                raise _Unsupported(
                    "Repeated source/shard records require a reviewed merge; counts were not summed"
                )
            seen.add(name)
            active = {
                "file": name,
                "lines": {},
                "branches": {},
                "functions": {},
                "hits": {},
                "summary": {},
            }
            continue
        if tag not in {
            "VER",
            "DA",
            "BRDA",
            "FN",
            "FNDA",
            "LF",
            "LH",
            "BRF",
            "BRH",
            "FNF",
            "FNH",
        }:
            raise _Unsupported(f"Unsupported LCOV record {tag}")
        if active is None:
            raise ValueError("LCOV measurement appears outside a source record")
        if tag == "VER":
            continue  # Opaque source-version metadata is not source authentication.
        if tag == "DA":
            parts = value.split(",")
            if len(parts) not in {2, 3} or (len(parts) == 3 and not parts[2]):
                raise ValueError("Malformed LCOV DA record")
            line = _counter(parts[0], "line", positive=True)
            count = _counter(parts[1], "line hit count")
            if line in active["lines"]:
                raise ValueError("Duplicate LCOV line unit")
            active["lines"][line] = count
        elif tag == "BRDA":
            parts = value.split(",")
            if len(parts) != 4:
                raise ValueError("Malformed LCOV BRDA record")
            key = (
                _counter(parts[0], "branch line", positive=True),
                parts[1].startswith("e"),
                _counter(parts[1].removeprefix("e"), "block"),
                _counter(parts[2], "branch"),
            )
            count = 0 if parts[3] == "-" else _counter(parts[3], "branch hit count")
            if key in active["branches"]:
                raise ValueError("Duplicate LCOV branch unit")
            active["branches"][key] = count
        elif tag in {"FN", "FNDA"}:
            if "," not in value:
                raise ValueError("Malformed LCOV function record")
            number, name = value.split(",", 1)
            name = _name(name, "function name")
            selected = active["functions" if tag == "FN" else "hits"]
            if name in selected:
                raise ValueError("Duplicate or ambiguous LCOV function identity")
            selected[name] = _counter(
                number,
                "function line" if tag == "FN" else "function hit count",
                positive=tag == "FN",
            )
        else:
            if tag in active["summary"]:
                raise ValueError("Duplicate LCOV summary")
            active["summary"][tag] = _counter(value, tag)
        if (
            sum(len(active[key]) for key in ("lines", "branches", "functions", "hits"))
            > MAX_XML_NODES
        ):
            raise _Unsupported("LCOV unit bound exceeded")
    if active is not None:
        raise ValueError("LCOV source record is truncated before end_of_record")
    return tuple(files)


def _tree(text: str) -> Element:
    builder = TreeBuilder()
    parser = expat.ParserCreate(namespace_separator="}")
    depth = nodes = 0

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth, nodes
        depth += 1
        nodes += 1
        if depth > MAX_XML_DEPTH or nodes > MAX_XML_NODES:
            raise _Unsupported("Coverage XML node/depth bound exceeded")
        builder.start(name, attrs)

    def end(name: str) -> None:
        nonlocal depth
        builder.end(name)
        depth -= 1

    def namespace(*args: Any) -> None:
        raise _Unsupported("Coverage XML namespaces require another reviewed adapter")

    def forbidden(*args: Any) -> None:
        raise ValueError("Coverage XML entities/internal subsets are forbidden")

    def doctype(
        name: str, system: str | None, public: str | None, internal: int
    ) -> None:
        if (
            name != "coverage"
            or internal
            or public is not None
            or system
            not in {
                "http://cobertura.sourceforge.net/xml/coverage-04.dtd",
                "https://cobertura.sourceforge.net/xml/coverage-04.dtd",
                "https://github.com/cobertura/cobertura/blob/e5eea8679ebce047ec6ccdfdbf6cf2c14b376875/cobertura/src/site/htdocs/xml/coverage-04.dtd",
            }
        ):
            raise ValueError(
                "Unsupported Cobertura doctype; no external resources are loaded"
            )

    def declaration(version: str, encoding: str | None, standalone: int) -> None:
        if encoding and encoding.casefold().replace("-", "") != "utf8":
            raise _Unsupported("Coverage XML supports UTF-8 only")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = builder.data
    parser.StartNamespaceDeclHandler = namespace
    parser.StartDoctypeDeclHandler = doctype
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.XmlDeclHandler = declaration
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(text, True)
    return builder.close()


def _rate(value: str, covered: int, total: int, *, percent: bool = False) -> None:
    if len(value) > 128:
        raise ValueError("Coverage rate is too long")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Coverage rate is not a decimal") from error
    bound = 100 if percent else 1
    if (
        not number.is_finite()
        or not 0 <= number <= bound
        or abs(number.as_tuple().exponent) > 100
    ):
        raise ValueError("Coverage rate is outside its finite supported range")
    if total:
        actual = Fraction(covered * bound, total)
        if percent and number.as_tuple().exponent == 0:
            # gcovr 8.8 deliberately serializes int(percent), not round(percent).
            if not Fraction(number) <= actual < Fraction(number) + 1:
                raise ValueError("Coverage percentage contradicts exact unit counts")
            return
        tolerance = Fraction(1, 10**12)
        if percent:
            tolerance = max(tolerance, Fraction(10) ** number.as_tuple().exponent / 2)
        if abs(Fraction(number) - actual) > tolerance:
            raise ValueError("Coverage rate contradicts exact unit counts")


def _children(element: Element, allowed: set[str]) -> None:
    if any(child.tag not in allowed for child in element):
        raise _Unsupported(f"Unsupported {element.tag} child in Cobertura XML")


def _cobertura(text: str) -> tuple[tuple[CoverageFile, ...], tuple[str, ...]]:
    root = _tree(text)
    if root.tag != "coverage":
        raise _Unsupported("Expected supported Cobertura coverage root")
    _children(root, {"sources", "packages"})
    if len(root.findall("packages")) != 1 or len(root.findall("sources")) > 1:
        raise ValueError("Cobertura packages/source containers are ambiguous")
    sources = []
    source_container = root.find("sources")
    if source_container is not None:
        _children(source_container, {"source"})
        for source in source_container:
            if len(source):
                raise ValueError("Cobertura source must contain plain text")
            sources.append(_name(source.text or "", "Cobertura source root"))
    packages = root.find("packages")
    _children(packages, {"package"})
    files = []
    seen = set()
    for package in packages:
        package_start = len(files)
        _children(package, {"classes"})
        if len(package.findall("classes")) != 1:
            raise ValueError("Cobertura package classes are ambiguous")
        classes = package.find("classes")
        _children(classes, {"class"})
        for cls in classes:
            _children(cls, {"methods", "lines"})
            name = _name(cls.get("filename", ""), "Cobertura filename")
            if name in seen:
                raise _Unsupported(
                    "Repeated classes/shards for one source require a reviewed merge"
                )
            seen.add(name)
            if len(cls.findall("lines")) != 1 or len(cls.findall("methods")) > 1:
                raise ValueError("Cobertura class line/method containers are ambiguous")
            lines = cls.find("lines")
            _children(lines, {"line"})
            line_units = []
            branch_units = []
            numbers = set()
            for line in lines:
                _children(line, {"conditions"})
                number = _counter(line.get("number", ""), "line number", positive=True)
                if number in numbers:
                    raise ValueError("Duplicate Cobertura source line")
                numbers.add(number)
                hits = _counter(line.get("hits", ""), "line hit count")
                line_units.append(
                    CoverageUnit(_identity("line", number), int(hits > 0), 1, number)
                )
                branch = line.get("branch", "false")
                if branch not in {"true", "false"}:
                    raise ValueError("Unknown Cobertura branch flag")
                if branch == "true":
                    matched = re.fullmatch(
                        r"([^%]+)%\s*\(([0-9]+)/([0-9]+)\)",
                        line.get("condition-coverage", ""),
                    )
                    if not matched:
                        raise ValueError(
                            "Branch groups require exact covered/total counts"
                        )
                    covered = _counter(matched.group(2), "covered branches")
                    total = _counter(matched.group(3), "total branches")
                    if covered > total:
                        raise ValueError("Covered branches exceed total")
                    _rate(matched.group(1), covered, total, percent=True)
                    branch_units.append(
                        CoverageUnit(
                            _identity("branch-group", number), covered, total, number
                        )
                    )
                elif "condition-coverage" in line.attrib:
                    raise ValueError("Non-branch line declares branch counts")
                for conditions in line:
                    _children(conditions, {"condition"})
                    if branch != "true" or len(conditions) != 1 or len(line) != 1:
                        raise _Unsupported(
                            "Only a single aggregate Cobertura condition is supported"
                        )
                    if any(len(condition) for condition in conditions):
                        raise ValueError(
                            "Cobertura condition metadata contains nested elements"
                        )
                    condition = conditions[0]
                    if (
                        condition.get("number") != "0"
                        or condition.get("type") != "jump"
                    ):
                        raise _Unsupported("Unsupported Cobertura condition metadata")
                    percentage = condition.get("coverage", "")
                    if not percentage.endswith("%"):
                        raise ValueError("Condition coverage requires a percentage")
                    _rate(percentage[:-1], covered, total, percent=True)
            measurements = [
                _measurement("line", COBERTURA_LINE_METHOD, line_units),
                _measurement("branch", COBERTURA_BRANCH_METHOD, branch_units),
            ]
            for kind in ("line", "branch"):
                if kind + "-rate" in cls.attrib:
                    measurement = next(row for row in measurements if row.kind == kind)
                    _rate(
                        cls.get(kind + "-rate"), measurement.covered, measurement.total
                    )
            # Method line/branch rates are not direct function-entry counts.
            for methods in cls.findall("methods"):
                _children(methods, {"method"})
                primary_lines = {line.get("number"): line for line in lines}
                for method in methods:
                    _children(method, {"lines"})
                    if len(method) != 1:
                        raise ValueError("Cobertura method lines are ambiguous")
                    _children(method[0], {"line"})
                    for line in method[0]:
                        primary = primary_lines.get(line.get("number"))
                        if primary is None or line.attrib != primary.attrib:
                            raise _Unsupported(
                                "Method-only or inconsistent lines need another adapter"
                            )
                        if [
                            (
                                child.tag,
                                child.attrib,
                                [(c.tag, c.attrib) for c in child],
                            )
                            for child in line
                        ] != [
                            (
                                child.tag,
                                child.attrib,
                                [(c.tag, c.attrib) for c in child],
                            )
                            for child in primary
                        ]:
                            raise ValueError(
                                "Method conditions contradict class line facts"
                            )
            files.append(CoverageFile(name, tuple(measurements)))
        for kind in ("line", "branch"):
            selected = [
                row
                for file in files[package_start:]
                for row in file.measurements
                if row.kind == kind
            ]
            if kind + "-rate" in package.attrib:
                _rate(
                    package.get(kind + "-rate"),
                    sum(row.covered for row in selected),
                    sum(row.total for row in selected),
                )
    for kind, valid, covered in [
        ("line", "lines-valid", "lines-covered"),
        ("branch", "branches-valid", "branches-covered"),
    ]:
        total = sum(
            row.total for file in files for row in file.measurements if row.kind == kind
        )
        hit = sum(
            row.covered
            for file in files
            for row in file.measurements
            if row.kind == kind
        )
        if valid in root.attrib and _counter(root.get(valid), valid) != total:
            raise ValueError("Cobertura root denominator contradicts exact units")
        if covered in root.attrib and _counter(root.get(covered), covered) != hit:
            raise ValueError("Cobertura root covered count contradicts exact units")
        if kind + "-rate" in root.attrib:
            _rate(root.get(kind + "-rate"), hit, total)
    return tuple(files), tuple(sources)


def parse_coverage_report(
    path: str | Path,
    adapter: str,
    adapter_version: str = "1.0.0",
    *,
    producer: dict[str, Any],
) -> CoverageReport:
    """Parse exact bounded report bytes as import claims without running tools."""
    identity: dict[str, Any] = {}

    def result(
        usability: str,
        reason: str,
        files: tuple[CoverageFile, ...] = (),
        sources: tuple[str, ...] = (),
    ) -> CoverageReport:
        limits = [_IMPORT, reason]
        if adapter == "cobertura":
            limits.append(
                "Function-entry coverage is unavailable in this Cobertura adapter; method/line rates are not function call counts."
            )
        if usability == "usable" and not files:
            limits.append(
                "No coverage file units were reported; no success percentage is inferred."
            )
        return CoverageReport(
            adapter,
            adapter_version,
            deepcopy(producer),
            usability,
            files,
            sources,
            tuple(limits),
            **identity,
        )

    if adapter not in {"lcov", "cobertura"} or adapter_version != "1.0.0":
        return result("unsupported", "Unsupported coverage adapter or version")
    if not isinstance(producer, dict) or any(
        not isinstance(producer.get(key), str) or not producer[key].strip()
        for key in ("name", "version")
    ):
        return result(
            "unsupported", "Coverage producer declaration needs name/version strings"
        )
    try:
        content = _read(Path(path))
    except OSError as error:
        return result("missing", "Coverage report is unavailable: " + str(error))
    except _Unsupported as error:
        return result("unsupported", str(error))
    except ValueError as error:
        return result("malformed", str(error))
    identity.update(
        report_sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)
    )
    try:
        text = content.decode("utf-8-sig")
        if adapter == "lcov":
            files, sources = _lcov(text), ()
        else:
            files, sources = _cobertura(text)
    except _Unsupported as error:
        return result("unsupported", str(error))
    except (ValueError, UnicodeError, expat.ExpatError) as error:
        return result("malformed", str(error))
    return result(
        "usable",
        "Exact unit counts retained separately by measurement kind; no report shards were merged.",
        files,
        sources,
    )
