"""Closed declarations and provisional output types for private JSON projections.

These types do not parse a stream, verify a report schema, normalize evidence or
authenticate a producer. Only a fully consumed producer can emit completion.
"""

# Closed wire profiles deliberately reject coercion and subclasses.
# ruff: noqa: E721

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal

from cppulse.contracts.json_stream import JsonStreamLimits, VERSION as BASE_VERSION
from cppulse.errors import ContractError

VERSION = "0.1.0"
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}")
_MAX_RECORDS = 10_000_000
_MAX_BYTES = 16 * 1024**3
_MAX_CAPTURE = 32 * 1024**2


def _name(value: object) -> None:
    if type(value) is not str or _NAME.fullmatch(value) is None:
        raise ContractError("Invalid canonical projection selector name")


def _count(value: object, maximum: int, label: str, *, minimum: int = 1) -> None:
    if (
        type(value) is not int or not minimum <= value <= maximum
    ):  # noqa: E721 -- exact finite budgets
        raise ContractError("Invalid projection integer bound: " + label)


@dataclass(frozen=True, slots=True)
class ProjectionSelector:
    """One literal object-key path, distinct from every other selected subtree."""

    name: str
    path: tuple[str, ...]
    mode: Literal["array", "value"]
    required: bool = True


@dataclass(frozen=True, slots=True)
class ProjectionLimits:
    """Reuse whole-parser caps and separately bound value/selector metadata."""

    json_limits: JsonStreamLimits = JsonStreamLimits()
    max_value_bytes: int = 64 * 1024
    max_selectors: int = 32
    max_selector_bytes: int = 16 * 1024

    def validate(self) -> None:
        if (
            type(self) is not ProjectionLimits
            or type(self.json_limits) is not JsonStreamLimits
        ):  # noqa: E721 -- closed profiles
            raise ContractError("Projection limits require the exact frozen profiles")
        self.json_limits.validate()
        _count(self.max_value_bytes, _MAX_CAPTURE, "max_value_bytes")
        _count(self.max_selectors, 32, "max_selectors")
        _count(self.max_selector_bytes, 64 * 1024, "max_selector_bytes")


def validate_selectors(
    selectors: list[ProjectionSelector] | tuple[ProjectionSelector, ...],
    limits: ProjectionLimits = ProjectionLimits(),
) -> tuple[ProjectionSelector, ...]:
    """Freeze and check bounded declarations before any source I/O or cache work."""
    if type(limits) is not ProjectionLimits:  # noqa: E721 -- no profile coercion
        raise ContractError("Projection limits require the frozen budget dataclass")
    limits.validate()
    if (
        type(selectors) not in (list, tuple)
        or not 1 <= len(selectors) <= limits.max_selectors
    ):
        raise ContractError(
            "Projection selectors require a nonempty bounded list/tuple"
        )
    frozen = tuple(selectors)
    names: set[str] = set()
    paths: list[tuple[str, ...]] = []
    metadata = 0
    for selector in frozen:
        if (
            type(selector) is not ProjectionSelector
        ):  # noqa: E721 -- frozen declaration type
            raise ContractError("Invalid projection selector declaration")
        _name(selector.name)
        if selector.name in names:
            raise ContractError("Duplicate projection selector name")
        names.add(selector.name)
        if (
            type(selector.path) is not tuple or not 1 <= len(selector.path) <= 32
        ):  # noqa: E721 -- immutable bounded path
            raise ContractError("Projection paths require1–32literal object keys")
        if (
            type(selector.mode) is not str
            or selector.mode not in ("array", "value")
            or type(selector.required) is not bool
        ):  # noqa: E721 -- exact declarations
            raise ContractError("Invalid projection selector mode/required flag")
        metadata += len(selector.name) + len(selector.mode) + 1
        for key in selector.path:
            if (
                type(key) is not str
                or not key
                or "\0" in key
                or len(key) > limits.json_limits.max_key_bytes
            ):  # noqa: E721 -- literal decoded keys
                raise ContractError("Invalid bounded projection path key")
            try:
                size = len(key.encode("utf-8", errors="strict"))
            except UnicodeError as error:
                raise ContractError("Projection path key is invalid Unicode") from error
            if size > limits.json_limits.max_key_bytes:
                raise ContractError("Projection path key exceeds UTF8 budget")
            metadata += size
            if metadata > limits.max_selector_bytes:
                raise ContractError("Projection selector metadata exceeds byte budget")
        for previous in paths:
            common = min(len(previous), len(selector.path))
            if previous[:common] == selector.path[:common]:
                raise ContractError("Projection selected paths overlap")
        paths.append(selector.path)
    return frozen


