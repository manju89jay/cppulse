"""Private compressed projection store contract controls."""
import hashlib
import io
import sqlite3
import zlib

import pytest

from cppulse.contracts.json_projection import (
    ProjectionComplete,
    ProjectionRecord,
    ProjectionSelector,
)
from cppulse.errors import ContractError, IntegrityError
from cppulse.json_projection import iter_json_projection
from cppulse.native_projection_store import ProjectionStoreLimits, stage_projection

SHA = hashlib.sha256(b"{}").hexdigest()
SEL = (
    ProjectionSelector("rows", ("rows",), "array"),
    ProjectionSelector("value", ("value",), "value", False),
)


def marker(count=1, present=("rows",)):
    return ProjectionComplete(
        SHA, 2, present, (("rows", count), ("value", int("value" in present)))
    )


def stage(tmp_path, events, **kw):
    return stage_projection(
        events,
        selectors=SEL,
        expected_sha256=SHA,
        expected_size=2,
        directory=tmp_path,
        source_guard=lambda: None,
        **kw,
    )


def test_roundtrip(tmp_path):
    events = [
        ProjectionRecord("rows", 0, b'{"x":123456789012345678901}'),
        ProjectionRecord("value", None, b"null"),
        marker(present=("rows", "value")),
    ]
    with stage(tmp_path, events) as s:
        assert s.record_count("rows") == 1
        assert s.get_raw("rows", 0) == events[0].raw
        assert list(s.iter_raw("rows")) == [events[0].raw]
        assert s.raw_value("value") == b"null"
        p = s.path
        iterator = s.iter_raw("rows")
        assert not s.completion.analysis_cache_eligible
    assert not p.exists()
    with pytest.raises(ContractError):
        next(iterator)
    with pytest.raises(ContractError):
        s.raw_value("value")


def test_real_producer(tmp_path):
    raw = b'{"rows":[1,1,{"a":2}],"value":null,"ignored":[0]}'
    events = iter_json_projection(
        io.BytesIO(raw),
        SEL,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_size=len(raw),
    )
    with stage_projection(
        events,
        selectors=SEL,
        expected_sha256=hashlib.sha256(raw).hexdigest(),
        expected_size=len(raw),
        directory=tmp_path,
        source_guard=lambda: None,
    ) as s:
        assert list(s.iter_raw("rows")) == [b"1", b"1", b'{"a":2}']
        assert s.raw_value("value") == b"null"


@pytest.mark.parametrize(
    "events",
    [
        [],
        [ProjectionRecord("rows", 0, b"1")],
        [marker(0), marker(0)],
        [marker(0), ProjectionRecord("rows", 0, b"1")],
        [ProjectionRecord("rows", 1, b"1"), marker()],
        [ProjectionRecord("rows", None, b"1"), marker()],
        [ProjectionRecord("unknown", 0, b"1"), marker()],
        [
            ProjectionRecord("rows", 0, b"1"),
            ProjectionRecord("rows", 0, b"1"),
            marker(2),
        ],
        [ProjectionRecord("rows", 0, b"1"), marker(0)],
        [ProjectionComplete(SHA, 2, (), (("rows", 0), ("value", 0)))],
        [ProjectionComplete("0" * 64, 2, ("rows",), (("rows", 0), ("value", 0)))],
        [ProjectionComplete(SHA, 3, ("rows",), (("rows", 0), ("value", 0)))],
        [ProjectionComplete(SHA, 2, ("rows",), (("value", 0), ("rows", 0)))],
        [ProjectionRecord("value", 0, b"1"), marker(0, present=("rows", "value"))],
        [object()],
    ],
)
def test_reject_incomplete_protocol(tmp_path, events):
    with pytest.raises(ContractError):
        with stage(tmp_path, events):
            pytest.fail("published invalid events")
    assert list(tmp_path.iterdir()) == []


def test_optional_empty_and_absent(tmp_path):
    with stage(tmp_path, [marker(0)]) as s:
        assert s.record_count("rows") == 0 and s.raw_value("value") is None
        with pytest.raises(ContractError):
            s.get_raw("rows", 0)
        with pytest.raises(ContractError):
            s.iter_raw("value")


