"""Checked streaming access never bypasses snapshot or artifact byte pins."""

from dataclasses import replace
import os
import tracemalloc

import pytest

from cppulse.errors import IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from test_contracts_v2 import manifest_document


def make_snapshot(tmp_path, data=b"original artifact", *, name="retained"):
    store = RunStore(tmp_path / "store")
    source = tmp_path / "producer.bin"
    source.write_bytes(data)
    with store.begin(name) as stage:
        stage.copy_artifact("raw", source, "raw/artifact.bin")
        manifest = manifest_document()
        manifest.update(run_id=name, artifacts=stage.artifacts)
        snapshot = stage.publish(manifest)
    return store, snapshot


def test_stream_uses_pinned_artifact_without_whole_body_read(tmp_path, monkeypatch):
    _, snapshot = make_snapshot(tmp_path)
    monkeypatch.setattr(
        type(snapshot), "read_bytes", lambda *args: pytest.fail("eager read")
    )
    with snapshot.open_binary("raw") as stream:
        assert stream.read(8) == b"original"
        stream.seek(0)
        assert stream.read() == b"original artifact"
    assert stream.closed


@pytest.mark.parametrize(
    "change",
    ["pre-corrupt", "same-inode", "replace", "symlink", "manifest", "ancestor"],
)
def test_corruption_and_redirects_fail_without_a_successful_context(tmp_path, change):
    _, snapshot = make_snapshot(tmp_path)
    path = snapshot.path / "raw/artifact.bin"
    if change == "pre-corrupt":
        path.write_bytes(b"bad")
    with pytest.raises(IntegrityError):
        with snapshot.open_binary("raw") as stream:
            assert stream.read(1) == b"o"
            if change == "same-inode":
                old = path.stat()
                path.write_bytes(b"changed! artifact")
                os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
            elif change == "replace":
                replacement = path.with_suffix(".replacement")
                replacement.write_bytes(b"original artifact")
                replacement.replace(path)
            elif change == "symlink":
                path.unlink()
                path.symlink_to(tmp_path / "foreign")
            elif change == "manifest":
                (snapshot.path / "run_manifest.json").write_text("{}")
            elif change == "ancestor":
                parent = path.parent
                parent.rename(parent.with_name("moved"))
                parent.symlink_to(parent.with_name("moved"), target_is_directory=True)


def test_byte_limit_and_unknown_id_refuse_before_consumer(tmp_path):
    _, snapshot = make_snapshot(tmp_path)
    capped = replace(snapshot, _max_read_bytes=2)
    for reader, name in [(capped, "raw"), (snapshot, "absent")]:
        with pytest.raises(IntegrityError):
            with reader.open_binary(name):
                pytest.fail("unqualified bytes exposed")


def test_consumer_exception_propagates_and_descriptor_closes(tmp_path):
    _, snapshot = make_snapshot(tmp_path)
    with pytest.raises(RuntimeError, match="cancel"):
        with snapshot.open_binary("raw") as stream:
            raise RuntimeError("cancel")
    assert stream.closed


def test_staged_stream_is_bound_to_active_projection_and_stage_ownership(tmp_path):
    store = RunStore(tmp_path / "store")
    source = tmp_path / "producer.bin"
    source.write_bytes(b"actual")
    with store.begin("staged") as stage:
        stage.copy_artifact("raw", source, "raw.bin")
        manifest = manifest_document()
        manifest.update(run_id="staged", artifacts=stage.artifacts)
        projection = stage.project(manifest)
        with projection.open_binary("raw") as stream:
            assert stream.read() == b"actual"
        with pytest.raises(IntegrityError):
            with projection.open_binary("raw"):
                (stage.path / "raw.bin").write_bytes(b"corrupt")
    with pytest.raises((IntegrityError, PublicationConflict)):
        with projection.open_binary("raw"):
            pytest.fail("closed stage exposed")


def test_multimegabyte_stream_has_constant_python_allocation(tmp_path):
    _, snapshot = make_snapshot(tmp_path, b"x" * (6 * 1024**2))
    tracemalloc.start()
    try:
        with snapshot.open_binary("raw") as stream:
            count = 0
            while chunk := stream.read(32768):
                count += len(chunk)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert count == 6 * 1024**2 and peak < 4 * 1024**2