@dataclass(frozen=True, slots=True)
class ProjectionRecord:
    """One immutable provisional value; its existence does not prove completion."""

    selector: str
    ordinal: int | None
    raw: bytes
    kind: Literal["record"] = field(default="record", init=False)

    def __post_init__(self) -> None:
        if type(self) is not ProjectionRecord:
            raise ContractError("Projection records require the exact frozen class")
        _name(self.selector)
        if self.ordinal is not None:
            _count(self.ordinal, _MAX_RECORDS - 1, "ordinal", minimum=0)
        if (
            type(self.raw) is not bytes or not 1 <= len(self.raw) <= _MAX_CAPTURE
        ):  # noqa: E721 -- no mutable output buffer
            raise ContractError(
                "Projection records require bounded immutable JSON bytes"
            )


@dataclass(frozen=True, slots=True)
class ProjectionComplete:
    """Byte/structure completion only, after all selector and EOF checks pass."""

    sha256: str
    size_bytes: int
    present: tuple[str, ...]
    counts: tuple[tuple[str, int], ...]
    kind: Literal["complete"] = field(default="complete", init=False)
    version: str = field(default=VERSION, init=False)
    base_stream_version: str = field(default=BASE_VERSION, init=False)
    number_policy: str = field(default="finite-python-json", init=False)
    read_scope: str = field(default="structural_projection", init=False)
    schema_verified: bool = field(default=False, init=False)
    source_verified: bool = field(default=False, init=False)
    native_executed: bool = field(default=False, init=False)
    analysis_cache_eligible: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if type(self) is not ProjectionComplete:
            raise ContractError("Projection completion requires the exact frozen class")
        if (
            type(self.sha256) is not str
            or re.fullmatch(r"[a-f0-9]{64}", self.sha256) is None
        ):
            raise ContractError("Projection completion requires canonical SHA256")
        _count(self.size_bytes, _MAX_BYTES, "size_bytes", minimum=0)
        if (
            type(self.present) is not tuple or len(self.present) > 32
        ):  # noqa: E721 -- immutable bounded names
            raise ContractError("Invalid projection presence metadata")
        if (
            type(self.counts) is not tuple or not 1 <= len(self.counts) <= 32
        ):  # noqa: E721 -- immutable bounded counts
            raise ContractError("Invalid projection count metadata")
        names: set[str] = set()
        total = 0
        for row in self.counts:
            if (
                type(row) is not tuple or len(row) != 2
            ):  # noqa: E721 -- immutable exact pair
                raise ContractError("Invalid projection count pair")
            name, count = row
            _name(name)
            _count(count, _MAX_RECORDS, "record_count", minimum=0)
            if name in names:
                raise ContractError("Duplicate projection count selector")
            names.add(name)
            total += count
        if total > _MAX_RECORDS:
            raise ContractError("Projection global record count exceeds profile")
        seen: set[str] = set()
        for name in self.present:
            _name(name)
            if name in seen or name not in names:
                raise ContractError("Projection presence/count identities disagree")
            seen.add(name)
        if any(count and name not in seen for name, count in self.counts):
            raise ContractError("Absent projection selectors cannot have records")
