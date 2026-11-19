"""Bounded whole-document JSON projections with provisional records.

Completion certifies structural/number/byte checks only. Consumers still need a
transaction plus their own report schema, aggregate and provenance checks.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass, field
import json
import math
import re
from typing import BinaryIO, Callable, Iterator

from cppulse.contracts.json_projection import (
    ProjectionComplete,
    ProjectionLimits,
    ProjectionRecord,
    ProjectionSelector,
    validate_selectors,
)
from cppulse.errors import ContractError, IntegrityError
from cppulse.json_stream import _Parser, _Reader

ObjectAudit = Callable[[tuple[str, ...], tuple[str, ...]], None]


@dataclass
class _Node:
    children: dict[str, _Node] = field(default_factory=dict)
    selector: ProjectionSelector | None = None


class _ValueCapture:
    def __init__(self, maximum: int) -> None:
        self.data = bytearray()
        self.maximum = maximum

    def extend(self, raw: bytes) -> None:
        if len(self.data) + len(raw) > self.maximum:
            raise ContractError("Projection value exceeds compact byte budget")
        self.data.extend(raw)


class _ScalarCapture:
    def __init__(self, destination) -> None:
        self.data = bytearray()
        self.destination = destination

    def extend(self, raw: bytes) -> None:
        # Forward to the bounded outer capture BEFORE allocating another token
        # byte. The frozen scalar parser separately bounds every token.
        if self.destination is not None:
            self.destination.extend(raw)
        self.data.extend(raw)


class _ProjectionParser(_Parser):
    def __init__(
        self,
        reader: _Reader,
        selectors,
        limits: ProjectionLimits,
        object_audit: ObjectAudit | None = None,
    ) -> None:
        super().__init__(reader, "")
        self.selectors = selectors
        self.projection_limits = limits
        self.present: set[str] = set()
        self.counts = {selector.name: 0 for selector in selectors}
        self.object_audit = object_audit
        self.trie = _Node()
        for selector in selectors:
            node = self.trie
            for key in selector.path:
                node = node.children.setdefault(key, _Node())
            node.selector = selector

    def scalar(self, capture) -> None:
        token = _ScalarCapture(capture)
        super().scalar(token)
        try:
            value = json.loads(token.data)
        except (ValueError, UnicodeError, RecursionError) as error:
            raise ContractError(
                "Projection number is outside the bounded Python JSON profile"
            ) from error
        if isinstance(value, float) and not math.isfinite(value):
            raise ContractError("Projection numbers must remain finite in Python JSON")

    def chosen(
        self, selector: ProjectionSelector, depth: int
    ) -> Iterator[ProjectionRecord]:
        self.present.add(selector.name)
        if selector.mode == "array":
            if self.reader.peek() != 91:
                raise ContractError("Present projection array selector is not an array")
            for ordinal, raw in enumerate(self.selected(depth)):
                self.counts[selector.name] += 1
                yield ProjectionRecord(selector.name, ordinal, raw)
        else:
            self.records += 1
            if self.records > self.limits.max_records:
                raise ContractError("Projection global selected-record budget exceeded")
            capture = _ValueCapture(self.projection_limits.max_value_bytes)
            self.value(depth, capture)
            self.counts[selector.name] = 1
            yield ProjectionRecord(selector.name, None, bytes(capture.data))

    def object(
        self,
        depth: int,
        node: _Node,
        path: tuple[str, ...] = (),
    ) -> Iterator[ProjectionRecord]:
        if self.reader.peek() != 123:
            raise ContractError("Existing projection path prefixes must be objects")
        # The existing object-key limits also bound this ordered reference list.
        # Audit only trie prefixes: selected subtrees already retain their full
        # raw bodies, and ignored nested objects are not schema evidence.
        observed = [] if self.object_audit is not None else None
        with closing(self.object_keys(depth, None)) as keys:
            for key in keys:
                if observed is not None:
                    observed.append(key)
                selected = node.children.get(key)
                if selected is None:
                    self.value(depth + 1, None)
                elif selected.selector is not None:
                    yield from self.chosen(selected.selector, depth + 1)
                else:
                    yield from self.object(depth + 1, selected, path + (key,))
        if self.object_audit is not None:
            self.object_audit(path, tuple(observed))

    def project(self) -> Iterator[ProjectionRecord]:
        self.reader.space()
        yield from self.object(1, self.trie)
        self.reader.space()
        if self.reader.peek() is not None:
            raise ContractError("Trailing material after projection root object")
        if self.reader.read_bytes != self.reader.size:
            raise IntegrityError("Projection input size differs from its pin")
        if any(
            selector.required and selector.name not in self.present
            for selector in self.selectors
        ):
            raise ContractError("Required projection path is absent")


def iter_json_projection(
    binary_stream: BinaryIO,
    selectors: list[ProjectionSelector] | tuple[ProjectionSelector, ...],
    *,
    expected_sha256: str,
    expected_size: int,
    limits: ProjectionLimits = ProjectionLimits(),
    object_audit: ObjectAudit | None = None,
) -> Iterator[ProjectionRecord | ProjectionComplete]:
    """Eagerly validate declarations; lazily emit provisional records then EOF proof.

    The supplied stream remains caller-owned. Closing or abandoning iteration
    before completion cannot establish successful projection or publication.
    An optional observer receives completed trie-prefix objects and their
    ordered decoded keys, including ignored members and present empty objects.
    These observations are provisional too; an observer failure prevents the
    completion marker. The observer must not infer schema/source verification
    merely from receiving keys.
    """
    frozen = validate_selectors(selectors, limits)
    if object_audit is not None and not callable(object_audit):
        raise ContractError("Projection object audit must be callable")
    if (
        type(expected_sha256) is not str  # noqa: E721 -- exact identity type
        or re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None
    ):  # noqa: E721 -- closed identity type
        raise ContractError("Projection requires an exact lowercase SHA256 pin")
    if (
        type(expected_size) is not int  # noqa: E721 -- exact byte count
        or not 0 <= expected_size <= limits.json_limits.max_bytes
    ):  # noqa: E721 -- exact bounded size
        raise ContractError("Projection requires an exact bounded byte size")
    try:
        readable = callable(getattr(binary_stream, "read", None))
    except Exception as error:
        raise ContractError(
            "Projection stream read interface is unavailable"
        ) from error
    if not readable:
        raise ContractError("Projection requires a binary readable stream")

    def generate() -> Iterator[ProjectionRecord | ProjectionComplete]:
        reader = _Reader(binary_stream, expected_size, limits.json_limits)
        parser = _ProjectionParser(reader, frozen, limits, object_audit)
        try:
            yield from parser.project()
            if reader.digest.hexdigest() != expected_sha256:
                raise IntegrityError("Projection input SHA256 differs from its pin")
            yield ProjectionComplete(
                expected_sha256,
                expected_size,
                tuple(
                    selector.name
                    for selector in frozen
                    if selector.name in parser.present
                ),
                tuple(
                    (selector.name, parser.counts[selector.name]) for selector in frozen
                ),
            )
        except (RecursionError, MemoryError) as error:
            raise ContractError("Projection parser local capacity exhausted") from error

    return generate()
