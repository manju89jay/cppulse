"""Bounded JSON producer controls; every yielded row remains provisional."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import io
import json

import pytest

from cppulse.contracts.json_stream import JsonStreamLimits
from cppulse.errors import ContractError, IntegrityError
from cppulse.json_stream import iter_json_array


def parse(
    data: bytes,
    *,
    member: str = "rows",
    limits: JsonStreamLimits = JsonStreamLimits(),
    **pins,
):
    return iter_json_array(
        io.BytesIO(data),
        member,
        expected_sha256=pins.get("expected_sha256", hashlib.sha256(data).hexdigest()),
        expected_size=pins.get("expected_size", len(data)),
        limits=limits,
    )


@pytest.mark.parametrize("chunk", [1, 2, 3, 7, 31])
def test_nested_values_and_utf8_escapes_cross_chunks_keep_number_lexemes(
    chunk: int,
) -> None:
    data = '{"metadata":[{"ignored":true}],"rows":[ {"café":"λ😀","quote":"\\"\\\\","pair":"\\ud834\\udd1e"}, -0,1.2300e+040,999999999999999999999999999999999999999999,null,true,false,[1,2] ],"end":0}'.encode()
    rows = list(parse(data, limits=replace(JsonStreamLimits(), chunk_bytes=chunk)))
    assert [json.loads(row) for row in rows[:2]] == [
        {"café": "λ😀", "quote": '"\\', "pair": "𝄞"},
        0,
    ]
    assert rows[1:7] == [
        b"-0",
        b"1.2300e+040",
        b"999999999999999999999999999999999999999999",
        b"null",
        b"true",
        b"false",
    ]
    assert json.loads(rows[-1]) == [1, 2]


@pytest.mark.parametrize(
    "data",
    [
        b"[]",
        b"{}",
        b'{"rows":1}',
        b'{"rows":[1,]}',
        b'{"rows":[01]}',
        b'{"rows":[1e]}',
        b'{"rows":[+1]}',
        b'{"rows":[NaN]}',
        b'{"rows":[Infinity]}',
        b'{"rows":["\\ud800"]}',
        b'{"rows":["\\udd00"]}',
        b'{"rows":["\xed\xa0\x80"]}',
        b'{"rows":["bad\\q"]}',
        b'{"rows":["raw\nline"]}',
        b'{"rows":[true false]}',
        b'{"rows":[] trailing}',
        b'{"rows":[]} []',
        b'{"rows":[',
        b'{"rows":[]',
        b'{"rows":[],"ignored":{"a":1,"\\u0061":2}}',
        b'{"rows":[],"\\u0072ows":[]}',
    ],
)
def test_malformed_or_incomplete_whole_document_never_finishes(data: bytes) -> None:
    with pytest.raises((ContractError, IntegrityError)):
        list(parse(data, limits=replace(JsonStreamLimits(), chunk_bytes=2)))


def test_rows_before_late_failure_are_only_provisional() -> None:
    data = b'{"rows":[1,1],"ignored":{"key":0,"key":1}}'
    rows = parse(data)
    assert next(rows) == b"1" and next(rows) == b"1"
    with pytest.raises(ContractError):
        next(rows)


@pytest.mark.parametrize(
    "pins", [{"expected_sha256": "0" * 64}, {"expected_size": 999}]
)
def test_integrity_mismatch_is_detected_even_after_rows(pins: dict) -> None:
    with pytest.raises(IntegrityError):
        list(parse(b'{"rows":[0]}', **pins))


@pytest.mark.parametrize(
    "field,data,bound",
    [
        ("max_token_bytes", b'{"rows":[123456]}', 6),
        ("max_item_bytes", b'{"rows":[[1,2]]}', 5),
        ("max_depth", b'{"rows":[{}]}', 3),
        ("max_object_members", b'{"rows":[],"x":0}', 2),
        ("max_live_key_bytes", b'{"rows":[{"x":0}]}', 5),
        ("max_key_bytes", b'{"rows":[]}', 4),
        ("max_array_items", b'{"rows":[[0],0]}', 3),
        ("max_records", b'{"rows":[0,0]}', 2),
    ],
)
def test_every_logical_budget_exact_boundary_and_one_over(field, data, bound):
    assert (
        list(parse(data, limits=replace(JsonStreamLimits(), **{field: bound})))
        or b"[]" in data
    )
    with pytest.raises(ContractError):
        list(parse(data, limits=replace(JsonStreamLimits(), **{field: bound - 1})))


@pytest.mark.parametrize(
    "data,field,bound",
    [
        (b'{"rows":[],"x":[1234]}', "max_token_bytes", 3),
        (b'{"rows":[],"x":[[1,2]]}', "max_item_bytes", 4),
        (b'{"rows":[],"x":[0,0]}', "max_array_items", 1),
        (b'{"rows":[],"x":{"long":0}}', "max_live_key_bytes", 8),
        (b'{"rows":[],"x":{"abcdef":0}}', "max_key_bytes", 5),
        (b'{"rows":[],"x":{"a":0,"b":0}}', "max_object_members", 1),
        (b'{"rows":[],"x":[[]]}', "max_depth", 2),
    ],
)
def test_ignored_metadata_cannot_evade_limits(data, field, bound):
    with pytest.raises(ContractError):
        list(parse(data, limits=replace(JsonStreamLimits(), **{field: bound})))


def test_key_budget_is_live_not_cumulative_and_whitespace_not_item_bytes():
    data = b'{"rows":[ { "x" : 0 }, { "x" : 1 } ]}'
    assert list(
        parse(
            data,
            limits=replace(JsonStreamLimits(), max_live_key_bytes=5, max_item_bytes=7),
        )
    ) == [b'{"x":0}', b'{"x":1}']


@pytest.mark.parametrize("name", list(JsonStreamLimits.__dataclass_fields__))
@pytest.mark.parametrize("value", [0, -1, True, 1.0])
def test_invalid_budget_values(name, value):
    with pytest.raises(ContractError):
        list(parse(b'{"rows":[]}', limits=replace(JsonStreamLimits(), **{name: value})))


@pytest.mark.parametrize(
    "pins",
    [
        {"expected_size": True},
        {"expected_size": 1.0},
        {"expected_size": -1},
        {"expected_sha256": "A" * 64},
        {"expected_sha256": None},
    ],
)
def test_invalid_identity_arguments(pins):
    with pytest.raises(ContractError):
        list(parse(b'{"rows":[]}', **pins))


@pytest.mark.parametrize("member", ["", "\x00", "\ud800", "x" * 1025, None])
def test_invalid_member_arguments(member):
    with pytest.raises(ContractError):
        list(parse(b'{"rows":[]}', member=member))


class TrackingStream(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.requests = []

    def read(self, size=-1):
        self.requests.append(size)
        return super().read(size)


def test_reads_bounded_and_caller_stream_not_closed_on_abandon_or_finish():
    data = b'{"rows":[0,1]}'
    stream = TrackingStream(data)
    rows = iter_json_array(
        stream,
        "rows",
        expected_sha256=hashlib.sha256(data).hexdigest(),
        expected_size=len(data),
        limits=replace(JsonStreamLimits(), chunk_bytes=2),
    )
    assert next(rows) == b"0"
    rows.close()
    assert not stream.closed
    stream.seek(0)
    assert list(
        iter_json_array(
            stream,
            "rows",
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
            limits=replace(JsonStreamLimits(), chunk_bytes=2),
        )
    ) == [b"0", b"1"]
    assert not stream.closed and max(stream.requests) <= 2 and min(stream.requests) >= 1


@pytest.mark.parametrize("mode", ["overreturn", "text", "error"])
def test_bad_binary_stream_contract(mode):
    class Bad:
        def read(self, size):
            if mode == "error":
                raise OSError("fixture read failure")
            return "x" if mode == "text" else b"x" * (size + 1)

    with pytest.raises(IntegrityError):
        list(iter_json_array(Bad(), "rows", expected_sha256="0" * 64, expected_size=10))


def test_one_extra_byte_is_rejected_and_short_stream_rejected():
    data = b'{"rows":[]}'
    for actual in [data + b"x", data[:-1]]:
        with pytest.raises((ContractError, IntegrityError)):
            list(
                iter_json_array(
                    TrackingStream(actual),
                    "rows",
                    expected_sha256=hashlib.sha256(data).hexdigest(),
                    expected_size=len(data),
                    limits=replace(JsonStreamLimits(), chunk_bytes=1),
                )
            )


def test_large_ignored_array_streams_without_materializing():
    import tracemalloc

    class Generated:
        def __init__(self):
            from itertools import chain, repeat

            self.parts = iter(
                chain([b'{"ignored":['], repeat(b"0,", 40000), [b'0],"rows":[7]}'])
            )
            self.pending = b""

        def read(self, size):
            while len(self.pending) < size:
                self.pending += next(self.parts, b"")
                if not self.pending or len(self.pending) >= size:
                    break
                # EOF must not loop after a final short piece.
                if self.pending.endswith(b"]}"):
                    break
            result, self.pending = self.pending[:size], self.pending[size:]
            return result

    data = b'{"ignored":[' + b"0," * 40000 + b'0],"rows":[7]}'
    stream = Generated()
    tracemalloc.start()
    try:
        assert list(
            iter_json_array(
                stream,
                "rows",
                expected_sha256=hashlib.sha256(data).hexdigest(),
                expected_size=len(data),
                limits=replace(JsonStreamLimits(), chunk_bytes=127, max_item_bytes=8),
            )
        ) == [b"7"]
        assert tracemalloc.get_traced_memory()[1] < 1024 * 1024
    finally:
        tracemalloc.stop()


def test_max_bytes_exact_and_over_and_unknown_limits():
    data = b'{"rows":[]}'
    assert (
        list(parse(data, limits=replace(JsonStreamLimits(), max_bytes=len(data)))) == []
    )
    with pytest.raises(ContractError):
        list(parse(data, limits=replace(JsonStreamLimits(), max_bytes=len(data) - 1)))
    with pytest.raises(ContractError):
        list(parse(data, limits=None))
    with pytest.raises(ContractError):
        list(parse(data, limits=replace(JsonStreamLimits(), max_depth=129)))


def test_decoded_surrogate_pair_and_literal_unicode_keys_are_duplicates():
    with pytest.raises(ContractError):
        list(parse('{"rows":[],"ignored":{"𝄞":0,"\\ud834\\udd1e":1}}'.encode()))


def test_empty_and_unicode_selected_member_and_differential_nested_values():
    values = [{}, [], {"a": [1, True, False, None, "λ", '\\"', {"𝄞": -1.25}]}, 0, ""]
    for ensure_ascii in [True, False]:
        for chunk in [1, 5, 256]:
            data = json.dumps(
                {"before": values, "é": values, "after": values},
                ensure_ascii=ensure_ascii,
            ).encode()
            result = list(
                parse(
                    data,
                    member="é",
                    limits=replace(JsonStreamLimits(), chunk_bytes=chunk),
                )
            )
            assert [json.loads(row) for row in result] == values
    assert list(parse(b'{"rows":[]}')) == []
