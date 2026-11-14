"""Persistence regressions: retained snapshots never imply a mutable latest run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest

from cppulse.errors import (
    ContractError,
    InputChanged,
    IntegrityError,
    PublicationConflict,
)
from cppulse.run_store import RunSnapshot, RunStore
from test_contracts_v2 import (
    evidence_document,
    manifest_document,
    passed_policy_assessment,
    receipt_document,
    source_document,
)
from test_compatibility_v2 import legacy_risk


def publish(
    store: RunStore,
    run_id: str,
    *,
    status: str = "completed",
    source_check: Callable[[], None] | None = None,
) -> RunSnapshot:
    """Publish synthetic contracted facts, not a claim of project verification."""
    with store.begin(run_id) as stage:
        artifact = stage.write_json(
            "artifacts/source.json", source_document(), contract="source"
        )
        manifest = manifest_document()
        manifest.update(run_id=run_id, status=status, artifacts=[artifact])
        return stage.publish(manifest, source_check=source_check)


def test_publish_roundtrip_and_frozen_latest(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    first = publish(store, "first")
    frozen = store.resolve_latest()
    second = publish(store, "second")
    assert store.resolve_latest().run_id == second.run_id
    assert frozen.run_id == first.run_id
    assert frozen.read_json("source") == source_document()
    frozen.verify()
    altered = frozen.manifest
    altered["source"]["files"].clear()
    assert frozen.manifest["source"]["files"]
    (store.root / "latest.json").write_text("malformed pointer")
    assert frozen.read_json("source") == source_document()
    with pytest.raises(IntegrityError):
        store.resolve_latest()


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_partial_and_cancelled_runs_do_not_replace_completed_latest(
    tmp_path: Path, status: str
) -> None:
    store = RunStore(tmp_path / "output")
    publish(store, "completed")
    retained = publish(store, status, status=status)
    assert retained.manifest["status"] == status
    retained.verify()
    assert store.resolve_latest().run_id == "completed"
    assert store.resolve_latest_attempt().run_id == status
    assert store.open_run(status).run_id == status


def test_staging_is_not_readable_as_committed_run(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    with pytest.raises(RuntimeError, match="interrupted"):
        with store.begin("unfinished") as stage:
            stage.write_json("source.json", source_document(), contract="source")
            raise RuntimeError("interrupted")
    assert not (store.root / "latest.json").exists()
    assert not (store.root / "runs/unfinished/run_manifest.json").exists()
    with pytest.raises(IntegrityError):
        store.open_run("unfinished")
    with pytest.raises(PublicationConflict):
        store.begin("unfinished")


def test_global_writer_lock_and_duplicate_run_are_explicit(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    with store.begin("writer"):
        with pytest.raises(PublicationConflict):
            RunStore(store.root).begin("other")
    publish(store, "taken")
    with pytest.raises(PublicationConflict):
        store.begin("taken")
    (store.root / ".publication.lock").write_text("unknown prior owner")
    with pytest.raises(PublicationConflict):
        store.begin("next")
    assert (store.root / ".publication.lock").read_text() == "unknown prior owner"


@pytest.mark.parametrize(
    "path",
    [
        "../escape.json",
        "/absolute.json",
        "a/../escape.json",
        "a//b.json",
        "./alias.json",
        "C:\\outside.json",
        "run_manifest.json",
        "latest.json",
        "LATEST_ATTEMPT.JSON",
        "RUN_MANIFEST.JSON",
    ],
)
def test_unsafe_or_reserved_artifact_paths_are_rejected(
    tmp_path: Path, path: str
) -> None:
    with RunStore(tmp_path / "output").begin("unsafe") as stage:
        with pytest.raises((ContractError, IntegrityError)):
            stage.write_json(path, source_document(), contract="source")


def test_artifact_case_collisions_and_mutated_descriptors_do_not_alias(
    tmp_path: Path,
) -> None:
    with RunStore(tmp_path / "output").begin("aliases") as stage:
        descriptor = stage.write_json(
            "Source.json", source_document(), contract="source"
        )
        descriptor["path"] = "elsewhere.json"
        assert stage.artifacts[0]["path"] == "Source.json"
        with pytest.raises(PublicationConflict):
            stage.write_json(
                "source.json",
                source_document(),
                contract="source",
                artifact_id="different",
            )


@pytest.mark.parametrize(
    "mutation", ["changed", "missing", "symlink", "parent_symlink"]
)
def test_snapshot_rejects_corrupted_or_redirected_artifact(
    tmp_path: Path, mutation: str
) -> None:
    store = RunStore(tmp_path / "output")
    snapshot = publish(store, "check")
    artifact = snapshot.path / "artifacts/source.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(artifact.read_bytes())
    if mutation == "changed":
        artifact.write_text("{}")
    elif mutation == "missing":
        artifact.unlink()
    elif mutation == "symlink":
        artifact.unlink()
        artifact.symlink_to(outside)
    else:
        artifact.unlink()
        artifact.parent.rmdir()
        artifact.parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(IntegrityError):
        snapshot.read_json("source")
    with pytest.raises(IntegrityError):
        snapshot.verify()


def test_pointer_digest_and_manifest_tampering_are_detected(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    snapshot = publish(store, "check")
    path = snapshot.path / "run_manifest.json"
    changed = snapshot.manifest
    changed["limitations"].append("changed after publication")
    path.write_text(json.dumps(changed))
    with pytest.raises(IntegrityError):
        store.resolve_latest()
    with pytest.raises(IntegrityError):
        snapshot.read_bytes("source")


def test_source_verification_is_explicit_and_mutation_blocks_publication(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "output")
    imported = publish(store, "imported")
    assert imported.manifest["input_verification"] == "unverified"
    assert any("freshness" in value for value in imported.manifest["limitations"])
    verified = publish(store, "verified", source_check=lambda: None)
    assert verified.manifest["input_verification"] == "verified"

    def changed() -> None:
        raise InputChanged("synthetic selected-input mutation")

    with pytest.raises(InputChanged):
        publish(store, "changed", source_check=changed)
    assert store.resolve_latest().run_id == "verified"
    assert not (store.root / "runs/changed").exists()
    with pytest.raises(ContractError, match="return None"):
        publish(store, "bad-check", source_check=lambda: [])
    assert store.resolve_latest().run_id == "verified"


@pytest.mark.parametrize("pointer", ["latest.json", "latest_attempt.json"])
def test_interruption_before_pointer_keeps_previous_latest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pointer: str
) -> None:
    import cppulse.run_store as module

    store = RunStore(tmp_path / "output")
    publish(store, "old")
    original_replace = module.os.replace

    def interrupt(source: str, destination: str, *args: Any, **kwargs: Any) -> None:
        if destination == pointer:
            raise OSError("synthetic interruption before pointer replace")
        return original_replace(source, destination, *args, **kwargs)

    monkeypatch.setattr(module.os, "replace", interrupt)
    with pytest.raises(IntegrityError):
        publish(store, "retained")
    assert store.resolve_latest().run_id == "old"
    store.open_run("retained").verify()
    assert store.resolve_latest_attempt().run_id == (
        "retained" if pointer == "latest.json" else "old"
    )


def test_copy_artifact_and_explicit_prototype_contract(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    data = tmp_path / "input.bin"
    data.write_bytes(b"retained binary log\x00\xff")
    with store.begin("copy") as stage:
        copied = stage.copy_artifact("log", data, "artifacts/log.bin")
        original = legacy_risk()
        original["metadata"]["model_type"] = "heuristic"
        original["metadata"]["f1_score"] = None
        original["health_score"]["overall"] = None
        risk = stage.write_json(
            "risk_scores.json", original, contract=("risk_scores", "prototype_v1")
        )
        manifest = manifest_document()
        manifest.update(run_id="copy", artifacts=[copied, risk])
        snapshot = stage.publish(manifest)
    assert snapshot.read_bytes("log") == data.read_bytes()
    assert snapshot.read_json("risk_scores") == original
    snapshot.verify()


def test_inventory_mismatch_and_symlink_source_are_rejected(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    outside = tmp_path / "outside"
    outside.write_text("source")
    link = tmp_path / "link"
    link.symlink_to(outside)
    with store.begin("mismatch") as stage:
        with pytest.raises(IntegrityError):
            stage.copy_artifact("link", link, "link.bin")
        artifact = stage.write_json("source.json", source_document(), contract="source")
        manifest = manifest_document()
        manifest.update(run_id="mismatch", artifacts=[])
        with pytest.raises(IntegrityError, match="inventory"):
            stage.publish(manifest)
        manifest["artifacts"] = [artifact]
        stage.publish(manifest).verify()


def test_completed_collection_can_contain_observed_check_failure(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "output")
    with store.begin("observed-failure") as stage:
        artifact = stage.write_json("source.json", source_document(), contract="source")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=[artifact])
        manifest["stages"][0]["status"] = "failed"
        snapshot = stage.publish(manifest)
    assert snapshot.manifest["status"] == "completed"
    assert store.resolve_latest().run_id == snapshot.run_id
    assert snapshot.manifest["stages"][0]["status"] == "failed"


def test_case_folded_parent_aliases_and_file_directory_collisions(
    tmp_path: Path,
) -> None:
    with RunStore(tmp_path / "output").begin("paths") as stage:
        stage.write_json(
            "Artifacts/first.json",
            source_document(),
            contract="source",
            artifact_id="first",
        )
        for path in [
            "artifacts/second.json",
            "Artifacts/first.json/child.json",
            "Artifacts",
        ]:
            with pytest.raises(PublicationConflict):
                stage.write_json(
                    path, source_document(), contract="source", artifact_id="second"
                )


def test_store_root_and_staging_symlinks_are_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    link = tmp_path / "output"
    link.symlink_to(outside, target_is_directory=True)
    with pytest.raises(IntegrityError):
        RunStore(link)
    root = tmp_path / "normal"
    root.mkdir()
    (root / ".staging").symlink_to(outside, target_is_directory=True)
    with pytest.raises(IntegrityError):
        RunStore(root)


def test_artifact_fifo_is_rejected_without_waiting_for_a_writer(tmp_path: Path) -> None:
    import os

    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with RunStore(tmp_path / "output").begin("pipe") as stage:
        with pytest.raises(IntegrityError, match="regular"):
            stage.copy_artifact("pipe", fifo, "pipe.bin")


def test_read_returns_the_same_bytes_it_verified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.run_store as module

    snapshot = publish(RunStore(tmp_path / "output"), "one-read")
    original_read = module._read
    artifact = snapshot.path / "artifacts/source.json"
    expected = artifact.read_bytes()
    reads = []

    def replace_after_read(path: Path) -> bytes:
        content = original_read(path)
        if path == artifact:
            reads.append(path)
            artifact.write_text("changed after the checked descriptor was read")
        return content

    monkeypatch.setattr(module, "_read", replace_after_read)
    assert snapshot.read_bytes("source") == expected
    assert len(reads) == 1
    with pytest.raises(IntegrityError):
        snapshot.read_bytes("source")


@pytest.mark.parametrize(
    "run_id", ["", "../outside", "/absolute", "_hidden", "with space", "x" * 65]
)
def test_noncanonical_run_ids_do_not_create_a_writer(
    tmp_path: Path, run_id: str
) -> None:
    store = RunStore(tmp_path / "output")
    with pytest.raises(IntegrityError):
        store.begin(run_id)
    assert not (store.root / ".publication.lock").exists()


def test_partial_first_attempt_is_visible_without_a_completed_run(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "output")
    snapshot = publish(store, "first-partial", status="partial")
    assert store.resolve_latest_attempt().run_id == snapshot.run_id
    with pytest.raises(IntegrityError):
        store.resolve_latest()


def test_staging_attempt_does_not_replace_either_published_pointer(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "output")
    publish(store, "finished")
    with store.begin("in-progress") as stage:
        stage.write_json("source.json", source_document(), contract="source")
        assert store.resolve_latest_attempt().run_id == "finished"
        assert store.resolve_latest().run_id == "finished"


def test_explicit_nonpromotion_retains_last_completed_but_records_attempt(
    tmp_path: Path,
) -> None:
    store = RunStore(tmp_path / "output")
    publish(store, "prior")
    with store.begin("imported") as stage:
        artifact = stage.write_json("source.json", source_document(), contract="source")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=[artifact])
        snapshot = stage.publish(manifest, make_latest=False)
    assert store.resolve_latest().run_id == "prior"
    assert store.resolve_latest_attempt().run_id == snapshot.run_id


def test_claimed_verification_without_checker_is_downgraded(tmp_path: Path) -> None:
    with RunStore(tmp_path / "output").begin("claim") as stage:
        artifact = stage.write_json("source.json", source_document(), contract="source")
        manifest = manifest_document()
        manifest.update(
            run_id=stage.run_id, artifacts=[artifact], input_verification="verified"
        )
        snapshot = stage.publish(manifest)
    assert snapshot.manifest["input_verification"] == "unverified"
    assert manifest["input_verification"] == "verified"


def test_published_run_is_closed_to_api_mutations(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "output")
    with store.begin("immutable") as stage:
        artifact = stage.write_json("source.json", source_document(), contract="source")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=[artifact])
        snapshot = stage.publish(manifest)
        with pytest.raises(PublicationConflict):
            stage.write_json("another.json", source_document(), contract="source")
        with pytest.raises(PublicationConflict):
            stage.publish(manifest)
        manifest["limitations"].append("caller edit after publication")
    assert "caller edit after publication" not in snapshot.manifest["limitations"]
    snapshot.verify()


def test_unregistered_staged_file_is_not_silently_published(tmp_path: Path) -> None:
    with RunStore(tmp_path / "output").begin("extra") as stage:
        artifact = stage.write_json("source.json", source_document(), contract="source")
        (stage.path / "unregistered.txt").write_text("not in manifest")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=[artifact])
        with pytest.raises(IntegrityError, match="inventory"):
            stage.publish(manifest)
    assert not (stage.path.parent.parent / "runs/extra").exists()


def test_writer_lock_is_exclusive_across_processes(tmp_path: Path) -> None:
    """A separate interpreter cannot publish while another process owns the slot."""
    import os
    import subprocess
    import sys

    import cppulse

    # pytest.ini adjusts only this interpreter's sys.path. Bootstrap the child
    # from the exact package location under test, without requiring a caller's
    # manually exported PYTHONPATH or falling back to another installed version.
    child_environment = os.environ.copy()
    package_parent = str(Path(cppulse.__file__).resolve().parent.parent)
    inherited_path = child_environment.get("PYTHONPATH")
    child_environment["PYTHONPATH"] = os.pathsep.join(
        [package_parent] + ([inherited_path] if inherited_path else [])
    )
    store = RunStore(tmp_path / "output")
    program = """
