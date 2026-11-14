"""Public baseline/finding dispatch preserves typed source and foreign namespaces."""

from __future__ import annotations

from pathlib import Path

import pytest

from cppulse.consumer import RetainedBlob
from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.run_store import RunStore
from cppulse.workflows import _derive, create_baseline, check_findings
from test_collection import documents
from test_findings import normalized, SCOPE


def test_baseline_and_repeated_finding_checks_share_no_policy_gate(
    tmp_path: Path,
) -> None:
    snapshot = normalized(tmp_path)
    store = snapshot.path.parents[1]
    request = {
        "version": "2.0.0",
        "baseline_id": "reviewed",
        **SCOPE,
        "reason": "Explicitly synthetic baseline integration fixture",
    }
    result = create_baseline(snapshot, request, workspace=tmp_path, store=store)
    validate("workflow_result", result)
    assert result["status"] == "completed" and result["policy_gate"] is None
    reader = RunStore.open_existing(store)
    baseline = reader.open_run(result["final_run"]["run_id"])
    selected = {
        "source": "local_run",
        "store": str(store),
        "run_id": baseline.run_id,
        "manifest_sha256": baseline.manifest_sha256,
        "artifact_id": result["baseline_artifact_id"],
    }
    checking = {"version": "2.0.0", "baseline": selected, **SCOPE, "max_new": 0}
    first = check_findings(baseline, checking, workspace=tmp_path, store=store)
    validate("check_result", first)
    assert first["status"] == "passed" and first["policy_sha256"] is None
    current = reader.open_run(first["run"]["run_id"])
    second = check_findings(current, checking, workspace=tmp_path, store=store)
    assert second["status"] == "passed"
    final = reader.open_run(second["run"]["run_id"])
    assert final.manifest["source"] == snapshot.manifest["source"]
    assert documents(final, "finding_comparison")[-1]["counts"]["unchanged"] == 1
    assert not documents(final, "assessment")
    with pytest.raises(ContractError):
        create_baseline(baseline, request, workspace=tmp_path, store=store)


def test_identical_generic_roles_are_reused_without_overwriting(tmp_path: Path) -> None:
    snapshot = normalized(tmp_path)
    blob = RetainedBlob("retained-review", "review/retained.json", b"{}")
    first = _derive(
        snapshot,
        workspace=tmp_path,
        store=snapshot.path.parents[1],
        operation="first-role",
        blobs=[blob],
        reason="Explicit immutable role fixture",
    )
    second = _derive(
        first,
        workspace=tmp_path,
        store=snapshot.path.parents[1],
        operation="second-role",
        blobs=[blob],
        reason="The same checked byte role is reusable",
    )
    assert second.read_bytes(blob.id) == b"{}"
    assert sum(row["id"] == blob.id for row in second.manifest["artifacts"]) == 1
