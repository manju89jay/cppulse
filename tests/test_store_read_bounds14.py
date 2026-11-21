"""Malformed sizes/growing files must fail without reading an unbounded body."""

import pytest

from cppulse import run_store as module
from cppulse.errors import IntegrityError
from cppulse.run_store import RunStore
from test_contracts_v2 import manifest_document, source_document
from test_run_store_v2 import publish


def tracked_reader(monkeypatch, path, *, append=False):
    original = module.os.fdopen
    reads = []
    delivered = []

    class Reader:
        def __init__(self, inner):
            self.inner = inner
            self.appended = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

        def fileno(self):
            return self.inner.fileno()

        def read(self, count=-1):
            reads.append(count)
            if append and not self.appended:
                with path.open("ab") as stream:
                    stream.write(b"x" * 4096)
                self.appended = True
            raw = self.inner.read(count)
            delivered.append(len(raw))
            return raw

    def selected(fd, mode="r", *args, **kwargs):
        target = module.os.readlink(f"/proc/self/fd/{fd}")
        inner = original(fd, mode, *args, **kwargs)
        return Reader(inner) if mode == "rb" and target == str(path) else inner

    monkeypatch.setattr(module.os, "fdopen", selected)
    return reads, delivered


@pytest.mark.parametrize("operation", ["read", "verify", "projection", "publish"])
def test_declared_artifact_growth_is_rejected_before_body_read(
    tmp_path, monkeypatch, operation
):
    store = RunStore(tmp_path / "store")
    if operation in ("read", "verify"):
        snapshot = publish(store, "original")
        path = snapshot.path / "artifacts/source.json"
        path.write_bytes(path.read_bytes() + b" " * 4096)
        reads, _ = tracked_reader(monkeypatch, path)
        with pytest.raises(IntegrityError):
            snapshot.read_bytes("source") if operation == "read" else snapshot.verify()
    else:
        with store.begin("candidate") as stage:
            entry = stage.write_json(
                "source.json", source_document(), contract="source"
            )
            document = manifest_document()
            document.update(run_id=stage.run_id, artifacts=[entry])
            projection = stage.project(document)
            path = stage.path / "source.json"
            path.write_bytes(path.read_bytes() + b" " * 4096)
            reads, _ = tracked_reader(monkeypatch, path)
            with pytest.raises(IntegrityError):
                (
                    projection.read_bytes("source")
                    if operation == "projection"
                    else stage.publish(document)
                )
    assert reads == [], "Registered size mismatch must fail before artifact body IO"


def test_opaque_declared_growth_is_rejected_before_hashing(tmp_path, monkeypatch):
    path = tmp_path / "opaque"
    path.write_bytes(b"too large")
    reads, _ = tracked_reader(monkeypatch, path)
    with pytest.raises(IntegrityError):
        module._check_file(
            path, {"path": "opaque", "size_bytes": 1, "sha256": "a" * 64}
        )
    assert reads == []


@pytest.mark.parametrize("streaming", [False, True])
def test_growth_after_stat_is_bounded_by_initial_size_and_one_probe(
    tmp_path, monkeypatch, streaming
):
    path = tmp_path / "growing"
    path.write_bytes(b"start")
    reads, delivered = tracked_reader(monkeypatch, path, append=True)
    retained = []
    with pytest.raises(IntegrityError):
        (
            module._stream_file(path, write=retained.append)
            if streaming
            else module._read(path)
        )
    assert reads and all(0 <= count <= 6 for count in reads)
    assert sum(delivered) <= 6
    if streaming:
        assert b"".join(retained) == b"start"


def test_empty_and_legacy_integral_size_descriptors_remain_supported(tmp_path):
    import hashlib

    path = tmp_path / "empty"
    path.write_bytes(b"")
    assert module._read(path, max_bytes=0) == b""
    module._check_file(
        path,
        {"path": "empty", "size_bytes": 0.0, "sha256": hashlib.sha256(b"").hexdigest()},
    )
