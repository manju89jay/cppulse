"""Transport actual evaluator output over synthetic review facts, not execution."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cppulse.identities import snapshot_inputs, verify_inputs
from cppulse.policy import evaluate_policy
from cppulse.presentation import build_snapshot_view, render_snapshot_html
from cppulse.run_store import RunSnapshot, RunStore
from test_policy import NOW
from test_policy_extensions_contract import review_policy
from test_policy_extensions_runtime import reviews_bundle


def review_snapshot(workspace: Path, *, missing_hashes: bool) -> RunSnapshot:
    """Persist a calculated scoped review decision with exact synthetic bytes."""
    bundle, policy = reviews_bundle(), review_policy()
    (workspace / "src").mkdir()
    (workspace / "src/main.cpp").write_text("int main() { return 0; }\n")
    source = snapshot_inputs(workspace, ["src/main.cpp"], inventory_complete=True)
    bundle["run_manifest"]["source"] = source
    for receipt in bundle["execution_receipt"]:
        receipt["source_digest"] = source["digest"]
    bundle["evidence"]["source_digest"] = source["digest"]
    bundle["evidence"]["records"][0]["review_details"]["source_digest"] = source[
        "digest"
    ]
    store = RunStore(workspace / "store")
    report = workspace / "reviewed-report.txt"
    report.write_text("Clearly synthetic reviewed report bytes.\n")
    with store.begin(bundle["run_manifest"]["run_id"]) as stage:
        descriptor = stage.copy_artifact("findings", report, "facts/reviewed.txt")
        details = bundle["evidence"]["records"][0]["review_details"]
        details["reviewed_artifact_sha256"] = {"findings": descriptor["sha256"]}
        if missing_hashes:
            del details["reviewed_artifact_sha256"]
        for receipt in bundle["execution_receipt"]:
            stage.write_json(
                "facts/" + receipt["id"] + ".json",
                receipt,
                artifact_id=receipt["id"],
                contract="execution_receipt",
            )
        stage.write_json("facts/evidence.json", bundle["evidence"], contract="evidence")
        stage.write_json("facts/policy.json", policy, contract="policy")
        manifest = bundle["run_manifest"]
        manifest["artifacts"] = stage.artifacts
        assessment = evaluate_policy(policy, bundle, generated_at=NOW)
        stage.write_json("facts/assessment.json", assessment, contract="assessment")
        manifest["artifacts"] = stage.artifacts

        def check_source() -> None:
            assert verify_inputs(workspace, source) == []

        return stage.publish(manifest, source_check=check_source)


@pytest.mark.parametrize("missing_hashes", [False, True])
def test_api_and_html_preserve_calculated_profile12_review_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_hashes: bool
) -> None:
    """A presentation must copy the stored gate, links, and identity limitation."""
    from cppulse.report_engine import api

    snapshot = review_snapshot(tmp_path, missing_hashes=missing_hashes)
    expected = snapshot.read_json("assessment")
    view = build_snapshot_view(snapshot)
    assert json.loads(view["assessment"]["raw_json"]) == expected
    expected_gate = "insufficient_evidence" if missing_hashes else "passed"
    assert expected["gate"] == expected_gate
    html = render_snapshot_html(view)
    assert expected_gate in html
    assert "self-declared" in html
    assert "review:review" in html
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "store"))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    api._json_cache.clear()
    response = TestClient(api.app).get(
        "/api/v1/view",
        params={
            "run_id": snapshot.run_id,
            "manifest_sha256": snapshot.manifest_sha256,
        },
    )
    assert response.status_code == 200
    actual = response.json()
    assert actual["assessment"]["raw_json"] == view["assessment"]["raw_json"]
    assert actual["assessment"]["display"]["gate"] == expected_gate
