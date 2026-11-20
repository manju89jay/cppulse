"""Checked view/render regressions; synthetic transport fixtures claim no execution."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError, CppulseError, IntegrityError
from cppulse.identities import digest_json
from cppulse.presentation import (
    build_snapshot_view,
    render_snapshot_html,
    render_snapshot_json,
    render_snapshot_pdf,
)
from cppulse.run_store import RunSnapshot, RunStore
from test_contracts_v2 import (
    evidence_document,
    manifest_document,
    passed_policy_assessment,
    receipt_document,
    source_document,
)


def legacy_documents() -> dict[str, dict[str, Any]]:
    """Return valid empty prototype documents with no accuracy/verification claim."""
    return {
        "findings": {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/synthetic",
                "analyzed_at": "2026-11-13T10:00:00Z",
                "file_count": 0,
                "total_loc": 0,
            },
            "findings": [],
            "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
        },
        "git_metrics": {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/synthetic",
                "analyzed_at": "2026-11-13T10:00:00Z",
                "commit_range": "synthetic",
                "total_commits": 0,
            },
            "file_metrics": [],
            "knowledge_silos": [],
        },
        "risk_scores": {
            "version": "1.0.0",
            "metadata": {
                "generated_at": "2026-11-13T10:00:00Z",
                "model_type": "heuristic",
                "feature_count": 0,
                "profile": "default",
                "experimental": True,
                "limitations": ["Synthetic unavailable legacy ranking fixture."],
            },
            "health_score": {"overall": None, "status": "no_data", "by_category": {}},
            "file_risks": [],
            "hotspots": [],
        },
        "roadmap": {"version": "1.0.0", "items": []},
    }


def publish_snapshot(
    tmp_path: Path,
    *,
    gate: str = "passed",
    run_id: str = "run-1",
    status: str = "completed",
    assessed: bool = True,
    legacy: bool = False,
    duplicate_assessment: bool = False,
    duplicate_legacy: bool = False,
    weight: int | float = 1,
    lexical_weight: str | None = None,
    reason: str = "Synthetic transport outcome; no tool execution.",
) -> RunSnapshot:
    """Persist explicitly synthetic linked contracts for presentation tests only."""
    store = RunStore(tmp_path / "store")
    policy, assessment = passed_policy_assessment()
    assessment["run_id"] = run_id
    receipt = receipt_document()
    evidence = evidence_document()
    control = assessment["controls"][0]
    policy["controls"][0]["weight"] = control["weight"] = weight
    assessment["policy"]["sha256"] = digest_json(policy)
    control["reason"] = reason
    assessment["gate"] = gate
    if gate == "failed":
        control["status"] = "failed"
        receipt.update(status="failed", exit_code=1)
        receipt["tests"].update(passed=0, failed=1)
        evidence["records"][0]["status"] = "failed"
        assessment["weights"] = {"passed": 0, "failed": weight, "unknown": 0}
        assessment["scores"] = {
            "readiness": 0,
            "evidence_completeness": 100,
            "observed_satisfaction": 0,
            "maximum_possible_readiness": 0,
        }
    elif gate == "insufficient_evidence":
        control.update(status="unknown", incomplete=True)
        receipt.update(
            status="skipped", exit_code=None, reason="Synthetic test was not executed"
        )
        receipt.pop("tests")
        evidence["records"][0].update(status="skipped", usability="missing")
        assessment["weights"] = {"passed": 0, "failed": 0, "unknown": weight}
        assessment["scores"] = {
            "readiness": 0,
            "evidence_completeness": 0,
            "observed_satisfaction": None,
            "maximum_possible_readiness": 100,
        }
    else:
        assessment["weights"] = {"passed": weight, "failed": 0, "unknown": 0}
    with store.begin(run_id) as stage:
        for identifier, kind, document in [
            ("findings", "source", source_document()),
            ("receipt", "execution_receipt", receipt),
            ("evidence", "evidence", evidence),
            ("policy", "policy", policy),
        ]:
            stage.write_json(
                f"facts/{identifier}.json",
                document,
                artifact_id=identifier,
                contract=kind,
            )
        if assessed:
            raw = json.dumps(assessment, sort_keys=True, indent=2) + "\n"
            if lexical_weight:
                raw = raw.replace(str(weight), lexical_weight)
            path = tmp_path / "raw-assessment.json"
            path.write_text(raw)
            stage.copy_artifact(
                "selected-assessment",
                path,
                "assessment/selected.json",
                "application/json",
                contract="assessment",
            )
            if duplicate_assessment:
                stage.copy_artifact(
                    "other-assessment",
                    path,
                    "assessment/other.json",
                    "application/json",
                    contract="assessment",
                )
        if legacy:
            for kind, document in legacy_documents().items():
                stage.write_json(
                    f"legacy/{kind}.json",
                    document,
                    artifact_id="legacy-" + kind,
                    contract=(kind, "prototype_v1"),
                )
            if duplicate_legacy:
                stage.write_json(
                    "legacy/other-findings.json",
                    legacy_documents()["findings"],
                    artifact_id="other-findings",
                    contract=("findings", "prototype_v1"),
                )
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, status=status, artifacts=stage.artifacts)
        manifest["limitations"] = [
            "Synthetic presentation transport fixture; no execution, accuracy or authenticity claim."
        ]
        if status != "completed":
            manifest["stages"][0].update(
                status="cancelled" if status == "cancelled" else "error",
                reason="Synthetic incomplete stage",
            )
        return stage.publish(manifest)


@pytest.mark.parametrize("gate", ["passed", "failed", "insufficient_evidence"])
def test_view_copies_stored_gate_controls_scores_and_original_byte_pins(
    tmp_path: Path, gate: str
) -> None:
    snapshot = publish_snapshot(tmp_path, gate=gate)
    view = build_snapshot_view(snapshot)
    validate("snapshot_view", view)
    assert view["run"]["manifest_sha256"] == snapshot.manifest_sha256
    assert view["run_manifest_json"].encode() == snapshot.read_manifest_bytes()
    selected = view["assessment"]
    assert selected["raw_json"].encode() == snapshot.read_bytes("selected-assessment")
    original = json.loads(selected["raw_json"])
    assert selected["display"]["gate"] == original["gate"] == gate
    assert selected["display"]["scores"] == {
        key: None if value is None else str(value)
        for key, value in original["scores"].items()
    }
    assert (
        selected["display"]["controls"][0]["status"]
        == original["controls"][0]["status"]
    )
    assert json.loads(render_snapshot_json(view)) == view
    assert gate in render_snapshot_html(view)


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_incomplete_unassessed_runs_show_facts_gaps_and_no_invented_gate(
    tmp_path: Path, status: str
) -> None:
    snapshot = publish_snapshot(tmp_path, status=status, assessed=False)
    view = build_snapshot_view(snapshot)
    assert view["run"]["status"] == status
    assert view["run"]["input_verification"] == "unverified"
    assert view["assessment"] is None
    assert view["facts"]
    assert any(gap["kind"] == "assessment" for gap in view["gaps"])
    html = render_snapshot_html(view)
    assert "Not assessed" in html and status in html


def test_empty_snapshot_legacy_slots_do_not_read_unrelated_flat_exports(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path, assessed=False)
    (snapshot.path.parent.parent / "risk_scores.json").write_text(
        "not trusted flat data"
    )
    view = build_snapshot_view(snapshot)
    assert all(slot is None for slot in view["legacy"].values())
    assert "Unavailable" in render_snapshot_html(view)


def test_explicit_assessment_selector_and_ambiguity_are_artifact_based(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path, duplicate_assessment=True)
    with pytest.raises(ContractError):
        build_snapshot_view(snapshot)
    view = build_snapshot_view(snapshot, assessment_artifact_id="other-assessment")
    assert view["assessment"]["artifact_id"] == "other-assessment"
    for identifier in ["missing", "receipt", "assessment/selected.json"]:
        with pytest.raises(ContractError):
            build_snapshot_view(snapshot, assessment_artifact_id=identifier)


def test_legacy_slots_are_checked_optional_and_keep_all_seven_sections(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path, legacy=True)
    view = build_snapshot_view(snapshot)
    for kind, slot in view["legacy"].items():
        assert slot["document"] == legacy_documents()[kind]
        assert slot["raw_json"].encode() == snapshot.read_bytes(slot["artifact_id"])
    html = render_snapshot_html(view)
    for title in [
        "Executive Summary",
        "Health Score Breakdown",
        "Hotspot Map",
        "Detection Findings",
        "Knowledge Silo Alerts",
        "Bug Prediction",
        "Refactoring Roadmap",
    ]:
        assert title in html
    assert "Experimental" in html
    assert "No score" in html
    assert "No findings recorded" in html
    assert "No hotspots recorded" in html


def test_duplicate_legacy_kind_requires_explicit_ids_and_never_filename_guess(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path, legacy=True, duplicate_legacy=True)
    with pytest.raises(ContractError):
        build_snapshot_view(snapshot)
    view = build_snapshot_view(
        snapshot, legacy_artifact_ids={"findings": "other-findings"}
    )
    assert view["legacy"]["findings"]["artifact_id"] == "other-findings"
    assert view["legacy"]["risk_scores"] is None
    with pytest.raises(ContractError):
        build_snapshot_view(
            snapshot, legacy_artifact_ids={"unregistered": "other-findings"}
        )


def test_large_integer_and_original_decimal_token_are_not_rounded_for_display(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path / "huge", weight=10**400)
    view = build_snapshot_view(snapshot)
    assert view["assessment"]["display"]["weights"]["passed"] == str(10**400)
    assert str(10**400) in render_snapshot_html(view)
    lexical = publish_snapshot(
        tmp_path / "lexical",
        weight=9007199254740992.0,
        lexical_weight="9007199254740993.0",
    )
    assert (
        build_snapshot_view(lexical)["assessment"]["display"]["controls"][0]["weight"]
        == "9007199254740993.0"
    )


def test_html_escapes_stored_messages_and_does_not_load_external_assets(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(
        tmp_path,
        reason='<script>alert("stored")</script> <img src="https://example.invalid/x">',
    )
    html = render_snapshot_html(build_snapshot_view(snapshot))
    assert '<script>alert("stored")</script>' not in html
    assert "&lt;script&gt;" in html
    assert '<img src="https://example.invalid/x">' not in html
    assert "<link " not in html


def test_builder_and_renderers_do_not_evaluate_or_mutate_policy_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.policy

    snapshot = publish_snapshot(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Presentation must not evaluate a policy")

    monkeypatch.setattr(cppulse.policy, "evaluate_policy", forbidden)
    view = build_snapshot_view(snapshot)
    original = deepcopy(view)
    render_snapshot_json(view)
    render_snapshot_html(view)
    assert view == original
    changed = deepcopy(view)
    changed["assessment"]["display"]["gate"] = "failed"
    with pytest.raises(ContractError):
        render_snapshot_html(changed)
    assert build_snapshot_view(snapshot) == original


def test_artifact_corruption_blocks_view_without_old_data_fallback(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path)
    artifact = next(
        row
        for row in snapshot.manifest["artifacts"]
        if row["id"] == "selected-assessment"
    )
    (snapshot.path / artifact["path"]).write_bytes(b"{}")
    with pytest.raises(IntegrityError):
        build_snapshot_view(snapshot)


def test_pdf_is_nonempty_readable_and_contains_same_run_and_gate(
    tmp_path: Path,
) -> None:
    view = build_snapshot_view(publish_snapshot(tmp_path, gate="insufficient_evidence"))
    content = render_snapshot_pdf(view)
    assert content.startswith(b"%PDF-") and len(content) > 2000
    text = subprocess.run(
        ["pdftotext", "-", "-"], input=content, capture_output=True, check=True
    ).stdout.decode()
    assert view["run"]["id"] in text
    assert "insufficient_evidence" in text
    assert view["assessment"]["display"]["policy"]["id"] in text


def test_optional_pdf_backend_failure_is_actionable_without_affecting_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    view = build_snapshot_view(publish_snapshot(tmp_path))
    original_import = builtins.__import__

    def blocked(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.split(".")[0] == "weasyprint":
            raise ModuleNotFoundError("optional PDF backend blocked for regression")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    assert "cppulse" in render_snapshot_html(view)
    with pytest.raises(CppulseError, match="cppulse\\[pdf\\]"):
        render_snapshot_pdf(view)


def test_pdf_links_use_explicit_api_origin_without_fetching_it(tmp_path: Path) -> None:
    view = build_snapshot_view(publish_snapshot(tmp_path))
    content = render_snapshot_pdf(view, base_url="https://explicit-api.invalid/")
    urls = subprocess.run(
        ["pdfinfo", "-url", "-"], input=content, capture_output=True, check=True
    ).stdout.decode()
    assert "https://explicit-api.invalid/api/v1/runs/run-1/artifacts/" in urls
    assert view["run"]["manifest_sha256"] in urls
