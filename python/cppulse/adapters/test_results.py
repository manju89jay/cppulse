"""Read the declared CTest 3.31.6 JUnit dialect or a small generic import subset.

Adapter version 1.0.0 supports testsuite/testsuites containers, testcase outcomes
from failure/error/skipped children, and optional consistent integer counters.
Nested suites are aggregated; output/property metadata is not execution proof.
Unknown testcase statuses, contradictory outcomes and nonfinite durations fail
closed. Repeated cases retain every occurrence, including failed retries.

Limits are part of this adapter version: UTF-8 XML, 10 MiB, 100,000 elements and
depth 64. DTD/entity declarations are forbidden by parser callbacks, including
external references; standard escaped text and CDATA remain valid. No commands,
network operations or external XML resources are used.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Literal
from xml.etree.ElementTree import Element, TreeBuilder
from xml.parsers import expat

MAX_REPORT_BYTES = 10 * 1024 * 1024
MAX_XML_NODES = 100_000
MAX_XML_DEPTH = 64
_VERSION = "1.0.0"
_CTEST = {"name": "ctest", "version": "3.31.6"}
_COUNT_KEYS = ("total", "passed", "failed", "skipped", "errors")
_ORIGIN_LIMIT = (
    "Parsing a report observes imported outcome claims only; it does not prove "
    "execution, source revision, executable identity or report authenticity."
)
Outcome = Literal["passed", "failed", "skipped", "error"]
Usability = Literal["usable", "malformed", "unsupported", "missing"]


class _UnsupportedFormat(ValueError):
    """Valid XML uses semantics outside this adapter's declared dialect."""


@dataclass(frozen=True)
class TestCase:
    """One occurrence with an identity distinct from every repeated occurrence."""

    __test__ = False
    identity: str
    name: str
    classname: str
    status: Outcome
    duration_seconds: float | None


@dataclass(frozen=True)
class TestReport:
    """Observed report facts; unavailable counts are None rather than fake zero."""

    __test__ = False
    adapter: str
    adapter_version: str
    producer: dict[str, Any]
    status: Outcome
    usability: Usability
    total: int | None
    passed: int | None
    failed: int | None
    skipped: int | None
    errors: int | None
    cases: tuple[TestCase, ...]
    limitations: tuple[str, ...]
    origin: Literal["import"] = "import"
    report_sha256: str | None = None
    size_bytes: int | None = None

    @property
    def counts(self) -> dict[str, int] | None:
        """Return receipt-compatible counts, or None when no valid report exists."""
        if self.total is None:
            return None
        return {key: getattr(self, key) for key in _COUNT_KEYS}

    def as_dict(self) -> dict[str, Any]:
        """Return independent JSON-serializable facts and explicit import origin."""
        result = asdict(self)
        result["counts"] = self.counts
        return result


def _unavailable(
    adapter: str,
    version: str,
    producer: dict[str, Any],
    usability: Usability,
    reason: str,
    *,
    report_sha256: str | None = None,
    size_bytes: int | None = None,
) -> TestReport:
    return TestReport(
        adapter,
        version,
        deepcopy(producer),
        "error",
        usability,
        None,
        None,
        None,
        None,
        None,
        (),
        (_ORIGIN_LIMIT, reason),
        report_sha256=report_sha256,
        size_bytes=size_bytes,
    )


def _read_xml(path: Path) -> bytes:
    """Read bounded regular-file bytes without blocking on pipes or following links."""
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Test report must be a regular file")
        if info.st_size > MAX_REPORT_BYTES:
            raise ValueError(f"Test report exceeds the {MAX_REPORT_BYTES} byte limit")
        content = stream.read(MAX_REPORT_BYTES + 1)
    if len(content) > MAX_REPORT_BYTES:
        raise ValueError(f"Test report exceeds the {MAX_REPORT_BYTES} byte limit")
    return content


def _xml_tree(text: str) -> Element:
    builder = TreeBuilder()
    # Namespace processing must be enabled: otherwise default namespaces are
    # silently stripped into bare names and a foreign testcase can look native.
    parser = expat.ParserCreate(namespace_separator="}")
    depth = nodes = 0

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal depth, nodes
        if "}" in name or any("}" in key for key in attributes):
            raise _UnsupportedFormat("XML namespaces require another reviewed adapter")
        depth += 1
        nodes += 1
        if depth > MAX_XML_DEPTH:
            raise ValueError(f"XML depth exceeds {MAX_XML_DEPTH}")
        if nodes > MAX_XML_NODES:
            raise ValueError(f"XML node count exceeds {MAX_XML_NODES}")
        builder.start(name, attributes)

    def end(name: str) -> None:
        nonlocal depth
        builder.end(name)
        depth -= 1

    def forbidden(*args: Any) -> None:
        raise ValueError("DTD and entity declarations or references are forbidden")

    def declaration(version: str, encoding: str | None, standalone: int) -> None:
        if encoding and encoding.casefold().replace("-", "") != "utf8":
            raise ValueError("Only UTF-8 test reports are supported")

    def namespace(prefix: str | None, uri: str | None) -> None:
        if uri:
            raise _UnsupportedFormat("XML namespaces require another reviewed adapter")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = builder.data
    parser.XmlDeclHandler = declaration
    parser.StartNamespaceDeclHandler = namespace
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(text, True)
    return builder.close()


