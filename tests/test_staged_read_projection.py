"""Staged material has checked reads but no published snapshot authority."""

from __future__ import annotations

from pathlib import Path
import os
from typing import Any

import pytest

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.run_store import RunSnapshot, RunStore
from test_contracts_v2 import manifest_document, source_document
from test_run_store_v2 import publish


def manifest(stage: Any) -> dict[str, Any]:
    value = manifest_document()
    value.update(run_id=stage.run_id, artifacts=stage.artifacts)
    return value


def test_projection_reads_checked_bytes_without_published_identity_or_visibility(
    tmp_path: Path,
):
    store = RunStore(tmp_path / "store")
    baseline = publish(store, "baseline")
    before = {name: (store.root / name).read_bytes() for name in ["heads.json"]}
    with store.begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        view.verify()
        assert view.read_json("source") == source_document()
        assert view.manifest["run_id"] == "candidate"
        assert view.manifest["input_verification"] == "unverified"
        assert not isinstance(view, RunSnapshot)
        for attribute in ["path", "manifest_sha256", "run_id", "read_manifest_bytes"]:
            assert not hasattr(view, attribute)
        for name, value in before.items():
            assert (store.root / name).read_bytes() == value
        assert store.resolve_latest_attempt().run_id == baseline.run_id
        with pytest.raises(IntegrityError):
            store.open_run("candidate")
        assert not (stage.path / "run_manifest.json").exists()


def test_projection_freezes_metadata_and_survives_registered_append(tmp_path: Path):
    store = RunStore(tmp_path / "store")
    with store.begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        declaration = manifest(stage)
        view = stage.project(declaration)
        declaration["source"]["files"].clear()
        detached = view.manifest
        detached["source"]["files"].clear()
        stage.write_json(
            "second/source.json",
            source_document(),
            contract="source",
            artifact_id="second",
        )
        assert view.read_json("source") == source_document()
        assert view.manifest["source"]["files"]
        assert len(view.manifest["artifacts"]) == 1
        with pytest.raises(IntegrityError):
            view.read_bytes("second")
        view.verify()
        final = stage.project(manifest(stage))
        assert final.read_json("second") == source_document()


def test_projection_refuses_changed_bytes_and_missing_or_unregistered_material(
    tmp_path: Path,
):
    store = RunStore(tmp_path / "store")
    with store.begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        (stage.path / "source.json").write_bytes(b"changed")
        with pytest.raises(IntegrityError):
            view.read_bytes("source")
        with pytest.raises(IntegrityError):
            view.verify()


@pytest.mark.parametrize("kind", ["ordinary", "symlink", "fifo"])
def test_projection_refuses_unregistered_namespace_material(tmp_path: Path, kind: str):
    with RunStore(tmp_path / "store").begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        if kind == "ordinary":
            (stage.path / "other").write_bytes(b"other")
        elif kind == "symlink":
            (stage.path / "other").symlink_to(stage.path / "source.json")
        else:
            os.mkfifo(stage.path / "other")
        with pytest.raises(IntegrityError):
            view.verify()


def test_projection_requires_exact_registered_manifest_inventory(tmp_path: Path):
    with RunStore(tmp_path / "store").begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        value = manifest(stage)
        value["artifacts"] = []
        with pytest.raises(IntegrityError):
            stage.project(value)


@pytest.mark.parametrize("close", ["exit", "publish"])
def test_projection_cannot_outlive_its_active_owned_stage(tmp_path: Path, close: str):
    with RunStore(tmp_path / "store").begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        if close == "publish":
            final = stage.publish(manifest(stage))
            final.verify()
    with pytest.raises(PublicationConflict):
        view.verify()
    with pytest.raises(PublicationConflict):
        view.read_bytes("source")


def test_projection_verifies_current_source_callback_without_publishing(tmp_path: Path):
    checks = []
    with RunStore(tmp_path / "store").begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(
            manifest(stage), source_check=lambda: checks.append("checked")
        )
        assert checks == ["checked"]
        assert view.manifest["input_verification"] == "verified"
        with pytest.raises(ContractError):
            stage.project(manifest(stage), source_check=lambda: False)
        assert not (stage.path / "run_manifest.json").exists()


def test_projection_refuses_changed_descriptor_prefix(tmp_path: Path):
    with RunStore(tmp_path / "store").begin("candidate") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        view = stage.project(manifest(stage))
        stage._artifacts[0]["sha256"] = "0" * 64
        with pytest.raises(IntegrityError):
            view.verify()
