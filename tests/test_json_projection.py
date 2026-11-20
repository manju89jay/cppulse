"""Projection records are provisional until a single verified completion."""
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path

import pytest

from cppulse.contracts.json_projection import (
    ProjectionComplete,
    ProjectionLimits,
    ProjectionRecord,
    ProjectionSelector,
)
from cppulse.contracts.json_stream import JsonStreamLimits
from cppulse.errors import ContractError, IntegrityError
from cppulse.json_projection import iter_json_projection


def project(data, selectors, limits=ProjectionLimits(), **pins):
    return iter_json_projection(
        io.BytesIO(data),
        selectors,
        expected_sha256=pins.get("expected_sha256", hashlib.sha256(data).hexdigest()),
        expected_size=pins.get("expected_size", len(data)),
        limits=limits,
    )


def test_live_module_origin():
    import cppulse.json_projection as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[1] / "python/cppulse/json_projection.py"
    )


@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 127])
def test_shared_object_ancestors_raw_lexemes_and_completion_order(chunk):
    data = '{"ignored":{"array":[0,1]},"meta":{"count":1.2300e-02,"rows":[{"é":"λ😀"},-0,-0]},"tail":null}'.encode()
    selectors = [
        ProjectionSelector("rows", ("meta", "rows"), "array"),
        ProjectionSelector("count", ("meta", "count"), "value"),
        ProjectionSelector("absent", ("not.here",), "value", False),
    ]
    records = list(
        project(
            data,
            selectors,
            ProjectionLimits(
                json_limits=replace(JsonStreamLimits(), chunk_bytes=chunk)
            ),
        )
    )
    assert [(row.selector, row.ordinal, row.raw) for row in records[:-1]] == [
        ("count", None, b"1.2300e-02"),
        ("rows", 0, '{"é":"λ😀"}'.encode()),
        ("rows", 1, b"-0"),
        ("rows", 2, b"-0"),
    ]
    complete = records[-1]
    assert isinstance(complete, ProjectionComplete)
    assert complete.present == ("rows", "count") and complete.counts == (
        ("rows", 3),
        ("count", 1),
        ("absent", 0),
    )
    assert complete.sha256 == hashlib.sha256(
        data
    ).hexdigest() and complete.size_bytes == len(data)
    assert (
        not complete.schema_verified
        and not complete.source_verified
        and not complete.analysis_cache_eligible
    )


def test_ignored_overflow_prevents_completion_after_provisional_rows():
    rows = project(
        b'{"rows":[1],"ignored":1e999}',
        [ProjectionSelector("rows", ("rows",), "array")],
    )
    assert next(rows) == ProjectionRecord("rows", 0, b"1")
    with pytest.raises(ContractError):
        next(rows)


class NoRead:
    def read(self, size):
        pytest.fail("invalid argument caused source I/O")


@pytest.mark.parametrize(
    "selectors",
    [
        [],
        [
            ProjectionSelector("a", ("x",), "array"),
            ProjectionSelector("b", ("x", "y"), "value"),
        ],
        [
            ProjectionSelector("a", ("x",), "array"),
            ProjectionSelector("a", ("z",), "array"),
        ],
    ],
)
def test_selector_validation_is_eager_before_io(selectors):
    with pytest.raises(ContractError):
        iter_json_projection(
            NoRead(), selectors, expected_sha256="0" * 64, expected_size=1
        )


def test_optional_absent_null_and_empty_are_distinct():
    selectors = [
        ProjectionSelector("none", ("none",), "value"),
        ProjectionSelector("empty", ("empty",), "array"),
        ProjectionSelector("absent", ("absent",), "array", False),
    ]
    output = list(project(b'{"none":null,"empty":[]}', selectors))
    assert output[:-1] == [ProjectionRecord("none", None, b"null")]
    assert output[-1].present == ("none", "empty")
    assert output[-1].counts == (("none", 1), ("empty", 0), ("absent", 0))


@pytest.mark.parametrize("value", [b"null", b"[]", b'"string"', b"1", b"false"])
@pytest.mark.parametrize("required", [False, True])
def test_existing_ancestor_must_be_object_even_for_optional_path(value, required):
    with pytest.raises(ContractError):
        list(
            project(
                b'{"a":' + value + b"}",
                [ProjectionSelector("row", ("a", "b"), "value", required)],
            )
        )


