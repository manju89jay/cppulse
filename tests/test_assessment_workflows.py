"""Current-source assessments re-evaluate checked facts without project commands."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.presentation import build_snapshot_view
from cppulse.run_store import RunSnapshot, RunStore, StagedRun
from cppulse.workflows import (
    assess_run,
    check_policy,
    collect_request,
    ensure_current_materials,
)
from test_collection import documents
from test_public_workflows import request_for


def captured(workspace: Path) -> RunSnapshot:
    """Execute a clearly synthetic build-job fixture, not a C++ compiler claim."""
    request = request_for(
        workspace,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('original observed material')",
    )
    result = collect_request(request, workspace=workspace, store=workspace / "store")
    return RunStore.open_existing(workspace / "store").open_run(
        result["final_run"]["run_id"],
        manifest_sha256=result["final_run"]["manifest_sha256"],
    )


def selected_policy() -> dict[str, Any]:
    return {
        "version": "2.0.0",
        "id": "observed-fixture-job",
        "policy_version": "1.0.0",
        "standards": [],
        "scope": {"include": ["source.cpp"], "exclude": []},
        "contexts": ["local"],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": "observed-job",
                "title": "Selected job has observed scope",
                "kind": "required_contexts",
                "weight": 1,
                "required": True,
                "parameters": {"contexts": ["local"]},
                "depends_on": [],
            }
        ],
    }


def test_assessment_retains_facts_and_one_active_typed_decision(tmp_path: Path) -> None:
    snapshot = captured(tmp_path)
    result = assess_run(
        snapshot, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    validate("workflow_result", result)
    assert result["status"] == "completed" and result["exit_code"] == 0
    assert (
        result["facts_base_run"]["run_id"]
        == result["raw_run"]["run_id"]
        == snapshot.run_id
    )
    derived = RunStore.open_existing(tmp_path / "store").open_run(
        result["final_run"]["run_id"],
        manifest_sha256=result["final_run"]["manifest_sha256"],
    )
    assert derived.manifest["source"] == snapshot.manifest["source"]
    assert derived.manifest["contexts"] == snapshot.manifest["contexts"]
    assert derived.manifest["config_digest"] == snapshot.manifest["config_digest"]
    assert all(
        entry in derived.manifest["artifacts"]
        for entry in snapshot.manifest["artifacts"]
    )
    assert (
        len(documents(derived, "assessment"))
        == len(documents(derived, "policy"))
        == len(documents(derived, "assessment_lineage"))
        == 1
    )
    assert derived.read_json(result["assessment_artifact_id"])["gate"] == "passed"
    assert (
        RunStore.open_existing(tmp_path / "store").resolve_latest_attempt().run_id
        == derived.run_id
    )


def test_repeated_assess_and_check_use_base_and_archive_old_exact_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    base = captured(tmp_path)
    first = assess_run(
        base, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    reader = RunStore.open_existing(tmp_path / "store")
    parent = reader.open_run(first["final_run"]["run_id"])
    old_bytes = parent.read_bytes(first["assessment_artifact_id"])

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Assessment must not run project commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    second = assess_run(
        parent, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    child = reader.open_run(second["final_run"]["run_id"])
    assert second["facts_base_run"]["run_id"] == base.run_id
    assert second["raw_run"]["run_id"] == parent.run_id
    assert child.read_bytes(first["assessment_artifact_id"]) == old_bytes
    old_descriptor = next(
        row
        for row in child.manifest["artifacts"]
        if row["id"] == first["assessment_artifact_id"]
    )
    assert "contract" not in old_descriptor
    assert len(documents(child, "assessment")) == 1
    checked = check_policy(
        child, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    validate("check_result", checked)
    assert checked["status"] == "passed" and checked["exit_code"] == 0
    latest = reader.resolve_latest_attempt()
    view = build_snapshot_view(latest)
    assert view["assessment"]["artifact_id"] == checked["assessment_artifact_id"]
    assert json.loads(view["assessment"]["raw_json"])["gate"] == "passed"
    with pytest.raises(ContractError):
        build_snapshot_view(
            latest, assessment_artifact_id=first["assessment_artifact_id"]
        )


@pytest.mark.parametrize(
    "path,code", [("source.cpp", "STALE_SOURCE"), ("build/app", "STALE_OUTPUT")]
)
def test_stale_source_or_rebuilt_binary_cannot_reuse_old_test_facts(
    tmp_path: Path, path: str, code: str
) -> None:
    base = captured(tmp_path)
    passed = assess_run(
        base, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    reader = RunStore.open_existing(tmp_path / "store")
    parent = reader.open_run(passed["final_run"]["run_id"])
    old_assessment = parent.read_bytes(passed["assessment_artifact_id"])
    (tmp_path / path).write_text("different current material")
    result = check_policy(
        parent, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    assert result["status"] == "insufficient_evidence" and result["exit_code"] == 3
    assert result["error"]["code"] == code
    latest = reader.resolve_latest_attempt()
    assert latest.run_id == result["run"]["run_id"] != parent.run_id
    assert (
        latest.manifest["status"] == "partial"
        and latest.manifest["input_verification"] == "unverified"
    )
    assert build_snapshot_view(latest)["assessment"] is None
    assert not documents(latest, "assessment")
    assert parent.read_bytes(passed["assessment_artifact_id"]) == old_assessment
    assert any(
        latest.read_bytes(row["id"]) == parent.read_manifest_bytes()
        for row in latest.manifest["artifacts"]
    )
    assert reader.resolve_latest().run_id == parent.run_id


def test_output_change_at_publication_prevents_new_assessment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = captured(tmp_path)
    reader = RunStore.open_existing(tmp_path / "store")
    previous = reader.resolve_latest_attempt().run_id
    method = StagedRun.publish

    def publish(
        stage: StagedRun, manifest: dict[str, Any], **kwargs: Any
    ) -> RunSnapshot:
        (tmp_path / "build/app").write_text("changed during publication")
        return method(stage, manifest, **kwargs)

    monkeypatch.setattr(StagedRun, "publish", publish)
    result = assess_run(
        base, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    assert result["error"]["code"] == "STALE_OUTPUT" and result["exit_code"] == 3
    latest = reader.resolve_latest_attempt()
    assert latest.run_id != previous and latest.manifest["status"] == "partial"
    assert latest.manifest["input_verification"] == "unverified"
    assert build_snapshot_view(latest)["assessment"] is None
    assert reader.resolve_latest().run_id == previous


def test_expiry_is_recomputed_on_repeated_check_without_rerunning_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use an explicitly controlled future test clock; production uses UTC now."""
    import cppulse.workflows as workflows

    base = captured(tmp_path)
    deadline = datetime.now(timezone.utc) + timedelta(hours=1)
    store = RunStore(tmp_path / "store")
    with store.begin() as stage:
        for entry in base.manifest["artifacts"]:
            if entry.get("contract", {}).get("kind") == "evidence":
                value = base.read_json(entry["id"])
                for record in value["records"]:
                    record["expires_at"] = deadline.isoformat().replace("+00:00", "Z")
                stage.write_json(
                    entry["path"], value, contract="evidence", artifact_id=entry["id"]
                )
            else:
                stage.copy_artifact(
                    entry["id"],
                    base.path / entry["path"],
                    entry["path"],
                    entry["media_type"],
                    contract=entry.get("contract"),
                )
        manifest = deepcopy(base.manifest)
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        expiring = stage.publish(
            manifest, source_check=lambda: ensure_current_materials(base, tmp_path)
        )
    monkeypatch.setattr(
        workflows,
        "_now",
        lambda: (deadline - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    )
    first = check_policy(
        expiring, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    assert first["status"] == "passed"
    reader = RunStore.open_existing(tmp_path / "store")
    parent = reader.resolve_latest_attempt()
    monkeypatch.setattr(
        workflows,
        "_now",
        lambda: (deadline + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
    )
    second = check_policy(
        parent, selected_policy(), workspace=tmp_path, store=tmp_path / "store"
    )
    assert second["status"] == "insufficient_evidence" and second["exit_code"] == 3
    assert second["facts_base_run"]["run_id"] == expiring.run_id
    assert second["assessment_artifact_id"] != first["assessment_artifact_id"]
    latest = reader.resolve_latest_attempt()
    assert (
        json.loads(build_snapshot_view(latest)["assessment"]["raw_json"])["gate"]
        == "insufficient_evidence"
    )