def _case_status(element: Element) -> Outcome:
    tags = {child.tag for child in element}
    if tags - {"failure", "error", "skipped", "system-out", "system-err", "properties"}:
        raise ValueError("Unsupported testcase child element")
    outcomes = tags & {"failure", "error", "skipped"}
    # Actual CTest 3.31.6 emits disabled cases without a <skipped/> child.
    # Its disabled counter is normalized into skipped, never executed/passed.
    if not outcomes and element.get("status") == "disabled":
        outcomes = {"skipped"}
    if len(outcomes) > 1:
        raise ValueError("Testcase contains contradictory outcome elements")
    for child in element:
        _check_metadata(child)
    status: Outcome = (
        "error"
        if "error" in outcomes
        else (
            "failed"
            if "failure" in outcomes
            else "skipped" if "skipped" in outcomes else "passed"
        )
    )
    allowed = {
        "passed": {None, "run", "passed"},
        "failed": {None, "run", "fail", "failed"},
        "error": {None, "run", "error"},
        "skipped": {None, "run", "notrun", "skipped", "disabled"},
    }
    if element.get("status") not in allowed[status]:
        raise ValueError("Testcase status is unknown or contradicts its outcome")
    return status


def _check_metadata(element: Element) -> None:
    if element.tag in {"system-out", "system-err"} and len(element):
        raise ValueError("Output metadata must contain text, not nested test elements")
    if element.tag == "properties" and any(
        item.tag != "property" or len(item) for item in element
    ):
        raise ValueError("Unsupported property element")


def _duration(element: Element) -> float | None:
    duration = float(element.attrib["time"]) if "time" in element.attrib else None
    if duration is not None and (not math.isfinite(duration) or duration < 0):
        raise ValueError("Reported duration must be finite and nonnegative")
    return duration


def _consistent_counts(element: Element, counts: dict[str, int], disabled: int) -> None:
    expected = {
        "tests": counts["total"],
        "passed": counts["passed"],
        "failures": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"]
        - (disabled if "disabled" in element.attrib else 0),
        "disabled": disabled,
    }
    for name, value in expected.items():
        declared = element.get(name)
        if declared is not None and (
            not re.fullmatch(r"[0-9]+", declared) or int(declared) != value
        ):
            raise ValueError(
                f"Inconsistent {name} count: declared {declared!r}, observed {value}"
            )


