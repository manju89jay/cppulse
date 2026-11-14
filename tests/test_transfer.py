"""Checked directory transfer keeps foreign facts separate and unauthenticated."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.run_store import RunStore
from cppulse.transfer import (
    TransferLimits,
    copy_bundle,
    export_bundle,
    open_bundle,
)
from test_contracts_v2 import source_document
from test_run_store_v2 import publish


@pytest.fixture()
def exported(tmp_path: Path):
    snapshot = publish(RunStore(tmp_path / "store"), "original")
    bundle = export_bundle({"upstream": snapshot}, tmp_path / "bundle")
    return snapshot, bundle


def descriptor(path: Path) -> dict[str, Any]:
    return json.loads((path / "transfer_bundle.json").read_bytes())


def change_descriptor(path: Path, document: dict[str, Any]) -> None:
    (path / "transfer_bundle.json").write_text(json.dumps(document))


def test_export_preserves_exact_bytes_and_import_claims(exported) -> None:
    snapshot, bundle = exported
    run = bundle.open_run("upstream")
    assert run.run_id == snapshot.run_id
    assert run.manifest == snapshot.manifest
    assert run.manifest_sha256 == snapshot.manifest_sha256
    assert (
        run.read_manifest_bytes() == (snapshot.path / "run_manifest.json").read_bytes()
    )
    assert hashlib.sha256(run.read_manifest_bytes()).hexdigest() == run.manifest_sha256
    assert run.read_bytes("source") == snapshot.read_bytes("source")
    assert run.read_json("source") == source_document()
    assert run.origin == "import"
    assert run.authentication == "unverified"
    assert run.source_freshness == "not_rechecked"
    assert bundle.metadata["origin"] == "import"
    assert bundle.metadata["authentication"] == "unverified"
    assert bundle.root_ids == ("upstream",)
    assert not list(bundle.path.rglob("latest*.json"))
    assert not list(bundle.path.rglob(".staging"))
    run.verify()
    bundle.verify()


def test_original_verified_claim_is_preserved_without_promoting_import(tmp_path: Path):
    snapshot = publish(
        RunStore(tmp_path / "store"), "verified", source_check=lambda: None
    )
    run = export_bundle({"upstream": snapshot}, tmp_path / "bundle").open_run(
        "upstream"
    )
    assert run.manifest["input_verification"] == "verified"
    assert run.source_freshness == "not_rechecked"
    assert run.authentication == "unverified"
    changed = run.manifest
    changed["source"]["files"].clear()
    assert run.manifest["source"]["files"]


def test_multiple_sources_and_same_run_id_keep_distinct_namespaces(tmp_path: Path):
    first = publish(RunStore(tmp_path / "one"), "same")
    second = publish(RunStore(tmp_path / "two"), "same")
    bundle = export_bundle({"upstream": first, "local": second}, tmp_path / "bundle")
    assert bundle.root_ids == ("local", "upstream")
    assert bundle.open_run("local").run_id == bundle.open_run("upstream").run_id
    assert len(bundle.metadata["roots"]) == 2


def test_load_is_readonly_and_retains_frozen_checked_bytes(exported, monkeypatch):
    snapshot, original = exported
    before = sorted(
        str(path.relative_to(original.path)) for path in original.path.rglob("*")
    )

    def reject(*args, **kwargs):
        raise AssertionError("Transfer reader must not execute or initialize a store")

    monkeypatch.setattr(RunStore, "__init__", reject)
    monkeypatch.setattr(subprocess, "run", reject)
    bundle = open_bundle(original.path)
    run = bundle.open_run("upstream")
    payload = original.path / "roots/upstream/runs/original/artifacts/source.json"
    payload.write_bytes(b"corrupt after frozen load")
    assert run.read_bytes("source") == snapshot.read_bytes("source")
    run.verify()
    assert (
        sorted(
            str(path.relative_to(original.path)) for path in original.path.rglob("*")
        )
        == before
    )
    with pytest.raises(IntegrityError):
        open_bundle(original.path)


def test_copy_preserves_descriptor_and_payload(exported, tmp_path: Path):
    _, bundle = exported
    copied = copy_bundle(bundle.path, tmp_path / "copied")
    assert (copied.path / "transfer_bundle.json").read_bytes() == (
        bundle.path / "transfer_bundle.json"
    ).read_bytes()
    assert copied.open_run("upstream").manifest == bundle.open_run("upstream").manifest
    copied.verify()


@pytest.mark.parametrize(
    "mutation",
    [
        "changed",
        "missing",
        "extra",
        "symlink",
        "directory_symlink",
        "fifo",
        "empty_extra_directory",
    ],
)
def test_reader_rejects_corrupt_unlisted_or_nonregular_entries(
    exported, tmp_path, mutation
):
    _, bundle = exported
    payload = bundle.path / "roots/upstream/runs/original/artifacts/source.json"
    if mutation == "changed":
        payload.write_text("{}")
    elif mutation == "missing":
        payload.unlink()
    elif mutation == "extra":
        (bundle.path / "extra.txt").write_text("unlisted")
    elif mutation == "symlink":
        content = payload.read_bytes()
        outside = tmp_path / "outside.json"
        outside.write_bytes(content)
        payload.unlink()
        payload.symlink_to(outside)
    elif mutation == "directory_symlink":
        payload.unlink()
        payload.parent.rmdir()
        payload.parent.symlink_to(tmp_path, target_is_directory=True)
    elif mutation == "fifo":
        payload.unlink()
        os.mkfifo(payload)
    else:
        (bundle.path / "extra").mkdir()
    with pytest.raises(IntegrityError):
        open_bundle(bundle.path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_files", 1),
        ("max_file_bytes", 10),
        ("max_total_bytes", 10),
        ("max_metadata_bytes", 10),
    ],
)
def test_reader_local_caps_cannot_be_raised_by_descriptor(exported, field, value):
    _, bundle = exported
    kwargs = {field: value}
    with pytest.raises((ContractError, IntegrityError)):
        open_bundle(bundle.path, limits=TransferLimits(**kwargs))


@pytest.mark.parametrize("value", [0, -1, True, 10001])
def test_invalid_limits_are_rejected(value):
    with pytest.raises(ContractError):
        TransferLimits(max_files=value)


def test_descriptor_is_size_bounded_before_json_decode(exported):
    _, bundle = exported
    (bundle.path / "transfer_bundle.json").write_bytes(b"{" + b"x" * 1024)
    with pytest.raises(IntegrityError, match="bound|limit|cap"):
        open_bundle(bundle.path, limits=TransferLimits(max_metadata_bytes=128))


def test_contract_json_is_bounded_even_if_payload_file_cap_is_large(exported):
    _, bundle = exported
    manifest_path = bundle.path / "roots/upstream/runs/original/run_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    artifact = manifest["artifacts"][0]
    content = json.dumps({**source_document(), "padding": "x" * 10000}).encode()
    artifact.update(size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    (manifest_path.parent / artifact["path"]).write_bytes(content)
    raw = json.dumps(manifest).encode()
    manifest_path.write_bytes(raw)
    document = descriptor(bundle.path)
    for entry in document["files"]:
        if entry["path"].endswith("run_manifest.json"):
            entry.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        else:
            entry.update(
                size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest()
            )
    document["roots"][0]["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    change_descriptor(bundle.path, document)
    with pytest.raises(IntegrityError, match="metadata|bound|cap"):
        open_bundle(bundle.path, limits=TransferLimits(max_metadata_bytes=5000))


@pytest.mark.parametrize(
    "mutation", ["manifest", "source", "unlisted_artifact", "contract", "duplicate_key"]
)
def test_payload_manifests_and_contracts_are_validated(exported, mutation):
    _, bundle = exported
    document = descriptor(bundle.path)
    root = document["roots"][0]
    manifest_path = bundle.path / root["manifest_path"]
    manifest = json.loads(manifest_path.read_bytes())
    if mutation == "manifest":
        manifest["run_id"] = "other"
    elif mutation == "source":
        root["source_digest"] = "f" * 64
    elif mutation == "unlisted_artifact":
        manifest["artifacts"][0]["path"] = "missing.json"
    elif mutation == "contract":
        manifest["artifacts"][0]["contract"]["kind"] = "evidence"
    raw = json.dumps(manifest).encode()
    if mutation == "duplicate_key":
        raw = raw[:-1] + b', "run_id": "original"}'
    manifest_path.write_bytes(raw)
    root["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    next(
        entry for entry in document["files"] if entry["path"] == root["manifest_path"]
    ).update(size_bytes=len(raw), sha256=root["manifest_sha256"])
    change_descriptor(bundle.path, document)
    with pytest.raises((ContractError, IntegrityError)):
        open_bundle(bundle.path)


def test_snapshot_mutation_is_detected_before_export(exported, tmp_path):
    snapshot, _ = exported
    (snapshot.path / "artifacts/source.json").write_text("{}")
    with pytest.raises(IntegrityError):
        export_bundle({"upstream": snapshot}, tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_existing_destination_is_never_replaced(exported):
    snapshot, bundle = exported
    before = (bundle.path / "transfer_bundle.json").read_bytes()
    with pytest.raises(PublicationConflict):
        export_bundle({"upstream": snapshot}, bundle.path)
    assert (bundle.path / "transfer_bundle.json").read_bytes() == before


def test_raced_empty_destination_is_not_overwritten(exported, tmp_path, monkeypatch):
    import cppulse.transfer as module

    snapshot, _ = exported
    destination = tmp_path / "raced"
    original = module._commit

    def race(parent, staging, name):
        destination.mkdir()
        return original(parent, staging, name)

    monkeypatch.setattr(module, "_commit", race)
    with pytest.raises(PublicationConflict):
        export_bundle({"upstream": snapshot}, destination)
    assert destination.is_dir()
    assert not list(destination.iterdir())
    assert not list(tmp_path.glob(".cppulse-transfer-*"))


def test_interrupted_export_removes_staging_and_exposes_no_bundle(
    exported, tmp_path, monkeypatch
):
    import cppulse.transfer as module

    snapshot, _ = exported

    def interrupt(*args):
        raise RuntimeError("interrupted publication")

    monkeypatch.setattr(module, "_commit", interrupt)
    with pytest.raises(RuntimeError, match="interrupted"):
        export_bundle({"upstream": snapshot}, tmp_path / "interrupted")
    assert not (tmp_path / "interrupted").exists()
    assert not list(tmp_path.glob(".cppulse-transfer-*"))


def test_corrupt_staged_copy_is_rejected_before_publication(
    exported, tmp_path, monkeypatch
):
    import cppulse.transfer as module

    snapshot, _ = exported
    original = module._write

    def corrupt(directory, path, content):
        original(directory, path, content)
        if path.endswith("artifacts/source.json"):
            descriptor = os.open(path, os.O_WRONLY | os.O_TRUNC, dir_fd=directory)
            try:
                os.write(descriptor, b"corrupt copied bytes")
            finally:
                os.close(descriptor)

    monkeypatch.setattr(module, "_write", corrupt)
    with pytest.raises(IntegrityError):
        export_bundle({"upstream": snapshot}, tmp_path / "corrupt-copy")
    assert not (tmp_path / "corrupt-copy").exists()
    assert not list(tmp_path.glob(".cppulse-transfer-*"))


def test_unsupported_atomic_rename_has_no_overwrite_fallback(
    exported, tmp_path, monkeypatch
):
    import cppulse.transfer as module

    snapshot, _ = exported

    def unsupported(*args):
        raise IntegrityError("Atomic no-replace publication is unsupported")

    monkeypatch.setattr(module, "_commit", unsupported)
    with pytest.raises(IntegrityError, match="unsupported"):
        export_bundle({"upstream": snapshot}, tmp_path / "unsupported")
    assert not (tmp_path / "unsupported").exists()


def test_destinations_inside_snapshots_or_input_bundle_are_rejected(exported):
    snapshot, bundle = exported
    with pytest.raises(IntegrityError):
        export_bundle({"upstream": snapshot}, snapshot.path / "exported")
    with pytest.raises(IntegrityError):
        copy_bundle(bundle.path, bundle.path / "copied")


def test_unknown_root_and_artifact_are_explicit_errors(exported):
    _, bundle = exported
    with pytest.raises(IntegrityError):
        bundle.open_run("missing")
    with pytest.raises(IntegrityError):
        bundle.open_run("upstream").read_bytes("missing")


def test_descriptor_mutation_does_not_change_frozen_metadata(exported):
    _, bundle = exported
    original = deepcopy(bundle.metadata)
    metadata = bundle.metadata
    metadata["roots"].clear()
    (bundle.path / "transfer_bundle.json").write_text("{}")
    assert bundle.metadata == original
    bundle.verify()
