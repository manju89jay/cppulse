"""Exact bounded global duplication oracle and adversarial controls."""
from copy import deepcopy
from pathlib import Path
import random

import pytest

from cppulse.errors import ContractError
from cppulse.measurements import duplicate_token_counts
from cppulse.indexed_duplication import (
    DuplicationIndexLimits,
    indexed_duplicate_token_counts,
)


def frame(words):
    return {
        "complete": True,
        "availability": "measured",
        "records": [
            {
                "kind": "identifier",
                "spelling": w,
                "line": i + 1,
                "end_line": i + 1,
                "end_column": 2,
            }
            for i, w in enumerate(words)
        ],
    }


def check(tmp_path, rows):
    actual = indexed_duplicate_token_counts(iter(rows.items()), directory=tmp_path)
    assert actual == duplicate_token_counts(rows)
    assert list(actual) == list(rows)
    assert not list(tmp_path.iterdir())
    return actual


@pytest.mark.parametrize("length", [0, 1, 29, 30, 31, 35, 59, 60, 61, 90])
def test_exact_threshold_and_samefile(tmp_path, length):
    check(tmp_path, {"b": frame(["x"] * length), "a": frame(["x"] * length)})
    check(tmp_path, {"single": frame(["x"] * length)})


def test_literal_geometry_and_reverse(tmp_path):
    a = frame([str(i) for i in range(31)])
    b = deepcopy(a)
    for r in a["records"] + b["records"]:
        r.update(line=1, end_line=1000000, end_column=1)
    assert check(tmp_path, {"a": a, "b": b})["a"].lines == 999999
    b["records"][0]["kind"] = "literal"
    check(tmp_path, {"a": a, "b": b})
    b["records"][1]["spelling"] = "different"
    check(tmp_path, {"b": b, "a": a})


def test_random_oracle(tmp_path):
    rng = random.Random(421)
    for _ in range(30):
        seed = [str(rng.randrange(4)) for _ in range(35)]
        rows = {
            str(i): frame(
                (seed if rng.randrange(2) else ["q"] * rng.randrange(95))
                + seed[: rng.randrange(36)]
            )
            for i in range(rng.randrange(1, 5))
        }
        check(tmp_path, rows)


@pytest.mark.parametrize("position", [0, 1])
def test_unknown_peer(tmp_path, position):
    rows = {"a": frame(["x"] * 60), "b": frame(["x"] * 60)}
    rows[list(rows)[position]].update(complete=False, availability="partial")
    assert check(tmp_path, rows)["a"].tokens is None


def test_forced_fingerprint_collisions(tmp_path, monkeypatch):
    import cppulse.indexed_duplication as module

    monkeypatch.setattr(module, "_fingerprint", lambda ids: b"constant")
    rows = {
        "a": frame([str(i) for i in range(31)]),
        "b": frame([str(i + 100) for i in range(31)]),
        "c": frame([str(i) for i in range(31)]),
    }
    assert check(tmp_path, rows)["b"].tokens == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"minimum_tokens": 29},
        {"minimum_tokens": True},
        {"limits": DuplicationIndexLimits(max_files=True)},
        {"limits": DuplicationIndexLimits(max_database_bytes=1)},
    ],
)
def test_bad_profile_before_io(tmp_path, kwargs):
    with pytest.raises(ContractError):
        indexed_duplicate_token_counts([], directory=tmp_path, **kwargs)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "rows",
    [
        [("a", frame([])), ("a", frame([]))],
        [("a", {"complete": True, "availability": "measured", "records": [{}]})],
    ],
)
def test_bad_inputs(tmp_path, rows):
    with pytest.raises(ContractError):
        indexed_duplicate_token_counts(rows, directory=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "limit",
    [
        DuplicationIndexLimits(max_files=1),
        DuplicationIndexLimits(max_file_id_bytes_total=1),
        DuplicationIndexLimits(max_token_records_total=1),
        DuplicationIndexLimits(max_database_bytes=12288),
    ],
)
def test_budget(tmp_path, limit):
    with pytest.raises(ContractError):
        indexed_duplicate_token_counts(
            [("a", frame(["x"] * 60)), ("b", frame(["x"] * 60))],
            directory=tmp_path,
            limits=limit,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_generator_failure(tmp_path, error):
    def rows():
        yield "a", frame(["x"] * 60)
        raise error("tail")

    with pytest.raises(error):
        indexed_duplicate_token_counts(rows(), directory=tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.fixture(autouse=True)
def actual_module_origin():
    import cppulse.indexed_duplication as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[1] / "python/cppulse/indexed_duplication.py"
    )


def test_unknown_peer_still_enforces_token_budget(tmp_path):
    partial = frame(["x"] * 3)
    partial.update(complete=False, availability="partial")
    with pytest.raises(ContractError):
        indexed_duplicate_token_counts(
            [("a", partial)],
            directory=tmp_path,
            limits=DuplicationIndexLimits(max_token_records_total=2),
        )
    assert not list(tmp_path.iterdir())


def test_unknown_peer_still_rejects_duplicate_ids_and_bad_complete(tmp_path):
    partial = frame([])
    partial.update(complete=False, availability="unavailable")
    for rows in [
        [("a", partial), ("a", frame([]))],
        [
            ("a", partial),
            ("b", {"complete": True, "availability": "measured", "records": [{}]}),
        ],
    ]:
        with pytest.raises(ContractError):
            indexed_duplicate_token_counts(rows, directory=tmp_path)
    assert not list(tmp_path.iterdir())


def test_foreign_replacement_not_deleted(tmp_path):
    def streams():
        yield "a", frame(["x"] * 30)
        p = next(tmp_path.glob("duplication-*.sqlite"))
        p.rename(tmp_path / "retired.sqlite")
        p.write_bytes(b"foreign sentinel")

    from cppulse.errors import IntegrityError

    with pytest.raises(IntegrityError):
        indexed_duplicate_token_counts(streams(), directory=tmp_path)
    assert (
        next(tmp_path.glob("duplication-*.sqlite")).read_bytes() == b"foreign sentinel"
    )
    assert (tmp_path / "retired.sqlite").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("line", True),
        ("end_line", 0),
        ("end_column", 1.5),
        ("kind", None),
        ("spelling", "\ud800"),
    ],
)
def test_invalid_token_geometry_and_unicode(tmp_path, field, value):
    f = frame(["x"])
    f["records"][0][field] = value
    with pytest.raises(ContractError):
        indexed_duplicate_token_counts([("a", f)], directory=tmp_path)
    assert not list(tmp_path.iterdir())