@pytest.mark.parametrize(
    "limit",
    [
        ProjectionStoreLimits(max_record_bytes=True),
        ProjectionStoreLimits(max_records=0),
        ProjectionStoreLimits(max_database_bytes=1),
    ],
)
def test_invalid_profile_before_io(tmp_path, limit):
    with pytest.raises(ContractError):
        with stage(tmp_path, [], limits=limit):
            pass
    assert list(tmp_path.iterdir()) == []


def test_record_and_count_budget(tmp_path):
    for limits, events in [
        (
            ProjectionStoreLimits(max_record_bytes=1),
            [ProjectionRecord("rows", 0, b"12"), marker()],
        ),
        (
            ProjectionStoreLimits(max_records=1),
            [
                ProjectionRecord("rows", 0, b"1"),
                ProjectionRecord("rows", 1, b"2"),
                marker(2),
            ],
        ),
    ]:
        with pytest.raises(ContractError):
            with stage(tmp_path, events, limits=limits):
                pass
    assert not list(tmp_path.iterdir())


def test_generator_and_guard_failures(tmp_path):
    def events():
        yield marker(0)
        raise RuntimeError("tail failure")

    with pytest.raises(RuntimeError):
        with stage(tmp_path, events()):
            pass
    calls = []

    def guard():
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("drift")

    with pytest.raises(RuntimeError):
        with stage_projection(
            [marker(0)],
            selectors=SEL,
            expected_sha256=SHA,
            expected_size=2,
            directory=tmp_path,
            source_guard=guard,
        ):
            pass
    assert len(calls) == 2 and not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "payload,rawlen,digest",
    [
        (b"bad", 1, hashlib.sha256(b"1").hexdigest()),
        (zlib.compress(b"1") + b"tail", 1, hashlib.sha256(b"1").hexdigest()),
        (zlib.compress(b"1")[:-1], 1, hashlib.sha256(b"1").hexdigest()),
        (zlib.compress(b"x" * 10000), 1, hashlib.sha256(b"1").hexdigest()),
        (zlib.compress(b"1"), 1, "0" * 64),
    ],
)
def test_corruption(tmp_path, payload, rawlen, digest):
    with stage(tmp_path, [ProjectionRecord("rows", 0, b"1"), marker()]) as s:
        db = sqlite3.connect(s.path)
        db.execute(
            "UPDATE records SET payload=?, rawlen=?, sha256=?",
            (payload, rawlen, digest),
        )
        db.commit()
        db.close()
        with pytest.raises(IntegrityError):
            s.get_raw("rows", 0)


def test_database_budget(tmp_path):
    import os

    with pytest.raises(ContractError):
        with stage(
            tmp_path,
            [ProjectionRecord("rows", 0, os.urandom(20000)), marker()],
            limits=ProjectionStoreLimits(max_database_bytes=12288),
        ):
            pass
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("phase", [0, 1, 2])
def test_cancellation_cleanup(tmp_path, phase):
    def events():
        if phase == 0:
            raise KeyboardInterrupt()
        yield ProjectionRecord("rows", 0, b"1")
        if phase == 1:
            raise KeyboardInterrupt()
        yield marker()
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        with stage(tmp_path, events()):
            pass
    assert not list(tmp_path.iterdir())


def test_invalid_guard_before_io(tmp_path):
    calls = []
    with pytest.raises(ContractError):
        with stage_projection(
            [],
            selectors=SEL,
            expected_sha256="invalid",
            expected_size=2,
            directory=tmp_path,
            source_guard=lambda: calls.append(1),
        ):
            pass
    assert calls == [] and not list(tmp_path.iterdir())
    with pytest.raises(ContractError):
        with stage_projection(
            [],
            selectors=SEL,
            expected_sha256=SHA,
            expected_size=2,
            directory=tmp_path,
            source_guard=lambda: True,
        ):
            pass
    assert not list(tmp_path.iterdir())


def test_foreign_replacement_not_cleaned(tmp_path):
    with stage(tmp_path, [ProjectionRecord("rows", 0, b"1"), marker()]) as s:
        retired = tmp_path / "retired.sqlite"
        s.path.rename(retired)
        s.path.write_bytes(b"foreign sentinel")
        with pytest.raises(IntegrityError):
            s.get_raw("rows", 0)
        foreign = s.path
    assert foreign.read_bytes() == b"foreign sentinel"
    assert retired.exists()