@pytest.mark.parametrize("value", [b"null", b"{}", b"1", b'"x"'])
def test_optional_array_present_with_wrong_type_fails(value):
    with pytest.raises(ContractError):
        list(
            project(
                b'{"rows":' + value + b"}",
                [ProjectionSelector("rows", ("rows",), "array", False)],
            )
        )


def test_required_absence_fails_after_other_provisional_record():
    iterator = project(
        b'{"x":1}',
        [
            ProjectionSelector("x", ("x",), "value"),
            ProjectionSelector("missing", ("missing",), "array"),
        ],
    )
    assert next(iterator) == ProjectionRecord("x", None, b"1")
    with pytest.raises(ContractError):
        next(iterator)


def test_caller_selector_list_is_frozen_at_call_before_iteration():
    selectors = [ProjectionSelector("x", ("x",), "value")]
    iterator = project(b'{"x":1}', selectors)
    selectors[:] = [ProjectionSelector("other", ("other",), "value")]
    output = list(iterator)
    assert output[0].selector == "x" and output[-1].counts == (("x", 1),)


@pytest.mark.parametrize(
    "pins",
    [
        {"expected_size": True},
        {"expected_size": 1.0},
        {"expected_size": -1},
        {"expected_sha256": "A" * 64},
        {"expected_sha256": "0" * 64 + "\n"},
        {"expected_sha256": None},
    ],
)
def test_identity_arguments_validate_eagerly_without_source_read(pins):
    kwargs = {"expected_sha256": "0" * 64, "expected_size": 1, **pins}
    with pytest.raises(ContractError):
        iter_json_projection(
            NoRead(), [ProjectionSelector("x", ("x",), "value")], **kwargs
        )


def test_expected_byte_budget_rejects_before_read():
    limits = ProjectionLimits(json_limits=replace(JsonStreamLimits(), max_bytes=4))
    with pytest.raises(ContractError):
        iter_json_projection(
            NoRead(),
            [ProjectionSelector("x", ("x",), "value")],
            expected_sha256="0" * 64,
            expected_size=5,
            limits=limits,
        )


def test_non_readable_stream_is_eagerly_rejected():
    with pytest.raises(ContractError):
        iter_json_projection(
            None,
            [ProjectionSelector("x", ("x",), "value")],
            expected_sha256="0" * 64,
            expected_size=1,
        )


@pytest.mark.parametrize(
    "data",
    [
        b"[]",
        b"null",
        b'{"x":1,}',
        b'{"x":01}',
        b'{"x":1e}',
        b'{"x":NaN}',
        b'{"x":[true false]}',
        b'{"x":"\\ud800"}',
        b'{"x":1,"ignored":{"a":1,"\\u0061":2}}',
        b'{"x":1,"ignored":"\xff"}',
        b'{"x":1} trailing',
        b'{"x":1',
        b'{"x":1,"x":2}',
    ],
)
def test_every_ignored_or_selected_malformed_structure_prevents_complete(data):
    output = []
    with pytest.raises((ContractError, IntegrityError)):
        for row in project(
            data,
            [ProjectionSelector("x", ("x",), "value")],
            ProjectionLimits(json_limits=replace(JsonStreamLimits(), chunk_bytes=1)),
        ):
            output.append(row)
    assert not any(isinstance(row, ProjectionComplete) for row in output)


@pytest.mark.parametrize("value", [b"1e999", b"-1e999", b"9" * 5000])
@pytest.mark.parametrize("position", ["selected", "ignored", "ignored_array"])
def test_every_numeric_token_obeys_finite_bounded_python_policy(value, position):
    if position == "selected":
        data = b'{"x":' + value + b"}"
    elif position == "ignored":
        data = b'{"x":0,"ignored":' + value + b"}"
    else:
        data = b'{"x":0,"ignored":[' + value + b"]}"
    with pytest.raises(ContractError):
        list(project(data, [ProjectionSelector("x", ("x",), "value")]))


def test_finite_underflow_and_exact_lexemes_are_not_rewritten():
    data = b'{"x":[1e-999,-0,1.2300e+02,"1e999"]}'
    output = list(project(data, [ProjectionSelector("x", ("x",), "array")]))
    assert [row.raw for row in output[:-1]] == [
        b"1e-999",
        b"-0",
        b"1.2300e+02",
        b'"1e999"',
    ]


