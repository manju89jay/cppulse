"""Observable profile 1.2 behavior over explicitly synthetic closed facts."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from cppulse.contracts import validate_bundle
from cppulse.errors import ContractError
from cppulse.policy import evaluate_policy
from test_maintenance_metrics_contract import bound_metric_bundle
from test_policy import NOW, approval, facts as test_facts
from test_policy_extensions_contract import declared_review, metric_policy, review_policy


def metrics_bundle(values: tuple[int, ...] = (2, 7)) -> dict[str, Any]:
    """Reuse synthetic observed lineage; these numbers are not execution proof."""
    bundle = bound_metric_bundle()
    metrics = bundle["analysis_metrics"]
    metrics["items"][2]["value"] = len(values)
    for index, value in enumerate(values):
        metrics["items"].append(
            {
                "id": f"complexity-{index}",
                "file": "src/main.cpp",
                "symbol": f"fixture-function-{index}",
                "context_id": "parse-main",
                "metric": "cyclomatic_complexity",
                "metric_version": "cppulse-metrics-1",
                "value": value,
                "units": "count",
                "availability": "available",
                "location": {"line": 1, "column": 1, "end_line": 1, "end_column": 2},
                "limitations": [],
            }
        )
    return bundle


def metric_selected(**parameters: Any) -> dict[str, Any]:
    """Select one declared job; actual parse context is deliberately different."""
    policy = metric_policy()
    policy["contexts"] = ["native"]
    policy["scope"] = {"include": ["src/**/*.cpp"], "exclude": []}
    policy["controls"][0]["parameters"].update(parameters)
    return policy


def reviews_bundle() -> dict[str, Any]:
    """A declared review with metadata, never an authenticated human approval."""
    bundle = test_facts.__wrapped__()
    bundle["evidence"]["records"] = declared_review()["records"]
    return bundle


def test_numeric_each_reports_real_metric_links_and_preserves_inputs() -> None:
    bundle, policy = metrics_bundle(), metric_selected()
    before = deepcopy((bundle, policy))
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    control = result["controls"][0]
    assert result["gate"] == "passed"
    assert result["evaluator"]["version"] == "1.2.0"
    assert control["context_ids"] == ["native"]
    assert control["fact_ids"] == ["complexity-0", "complexity-1", "functions-main"]
    assert "analysis_inventory:native-inventory" in control["references"]
    assert "metric:complexity-1" in control["references"]
    assert (bundle, policy) == before
    validate_bundle({**bundle, "policy": policy, "assessment": result})


@pytest.mark.parametrize(
    "aggregation,operator,threshold,status",
    [
        ("each", "lte", 7, "passed"),
        ("each", "lt", 7, "failed"),
        ("max", "eq", 7, "passed"),
        ("min", "gte", 2, "passed"),
        ("sum", "eq", 9, "passed"),
        ("mean", "eq", 4.5, "passed"),
        ("mean", "gt", 4.5, "failed"),
        ("min", "gt", 2, "failed"),
        ("max", "lt", 7, "failed"),
    ],
)
def test_explicit_numeric_operators_and_hand_calculated_aggregation(
    aggregation: str, operator: str, threshold: float, status: str
) -> None:
    result = evaluate_policy(
        metric_selected(aggregation=aggregation, operator=operator, threshold=threshold),
        metrics_bundle(),
        generated_at=NOW,
    )
    assert result["controls"][0]["status"] == status
    assert result["controls"][0]["incomplete"] is False


@pytest.mark.parametrize("change", ["missing", "unavailable", "wrong_units", "wrong_method", "wrong_level", "missing_job", "legacy_unbound"])
def test_metric_missingness_or_incompatible_cells_cannot_pass(change: str) -> None:
    bundle, policy = metrics_bundle(), metric_selected()
    if change == "missing":
        del bundle["analysis_metrics"]["items"][-1]
    elif change == "unavailable":
        bundle["analysis_metrics"]["items"][-1].update(value=None, availability="unavailable", limitations=["Measurement unavailable."])
    elif change in {"wrong_units", "wrong_method", "wrong_level"}:
        policy["controls"][0]["parameters"].update(
            {"wrong_units": {"units": "levels"}, "wrong_method": {"metric_version": "another-method"}, "wrong_level": {"level": "file"}}[change]
        )
    elif change == "missing_job":
        policy["contexts"].append("not-observed")
    else:
        bundle["analysis_metrics"].pop("analysis_inventory_id")
        bundle["analysis_metrics"].pop("job_context_id")
        for row in bundle["analysis_metrics"]["items"]:
            row["metric_version"] = "legacy-unbound"
        policy["controls"][0]["parameters"]["metric_version"] = "legacy-unbound"
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    assert result["gate"] == "insufficient_evidence"
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True


def test_numeric_known_violation_survives_a_missing_symbol_and_job() -> None:
    bundle, policy = metrics_bundle((20, 2)), metric_selected()
    del bundle["analysis_metrics"]["items"][-1]
    policy["contexts"].append("missing-job")
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    assert result["gate"] == "failed"
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True


def test_incomplete_mean_does_not_treat_available_subset_as_complete() -> None:
    bundle = metrics_bundle((20, 2))
    del bundle["analysis_metrics"]["items"][-1]
    result = evaluate_policy(metric_selected(aggregation="mean"), bundle, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"


def test_metric_file_level_is_not_silently_promoted_to_a_symbol_measurement() -> None:
    result = evaluate_policy(
        metric_selected(metric="physical_loc", units="lines", level="file", threshold=1),
        metrics_bundle(),
        generated_at=NOW,
    )
    assert result["gate"] == "passed"
    assert result["controls"][0]["fact_ids"] == ["loc-main"]


def test_complete_declared_review_passes_with_explicit_identity_limits() -> None:
    bundle, policy = reviews_bundle(), review_policy()
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    assert result["gate"] == "passed"
    assert result["controls"][0]["evidence_ids"] == ["review"]
    assert result["controls"][0]["incomplete"] is False
    assert "declared" in result["controls"][0]["reason"].lower()
    assert any("authenticated" in text for text in result["limitations"])


@pytest.mark.parametrize("change", ["legacy", "wrong_source", "future_review", "future_recording", "expired", "missing_artifact", "missing_id", "unauthorized", "wrong_scope", "wrong_context", "unusable"])
def test_declared_review_provenance_and_scope_are_required(change: str) -> None:
    bundle, policy = reviews_bundle(), review_policy()
    record = bundle["evidence"]["records"][0]
    if change == "legacy":
        record.pop("review_details")
    elif change == "wrong_source":
        record["review_details"]["source_digest"] = "b" * 64
    elif change == "future_review":
        record["review_details"].update(reviewed_at="2026-11-13T13:00:00Z", recorded_at="2026-11-13T13:01:00Z")
    elif change == "future_recording":
        record["review_details"]["recorded_at"] = "2026-11-13T13:00:00Z"
    elif change == "expired":
        record["expires_at"] = NOW
    elif change == "missing_artifact":
        policy["controls"][0]["parameters"]["required_artifact_ids"].append("missing")
    elif change == "missing_id":
        policy["controls"][0]["parameters"]["evidence_ids"].append("missing")
    elif change == "unauthorized":
        record["reviewer"] = "not-configured"
    elif change == "wrong_scope":
        record["scope"]["files"] = []
    elif change == "wrong_context":
        policy["contexts"].append("missing-job")
    else:
        record["usability"] = "stale"
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    assert result["gate"] == "insufficient_evidence"
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True


def test_repeated_records_from_one_declared_id_do_not_meet_two_reviewer_quorum() -> None:
    bundle, policy = reviews_bundle(), review_policy()
    second = deepcopy(bundle["evidence"]["records"][0])
    second["id"] = "another-review"
    bundle["evidence"]["records"].append(second)
    policy["controls"][0]["parameters"].update(evidence_ids=["review", "another-review"], minimum_reviewers=2)
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    second["reviewer"] = "reviewer-bob"
    assert evaluate_policy(policy, bundle, generated_at=NOW)["gate"] == "passed"


def test_declared_rejection_fails_even_when_other_reviews_or_contexts_are_missing() -> None:
    bundle, policy = reviews_bundle(), review_policy()
    bundle["evidence"]["records"][0]["status"] = "failed"
    policy["controls"][0]["parameters"]["evidence_ids"].append("missing")
    policy["contexts"].append("missing-job")
    policy["controls"][0]["allow_deviation"] = True
    result = evaluate_policy(policy, bundle, generated_at=NOW, deviations=[approval(bundle)])
    assert result["gate"] == "failed"
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True
    assert result["deviations"][0]["active"] is False
    assert result["scores"]["readiness"] == 0


def test_profile_12_is_pure_and_does_not_inspect_project_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import socket
    import subprocess

    bundle, policy = metrics_bundle(), metric_selected()
    evaluate_policy(policy, bundle, generated_at=NOW)

    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Pure policy evaluation attempted external I/O")

    monkeypatch.setattr(Path, "open", reject)
    monkeypatch.setattr(os, "getenv", reject)
    monkeypatch.setattr(subprocess, "run", reject)
    monkeypatch.setattr(socket, "socket", reject)
    assert evaluate_policy(policy, bundle, generated_at=NOW)["gate"] == "passed"
    assert evaluate_policy(review_policy(), reviews_bundle(), generated_at=NOW)["gate"] == "passed"


def test_stored_profile12_assessment_cannot_invent_a_positive_metric_result() -> None:
    bundle, policy = metrics_bundle(), metric_selected()
    result = evaluate_policy(policy, bundle, generated_at=NOW)
    bundle["analysis_metrics"]["items"][-1]["value"] = 20
    with pytest.raises(ContractError):
        validate_bundle({**bundle, "policy": policy, "assessment": result})