import sys
from cppulse.errors import PublicationConflict
from cppulse.run_store import RunStore
try:
    RunStore(sys.argv[1]).begin('competing-process')
except PublicationConflict:
    sys.exit(0)
sys.exit(1)
"""
    with store.begin("owner"):
        result = subprocess.run(
            [sys.executable, "-c", program, str(store.root)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env=child_environment,
        )
        assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("policy_mismatch", [False, True])
def test_full_policy_assessment_bundle_publication(
    tmp_path: Path, policy_mismatch: bool
) -> None:
    """Persist synthetic linked contracts; this does not execute the named tests."""
    policy, assessment = passed_policy_assessment()
    if policy_mismatch:
        assessment["policy"]["sha256"] = "0" * 64
    store = RunStore(tmp_path / "output")
    with store.begin("run-1") as stage:
        documents = [
            ("findings", "source", source_document()),
            ("receipt", "execution_receipt", receipt_document()),
            ("evidence", "evidence", evidence_document()),
            ("policy", "policy", policy),
            ("assessment", "assessment", assessment),
        ]
        for artifact_id, kind, document in documents:
            stage.write_json(
                f"artifacts/{artifact_id}.json",
                document,
                artifact_id=artifact_id,
                contract=kind,
            )
        manifest = manifest_document()
        manifest["artifacts"] = stage.artifacts
        if policy_mismatch:
            with pytest.raises(ContractError, match="Assessment policy"):
                stage.publish(manifest)
            assert not (store.root / "runs/run-1").exists()
            assert not (store.root / "latest_attempt.json").exists()
            assert not (store.root / "latest.json").exists()
        else:
            snapshot = stage.publish(manifest)
            snapshot.verify()
            assert snapshot.read_json("assessment") == assessment
            assert store.resolve_latest_attempt().run_id == "run-1"
            assert store.resolve_latest().run_id == "run-1"


def test_multiple_policy_artifacts_are_explicitly_rejected(tmp_path: Path) -> None:
    policy, _ = passed_policy_assessment()
    store = RunStore(tmp_path / "output")
    with store.begin("policies") as stage:
        stage.write_json("one.json", policy, artifact_id="one", contract="policy")
        stage.write_json("two.json", policy, artifact_id="two", contract="policy")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        with pytest.raises(ContractError, match="one policy"):
            stage.publish(manifest)
    assert not (store.root / "runs/policies").exists()
    assert not (store.root / "latest_attempt.json").exists()


@pytest.mark.parametrize(
    ("first_id", "first_path", "second_id", "second_path"),
    [
        ("one", "foo", "foo", "bar"),
        ("foo", "one", "bar", "foo"),
        ("one", "FOO", "foo", "bar"),
    ],
)
def test_artifact_id_path_cross_aliases_are_rejected(
    tmp_path: Path, first_id: str, first_path: str, second_id: str, second_path: str
) -> None:
    """ID-or-path reads must never acquire an ambiguous inventory reference."""
    with RunStore(tmp_path / "output").begin("aliases") as stage:
        stage.write_json(
            first_path, source_document(), artifact_id=first_id, contract="source"
        )
        with pytest.raises(PublicationConflict, match="collides"):
            stage.write_json(
                second_path,
                source_document(),
                artifact_id=second_id,
                contract="source",
            )


def test_real_source_verification_rejects_same_size_input_mutation(
    tmp_path: Path,
) -> None:
    from cppulse.identities import snapshot_inputs, verify_inputs

    source_root = tmp_path / "source"
    source_root.mkdir()
    selected = source_root / "main.cpp"
    selected.write_text("int main() { return 0; }\n")
    source = snapshot_inputs(source_root, ["main.cpp"])
    store = RunStore(tmp_path / "output")

    def check_selected_source() -> None:
        errors = verify_inputs(source_root, source)
        if errors:
            raise InputChanged("; ".join(errors))

    for run_id in ("clean", "changed"):
        with store.begin(run_id) as stage:
            stage.write_json("source.json", source, contract="source")
            manifest = manifest_document()
            manifest.update(run_id=run_id, source=source, artifacts=stage.artifacts)
            if run_id == "clean":
                snapshot = stage.publish(manifest, source_check=check_selected_source)
                assert snapshot.manifest["input_verification"] == "verified"
            else:
                selected.write_text("int main() { return 1; }\n")
                assert selected.stat().st_size == source["files"][0]["size_bytes"]
                with pytest.raises(InputChanged, match="content differs"):
                    stage.publish(manifest, source_check=check_selected_source)
    assert store.resolve_latest().run_id == "clean"
    assert store.resolve_latest_attempt().run_id == "clean"
    assert not (store.root / "runs/changed").exists()