def test_flags_cannot_be_upgraded(tmp_path):
    m = marker(0)
    object.__setattr__(m, "schema_verified", True)
    with pytest.raises(ContractError):
        with stage(tmp_path, [m]):
            pass
    assert not list(tmp_path.iterdir())


def test_value_duplicate(tmp_path):
    with pytest.raises(ContractError):
        with stage(
            tmp_path,
            [
                ProjectionRecord("value", None, b"null"),
                ProjectionRecord("value", None, b"null"),
                marker(0, present=("rows", "value")),
            ],
        ):
            pass


def test_raw_reader_modes(tmp_path):
    with stage(tmp_path, [marker(0)]) as s:
        for fn in [
            lambda: s.raw_value("rows"),
            lambda: s.get_raw("rows", True),
            lambda: s.record_count("missing"),
            lambda: s.get_raw("value", 1),
        ]:
            with pytest.raises(ContractError):
                fn()


@pytest.fixture(autouse=True)
def exact_live_module_origin():
    from pathlib import Path
    import cppulse.native_projection_store as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[1]
        / "python/cppulse/native_projection_store.py"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("base_stream_version", "999"),
        ("version", "999"),
        ("kind", "record"),
        ("native_executed", True),
    ],
)
def test_marker_profile_closed(tmp_path, field, value):
    m = marker(0)
    object.__setattr__(m, field, value)
    with pytest.raises(ContractError):
        with stage(tmp_path, [m]):
            pass


def test_record_discriminator(tmp_path):
    r = ProjectionRecord("rows", 0, b"1")
    object.__setattr__(r, "kind", "complete")
    with pytest.raises(ContractError):
        with stage(tmp_path, [r, marker()]):
            pass


@pytest.mark.parametrize("events,directory", [(None, None), ([], "nul")])
def test_bad_arguments_before_guard(tmp_path, events, directory):
    from pathlib import Path

    calls = []
    with pytest.raises(ContractError):
        with stage_projection(
            events,
            selectors=SEL,
            expected_sha256=SHA,
            expected_size=2,
            directory=Path("bad\0path") if directory else tmp_path,
            source_guard=lambda: calls.append(1),
        ):
            pass
    assert not calls and not list(tmp_path.iterdir())


@pytest.mark.parametrize("mutation", ["extra", "reorder", "restored-mtime"])
def test_sealed_database_mutations(tmp_path, mutation):
    import os

    with stage(
        tmp_path,
        [
            ProjectionRecord("rows", 0, b"1"),
            ProjectionRecord("rows", 1, b"2"),
            marker(2),
        ],
    ) as s:
        original = s.path.stat()
        with sqlite3.connect(s.path) as db:
            if mutation == "extra":
                db.execute(
                    "INSERT INTO records VALUES(?,?,?,?,?)",
                    (
                        "rows",
                        2,
                        1,
                        hashlib.sha256(b"3").hexdigest(),
                        zlib.compress(b"3"),
                    ),
                )
            else:
                db.execute("UPDATE records SET ordinal=3 WHERE ordinal=0")
                db.execute("UPDATE records SET ordinal=0 WHERE ordinal=1")
                db.execute("UPDATE records SET ordinal=1 WHERE ordinal=3")
        if mutation == "restored-mtime":
            os.utime(s.path, ns=(original.st_atime_ns, original.st_mtime_ns))
        for read in [
            lambda: list(s.iter_raw("rows")),
            lambda: s.get_raw("rows", 0),
            lambda: s.record_count("rows"),
        ]:
            with pytest.raises(IntegrityError):
                read()


def test_miditeration_mutation_and_final_tail(tmp_path):
    with stage(
        tmp_path,
        [
            ProjectionRecord("rows", 0, b"1"),
            ProjectionRecord("rows", 1, b"2"),
            marker(2),
        ],
    ) as s:
        it = s.iter_raw("rows")
        assert next(it) == b"1"
        with sqlite3.connect(s.path) as db:
            db.execute("DELETE FROM records WHERE ordinal=1")
        with pytest.raises(IntegrityError):
            next(it)
    with stage(tmp_path, [ProjectionRecord("rows", 0, b"1"), marker()]) as s:
        it = s.iter_raw("rows")
        assert next(it) == b"1"
        with sqlite3.connect(s.path) as db:
            db.execute("DELETE FROM records")
        with pytest.raises(IntegrityError):
            next(it)
