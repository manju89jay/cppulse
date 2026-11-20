"""Local identity regressions independent of Git and filesystem timestamps."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import (
    canonical_json_bytes,
    context_identity,
    digest_json,
    file_identity,
    hash_artifact,
    snapshot_inputs,
    verify_inputs,
)


def context_payload() -> dict[str, Any]:
    """Return selected compile facts rather than invoking a compiler."""
    return {
        "compiler": {"name": "gcc", "version": "14"},
        "argv": ["g++", "-DVALUE=1", "-std=c++17", "src/a.cpp"],
        "working_directory": "/workspace/project",
        "language_standard": "c++17",
        "target": "x86_64-linux-gnu",
        "provenance": "observed",
        "dependencies": [],
    }


def test_canonical_json_is_utf8_and_sorted_without_reordering_lists() -> None:
    expected = '{"args":["b","a"],"name":"Größe"}'.encode()
    assert canonical_json_bytes({"name": "Größe", "args": ["b", "a"]}) == expected
    assert (
        digest_json({"name": "Größe", "args": ["b", "a"]})
        == hashlib.sha256(expected).hexdigest()
    )
    assert digest_json(["a", "b"]) != digest_json(["b", "a"])


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), -float("inf"), {"bad": object()}]
)
def test_nonfinite_or_non_json_identity_is_rejected(value: Any) -> None:
    with pytest.raises(ContractError):
        canonical_json_bytes(value)


def test_snapshot_is_sorted_content_based_and_independent_of_git_metadata(
    tmp_path: Path,
) -> None:
    (tmp_path / "b.cpp").write_bytes(b"beta")
    (tmp_path / "a.cpp").write_bytes(b"alpha")
    first = snapshot_inputs(tmp_path, ["b.cpp", "a.cpp"], revision="one", dirty=False)
    second = snapshot_inputs(
        tmp_path, [tmp_path / "a.cpp", "./b.cpp"], revision="two", dirty=True
    )
    assert first["digest"] == second["digest"]
    assert [entry["path"] for entry in first["files"]] == ["a.cpp", "b.cpp"]
    assert first["inventory_complete"] is False
    assert first["limitations"]
    projection = {name: first[name] for name in ["kind", "files", "inventory_complete"]}
    independent = hashlib.sha256(
        json.dumps(
            projection,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    assert first["digest"] == independent
    validate("source", first)
    assert verify_inputs(tmp_path, first) == []


def test_inventory_and_kind_are_semantic_but_unlisted_additions_are_not_observed(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.cpp").write_bytes(b"alpha")
    initial = snapshot_inputs(tmp_path, ["a.cpp"])
    complete = snapshot_inputs(tmp_path, ["a.cpp"], inventory_complete=True)
    library = snapshot_inputs(tmp_path, ["a.cpp"], kind="library")
    assert len({initial["digest"], complete["digest"], library["digest"]}) == 3
    (tmp_path / "new.cpp").write_bytes(b"new")
    assert verify_inputs(tmp_path, complete) == []
    assert any("unlisted" in item for item in complete["limitations"])


def test_empty_inventory_is_explicit_and_not_a_complete_repository_claim(
    tmp_path: Path,
) -> None:
    result = snapshot_inputs(tmp_path, [])
    assert result["files"] == []
    assert result["inventory_complete"] is False
    assert result["limitations"]
    validate("source", result)


@pytest.mark.parametrize(
    "name", ["../outside.cpp", "a/../a.cpp", "C:outside.cpp", "a\\b.cpp", ""]
)
def test_unsafe_source_spelling_is_rejected(tmp_path: Path, name: str) -> None:
    (tmp_path / "a.cpp").write_text("void valid() {}")
    with pytest.raises(IntegrityError):
        file_identity(tmp_path, name)


def test_outside_absolute_path_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.cpp"
    outside.write_bytes(b"outside")
    with pytest.raises(IntegrityError):
        snapshot_inputs(root, [outside])


def test_same_file_twice_is_not_two_selected_inputs(tmp_path: Path) -> None:
    (tmp_path / "a.cpp").write_bytes(b"alpha")
    with pytest.raises(ContractError, match="Duplicate"):
        snapshot_inputs(tmp_path, ["a.cpp", tmp_path / "a.cpp"])


@pytest.mark.parametrize("name", ["missing.cpp", "directory"])
def test_missing_and_nonregular_input_fail_explicitly(
    tmp_path: Path, name: str
) -> None:
    (tmp_path / "directory").mkdir()
    with pytest.raises(IntegrityError):
        snapshot_inputs(tmp_path, [name])


def test_symlink_file_and_parent_components_are_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "a.cpp").write_bytes(b"alpha")
    try:
        (root / "alias.cpp").symlink_to(external / "a.cpp")
        (root / "folder").symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")
    for name in ["alias.cpp", "folder/a.cpp"]:
        with pytest.raises(IntegrityError):
            snapshot_inputs(root, [name])


def test_same_size_edit_with_restored_mtime_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "a.cpp"
    path.write_bytes(b"first")
    snapshot = snapshot_inputs(tmp_path, [path])
    before = path.stat()
    path.write_bytes(b"other")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    errors = verify_inputs(tmp_path, snapshot)
    assert any("a.cpp" in error and "content" in error for error in errors)


def test_deleted_and_replaced_inputs_are_verified_by_actual_content(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.cpp"
    path.write_bytes(b"original")
    snapshot = snapshot_inputs(tmp_path, [path])
    path.unlink()
    assert any("a.cpp" in error for error in verify_inputs(tmp_path, snapshot))
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"replaced")
    replacement.replace(path)
    assert any("content" in error for error in verify_inputs(tmp_path, snapshot))


def test_mutation_during_read_is_not_a_successful_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "large.cpp"
    path.write_bytes(b"a" * (2 * 1024 * 1024))
    original_read = os.read
    changed = False
    inode = path.stat().st_ino

    def mutate_after_chunk(fd: int, size: int) -> bytes:
        nonlocal changed
        value = original_read(fd, size)
        if value and not changed and os.fstat(fd).st_ino == inode:
            changed = True
            path.write_bytes(b"b" * (2 * 1024 * 1024))
        return value

    monkeypatch.setattr(os, "read", mutate_after_chunk)
    with pytest.raises(InputChanged, match="changed"):
        snapshot_inputs(tmp_path, [path])
    assert changed


def test_path_replacement_during_read_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "large.cpp"
    path.write_bytes(b"a" * (2 * 1024 * 1024))
    replacement = tmp_path / "replacement"
    replacement.write_bytes(path.read_bytes())
    original_read = os.read
    replaced = False
    inode = path.stat().st_ino

    def replace_after_chunk(fd: int, size: int) -> bytes:
        nonlocal replaced
        value = original_read(fd, size)
        if value and not replaced and os.fstat(fd).st_ino == inode:
            replaced = True
            replacement.replace(path)
        return value

    monkeypatch.setattr(os, "read", replace_after_chunk)
    with pytest.raises(InputChanged, match="changed"):
        snapshot_inputs(tmp_path, [path])
    assert replaced


def test_context_identity_preserves_argv_and_tracks_dependencies() -> None:
    payload = context_payload()
    original = deepcopy(payload)
    first = context_identity(payload)
    assert payload == original
    validate("context", first)
    for key, value in [
        ("argv", list(reversed(payload["argv"]))),
        ("provenance", "inferred"),
        ("compiler", {"name": "gcc", "version": "15"}),
        (
            "dependencies",
            [{"id": "sdk", "sha256": None, "availability": "unavailable"}],
        ),
    ]:
        assert context_identity({**payload, key: value})["digest"] != first["digest"]
    renamed = context_identity(
        {**payload, "id": "gcc17", "limitations": ["local fixture"]}
    )
    assert renamed["digest"] == first["digest"]
    assert renamed["id"] == "gcc17"


def test_context_rejects_run_metadata_rather_than_hashing_it() -> None:
    with pytest.raises(ContractError):
        context_identity(
            {
                **context_payload(),
                "run_id": "run-1",
                "started_at": "2026-11-13T00:00:00Z",
            }
        )


def test_artifact_receipt_is_validated_and_does_not_copy_bytes(tmp_path: Path) -> None:
    path = tmp_path / "report.bin"
    path.write_bytes(b"retained bytes")
    record = hash_artifact(
        path, "report", "artifacts/report.bin", "application/octet-stream"
    )
    assert record == {
        "id": "report",
        "path": "artifacts/report.bin",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": len(path.read_bytes()),
        "media_type": "application/octet-stream",
    }
    validate("artifact", record)
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize(
    "destination",
    [
        "../outside.bin",
        "/absolute.bin",
        "artifacts\\report.bin",
        "run_manifest.json",
        "latest.json",
    ],
)
def test_unsafe_artifact_destination_is_rejected(
    tmp_path: Path, destination: str
) -> None:
    path = tmp_path / "report.bin"
    path.write_bytes(b"bytes")
    with pytest.raises(ContractError):
        hash_artifact(path, "report", destination, "application/octet-stream")


def test_non_string_keys_are_not_silently_coerced_into_colliding_identities() -> None:
    with pytest.raises(ContractError):
        canonical_json_bytes({1: "numeric", "1": "text"})


def test_stable_identical_content_replacement_keeps_source_identity(
    tmp_path: Path,
) -> None:
    path = tmp_path / "a.cpp"
    path.write_bytes(b"same bytes")
    snapshot = snapshot_inputs(tmp_path, [path])
    replacement = tmp_path / "replacement"
    replacement.write_bytes(path.read_bytes())
    replacement.replace(path)
    assert verify_inputs(tmp_path, snapshot) == []
    assert snapshot_inputs(tmp_path, [path])["digest"] == snapshot["digest"]


def test_unsafe_recorded_snapshot_is_rejected_before_reading(tmp_path: Path) -> None:
    snapshot = snapshot_inputs(tmp_path, [])
    snapshot["files"] = [
        {"path": "../outside.cpp", "sha256": "a" * 64, "size_bytes": 1}
    ]
    projection = {key: snapshot[key] for key in ["kind", "files", "inventory_complete"]}
    snapshot["digest"] = digest_json(projection)
    with pytest.raises(ContractError):
        verify_inputs(tmp_path, snapshot)
