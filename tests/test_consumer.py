"""Consumer declarations do not invent verification or a shared source identity."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from cppulse.consumer import (
    declare_consumer_matrix,
    describe_distribution,
    persist_consumer_documents,
)
from cppulse.contracts import validate
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import snapshot_inputs, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from test_consumer_contracts import configuration
from test_contracts_v2 import manifest_document


@pytest.fixture()
def selected_run(tmp_path: Path) -> tuple[RunSnapshot, Path]:
    """Retain real fixture bytes, with no claim that this fake archive was built."""
    workspace = tmp_path / "project"
    workspace.mkdir()
    header = workspace / "demo.hpp"
    header.write_text("// Clearly synthetic declaration input.\n")
    archive = workspace / "libdemo.a"
    archive.write_bytes(b"clearly synthetic distribution bytes, not an archive\n")
    source = snapshot_inputs(workspace, ["demo.hpp"], kind="library")

    def check() -> None:
        changed = verify_inputs(workspace, source)
        if changed:
            raise InputChanged("; ".join(changed))

    store = RunStore(tmp_path / "store")
    with store.begin() as stage:
        stage.copy_artifact("package", archive, "inputs/libdemo.a")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, source=source, artifacts=stage.artifacts)
        return stage.publish(manifest, source_check=check), workspace


def case() -> dict[str, Any]:
    """Declare an expected context and check without claiming either exists."""
    return {
        "id": "consumer-cpp17",
        "required": True,
        "context_id": "not-yet-executed",
        "configuration": configuration(),
        "tests": ["required-application-test"],
        "instantiations": ["selected<int>"],
        "self_containment_headers": ["include/demo.hpp"],
        "usage_ids": [],
    }


def test_selected_subject_uses_retained_byte_identity_and_source_subset(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, _ = selected_run
    original = snapshot.manifest
    document = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
        source_files=["demo.hpp"],
    )
    validate("distribution_subject", document)
    descriptor = original["artifacts"][0]
    assert document["distribution_files"] == [
        {
            "path": "lib/libdemo.a",
            "artifact_id": "package",
            "sha256": descriptor["sha256"],
            "size_bytes": descriptor["size_bytes"],
        }
    ]
    assert document["source_files"] == original["source"]["files"]
    assert document["source_relation"] == "selected_sources"
    assert snapshot.manifest == original


def test_distribution_only_does_not_claim_upstream_source_in_consumer_run(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, _ = selected_run
    document = describe_distribution(
        snapshot,
        subject_id="imported-package",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    assert document["source_relation"] == "distribution_only"
    assert document["source_files"] == []
    assert document["source_digest"] == snapshot.manifest["source"]["digest"]
    assert document["limitations"]


@pytest.mark.parametrize("source", ["absent.hpp", "../demo.hpp", "/demo.hpp"])
def test_source_subset_must_belong_to_the_owning_manifest(
    selected_run: tuple[RunSnapshot, Path], source: str
) -> None:
    snapshot, _ = selected_run
    with pytest.raises(ContractError):
        describe_distribution(
            snapshot,
            subject_id="demo",
            kind="compiled",
            distribution_files={"lib/libdemo.a": "package"},
            source_files=[source],
        )


@pytest.mark.parametrize("artifact", ["absent", "inputs/libdemo.a"])
def test_distribution_selection_requires_an_exact_artifact_id(
    selected_run: tuple[RunSnapshot, Path], artifact: str
) -> None:
    snapshot, _ = selected_run
    with pytest.raises(ContractError):
        describe_distribution(
            snapshot,
            subject_id="demo",
            kind="compiled",
            distribution_files={"lib/libdemo.a": artifact},
        )


def test_different_logical_names_cannot_alias_one_artifact(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, _ = selected_run
    with pytest.raises(ContractError):
        describe_distribution(
            snapshot,
            subject_id="demo",
            kind="compiled",
            distribution_files={"lib/a.a": "package", "lib/b.a": "package"},
        )


def test_matrix_remains_a_declaration_when_context_and_tests_are_missing(
    selected_run: tuple[RunSnapshot, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_execution(*_: Any, **__: Any) -> None:
        raise AssertionError("A declaration must not run project commands")

    monkeypatch.setattr("subprocess.run", no_execution)
    snapshot, _ = selected_run
    subject = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    expected = case()
    matrix = declare_consumer_matrix(
        snapshot, subject, matrix_id="requirements", cases=[expected]
    )
    validate("consumer_matrix", matrix)
    assert matrix["cases"] == [expected]
    assert matrix["cases"][0]["usage_ids"] == []
    assert "status" not in matrix["cases"][0]
    assert matrix["limitations"]
    expected["tests"].clear()
    assert matrix["cases"][0]["tests"] == ["required-application-test"]


def test_matrix_rejects_a_foreign_subject_identity(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, _ = selected_run
    subject = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    foreign = deepcopy(subject)
    foreign["source_digest"] = "f" * 64
    with pytest.raises(ContractError):
        declare_consumer_matrix(
            snapshot, foreign, matrix_id="requirements", cases=[case()]
        )


def test_corrupt_retained_distribution_is_rejected_before_description(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, _ = selected_run
    (snapshot.path / "inputs/libdemo.a").write_bytes(b"changed\n")
    with pytest.raises(IntegrityError):
        describe_distribution(
            snapshot,
            subject_id="demo",
            kind="compiled",
            distribution_files={"lib/libdemo.a": "package"},
        )


def test_derived_declarations_preserve_parent_bytes_and_source_identity(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, workspace = selected_run
    subject = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    matrix = declare_consumer_matrix(
        snapshot, subject, matrix_id="requirements", cases=[case()]
    )
    original = snapshot.manifest
    derived = persist_consumer_documents(
        snapshot,
        [("distribution_subject", subject), ("consumer_matrix", matrix)],
        workspace=workspace,
        store=snapshot._root,
    )
    derived.verify()
    assert derived.run_id != snapshot.run_id
    assert derived.manifest["source"] == original["source"]
    assert derived.manifest["input_verification"] == "verified"
    assert derived.read_bytes("package") == snapshot.read_bytes("package")
    for descriptor in original["artifacts"]:
        assert descriptor in derived.manifest["artifacts"]
    assert snapshot.manifest == original
    assert (
        persist_consumer_documents(
            derived,
            [("distribution_subject", subject), ("consumer_matrix", matrix)],
            workspace=workspace,
            store=snapshot._root,
        ).run_id
        == derived.run_id
    )


def test_changed_source_does_not_publish_a_new_declaration_attempt(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, workspace = selected_run
    subject = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    pointers = {
        name: (snapshot._root / name).read_bytes()
        for name in ["latest.json", "latest_attempt.json"]
    }
    (workspace / "demo.hpp").write_text("// changed after source capture\n")
    with pytest.raises(InputChanged):
        persist_consumer_documents(
            snapshot,
            [("distribution_subject", subject)],
            workspace=workspace,
            store=snapshot._root,
        )
    assert all(
        (snapshot._root / name).read_bytes() == content
        for name, content in pointers.items()
    )


def test_declaration_metadata_cap_is_checked_before_publication(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, workspace = selected_run
    subject = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    with pytest.raises(IntegrityError, match="metadata"):
        persist_consumer_documents(
            snapshot,
            [("distribution_subject", subject)],
            workspace=workspace,
            store=snapshot._root,
            max_metadata_bytes=64,
        )


def test_unverified_parent_is_not_upgraded_by_retaining_declarations(
    selected_run: tuple[RunSnapshot, Path],
) -> None:
    snapshot, workspace = selected_run
    store = RunStore(workspace.parent / "unverified-store")
    with store.begin() as stage:
        for entry in snapshot.manifest["artifacts"]:
            stage.copy_artifact(
                entry["id"], snapshot.path / entry["path"], entry["path"]
            )
        manifest = snapshot.manifest
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        unverified = stage.publish(manifest)
    assert unverified.manifest["input_verification"] == "unverified"
    subject = describe_distribution(
        unverified,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    derived = persist_consumer_documents(
        unverified,
        [("distribution_subject", subject)],
        workspace=workspace,
        store=store,
    )
    assert derived.manifest["input_verification"] == "unverified"


def test_imported_claims_cannot_be_published_as_current_local_declarations(
    selected_run: tuple[RunSnapshot, Path], tmp_path: Path
) -> None:
    from cppulse.transfer import export_bundle

    snapshot, workspace = selected_run
    imported = export_bundle({"upstream": snapshot}, tmp_path / "transfer").open_run(
        "upstream"
    )
    subject = describe_distribution(
        snapshot,
        subject_id="demo",
        kind="compiled",
        distribution_files={"lib/libdemo.a": "package"},
    )
    with pytest.raises(ContractError, match="imported claims"):
        persist_consumer_documents(
            imported,
            [("distribution_subject", subject)],
            workspace=workspace,
            store=tmp_path / "local-store",
        )