def test_literal_dotted_wildcard_and_surrogate_pair_keys_are_not_expressions():
    data = '{"a.b":{"*":["\\ud834\\udd1e"]},"a":{"b":{"*":[0]}}}'.encode()
    output = list(
        project(
            data,
            [ProjectionSelector("literal", ("a.b", "*"), "array")],
            ProjectionLimits(json_limits=replace(JsonStreamLimits(), chunk_bytes=1)),
        )
    )
    assert [json.loads(row.raw) for row in output[:-1]] == ["𝄞"]


@pytest.mark.parametrize("cap", [6, 7])
def test_value_capture_compact_byte_boundary(cap):
    data = b'{"meta":{ "a" : 1 }}'
    limits = replace(ProjectionLimits(), max_value_bytes=cap)
    iterator = project(data, [ProjectionSelector("v", ("meta",), "value")], limits)
    if cap == 6:
        with pytest.raises(ContractError):
            list(iterator)
    else:
        assert list(iterator)[0].raw == b'{"a":1}'


def test_value_capture_never_extends_past_cap(monkeypatch):
    import cppulse.json_projection as module

    original = module._ValueCapture.extend
    observed = []

    def checked(self, raw):
        try:
            return original(self, raw)
        finally:
            observed.append(len(self.data))

    monkeypatch.setattr(module._ValueCapture, "extend", checked)
    limits = ProjectionLimits(
        json_limits=replace(JsonStreamLimits(), chunk_bytes=16), max_value_bytes=7
    )
    with pytest.raises(ContractError):
        list(
            project(
                b'{"x":"' + b"a" * 1000 + b'"}',
                [ProjectionSelector("x", ("x",), "value")],
                limits,
            )
        )
    assert observed and max(observed) <= 7


def test_record_budget_is_global_across_values_and_both_array_selectors():
    selectors = [
        ProjectionSelector("v", ("v",), "value"),
        ProjectionSelector("a", ("a",), "array"),
        ProjectionSelector("b", ("b",), "array"),
    ]
    limits = ProjectionLimits(json_limits=replace(JsonStreamLimits(), max_records=3))
    iterator = project(b'{"v":null,"a":[1,2],"b":[3]}', selectors, limits)
    assert [next(iterator).selector for _ in range(3)] == ["v", "a", "a"]
    with pytest.raises(ContractError):
        next(iterator)


@pytest.mark.parametrize(
    "field,data,cap",
    [
        ("max_array_items", b'{"x":[],"ignored":[[0]]}', 1),
        ("max_item_bytes", b'{"x":[],"ignored":[[0,1]]}', 4),
        ("max_token_bytes", b'{"x":[],"ignored":123456789}', 8),
        ("max_depth", b'{"x":[],"ignored":{"nested":{}}}', 2),
        ("max_object_members", b'{"x":[],"ignored":{"a":0,"b":1}}', 1),
        ("max_live_key_bytes", b'{"x":[],"ignored":{"nested":{}}}', 8),
        ("max_key_bytes", b'{"x":[],"ignored":{"largekey":0}}', 7),
    ],
)
def test_ignored_content_retains_every_base_limit(field, data, cap):
    limits = ProjectionLimits(json_limits=replace(JsonStreamLimits(), **{field: cap}))
    with pytest.raises(ContractError):
        list(project(data, [ProjectionSelector("x", ("x",), "array")], limits))


def test_value_array_still_obeys_base_nested_item_and_global_array_caps():
    limits = ProjectionLimits(
        json_limits=replace(JsonStreamLimits(), max_item_bytes=4), max_value_bytes=100
    )
    with pytest.raises(ContractError):
        list(
            project(
                b'{"x":[[0,1]]}', [ProjectionSelector("x", ("x",), "value")], limits
            )
        )


def test_sha_failure_after_records_and_abandon_never_close_caller_stream():
    data = b'{"x":[1]}'
    stream = io.BytesIO(data)
    iterator = iter_json_projection(
        stream,
        [ProjectionSelector("x", ("x",), "array")],
        expected_sha256="0" * 64,
        expected_size=len(data),
    )
    assert next(iterator) == ProjectionRecord("x", 0, b"1")
    with pytest.raises(IntegrityError):
        next(iterator)
    assert not stream.closed
    stream.seek(0)
    iterator = iter_json_projection(
        stream,
        [ProjectionSelector("x", ("x",), "array")],
        expected_sha256=hashlib.sha256(data).hexdigest(),
        expected_size=len(data),
    )
    assert isinstance(next(iterator), ProjectionRecord)
    iterator.close()
    assert not stream.closed


