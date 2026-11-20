"""Large opaque artifacts retain exact immutable bytes without whole-file copies."""

from pathlib import Path
import hashlib
import os
import tracemalloc
import pytest
from cppulse.errors import IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from test_contracts_v2 import manifest_document


def test_actual_large_copy_publish_and_verify_have_bounded_python_memory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "native-report.bin"
    chunk = bytes(range(256)) * 4096
    expected = hashlib.sha256()
    with source.open("wb") as output:
        for _ in range(24):
            output.write(chunk)
            expected.update(chunk)
    store = RunStore(tmp_path / "store")
    tracemalloc.start()
    try:
        with store.begin("large") as stage:
            descriptor = stage.copy_artifact("raw", source, "raw/native-report.bin")
            assert descriptor["size_bytes"] == 24 * 1024**2
            assert descriptor["sha256"] == expected.hexdigest()
            manifest = manifest_document()
            manifest.update(run_id="large", artifacts=stage.artifacts)
            snapshot = stage.publish(manifest)
        snapshot.verify()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024**2, peak
    assert source.stat().st_size == descriptor["size_bytes"]
    # Retained-file corruption is still checked through the streaming verifier.
    with (snapshot.path / descriptor["path"]).open("r+b") as output:
        output.write(b"changed")
    with pytest.raises(IntegrityError, match="integrity mismatch"):
        snapshot.verify()


def test_fifo_source_fails_promptly_without_registering_partial_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "fifo"
    os.mkfifo(source)
    with RunStore(tmp_path / "store").begin("fifo") as stage:
        with pytest.raises(IntegrityError, match="regular artifact"):
            stage.copy_artifact("raw", source, "raw.bin")
        assert stage.artifacts == []
        assert not (stage.path / "raw.bin").exists()
        ordinary = tmp_path / "ordinary"
        ordinary.write_bytes(b"actual")
        assert stage.copy_artifact("raw", ordinary, "raw.bin")["size_bytes"] == 6


def test_symlink_or_existing_destination_cannot_be_overwritten(tmp_path: Path) -> None:
    victim = tmp_path / "victim"
    victim.write_bytes(b"preserve")
    link = tmp_path / "link"
    link.symlink_to(victim)
    with RunStore(tmp_path / "store").begin("guard") as stage:
        with pytest.raises(IntegrityError):
            stage.copy_artifact("raw", link, "raw.bin")
        (stage.path / "raw.bin").symlink_to(victim)
        with pytest.raises(PublicationConflict):
            stage.copy_artifact("raw", victim, "raw.bin")
        assert victim.read_bytes() == b"preserve"
        assert stage.artifacts == []
