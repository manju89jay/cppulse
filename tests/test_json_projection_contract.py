"""Closed bounded projection declarations; these tests do not run a producer."""

from dataclasses import FrozenInstanceError, replace

import pytest

from cppulse.contracts.json_projection import (
    ProjectionComplete,
    ProjectionLimits,
    ProjectionRecord,
    ProjectionSelector,
    validate_selectors,
)
from cppulse.contracts.json_stream import JsonStreamLimits
from cppulse.errors import ContractError


def selector(**changes):
    return replace(
        ProjectionSelector(
            "files", ("metadata", "analysis", "native_metrics", "files"), "array"
        ),
        **changes,
    )


def test_shared_ancestor_paths_are_distinct_and_declarations_detached():
    declarations = [
        selector(),
        ProjectionSelector(
            "version", ("metadata", "analysis", "native_metrics", "version"), "value"
        ),
    ]
    frozen = validate_selectors(declarations)
    declarations.clear()
    assert len(frozen) == 2 and isinstance(frozen, tuple)
    with pytest.raises(FrozenInstanceError):
        frozen[0].required = False


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": "x" * 65},
        {"name": "name\n"},
        {"name": "1name"},
        {"name": "é"},
        {"path": ()},
        {"path": ["findings"]},
        {"path": ("a",) * 33},
        {"path": ("",)},
        {"path": ("a\0b",)},
        {"path": ("é" * 513,)},
        {"path": (b"a",)},
        {"path": ("\ud800",)},
        {"mode": "rows"},
        {"mode": True},
        {"required": 1},
        {"required": None},
    ],
)
def test_invalid_selector_declarations(change):
    with pytest.raises(ContractError):
        validate_selectors([selector(**change)])


@pytest.mark.parametrize(
    "declarations",
    [
        [],
        (),
        None,
        iter([]),
        [object()],
        [
            ProjectionSelector("same", ("a",), "array"),
            ProjectionSelector("same", ("b",), "array"),
        ],
        [
            ProjectionSelector("a", ("a",), "array"),
            ProjectionSelector("b", ("a",), "value"),
        ],
        [
            ProjectionSelector("a", ("a",), "value"),
            ProjectionSelector("b", ("a", "b"), "array"),
        ],
    ],
)
def test_empty_unbounded_duplicate_and_overlapping_declarations(declarations):
    with pytest.raises(ContractError):
        validate_selectors(declarations)


def test_paths_are_literal_keys_not_dotted_or_pointer_expressions():
    items = [
        ProjectionSelector("a", ("a.b",), "value"),
        ProjectionSelector("b", ("a", "b"), "value"),
        ProjectionSelector("c", ("a/b", "*", "~1"), "array"),
    ]
    assert validate_selectors(items) == tuple(items)


@pytest.mark.parametrize(
    "name", ["max_value_bytes", "max_selectors", "max_selector_bytes"]
)
@pytest.mark.parametrize("value", [True, 1.0, 0, -1, 2**64])
def test_exact_finite_projection_budgets(name, value):
    with pytest.raises(ContractError):
        validate_selectors([selector()], replace(ProjectionLimits(), **{name: value}))


def test_json_budgets_must_use_exact_frozen_existing_class():
    class Derived(JsonStreamLimits):
        pass

    for profile in [None, {}, Derived(), replace(JsonStreamLimits(), max_records=True)]:
        with pytest.raises(ContractError):
            validate_selectors([selector()], ProjectionLimits(json_limits=profile))


def test_selector_count_and_utf8_metadata_budgets():
    with pytest.raises(ContractError):
        validate_selectors(
            [
                ProjectionSelector("x" + str(i), ("x" + str(i),), "value")
                for i in range(33)
            ]
        )
    with pytest.raises(ContractError):
        validate_selectors(
            [ProjectionSelector("x", ("é" * 100,), "value")],
            ProjectionLimits(max_selector_bytes=128),
        )
    with pytest.raises(ContractError):
        validate_selectors(
            [selector()], ProjectionLimits(max_selectors=1, max_selector_bytes=1)
        )


def test_provisional_record_and_completion_have_distinct_truth_boundaries():
    row = ProjectionRecord("files", 0, b'{"n":12345678901234567890}')
    assert row.kind == "record" and row.raw.endswith(b"90}")
    complete = ProjectionComplete(
        "a" * 64, 12, ("files",), (("files", 0), ("optional", 0))
    )
    assert (
        complete.kind == "complete" and complete.read_scope == "structural_projection"
    )
    assert not any(
        [
            complete.schema_verified,
            complete.source_verified,
            complete.native_executed,
            complete.analysis_cache_eligible,
        ]
    )
    with pytest.raises(FrozenInstanceError):
        complete.source_verified = True


@pytest.mark.parametrize(
    "change",
    [
        {"raw": bytearray(b"1")},
        {"ordinal": True},
        {"ordinal": -1},
        {"selector": "bad\n"},
    ],
)
def test_record_cannot_hide_mutable_bytes_or_invalid_identities(change):
    with pytest.raises(ContractError):
        ProjectionRecord(**{"selector": "rows", "ordinal": 0, "raw": b"1", **change})


@pytest.mark.parametrize(
    "change",
    [
        {"sha256": "A" * 64},
        {"size_bytes": True},
        {"size_bytes": -1},
        {"present": ["rows"]},
        {"present": ("absent",)},
        {"counts": (("rows", True),)},
        {"counts": (("rows", -1),)},
        {"counts": (("rows", 0), ("rows", 0))},
        {"present": ("rows", "rows")},
        {"present": (), "counts": (("rows", 1),)},
    ],
)
def test_completion_has_closed_detached_bounded_identities(change):
    with pytest.raises(ContractError):
        ProjectionComplete(
            **{
                "sha256": "a" * 64,
                "size_bytes": 12,
                "present": ("rows",),
                "counts": (("rows", 0),),
                **change,
            }
        )