@pytest.mark.parametrize("mode", ["overreturn", "text", "error"])
def test_stream_contract_violations_never_emit_completion(mode):
    class Bad:
        def read(self, size):
            if mode == "error":
                raise OSError("authored read error")
            return "x" if mode == "text" else b"x" * (size + 1)

    iterator = iter_json_projection(
        Bad(),
        [ProjectionSelector("x", ("x",), "value")],
        expected_sha256="0" * 64,
        expected_size=10,
    )
    with pytest.raises(IntegrityError):
        list(iterator)


def test_growth_and_truncation_detected_with_one_byte_eof_probe():
    data = b'{"x":[1]}'
    selectors = [ProjectionSelector("x", ("x",), "array")]
    for actual in [data + b" ", data[:-1]]:
        iterator = iter_json_projection(
            io.BytesIO(actual),
            selectors,
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
            limits=ProjectionLimits(
                json_limits=replace(JsonStreamLimits(), chunk_bytes=1)
            ),
        )
        with pytest.raises((ContractError, IntegrityError)):
            list(iterator)


def test_large_ignored_array_is_not_materialized():
    from itertools import chain, repeat
    import tracemalloc

    def pieces():
        return chain([b'{"ignored":['], repeat(b"0,", 20000), [b'0],"x":[]}'])

    digest = hashlib.sha256()
    size = 0
    for part in pieces():
        digest.update(part)
        size += len(part)

    class Generated:
        def __init__(self):
            self.parts = iter(pieces())
            self.pending = b""

        def read(self, size):
            while len(self.pending) < size:
                part = next(self.parts, None)
                if part is None:
                    break
                self.pending += part
            result, self.pending = self.pending[:size], self.pending[size:]
            return result

    stream = Generated()
    tracemalloc.start()
    try:
        output = list(
            iter_json_projection(
                stream,
                [ProjectionSelector("x", ("x",), "array")],
                expected_sha256=digest.hexdigest(),
                expected_size=size,
                limits=ProjectionLimits(
                    json_limits=replace(
                        JsonStreamLimits(), chunk_bytes=127, max_item_bytes=4
                    )
                ),
            )
        )
        assert len(output) == 1 and isinstance(output[0], ProjectionComplete)
        assert tracemalloc.get_traced_memory()[1] < 1024 * 1024
    finally:
        tracemalloc.stop()


def test_no_whole_container_is_passed_to_json_loads(monkeypatch):
    import cppulse.json_projection as module

    original = module.json.loads
    seen = []

    def token_only(raw, *args, **kwargs):
        encoded = raw.encode() if isinstance(raw, str) else bytes(raw)
        assert not encoded.lstrip().startswith((b"{", b"["))
        seen.append(len(encoded))
        return original(raw, *args, **kwargs)

    monkeypatch.setattr(module.json, "loads", token_only)
    data = b'{"ignored":{"wide":[0,1]},"x":{"items":[1,2],"label":"bounded"}}'
    output = list(project(data, [ProjectionSelector("x", ("x",), "value")]))
    assert seen and output[0].raw == b'{"items":[1,2],"label":"bounded"}'
    assert isinstance(output[-1], ProjectionComplete)


def test_failed_stream_interface_lookup_is_eager_typed_error():
    class Missing:
        @property
        def read(self):
            raise OSError("authored interface failure")

    with pytest.raises(ContractError):
        iter_json_projection(
            Missing(),
            [ProjectionSelector("x", ("x",), "value")],
            expected_sha256="0" * 64,
            expected_size=1,
        )


def test_value_record_after_array_cannot_escape_global_record_budget():
    selectors = [
        ProjectionSelector("a", ("a",), "array"),
        ProjectionSelector("v", ("v",), "value"),
    ]
    limits = ProjectionLimits(json_limits=replace(JsonStreamLimits(), max_records=1))
    iterator = project(b'{"a":[0],"v":null}', selectors, limits)
    assert next(iterator) == ProjectionRecord("a", 0, b"0")
    with pytest.raises(ContractError):
        next(iterator)


def test_valid_whole_structure_with_shorter_than_pinned_size_has_no_completion():
    data = b'{"x":0}'
    iterator = project(
        data, [ProjectionSelector("x", ("x",), "value")], expected_size=len(data) + 1
    )
    assert next(iterator) == ProjectionRecord("x", None, b"0")
    with pytest.raises(IntegrityError):
        next(iterator)