def _observed_cases(root: Element) -> tuple[tuple[TestCase, ...], bool, int]:
    cases: list[TestCase] = []
    occurrences: dict[str, int] = {}
    duplicate = False

    def suite(
        element: Element, ancestry: tuple[str, ...]
    ) -> tuple[dict[str, int], int]:
        nonlocal duplicate
        counts = dict.fromkeys(_COUNT_KEYS, 0)
        disabled = 0
        _duration(element)
        lineage = (*ancestry, element.get("name", ""))
        for child in element:
            if child.tag == "testsuite":
                nested, nested_disabled = suite(child, lineage)
                for key in counts:
                    counts[key] += nested[key]
                disabled += nested_disabled
            elif child.tag == "testcase" and element.tag == "testsuite":
                name, classname = child.get("name", ""), child.get("classname", "")
                if not name.strip():
                    raise ValueError("Testcase must have a nonempty name")
                status = _case_status(child)
                duration = _duration(child)
                key = json.dumps(
                    [lineage, classname, name],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                occurrence = occurrences.get(key, 0) + 1
                occurrences[key] = occurrence
                duplicate |= occurrence > 1
                identity = (
                    f"case-{hashlib.sha256(key.encode()).hexdigest()}-{occurrence}"
                )
                cases.append(TestCase(identity, name, classname, status, duration))
                counts["total"] += 1
                counts["errors" if status == "error" else status] += 1
                disabled += child.get("status") == "disabled"
            elif child.tag in {"properties", "system-out", "system-err"}:
                _check_metadata(child)
            else:
                raise ValueError(f"Unsupported {element.tag} child: {child.tag}")
        _consistent_counts(element, counts, disabled)
        return counts, disabled

    _, disabled = suite(root, ())
    return tuple(cases), duplicate, disabled


def parse_test_report(
    path: str | Path,
    adapter: str = "ctest-junit",
    adapter_version: str = _VERSION,
    *,
    producer: dict[str, Any],
) -> TestReport:
    """Parse one local report without executing or authenticating its producer.

    Args:
        path: Local regular UTF-8 XML report.
        adapter: ctest-junit (exact declared CTest 3.31.6) or generic-junit import.
        adapter_version: Supported parser contract version, currently 1.0.0.
        producer: Caller-declared producer metadata; not independently verified.

    Returns:
        Structured observed counts, or unavailable counts and actionable limits.
        Callers must omit receipt.tests when counts is None. Even usable facts
        require separately observed execution/source binding before verification.
    """
    if adapter not in {"ctest-junit", "generic-junit"} or adapter_version != _VERSION:
        return _unavailable(
            adapter,
            adapter_version,
            producer,
            "unsupported",
            "Supported adapters are ctest-junit and generic-junit at adapter version 1.0.0.",
        )
    if not isinstance(producer, dict) or any(
        not isinstance(producer.get(key), str) or not producer[key].strip()
        for key in ("name", "version")
    ):
        return _unavailable(
            adapter,
            adapter_version,
            producer,
            "unsupported",
            "Producer declaration requires nonempty name and version strings.",
        )
    if adapter == "ctest-junit" and any(
        producer.get(key) != value for key, value in _CTEST.items()
    ):
        return _unavailable(
            adapter,
            adapter_version,
            producer,
            "unsupported",
            "ctest-junit 1.0.0 supports only declared producer name=ctest, version=3.31.6; review another dialect or use generic-junit as an import.",
        )
    try:
        content = _read_xml(Path(path))
    except OSError as error:
        return _unavailable(
            adapter,
            adapter_version,
            producer,
            "missing",
            f"Test report is unavailable: {error}",
        )
    except ValueError as error:
        return _unavailable(adapter, adapter_version, producer, "malformed", str(error))
    # Bind both valid facts and malformed-but-observed input to these exact
    # bytes. Consumers can compare a frozen copied artifact's descriptor; a
    # later pathname read must never substitute different report bytes.
    report_sha256 = hashlib.sha256(content).hexdigest()
    observed_bytes = {"report_sha256": report_sha256, "size_bytes": len(content)}
    try:
        text = content.decode("utf-8-sig")
        root = _xml_tree(text)
        if root.tag not in {"testsuite", "testsuites"}:
            return _unavailable(
                adapter,
                adapter_version,
                producer,
                "unsupported",
                "Expected the supported testsuite/testsuites XML dialect; namespaced/custom formats require another reviewed adapter.",
                **observed_bytes,
            )
        cases, duplicate, disabled = _observed_cases(root)
    except _UnsupportedFormat as error:
        return _unavailable(
            adapter,
            adapter_version,
            producer,
            "unsupported",
            str(error),
            **observed_bytes,
        )
    except (UnicodeError, ValueError, expat.ExpatError) as error:
        return _unavailable(
            adapter,
            adapter_version,
            producer,
            "malformed",
            f"Malformed test report: {error}",
            **observed_bytes,
        )
    counts = {
        key: sum(case.status == key for case in cases)
        for key in ("passed", "failed", "skipped")
    }
    counts.update(
        total=len(cases), errors=sum(case.status == "error" for case in cases)
    )
    status: Outcome = (
        "error"
        if counts["errors"]
        else (
            "failed"
            if counts["failed"]
            else "passed" if counts["passed"] else "skipped"
        )
    )
    limitations = [_ORIGIN_LIMIT]
    if adapter == "generic-junit":
        limitations.append(
            "Generic JUnit import supports the documented structural subset only; it is not usable executed evidence by itself."
        )
    if duplicate:
        limitations.append(
            "Duplicate testcase identities retained as separate occurrence-qualified cases; failed retries were not discarded."
        )
    if disabled:
        limitations.append(
            f"{disabled} disabled test case(s) normalized into skipped; no execution is implied."
        )
    if counts["total"] == 0:
        limitations.append(
            "No test cases were reported; this is not a passed test run."
        )
    elif counts["skipped"]:
        limitations.append(f"{counts['skipped']} reported test case(s) were skipped.")
    return TestReport(
        adapter,
        adapter_version,
        deepcopy(producer),
        status,
        "usable",
        **counts,
        cases=cases,
        limitations=tuple(limitations),
        **observed_bytes,
    )
