"""Existing-store reads neither create directories nor acquire publication slots."""

from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import stat

import pytest

from cppulse.errors import IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from test_run_store_v2 import publish


def tree_state(root: Path) -> dict[str, tuple[int, int, int, str]]:
    """Record persistent namespace/content state, excluding read access times."""
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        observed = path.lstat()
        content = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if stat.S_ISREG(observed.st_mode)
            else str(path.readlink()) if path.is_symlink() else ""
        )
        result[str(path.relative_to(root))] = (
            observed.st_mode,
            observed.st_mtime_ns,
            observed.st_size,
            content,
        )
    return result


def test_read_existing_copy_without_staging_preserves_every_file(
    tmp_path: Path,
) -> None:
    writer = RunStore(tmp_path / "writer")
    original = publish(writer, "retained")
    copied = tmp_path / "read only copy"
    shutil.copytree(writer.root, copied)
    (copied / ".staging").rmdir()
    before = tree_state(copied)

    reader = RunStore.open_existing(copied)
    explicit = reader.open_run("retained", manifest_sha256=original.manifest_sha256)
    explicit.verify()
    assert explicit.manifest == original.manifest
    assert reader.resolve_latest().manifest_sha256 == original.manifest_sha256
    assert reader.resolve_latest_attempt().run_id == "retained"
    assert reader.read_json("source") == original.read_json("source")
    reader.verify()
    assert tree_state(copied) == before
    assert not (copied / ".staging").exists()


def test_reader_rejects_begin_before_creating_lock_or_staging(tmp_path: Path) -> None:
    writer = RunStore(tmp_path / "output")
    publish(writer, "retained")
    (writer.root / ".staging").rmdir()
    before = tree_state(writer.root)
    reader = RunStore.open_existing(writer.root)

    with pytest.raises(PublicationConflict, match="Read-only") as error:
        reader.begin("unwanted-write")
    assert error.value.code == "READ_ONLY_STORE"
    assert tree_state(writer.root) == before


def test_missing_reader_location_does_not_create_any_ancestor(tmp_path: Path) -> None:
    before = tree_state(tmp_path)
    with pytest.raises(IntegrityError):
        RunStore.open_existing(tmp_path / "missing" / "store")
    assert tree_state(tmp_path) == before


def test_flat_legacy_directory_is_not_silently_initialized(tmp_path: Path) -> None:
    (tmp_path / "findings.json").write_text('{"version":"1.0.0"}\n')
    before = tree_state(tmp_path)
    with pytest.raises(IntegrityError):
        RunStore.open_existing(tmp_path)
    assert tree_state(tmp_path) == before


@pytest.mark.parametrize("redirect", ["root", "runs", "ancestor"])
def test_reader_rejects_symlinked_directory_components(
    tmp_path: Path, redirect: str
) -> None:
    real = tmp_path / "real"
    writer = RunStore(real / "store")
    publish(writer, "retained")
    if redirect == "root":
        selected = tmp_path / "linked-store"
        selected.symlink_to(writer.root, target_is_directory=True)
    elif redirect == "ancestor":
        alias = tmp_path / "linked-parent"
        alias.symlink_to(real, target_is_directory=True)
        selected = alias / "store"
    else:
        selected = tmp_path / "selected"
        selected.mkdir()
        (selected / "runs").symlink_to(writer.root / "runs", target_is_directory=True)
    before = tree_state(tmp_path)
    with pytest.raises(IntegrityError):
        RunStore.open_existing(selected)
    assert tree_state(tmp_path) == before


@pytest.mark.parametrize("invalid", ["root-file", "runs-file", "traversal"])
def test_reader_rejects_non_directory_and_traversing_locations(
    tmp_path: Path, invalid: str
) -> None:
    if invalid == "root-file":
        selected = tmp_path / "file"
        selected.write_text("not a directory")
    elif invalid == "runs-file":
        selected = tmp_path / "store"
        selected.mkdir()
        (selected / "runs").write_text("not a directory")
    else:
        (tmp_path / "store" / "runs").mkdir(parents=True)
        selected = tmp_path / "store" / ".." / "store"
    before = tree_state(tmp_path)
    with pytest.raises(IntegrityError):
        RunStore.open_existing(selected)
    assert tree_state(tmp_path) == before


def test_writer_default_still_creates_staging_and_publishes(tmp_path: Path) -> None:
    writer = RunStore(tmp_path / "new" / "store")
    snapshot = publish(writer, "original-writer")
    assert (writer.root / ".staging").is_dir()
    assert writer.resolve_latest().run_id == snapshot.run_id


def test_reader_does_not_upgrade_historical_unverified_source(tmp_path: Path) -> None:
    writer = RunStore(tmp_path / "output")
    snapshot = publish(writer, "historical")
    assert snapshot.manifest["input_verification"] == "unverified"
    reader = RunStore.open_existing(writer.root)
    assert reader.open_run("historical").manifest["input_verification"] == "unverified"