def test_literal_ids_unicode_and_opaque_null(tmp_path):
    shared = frame(["λ\x00"] * 30)
    check(tmp_path, {"a\x00λ": shared, "b space": deepcopy(shared)})


def test_all_incomplete_empty_records(tmp_path):
    check(
        tmp_path,
        {
            "a": {"complete": False, "availability": "unavailable", "records": []},
            "b": frame([]),
        },
    )


def test_scope_empty_and_multiple_exact_groups(tmp_path):
    check(tmp_path, {})
    first = [str(i) for i in range(30)]
    second = [str(i + 100) for i in range(30)]
    check(tmp_path, {"a": frame(first + second), "b": frame(second), "c": frame(first)})


def test_empty_opaque_id_matches_reference(tmp_path):
    check(tmp_path, {"": frame(["x"] * 30), "other": frame(["x"] * 30)})


def test_late_incomplete_scope_hint_avoids_unneeded_index_budget(tmp_path):
    rows = [
        ("large-complete", frame([str(i) for i in range(600)])),
        ("late-partial", {"complete": False, "availability": "partial", "records": []}),
    ]
    limits = DuplicationIndexLimits(max_database_bytes=65536)
    with pytest.raises(ContractError, match="SQLite budget"):
        indexed_duplicate_token_counts(iter(rows), directory=tmp_path, limits=limits)
    result = indexed_duplicate_token_counts(
        iter(rows), directory=tmp_path, limits=limits, scope_complete=False
    )
    assert result == duplicate_token_counts(dict(rows))
    assert list(result) == ["large-complete", "late-partial"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "declaration,rows",
    [
        (False, []),
        (False, [("a", frame([]))]),
        (False, [("a", frame(["x"] * 30))]),
        (True, [("a", {"complete": False, "availability": "partial", "records": []})]),
    ],
)
def test_scope_hint_contradictions_refuse(tmp_path, declaration, rows):
    with pytest.raises(ContractError, match="scope completeness disagrees"):
        indexed_duplicate_token_counts(
            rows, directory=tmp_path, scope_complete=declaration
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("hint", [0, 1, "false", [], object()])
def test_scope_hint_type_before_any_io(tmp_path, hint):
    def rows():
        raise AssertionError("input consumed")
        yield

    with pytest.raises(ContractError):
        indexed_duplicate_token_counts(
            rows(), directory=tmp_path / "nonexistent", scope_complete=hint
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("hint", [None, True])
def test_complete_scope_hint_parity(tmp_path, hint):
    rows = {"a": frame(["x"] * 65), "b": frame([str(i) for i in range(31)])}
    actual = indexed_duplicate_token_counts(
        rows.items(), directory=tmp_path, scope_complete=hint
    )
    assert actual == duplicate_token_counts(rows)


@pytest.mark.parametrize(
    "case", ["malformed", "duplicate", "tokens", "ids", "cancel", "tail", "files"]
)
def test_false_scope_hint_does_not_hide_errors(tmp_path, case):
    partial = {"complete": False, "availability": "unavailable", "records": []}
    rows = [("a", frame(["x"])), ("partial", partial)]
    limits = DuplicationIndexLimits()
    if case == "malformed":
        rows[0][1]["records"][0]["end_line"] = 0
    elif case == "duplicate":
        rows[1] = ("a", partial)
    elif case == "tokens":
        limits = DuplicationIndexLimits(max_token_records_total=1)
        rows[0][1]["records"] *= 2
    elif case == "ids":
        limits = DuplicationIndexLimits(max_file_id_bytes_total=1)
    elif case == "files":
        limits = DuplicationIndexLimits(max_files=1)

    def source():
        yield from rows
        if case == "cancel":
            raise KeyboardInterrupt("cancel")
        if case == "tail":
            raise RuntimeError("tail")

    expected = (
        KeyboardInterrupt
        if case == "cancel"
        else RuntimeError
        if case == "tail"
        else ContractError
    )
    with pytest.raises(expected):
        indexed_duplicate_token_counts(
            source(), directory=tmp_path, limits=limits, scope_complete=False
        )
    assert not list(tmp_path.iterdir())


def test_false_scope_hint_checks_partial_record_budget(tmp_path):
    partial = frame(["x"] * 4)
    partial.update(complete=False, availability="partial")
    with pytest.raises(ContractError, match="token budget"):
        indexed_duplicate_token_counts(
            [("a", partial)],
            directory=tmp_path,
            scope_complete=False,
            limits=DuplicationIndexLimits(max_token_records_total=3),
        )
