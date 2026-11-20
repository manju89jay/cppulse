"""Bounded JSON-schema projection of a retained native report.

This is a private prerequisite, not full native-contract validation. The latter
also includes maintenance cross-field checks, source/SDK/receipt bindings and
normalization. The original projection completion flags are never upgraded.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, BinaryIO

import jsonschema
from jsonschema.validators import extend

from cppulse.contracts import load_schema
from cppulse.contracts.json_projection import ProjectionLimits, ProjectionSelector
from cppulse.contracts.validation import _valid_datetime
from cppulse.errors import ContractError
from cppulse.json_projection import iter_json_projection
from cppulse.native_projection_store import (
    ProjectionStore,
    ProjectionStoreLimits,
    stage_projection,
)

_decode_json = json.loads
_ARRAY_PATHS = frozenset(
    {
        ("findings",),
        ("metadata", "analysis", "files"),
        ("metadata", "analysis", "native_metrics", "files"),
    }
)


@dataclass(frozen=True)
class _Layout:
    schema: dict[str, Any]
    selectors: tuple[ProjectionSelector, ...]
    paths: dict[tuple[str, ...], str]
    prefixes: dict[tuple[str, ...], dict[str, Any]]
    digest: str


def _layout() -> _Layout:
    schema = load_schema("findings", "prototype_v1")
    selectors: list[ProjectionSelector] = []
    paths: dict[tuple[str, ...], str] = {}
    prefixes: dict[tuple[str, ...], dict[str, Any]] = {}
    ancestors = {path[:n] for path in _ARRAY_PATHS for n in range(len(path))}

    def walk(path: tuple[str, ...], node: dict[str, Any]) -> None:
        if node.get("type") != "object" or not isinstance(node.get("properties"), dict):
            raise ContractError("Unsupported native projection object schema")
        if node.get("patternProperties") or isinstance(
            node.get("additionalProperties"), dict
        ):
            raise ContractError(
                "Native prefix key schemas need an explicit projection profile"
            )
        prefixes[path] = node
        for key, child in node["properties"].items():
            selected = path + (key,)
            if selected in ancestors:
                walk(selected, child)
                continue
            mode = "array" if selected in _ARRAY_PATHS else "value"
            if mode == "array" and (
                child.get("type") != "array"
                or child.get("uniqueItems")
                or not isinstance(child.get("items"), dict)
            ):
                raise ContractError("Unsupported native streamed-array schema")
            name = "native" + str(len(selectors))
            selectors.append(ProjectionSelector(name, selected, mode, False))
            paths[selected] = name

    walk((), schema)
    if len(selectors) > 32:
        raise ContractError("Native projection exceeds the declared selector profile")
    digest = hashlib.sha256(
        json.dumps(
            schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()
    return _Layout(schema, tuple(selectors), paths, prefixes, digest)


class _Array(Sequence[Any]):
    """Only individual bounded rows are decoded; arrays are never cached."""

    __slots__ = ("_store", "_name")

    def __init__(self, store: ProjectionStore, name: str) -> None:
        self._store, self._name = store, name

    @property
    def store(self) -> ProjectionStore:
        return self._store

    @property
    def name(self) -> str:
        return self._name

    def __len__(self) -> int:
        return self.store.record_count(self.name)

    def __getitem__(self, index: int) -> Any:
        if type(index) is not int:  # noqa: E721 -- bool/subclass is not an index
            raise TypeError("Native projection arrays require an integral index")
        count = len(self)
        if index < 0:
            index += count
        if not 0 <= index < count:
            raise IndexError("Native projection index outside the retained array")
        return _decode_json(self.store.get_raw(self.name, index))

    def __iter__(self) -> Iterator[Any]:
        for raw in self.store.iter_raw(self.name):
            yield _decode_json(raw)

    def __eq__(self, other: Any) -> bool:
        # Retained SDK proofs compare original JSON objects. Preserve that
        # equality contract while decoding at most one row from each array.
        if not isinstance(other, (list, _Array)):
            return NotImplemented
        if len(self) != len(other):
            return False
        return all(left == right for left, right in zip(self, other))

    def __repr__(self) -> str:
        return "<bounded native array " + self.name + ">"


class NativeReportReader:
    """A JSON-schema-checked view whose remaining native truth is unavailable."""

    __slots__ = ("_store", "_layout", "_document", "_completion", "_schema_digest")

    json_schema_checked = True
    native_contract_verified = False
    source_verified = False
    native_executed = False
    analysis_cache_eligible = False

    def __init__(
        self, store: ProjectionStore, layout: _Layout, document: dict[str, Any]
    ) -> None:
        self._store, self._layout = store, layout
        self._document = document
        self._completion = store.completion
        self._schema_digest = layout.digest

    @property
    def document(self) -> dict[str, Any]:
        """Copy bounded headers while retaining read-only lazy array bindings."""
        return _copy_headers(self._document)

    @property
    def completion(self):
        return self._completion

    @property
    def schema_digest(self) -> str:
        return self._schema_digest

    def _array(self, path: tuple[str, ...]) -> Iterator[dict[str, Any]]:
        name = self._layout.paths[path]
        # Preserve absence versus an explicitly present empty array in document;
        # both provide no rows to a caller that explicitly requests iteration.
        if name not in self.completion.present:
            self._store.record_count(name)  # also refuses closed reader access
            return
        yield from _Array(self._store, name)

    def iter_findings(self) -> Iterator[dict[str, Any]]:
        """Read finding objects in the original order, with bounded decoding."""
        yield from self._array(("findings",))

    def iter_analysis_files(self) -> Iterator[dict[str, Any]]:
        """Read each declared analysis-file descriptor, if present."""
        yield from self._array(("metadata", "analysis", "files"))

    def iter_metric_files(self) -> Iterator[dict[str, Any]]:
        """Read each complete per-file metric subtree, if present."""
        yield from self._array(("metadata", "analysis", "native_metrics", "files"))


def _put(document: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = document
    for key in path[:-1]:
        node = node.setdefault(key, {})
    node[path[-1]] = value


def _copy_headers(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _copy_headers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_copy_headers(item) for item in value]
    return value


@contextmanager
def open_native_report(
    binary_stream: BinaryIO,
    *,
    expected_sha256: str,
    expected_size: int,
    directory: Path,
    source_guard: Callable[[], None],
    projection_limits: ProjectionLimits = ProjectionLimits(),
    store_limits: ProjectionStoreLimits = ProjectionStoreLimits(),
) -> Iterator[NativeReportReader]:
    """Validate a native JSON schema without materializing all array rows.

    Args:
        binary_stream: Caller-owned pinned bytes; never closed here.
        expected_sha256: Original byte pin, not producer authentication.
        expected_size: Exact source length under the selected projection profile.
        directory: Caller-owned temporary-output parent, outside the input.
        source_guard: Required before/after material checks, including after schema.
        projection_limits: Explicit parser/value budgets; real large runs must opt
            into the appropriate document/record sizes, not bypass the limits.
        store_limits: Logical private-database and raw-row budgets.

    Yields:
        A checked JSON-schema view only after all items and closed prefixes pass.
        Maintenance/native semantics, source/execution/cache truth remain false.

    Raises:
        ContractError: Invalid declarations, closed fields, shape or local capacity.
    """
    if (
        type(projection_limits) is not ProjectionLimits
        or type(store_limits) is not ProjectionStoreLimits
    ):
        raise ContractError("Exact native reader resource profiles required")
    projection_limits.validate()
    store_limits.validate()
    if not callable(source_guard):
        raise ContractError("Native reader requires a source guard")

    def checked_guard() -> None:
        if source_guard() is not None:
            raise ContractError("Native reader source guard must return None")

    layout = _layout()
    audited: dict[tuple[str, ...], tuple[str, ...]] = {}

    def audit(path: tuple[str, ...], keys: tuple[str, ...]) -> None:
        node = layout.prefixes[path]
        actual = set(keys)
        if not set(node.get("required", [])) <= actual:
            raise ContractError(
                "Native object lacks required members at " + "/".join(path)
            )
        if (
            node.get("additionalProperties") is False
            and not actual <= node["properties"].keys()
        ):
            raise ContractError("Unknown closed native member at " + "/".join(path))
        audited[path] = keys

    events = iter_json_projection(
        binary_stream,
        layout.selectors,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        limits=projection_limits,
        object_audit=audit,
    )
    with stage_projection(
        events,
        selectors=layout.selectors,
        expected_sha256=expected_sha256,
        expected_size=expected_size,
        directory=directory,
        source_guard=checked_guard,
        limits=store_limits,
    ) as store:
        document: dict[str, Any] = {}
        for path in sorted(audited, key=len):
            if path:
                _put(document, path, {})
        for selector in layout.selectors:
            if selector.name not in store.completion.present:
                continue
            value = (
                _Array(store, selector.name)
                if selector.mode == "array"
                else _decode_json(store.raw_value(selector.name))
            )
            _put(document, selector.path, value)
        array_types = jsonschema.Draft7Validator.TYPE_CHECKER.redefine(
            "array", lambda checker, value: isinstance(value, (list, _Array))
        )
        validator_type = extend(jsonschema.Draft7Validator, type_checker=array_types)
        formats = jsonschema.FormatChecker()
        formats.checks("date-time", raises=(ValueError, TypeError))(_valid_datetime)
        try:
            validator_type(layout.schema, format_checker=formats).validate(document)
        except jsonschema.ValidationError as error:
            # Never stringify a potentially large failed metric/token subtree.
            pointer = "/".join(str(part) for part in error.absolute_path)[:512]
            raise ContractError(
                "Native JSON schema mismatch ("
                + str(error.validator)
                + ") at /"
                + pointer
            ) from None
        except (MemoryError, RecursionError):
            raise ContractError(
                "Native schema reader local capacity exhausted"
            ) from None
        checked_guard()
        yield NativeReportReader(store, layout, document)
        checked_guard()
