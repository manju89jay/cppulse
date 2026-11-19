"""Pure evaluation over synthetic closed facts; these fixtures execute no project."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from importlib import resources
import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.contracts import validate_bundle, validate_evaluation_policy
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.identities import context_identity, digest_json
from cppulse.policy import evaluate_policy
from test_contracts_v2 import (
    context_document,
    evidence_document,
    manifest_document,
    policy_document,
    receipt_document,
)

NOW = "2026-11-13T12:00:00Z"


def control(
    identifier: str = "tests",
    *,
    kind: str = "test_outcomes",
    required: bool = True,
    weight: float = 1,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Declare a control without implying the underlying facts were executed."""
    return {
        "id": identifier,
        "title": identifier,
        "kind": kind,
        "weight": weight,
        "required": required,
        "parameters": (
            {"contexts": ["gcc17"]}
            if kind == "required_contexts"
            else {"evidence_ids": evidence_ids or ["unit-tests"]}
        ),
        "depends_on": [],
    }


@pytest.fixture()
def facts() -> dict[str, Any]:
    manifest = manifest_document()
    manifest["input_verification"] = "verified"
    result = {
        "run_manifest": manifest,
        "execution_receipt": [],
        "evidence": {
            "version": "2.0.0",
            "source_digest": manifest["source"]["digest"],
            "records": [],
        },
    }
    add_result(result)
    return result


@pytest.fixture()
def policy() -> dict[str, Any]:
    result = policy_document()
    result["controls"] = [control()]
    return result


def add_result(
    facts: dict[str, Any],
    identifier: str = "unit-tests",
    *,
    context: str = "gcc17",
    status: str = "passed",
    kind: str = "tests",
    files: list[str] | None = None,
    usability: str = "usable",
    origin: str = "execution",
) -> None:
    """Add a consistent typed receipt/result pair to an in-memory test bundle."""
    record = deepcopy(evidence_document()["records"][0])
    record.update(
        id=identifier,
        context_id=context,
        status=status,
        kind=kind,
        usability=usability,
        origin=origin,
        receipt_id=f"receipt-{identifier}" if origin == "execution" else None,
    )
    record["scope"] = {"files": files if files is not None else ["src/main.cpp"]}
    facts["evidence"]["records"].append(record)
    if origin == "execution":
        receipt = receipt_document()
        receipt.update(
            id=record["receipt_id"],
            context_id=context,
            status="passed" if status in {"passed", "skipped"} else status,
            reason="Synthetic outcome",
            exit_code=0 if status in {"passed", "skipped"} else 1,
        )
        receipt["source_digest"] = facts["run_manifest"]["source"]["digest"]
        if kind == "tests":
            receipt["tests"] = {
                "total": 1,
                "passed": int(status == "passed"),
                "failed": int(status == "failed"),
                "skipped": int(status == "skipped"),
                "errors": int(status == "error"),
            }
        else:
            receipt.pop("tests")
        facts["execution_receipt"].append(receipt)


def add_context(facts: dict[str, Any], identifier: str) -> None:
    context = context_document()
    context["id"] = identifier
    facts["run_manifest"]["contexts"].append(context)


def approval(facts: dict[str, Any], **updates: Any) -> dict[str, Any]:
    result = {
        "id": "approved-exception",
        "control_id": "tests",
        "source_digest": facts["run_manifest"]["source"]["digest"],
        "context_ids": ["gcc17"],
        "reason": "Synthetic approved exception",
        "owner": "fixture-owner",
        "reviewer": "fixture-reviewer",
        "approved_at": "2026-11-13T11:00:00Z",
        "expires_at": "2026-11-14T11:00:00Z",
        "gate": "required_controls",
    }
    result.update(updates)
    return result


def test_passed_test_facts_and_full_policy_identity(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    original = deepcopy((policy, facts))
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "passed"
    assert result["evaluator"] == {"name": "cppulse.policy", "version": "1.0.0"}
    assert result["policy"]["sha256"] == digest_json(policy)
    assert result["weights"] == {"passed": 1, "failed": 0, "unknown": 0}
    assert set(result["scores"].values()) == {100}
    assert result["controls"][0]["context_ids"] == ["gcc17"]
    assert result["controls"][0]["incomplete"] is False
    assert (policy, facts) == original
    validate_bundle({**facts, "policy": policy, "assessment": result})


def test_missing_expected_id_is_unknown_and_not_a_dangling_actual_reference(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    policy["controls"][0]["parameters"]["evidence_ids"].append("missing")
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "insufficient_evidence"
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["evidence_ids"] == ["unit-tests"]
    assert result["controls"][0]["incomplete"] is True
    assert "missing" in result["controls"][0]["reason"]


@pytest.mark.parametrize("verification", ["unverified", None])
@pytest.mark.parametrize("status", ["passed", "failed"])
def test_unverified_source_never_treats_old_pass_or_failure_as_current(
    policy: dict[str, Any], facts: dict[str, Any], verification: str | None, status: str
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status=status)
    if verification is None:
        facts["run_manifest"].pop("input_verification")
    else:
        facts["run_manifest"]["input_verification"] = verification
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["evidence_ids"] == ["unit-tests"]
    assert result["weights"] == {"passed": 0, "failed": 0, "unknown": 1}
    assert "not a current result" in result["controls"][0]["reason"]
    assert result["gate"] == "insufficient_evidence"


@pytest.mark.parametrize(
    "status,usability,origin",
    [
        ("passed", "stale", "execution"),
        ("failed", "mismatched", "execution"),
        ("passed", "usable", "import"),
        ("skipped", "usable", "execution"),
        ("error", "usable", "execution"),
    ],
)
def test_unusable_imported_skipped_and_error_facts_remain_unknown(
    policy: dict[str, Any],
    facts: dict[str, Any],
    status: str,
    usability: str,
    origin: str,
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status=status, usability=usability, origin=origin)
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True


def test_verified_partial_collection_keeps_independently_complete_test_facts(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    facts["run_manifest"]["status"] = "partial"
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "passed"


def test_scope_coverage_is_required_in_each_selected_context(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    add_context(facts, "second")
    policy["contexts"].append("second")
    assert (
        evaluate_policy(policy, facts, generated_at=NOW)["controls"][0]["status"]
        == "unknown"
    )
    add_result(facts, "second-tests", context="second")
    policy["controls"][0]["parameters"]["evidence_ids"].append("second-tests")
    assert evaluate_policy(policy, facts, generated_at=NOW)["gate"] == "passed"


def test_partial_scope_does_not_pass_even_when_named_test_succeeded(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    record = facts["evidence"]["records"][0]
    record["scope"]["files"] = []
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True


def test_required_context_presence_needs_observed_scoped_results_and_allows_observed_failure(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    policy["controls"] = [control("jobs", kind="required_contexts")]
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    assert (
        evaluate_policy(policy, facts, generated_at=NOW)["gate"]
        == "insufficient_evidence"
    )
    add_result(facts, "build", status="failed", kind="build")
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "passed"
    assert result["controls"][0]["evidence_ids"] == ["build"]


def test_missing_requested_context_is_unknown_not_bad_actual_data(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    policy["contexts"].append("expected-later")
    policy["controls"] = [control("jobs", kind="required_contexts")]
    policy["controls"][0]["parameters"]["contexts"].append("expected-later")
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["context_ids"] == ["gcc17", "expected-later"]


def test_optional_unknown_can_meet_explicit_zero_thresholds(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    policy["controls"][0].update(
        required=False, parameters={"evidence_ids": ["not-present"]}
    )
    policy["gates"] = {"minimum_readiness": 0, "minimum_completeness": 0}
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "passed"
    assert result["scores"] == {
        "readiness": 0,
        "evidence_completeness": 0,
        "observed_satisfaction": None,
        "maximum_possible_readiness": 100,
    }


def test_explicit_kind_mismatch_is_the_only_not_applicable_case(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    policy["controls"][0]["applicable_to"] = ["header-only"]
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "not_applicable"
    assert result["controls"][0]["incomplete"] is False
    assert result["weights"] == {"passed": 0, "failed": 0, "unknown": 0}
    assert set(result["scores"].values()) == {None}
    assert result["gate"] == "insufficient_evidence"


def test_dependency_blocks_a_positive_result_but_not_own_definite_failure(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    prerequisite = control("prerequisite", evidence_ids=["missing"])
    dependent = control("dependent")
    dependent["depends_on"] = ["prerequisite"]
    policy["controls"] = [dependent, prerequisite]
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status="failed")
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True


def test_nonapplicable_prerequisite_is_neutral(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    prerequisite = control("prerequisite", evidence_ids=["missing"])
    prerequisite["applicable_to"] = ["header-only"]
    dependent = control("dependent")
    dependent["depends_on"] = ["prerequisite"]
    policy["controls"] = [dependent, prerequisite]
    assert evaluate_policy(policy, facts, generated_at=NOW)["gate"] == "passed"


def test_complete_permitted_deviation_preserves_raw_failure_and_scores(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status="failed")
    policy["controls"][0]["allow_deviation"] = True
    policy["gates"] = {"minimum_readiness": 0, "minimum_completeness": 100}
    result = evaluate_policy(
        policy, facts, generated_at=NOW, deviations=[approval(facts, active=False)]
    )
    assert result["deviations"][0]["active"] is True
    assert result["deviations"][0]["reason"] == "Synthetic approved exception"
    assert result["controls"][0]["status"] == "failed"
    assert result["weights"] == {"passed": 0, "failed": 1, "unknown": 0}
    assert result["scores"]["readiness"] == 0
    assert result["gate"] == "passed"
    policy["gates"]["minimum_readiness"] = 1
    assert (
        evaluate_policy(policy, facts, generated_at=NOW, deviations=[approval(facts)])[
            "gate"
        ]
        == "failed"
    )


@pytest.mark.parametrize(
    "updates",
    [
        {"expires_at": NOW},
        {"approved_at": "2026-11-13T13:00:00Z"},
        {"source_digest": "b" * 64},
        {"context_ids": []},
        {"context_ids": ["other"]},
    ],
)
def test_inactive_deviation_reason_is_computed_even_when_caller_claims_active(
    policy: dict[str, Any], facts: dict[str, Any], updates: dict[str, Any]
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status="failed")
    policy["controls"][0]["allow_deviation"] = True
    result = evaluate_policy(
        policy,
        facts,
        generated_at=NOW,
        deviations=[approval(facts, active=True, **updates)],
    )
    assert result["deviations"][0]["active"] is False
    assert result["deviations"][0]["inactive_reason"]
    assert result["gate"] == "failed"


def test_missing_policy_permission_and_incomplete_failure_cannot_be_waived(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status="failed")
    result = evaluate_policy(
        policy, facts, generated_at=NOW, deviations=[approval(facts)]
    )
    assert result["deviations"][0]["active"] is False
    policy["controls"][0]["allow_deviation"] = True
    policy["controls"][0]["parameters"]["evidence_ids"].append("missing")
    result = evaluate_policy(
        policy, facts, generated_at=NOW, deviations=[approval(facts)]
    )
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True
    assert result["deviations"][0]["active"] is False
    assert result["gate"] == "failed"


@pytest.mark.parametrize(
    "generated",
    ["2026-11-13", "2026-11-13T12:00:00", "2026-11-13T12:00:00+01:00", "not-time"],
)
def test_generated_time_must_be_explicit_utc(
    policy: dict[str, Any], facts: dict[str, Any], generated: str
) -> None:
    with pytest.raises(ContractError, match="UTC|time"):
        evaluate_policy(policy, facts, generated_at=generated)


def test_malformed_actual_facts_and_conflicting_policy_are_errors(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    bad = deepcopy(facts)
    bad["evidence"]["records"][0]["context_id"] = "dangling"
    with pytest.raises(ContractError):
        evaluate_policy(policy, bad, generated_at=NOW)
    bad = deepcopy(facts)
    bad["policy"] = deepcopy(policy)
    bad["policy"]["policy_version"] = "different"
    with pytest.raises(ContractError):
        evaluate_policy(policy, bad, generated_at=NOW)


@pytest.mark.parametrize(
    "kind,parameters",
    [
        (
            "metric_threshold",
            {"metric": "complexity", "operator": "lte", "threshold": 10},
        ),
        ("minimum_coverage", {"minimum": 80, "evidence_ids": ["coverage"]}),
        ("reviewed_evidence", {"evidence_ids": ["review"]}),
    ],
)
def test_future_predicates_are_explicitly_unsupported(
    policy: dict[str, Any], facts: dict[str, Any], kind: str, parameters: dict[str, Any]
) -> None:
    policy["controls"][0].update(kind=kind, parameters=parameters)
    with pytest.raises(UnsupportedVersion):
        evaluate_policy(policy, facts, generated_at=NOW)


def test_evaluation_performs_no_project_io_process_network_or_environment_reads(
    policy: dict[str, Any], facts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    import socket

    # Warm immutable packaged schema resources; those are code/data loading.
    evaluate_policy(policy, facts, generated_at=NOW)

    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Pure evaluation must consume only supplied facts")

    monkeypatch.setattr(subprocess, "run", reject)
    monkeypatch.setattr(socket, "socket", reject)
    monkeypatch.setattr(Path, "open", reject)
    monkeypatch.setattr(os, "getenv", reject)
    assert evaluate_policy(policy, facts, generated_at=NOW)["gate"] == "passed"
    assert json.dumps(policy)


def test_mixed_raw_weights_and_exact_bounds_decide_gate_without_rounding(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    add_result(facts, "failed-tests", status="failed")
    policy["controls"] = [
        control("good", required=False, weight=4),
        control("bad", required=False, weight=2, evidence_ids=["failed-tests"]),
        control("unknown", required=False, weight=4, evidence_ids=["missing"]),
    ]
    policy["gates"] = {"minimum_readiness": 80, "minimum_completeness": 50}
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["weights"] == {"passed": 4, "failed": 2, "unknown": 4}
    assert result["scores"] == {
        "readiness": 40,
        "evidence_completeness": 60,
        "observed_satisfaction": pytest.approx(100 * 4 / 6),
        "maximum_possible_readiness": 80,
    }
    assert result["gate"] == "insufficient_evidence"
    policy["gates"]["minimum_readiness"] = 80.00000000001
    assert evaluate_policy(policy, facts, generated_at=NOW)["gate"] == "failed"
    policy["gates"] = {"minimum_readiness": 40, "minimum_completeness": 60}
    assert evaluate_policy(policy, facts, generated_at=NOW)["gate"] == "passed"


def test_score_display_rounding_cannot_raise_exact_readiness_to_threshold(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    add_result(facts, "failed-tests", status="failed")
    policy["controls"] = [
        control("good", required=False, weight=2),
        control("bad", required=False, evidence_ids=["failed-tests"]),
    ]
    policy["gates"] = {
        "minimum_readiness": 66.66666666666667,
        "minimum_completeness": 100,
    }
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["scores"]["readiness"] == policy["gates"]["minimum_readiness"]
    assert result["gate"] == "failed"  # exact 200/3 is below this JSON decimal


def test_empty_selected_scope_cannot_pass_or_import_an_out_of_scope_failure(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status="failed")
    policy["scope"]["include"] = ["not-selected/**"]
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "insufficient_evidence"
    assert result["controls"][0]["status"] == "unknown"


def test_known_complete_failure_is_not_made_incomplete_by_a_known_failed_prerequisite(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, "first", status="failed")
    add_result(facts, "second", status="failed")
    prerequisite = control("first", required=False, evidence_ids=["first"])
    dependent = control("second", required=False, evidence_ids=["second"])
    dependent["depends_on"] = ["first"]
    policy["controls"] = [dependent, prerequisite]
    policy["gates"] = {"minimum_readiness": 0, "minimum_completeness": 100}
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert [row["status"] for row in result["controls"]] == ["failed", "failed"]
    assert all(row["incomplete"] is False for row in result["controls"])


def test_aggregate_control_requires_exact_all_context_approval(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    add_context(facts, "second")
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status="failed")
    add_result(facts, "second-tests", context="second", status="failed")
    policy["contexts"].append("second")
    policy["controls"][0]["parameters"]["evidence_ids"].append("second-tests")
    policy["controls"][0]["allow_deviation"] = True
    policy["gates"] = {"minimum_readiness": 0, "minimum_completeness": 100}
    denied = evaluate_policy(
        policy, facts, generated_at=NOW, deviations=[approval(facts)]
    )
    assert denied["deviations"][0]["active"] is False
    assert denied["gate"] == "failed"
    allowed = evaluate_policy(
        policy,
        facts,
        generated_at=NOW,
        deviations=[approval(facts, context_ids=["second", "gcc17"])],
    )
    assert allowed["deviations"][0]["active"] is True
    assert allowed["controls"][0]["context_ids"] == ["gcc17", "second"]
    assert allowed["gate"] == "passed"


def test_unknown_control_cannot_be_excepted_and_threshold_gate_requests_are_rejected(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    policy["controls"][0]["allow_deviation"] = True
    policy["controls"][0]["parameters"]["evidence_ids"] = ["missing"]
    result = evaluate_policy(
        policy, facts, generated_at=NOW, deviations=[approval(facts)]
    )
    assert result["deviations"][0]["active"] is False
    assert result["gate"] == "insufficient_evidence"
    with pytest.raises(UnsupportedVersion):
        evaluate_policy(
            policy,
            facts,
            generated_at=NOW,
            deviations=[approval(facts, gate="minimum_readiness")],
        )


def test_omitted_deviation_gate_is_descriptive_and_inactive(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    request = approval(facts)
    request.pop("gate")
    result = evaluate_policy(policy, facts, generated_at=NOW, deviations=[request])
    assert result["deviations"][0]["active"] is False
    assert "explicitly" in result["deviations"][0]["inactive_reason"]


@pytest.mark.parametrize("field", ["reason", "owner", "reviewer"])
def test_blank_approval_claims_are_rejected(
    policy: dict[str, Any], facts: dict[str, Any], field: str
) -> None:
    with pytest.raises(ContractError):
        evaluate_policy(
            policy,
            facts,
            generated_at=NOW,
            deviations=[approval(facts, **{field: " "})],
        )


def test_full_policy_digest_covers_descriptive_metadata_and_list_valued_facts(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    first = evaluate_policy(policy, facts, generated_at=NOW)
    policy["standards"] = [
        {
            "name": "Illustrative organization guide",
            "edition": "example",
            "coverage_note": "Metadata, not a conformity claim",
        }
    ]
    facts["evidence"] = [facts["evidence"]]
    second = evaluate_policy(policy, facts, generated_at=NOW)
    assert first["gate"] == second["gate"] == "passed"
    assert first["policy"]["sha256"] != second["policy"]["sha256"]


def test_duplicate_actual_evidence_is_an_error_not_silently_deduplicated(
    policy: dict[str, Any], facts: dict[str, Any]
) -> None:
    facts["evidence"]["records"].append(deepcopy(facts["evidence"]["records"][0]))
    with pytest.raises(ContractError):
        evaluate_policy(policy, facts, generated_at=NOW)


@pytest.mark.parametrize("kind", ["test_outcomes", "required_contexts"])
@pytest.mark.parametrize("status", ["passed", "failed"])
def test_explicitly_expired_execution_facts_are_unavailable_for_current_controls(
    policy: dict[str, Any],
    facts: dict[str, Any],
    kind: str,
    status: str,
) -> None:
    facts["evidence"]["records"] = []
    facts["execution_receipt"] = []
    add_result(facts, status=status)
    facts["evidence"]["records"][0]["expires_at"] = NOW
    before = deepcopy(facts)
    policy["controls"] = [control(kind=kind)]
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True
    assert result["controls"][0]["evidence_ids"] == ["unit-tests"]
    assert "expired" in result["controls"][0]["reason"].lower()
    assert result["gate"] == "insufficient_evidence"
    assert facts == before


def test_failed_process_label_without_failed_test_counts_is_not_a_waivable_test_failure(
    policy: dict[str, Any],
    facts: dict[str, Any],
) -> None:
    facts["evidence"]["records"][0]["status"] = "failed"
    facts["execution_receipt"][0].update(status="failed", exit_code=1)
    before = deepcopy(facts)
    policy["controls"][0]["allow_deviation"] = True
    policy["gates"] = {"minimum_readiness": 0, "minimum_completeness": 0}
    result = evaluate_policy(
        policy, facts, generated_at=NOW, deviations=[approval(facts)]
    )
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True
    assert result["deviations"][0]["active"] is False
    assert result["gate"] == "insufficient_evidence"
    assert "inconsisten" in result["controls"][0]["reason"].lower()
    assert facts == before


@pytest.mark.parametrize("future", ["manifest", "used_receipt"])
def test_assessment_generation_cannot_precede_its_retained_facts(
    policy: dict[str, Any],
    facts: dict[str, Any],
    future: str,
) -> None:
    if future == "manifest":
        generated_at = "2000-01-01T00:00:00Z"
    else:
        generated_at = NOW
        facts["execution_receipt"][0]["finished_at"] = "2026-11-13T13:00:00Z"
    with pytest.raises(ContractError, match="preced|before|future"):
        evaluate_policy(policy, facts, generated_at=generated_at)


@pytest.mark.parametrize("weight,repeats", [(1e307, 1), (1e308, 1), (1e308, 2)])
def test_large_finite_weights_keep_exact_mass_and_finite_scores(
    policy: dict[str, Any],
    facts: dict[str, Any],
    weight: float,
    repeats: int,
) -> None:
    policy["controls"] = [
        control(f"tests-{index}", weight=weight) for index in range(repeats)
    ]
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["gate"] == "passed"
    assert Fraction(str(result["weights"]["passed"])) == repeats * Fraction(str(weight))
    assert set(result["scores"].values()) == {100}
    json.dumps(result, allow_nan=False)


def test_expired_alternative_does_not_block_complete_current_context_proof(
    policy: dict[str, Any],
    facts: dict[str, Any],
) -> None:
    add_result(facts, "old-result")
    facts["evidence"]["records"][-1]["expires_at"] = NOW
    policy["controls"] = [control("jobs", kind="required_contexts")]
    result = evaluate_policy(policy, facts, generated_at=NOW)
    assert result["controls"][0]["status"] == "passed"
    assert result["controls"][0]["evidence_ids"] == ["unit-tests"]
    assert result["gate"] == "passed"


def test_actual_ctest_snapshot_uses_explicit_test_job_selector(
    tmp_path: Path,
    policy: dict[str, Any],
) -> None:
    """Run a selected C++ fixture; an unused analysis-job declaration is not proof."""
    from cppulse.collection import collect
    from test_collection import ctest_fixture

    plan, source, contexts = ctest_fixture(tmp_path)
    contexts.append(
        context_identity(
            {
                "id": "analysis-job",
                "compiler": {"name": "libclang", "version": "declared-only"},
                "argv": ["-std=c++17"],
                "working_directory": str(tmp_path),
                "language_standard": "c++17",
                "target": None,
                "provenance": "inferred",
                "dependencies": [],
                "limitations": [
                    "Declared role only; this fixture does not execute native analysis."
                ],
            }
        )
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    snapshot.verify()
    documents: dict[str, Any] = {"run_manifest": snapshot.manifest}
    for descriptor in snapshot.manifest["artifacts"]:
        if "contract" not in descriptor:
            continue
        kind = descriptor["contract"]["kind"]
        document = snapshot.read_json(descriptor["id"])
        if kind in documents:
            if not isinstance(documents[kind], list):
                documents[kind] = [documents[kind]]
            documents[kind].append(document)
        else:
            documents[kind] = document
    policy["contexts"] = ["native", "analysis-job"]
    policy["scope"] = {"include": ["**/*.cpp"], "exclude": []}
    policy["controls"] = [
        control(evidence_ids=["native-tests"]),
        control("jobs", kind="required_contexts"),
    ]
    policy["controls"][0]["parameters"]["contexts"] = ["native"]
    policy["controls"][1]["parameters"]["contexts"] = ["native"]
    generated_at = datetime.now(timezone.utc).isoformat()
    result = evaluate_policy(policy, documents, generated_at=generated_at)
    assert result["gate"] == "passed"
    assert all(row["context_ids"] == ["native"] for row in result["controls"])
    assert all(row["incomplete"] is False for row in result["controls"])
    # Without the explicit test-role selection, the unexecuted analysis job
    # remains unknown; its declaration cannot supply test outcomes.
    policy["controls"][0]["parameters"].pop("contexts")
    unknown = evaluate_policy(policy, documents, generated_at=generated_at)
    assert unknown["gate"] == "insufficient_evidence"
    assert unknown["controls"][0]["status"] == "unknown"
    assert unknown["controls"][0]["context_ids"] == ["native", "analysis-job"]


@pytest.mark.parametrize("name", ["starter.json", "organization-example.json"])
def test_packaged_policy_examples_use_explicit_supported_job_scopes(name: str) -> None:
    path = resources.files("cppulse").joinpath("data", "policies", name)
    policy = json.loads(path.read_text(encoding="utf-8"))
    validate_evaluation_policy(policy)
    assert policy["contexts"]
    assert {row["kind"] for row in policy["controls"]} == {
        "test_outcomes",
        "required_contexts",
        "finding_limit",
        "minimum_analysis_coverage",
    }
    assert all(not row.get("allow_deviation", False) for row in policy["controls"])


def analysis_documents(
    tmp_path: Path, *, mutate: Any = None, database: bool = True
) -> tuple[dict[str, Any], str]:
    """Use the gated normalizer on labeled synthetic retained producer records."""
    from cppulse.analysis import persist_native_analysis
    from test_analysis_inventory import native_snapshot

    from test_measured_normalization import add_metrics

    def current_buffers(report: dict[str, Any], root: Path) -> None:
        if mutate is not None:
            mutate(report, root)
        add_metrics(report, root)
        coverage = report["metadata"]["analysis"]["files"]
        measured = report["metadata"]["analysis"]["native_metrics"]["files"]
        assert (
            len(coverage) == len(measured) == 1
        ), "Explicit multi-file fixture required"
        measured[0]["status"] = coverage[0]["status"]
        measured[0]["error_count"] = coverage[0]["error_count"]
        if coverage[0]["status"] != "analyzed" or coverage[0]["error_count"]:
            measured[0]["measurement_complete"] = False
            measured[0]["function_count"] = None

    snapshot, selection = native_snapshot(tmp_path, mutate=current_buffers)
    if not database:
        selection["compilation_database_artifact_id"] = None
    derived = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )
    documents: dict[str, Any] = {"run_manifest": derived.manifest}
    for descriptor in derived.manifest["artifacts"]:
        if descriptor.get("contract", {}).get("version") != "2.0.0":
            continue
        kind = descriptor["contract"]["kind"]
        document = derived.read_json(descriptor["id"])
        if kind in documents:
            documents[kind] = (
                documents[kind]
                if isinstance(documents[kind], list)
                else [documents[kind]]
            )
            documents[kind].append(document)
        else:
            documents[kind] = document
    return documents, derived.manifest["finished_at"]


def analysis_policy() -> dict[str, Any]:
    """Select one named analysis job, separate from per-file parse contexts."""
    result = policy_document()
    result["contexts"] = ["native"]
    result["scope"] = {"include": ["**/*.cpp"], "exclude": []}
    result["controls"] = [
        {
            **control("findings"),
            "kind": "finding_limit",
            "parameters": {"rule_ids": ["CPP-MOD-001"], "max_findings": 0},
        },
        {
            **control("parse"),
            "kind": "minimum_analysis_coverage",
            "parameters": {"minimum": 100},
        },
        {
            **control("jobs", kind="required_contexts"),
            "parameters": {"contexts": ["native"]},
        },
    ]
    return result


def test_complete_normalized_analysis_passes_without_promoting_parse_ids_to_jobs(
    tmp_path: Path,
) -> None:
    documents, stamp = analysis_documents(tmp_path)
    before = deepcopy(documents)
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert result["gate"] == "passed"
    assert [row["status"] for row in result["controls"]] == ["passed"] * 3
    assert all(row["context_ids"] == ["native"] for row in result["controls"])
    assert all(not row["incomplete"] for row in result["controls"])
    assert any(
        "analysis_inventory:" in reference
        for reference in result["controls"][0]["references"]
    )
    assert documents == before


@pytest.mark.parametrize("partial", [False, True])
def test_normalized_findings_remain_definite_while_partial_consideration_is_incomplete(
    tmp_path: Path, partial: bool
) -> None:
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(
        tmp_path, mutate=lambda report, root: _finding(report, root, partial=partial)
    )
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is partial
    assert result["controls"][1]["status"] == ("failed" if partial else "passed")
    assert result["controls"][1]["incomplete"] is False
    assert result["controls"][2]["status"] == "passed"
    assert result["gate"] == "failed"


def test_partial_parse_with_no_findings_is_unknown_findings_and_known_zero_parse_coverage(
    tmp_path: Path,
) -> None:
    def partial(report: dict[str, Any], root: Path) -> None:
        report["metadata"]["analysis"]["files"][0].update(
            status="partial", error_count=1
        )

    documents, stamp = analysis_documents(tmp_path, mutate=partial)
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert [row["status"] for row in result["controls"]] == [
        "unknown",
        "failed",
        "passed",
    ]
    assert "parse coverage" in result["controls"][1]["reason"].lower()
    assert result["controls"][1]["incomplete"] is False


def test_disabled_detector_does_not_reduce_parse_coverage_or_prove_zero_findings(
    tmp_path: Path,
) -> None:
    def disabled(report: dict[str, Any], root: Path) -> None:
        path = root / "native-config.json"
        config = json.loads(path.read_text())
        config["rules"]["CPP-MOD-001"] = {"enabled": False}
        path.write_text(json.dumps(config))
        report["metadata"]["analysis"]["enabled_rules"].remove("CPP-MOD-001")

    documents, stamp = analysis_documents(tmp_path, mutate=disabled)
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert [row["status"] for row in result["controls"]] == [
        "unknown",
        "passed",
        "passed",
    ]
    assert result["gate"] == "insufficient_evidence"


def test_missing_typed_analysis_is_not_legacy_zero_success(tmp_path: Path) -> None:
    documents, stamp = analysis_documents(tmp_path)
    documents.pop("analysis_inventory")
    documents.pop("analysis_metrics")
    documents.pop("observations")
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert [row["status"] for row in result["controls"]] == ["unknown"] * 3
    assert result["gate"] == "insufficient_evidence"


def test_unverified_mode_findings_do_not_fail_the_requested_named_job(
    tmp_path: Path,
) -> None:
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(tmp_path, mutate=_finding, database=False)
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert [row["status"] for row in result["controls"]] == ["unknown"] * 3
    assert result["gate"] == "insufficient_evidence"


def test_unknown_expected_rule_is_unknown_but_forged_actual_rule_is_error(
    tmp_path: Path,
) -> None:
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(tmp_path, mutate=_finding)
    policy = analysis_policy()
    policy["controls"][0]["parameters"]["rule_ids"] = ["UNKNOWN-001"]
    assert (
        evaluate_policy(policy, documents, generated_at=stamp)["controls"][0]["status"]
        == "unknown"
    )
    documents["observations"]["items"][0]["rule_id"] = "UNKNOWN-001"
    with pytest.raises(ContractError):
        evaluate_policy(policy, documents, generated_at=stamp)


def add_unknown_analysis_cell(documents: dict[str, Any]) -> None:
    """Add a synthetic selected source cell lacking analysis; no bytes are claimed executed."""
    source = documents["run_manifest"]["source"]
    source["files"].append(
        {"path": "unrequested.cpp", "sha256": "b" * 64, "size_bytes": 10}
    )
    source["digest"] = digest_json(
        {
            "kind": source["kind"],
            "files": sorted(source["files"], key=lambda row: row["path"]),
            "inventory_complete": source["inventory_complete"],
        }
    )

    def update(value: Any) -> None:
        if isinstance(value, dict):
            if "source_digest" in value:
                value["source_digest"] = source["digest"]
            for nested in value.values():
                update(nested)
        elif isinstance(value, list):
            for nested in value:
                update(nested)

    update(documents)


def test_parse_coverage_unknown_scope_and_strict_upper_bound(tmp_path: Path) -> None:
    def partial(report: dict[str, Any], root: Path) -> None:
        report["metadata"]["analysis"]["files"][0].update(
            status="partial", error_count=1
        )

    documents, stamp = analysis_documents(tmp_path, mutate=partial)
    add_unknown_analysis_cell(documents)
    policy = analysis_policy()
    policy["controls"] = [policy["controls"][1]]
    policy["controls"][0]["parameters"]["minimum"] = 75
    failure = evaluate_policy(policy, documents, generated_at=stamp)
    assert failure["controls"][0]["status"] == "failed"
    assert failure["controls"][0]["incomplete"] is True
    policy["controls"][0]["parameters"]["minimum"] = 50
    unknown = evaluate_policy(policy, documents, generated_at=stamp)
    assert unknown["controls"][0]["status"] == "unknown"


def test_missing_analysis_cells_do_not_pass_even_zero_parse_threshold(
    tmp_path: Path,
) -> None:
    documents, stamp = analysis_documents(tmp_path)
    add_unknown_analysis_cell(documents)
    policy = analysis_policy()
    policy["controls"] = [policy["controls"][1]]
    policy["controls"][0]["parameters"]["minimum"] = 0
    result = evaluate_policy(policy, documents, generated_at=stamp)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True


def test_nonrequested_enabled_rule_observation_can_fail_but_does_not_prove_complete_consideration(
    tmp_path: Path,
) -> None:
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(
        tmp_path, mutate=lambda report, root: _finding(report, root, rule="CPP-MOD-009")
    )
    policy = analysis_policy()
    policy["controls"][0]["parameters"]["rule_ids"] = ["CPP-MOD-009"]
    result = evaluate_policy(policy, documents, generated_at=stamp)
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True
    policy["controls"][0]["parameters"]["max_findings"] = 1
    assert (
        evaluate_policy(policy, documents, generated_at=stamp)["controls"][0]["status"]
        == "unknown"
    )


def test_context_mismatch_is_known_zero_parse_coverage_and_not_a_named_job_finding_failure(
    tmp_path: Path,
) -> None:
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(tmp_path, mutate=_finding)
    documents["analysis_inventory"]["items"][0]["context_match"] = "mismatched"
    result = evaluate_policy(analysis_policy(), documents, generated_at=stamp)
    assert [row["status"] for row in result["controls"]] == [
        "unknown",
        "failed",
        "unknown",
    ]
    assert result["controls"][1]["incomplete"] is False


def test_cross_job_observations_are_distinct_even_when_parse_context_and_fingerprint_match(
    tmp_path: Path,
) -> None:
    """Clone consistent synthetic job facts; this does not assert a second execution."""
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(tmp_path, mutate=_finding)
    original_inventory = documents["analysis_inventory"]
    inventory = deepcopy(original_inventory)
    inventory.update(
        id=inventory["id"] + "-second",
        job_context_id="second",
        receipt_id="analyze-second",
    )
    job = deepcopy(
        next(
            row
            for row in documents["run_manifest"]["contexts"]
            if row["id"] == "native"
        )
    )
    job["id"] = "second"
    documents["run_manifest"]["contexts"].append(job)
    original_receipt = documents["execution_receipt"]
    receipt = deepcopy(original_receipt)
    receipt.update(id="analyze-second", context_id="second")
    documents["execution_receipt"] = [original_receipt, receipt]
    original_facts = documents["execution_facts"]
    facts = deepcopy(original_facts)
    facts["receipt"] = deepcopy(receipt)
    documents["execution_facts"] = [original_facts, facts]
    observations = deepcopy(documents["observations"])
    observations["analysis_inventory_id"] = inventory["id"]
    for row in observations["items"]:
        row["id"] += "-second"
    documents["observations"] = [documents["observations"], observations]
    documents["analysis_inventory"] = [original_inventory, inventory]
    policy = analysis_policy()
    policy["contexts"].append("second")
    policy["controls"][0]["parameters"]["max_findings"] = 1
    policy["controls"][2]["parameters"]["contexts"].append("second")
    result = evaluate_policy(policy, documents, generated_at=stamp)
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is False
    assert "2 finding(s)" in result["controls"][0]["reason"]
    assert result["controls"][1]["status"] == "passed"


@pytest.mark.parametrize("forged", ["inventory", "parse_context", "source"])
def test_forged_actual_analysis_identities_are_contract_errors(
    tmp_path: Path, forged: str
) -> None:
    from test_analysis_inventory import _finding

    documents, stamp = analysis_documents(tmp_path, mutate=_finding)
    if forged == "inventory":
        documents["observations"]["analysis_inventory_id"] = "not-retained"
    elif forged == "parse_context":
        documents["observations"]["items"][0]["context_id"] = "native"
    else:
        documents["analysis_inventory"]["source_digest"] = "f" * 64
    with pytest.raises(ContractError):
        evaluate_policy(analysis_policy(), documents, generated_at=stamp)


def coverage_policy(
    documents: dict[str, Any], *, minimum: float = 50
) -> dict[str, Any]:
    """Select typed synthetic coverage; actual producer execution is tested below."""
    selected = policy_document()
    selected["evaluator_profile"] = "1.1.0"
    selected["contexts"] = [documents["coverage_facts"]["context_id"]]
    selected["controls"] = [
        {
            **control("coverage"),
            "kind": "minimum_coverage",
            "parameters": {
                "minimum": minimum,
                "fact_ids": [documents["coverage_facts"]["id"]],
                "measurement_kind": "line",
                "method": "lcov-da-v1",
            },
        }
    ]
    return selected


@pytest.mark.parametrize(
    "minimum,status", [(50, "passed"), (50.00000000000001, "failed")]
)
def test_typed_coverage_uses_exact_counts_and_explicit_profile(minimum, status):
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    policy = coverage_policy(documents, minimum=minimum)
    original = deepcopy((policy, documents))
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["evaluator"] == {"name": "cppulse.policy", "version": "1.1.0"}
    assert result["controls"][0]["status"] == status
    assert result["controls"][0]["fact_ids"] == ["coverage-observed"]
    assert result["controls"][0]["incomplete"] is False
    assert "1/2" in result["controls"][0]["reason"]
    assert (policy, documents) == original


def test_schema_valid_integral_float_coverage_counts_remain_exact_without_mutation():
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    measurement = documents["coverage_facts"]["files"][0]["measurements"][0]
    for row in [measurement, *measurement["units"]]:
        for key in ["covered", "total"]:
            row[key] = float(row[key])
    original = deepcopy(documents)
    result = evaluate_policy(coverage_policy(documents), documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "passed"
    assert documents == original


def test_explicit_profile_11_preserves_original_test_predicate(policy, facts):
    old = evaluate_policy(policy, facts, generated_at=NOW)
    policy["evaluator_profile"] = "1.1.0"
    current = evaluate_policy(policy, facts, generated_at=NOW)
    assert current["evaluator"]["version"] == "1.1.0"
    for key in ["controls", "scores", "weights", "gate"]:
        assert current[key] == old[key]
    policy["evaluator_profile"] = "1.0.0"
    explicit_old = evaluate_policy(policy, facts, generated_at=NOW)
    assert explicit_old["evaluator"]["version"] == "1.0.0"
    assert explicit_old["controls"] == old["controls"]


@pytest.mark.parametrize(
    "missing", ["fact", "context", "kind", "zero", "expired", "import"]
)
def test_unavailable_typed_coverage_never_invents_a_pass(missing):
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    policy = coverage_policy(documents)
    fact = documents["coverage_facts"]
    if missing == "fact":
        policy["controls"][0]["parameters"]["fact_ids"].append("missing")
    elif missing == "context":
        add_context(documents, "other")
        policy["contexts"].append("other")
    elif missing == "kind":
        policy["controls"][0]["parameters"].update(
            measurement_kind="branch", method="lcov-brda-v1"
        )
    elif missing == "zero":
        fact["files"][0]["measurements"][0].update(covered=0, total=0, units=[])
    elif missing == "expired":
        documents["evidence"]["records"][0]["expires_at"] = "2026-11-13T11:00:00Z"
    else:
        fact.update(
            origin="import",
            receipt_id=None,
            proof_receipt_ids=[],
            test_evidence_ids=[],
            instrumentation=[],
            profiles=[],
        )
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True
    assert result["controls"][0]["fact_ids"] == ["coverage-observed"]


def test_known_below_threshold_coverage_remains_failed_with_missing_job():
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    add_context(documents, "unobserved")
    policy = coverage_policy(documents, minimum=75)
    policy["contexts"].append("unobserved")
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True


@pytest.mark.parametrize("change", [None, "counts", "universe"])
def test_repeated_coverage_requires_identical_full_unit_groups(change):
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    policy = coverage_policy(documents)
    original = documents["coverage_facts"]
    repeated = deepcopy(original)
    repeated["id"] = "coverage-repeat"
    measurement = repeated["files"][0]["measurements"][0]
    if change == "counts":
        measurement["units"][1]["covered"] = 1
        measurement["covered"] = 2
    elif change == "universe":
        measurement["units"][1]["id"] = "other-unit"
    documents["coverage_facts"] = [original, repeated]
    policy["controls"][0]["parameters"]["fact_ids"].append(repeated["id"])
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == (
        "passed" if change is None else "unknown"
    )
    assert result["controls"][0]["incomplete"] is (change is not None)


def test_coverage_minimum_applies_to_each_file_not_an_average():
    from verification_fixtures import artifact, coverage_execution_bundle

    documents = coverage_execution_bundle()
    source = documents["run_manifest"]["source"]
    old_digest = source["digest"]
    second = {**source["files"][0], "path": "src/second.cpp", "sha256": "8" * 64}
    source["files"].append(second)
    source["digest"] = digest_json(
        {key: source[key] for key in ["kind", "files", "inventory_complete"]}
    )

    def update(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if item == old_digest:
                    value[key] = source["digest"]
                else:
                    update(item)
        elif isinstance(value, list):
            for item in value:
                update(item)

    update(documents)
    artifact(documents, "source-two", sha=second["sha256"], size=second["size_bytes"])
    compiled = documents["execution_facts"][0]
    observed = {
        **compiled["input_facts"][0],
        "path": second["path"],
        "sha256": second["sha256"],
    }
    compiled["input_facts"].append(observed)
    compiled["input_after_facts"].append(deepcopy(observed))
    compiled["binding"]["input_artifacts"].append(
        {"path": second["path"], "artifact_id": "source-two"}
    )
    compiled["receipt"]["artifact_ids"].append("source-two")
    documents["execution_receipt"][0]["artifact_ids"].append("source-two")
    fact = documents["coverage_facts"]
    fact["instrumentation"][0]["source_files"].append(second["path"])
    file = deepcopy(fact["files"][0])
    file.update(file=second["path"], source_sha256=second["sha256"])
    file["measurements"][0].update(
        covered=100,
        total=100,
        units=[
            {"id": f"line-{index}", "covered": 1, "total": 1} for index in range(1, 101)
        ],
    )
    fact["files"].append(file)
    result = evaluate_policy(
        coverage_policy(documents, minimum=75), documents, generated_at=NOW
    )
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is False


def test_typed_coverage_rejects_a_future_used_proof():
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    documents["coverage_facts"]["proof_receipt_ids"].append("ctest-version")
    for receipt in [
        next(
            row
            for row in documents["execution_receipt"]
            if row["id"] == "ctest-version"
        ),
        next(
            row
            for row in documents["execution_facts"]
            if row["receipt"]["id"] == "ctest-version"
        )["receipt"],
    ]:
        receipt.update(
            started_at="2026-11-13T12:59:59Z", finished_at="2026-11-13T13:00:00Z"
        )
    with pytest.raises(ContractError, match="predates|precedes"):
        evaluate_policy(coverage_policy(documents), documents, generated_at=NOW)


@pytest.fixture(scope="module")
def actual_coverage(tmp_path_factory):
    """Reuse the gated producer's real finite GCC/gcovr/CTest fixture recipe."""
    from test_coverage_normalization import actual

    return actual.__wrapped__(tmp_path_factory)


@pytest.mark.parametrize(
    "adapter,kind,method,counts",
    [
        ("lcov", "line", "lcov-da-v1", (5, 8)),
        ("lcov", "branch", "lcov-brda-v1", (1, 2)),
        ("lcov", "function", "lcov-fnda-v1", (2, 3)),
        ("cobertura", "line", "cobertura-lines-v1", (5, 8)),
        ("cobertura", "branch", "cobertura-condition-counts-v1", (1, 2)),
    ],
)
def test_actual_coverage_producer_counts_reach_policy_without_reinterpretation(
    actual_coverage, adapter, kind, method, counts
):
    from cppulse.coverage import normalize_coverage

    snapshot, _, selections = actual_coverage
    documents = {"run_manifest": snapshot.manifest}
    for entry in snapshot.manifest["artifacts"]:
        reference = entry.get("contract", {})
        if reference.get("version") == "2.0.0":
            documents.setdefault(reference["kind"], []).append(
                snapshot.read_json(entry["id"])
            )
    document = normalize_coverage(snapshot, **selections[adapter])
    documents["coverage_facts"] = document
    policy = coverage_policy(documents)
    policy["scope"]["include"] = ["main.cpp"]
    policy["controls"][0]["parameters"].update(measurement_kind=kind, method=method)
    before = deepcopy(document)
    result = evaluate_policy(
        policy, documents, generated_at=snapshot.manifest["finished_at"]
    )
    assert result["controls"][0]["status"] == "passed"
    assert result["controls"][0]["incomplete"] is False
    assert f"{counts[0]}/{counts[1]}" in result["controls"][0]["reason"]
    assert document == before
    policy["controls"][0]["parameters"]["minimum"] = 80
    assert (
        evaluate_policy(
            policy, documents, generated_at=snapshot.manifest["finished_at"]
        )["controls"][0]["status"]
        == "failed"
    )


def test_typed_coverage_evaluation_has_no_project_process_network_or_environment_io(
    monkeypatch,
):
    import os
    import socket
    from verification_fixtures import coverage_execution_bundle

    documents = coverage_execution_bundle()
    policy = coverage_policy(documents)
    evaluate_policy(policy, documents, generated_at=NOW)

    def reject(*args, **kwargs):
        raise AssertionError("Pure evaluation may only consume supplied facts")

    monkeypatch.setattr(subprocess, "run", reject)
    monkeypatch.setattr(socket, "socket", reject)
    monkeypatch.setattr(os, "getenv", reject)
    monkeypatch.setattr(Path, "read_bytes", reject)
    monkeypatch.setattr(Path, "read_text", reject)
    assert evaluate_policy(policy, documents, generated_at=NOW)["gate"] == "passed"


def sanitizer_policy(documents: dict[str, Any]) -> dict[str, Any]:
    """Select a named typed sanitizer claim without inventing execution proof."""
    selected = policy_document()
    fact = documents["sanitizer_facts"]
    selected.update(evaluator_profile="1.1.0", contexts=[fact["context_id"]])
    selected["controls"] = [
        {
            **control("sanitizer"),
            "kind": "sanitizer_outcome",
            "parameters": {"fact_ids": [fact["id"]], "sanitizer": fact["sanitizer"]},
        }
    ]
    return selected


def fail_sanitizer(documents: dict[str, Any]) -> None:
    """Record a synthetic credible diagnostic; the test process stays passed."""
    fact = documents["sanitizer_facts"]
    fact.update(
        outcome="failed",
        diagnostics=[
            {
                "id": "retained-diagnostic",
                "kind": "heap-buffer-overflow",
                "message": "Synthetic qualified diagnostic, not a runtime probe.",
                "file": None,
                "line": None,
                "artifact_id": "last-log",
                "test_case_id": "case",
            }
        ],
    )


@pytest.mark.parametrize("failed", [False, True])
def test_typed_sanitizer_outcome_is_independent_of_passed_test_label(failed):
    from test_sanitizer_facts_contract import sanitizer_bundle

    documents = sanitizer_bundle()
    if failed:
        fail_sanitizer(documents)
    policy = sanitizer_policy(documents)
    policy["controls"].append(control("tests", evidence_ids=["test-evidence"]))
    before = deepcopy(documents)
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert [row["status"] for row in result["controls"]] == [
        "failed" if failed else "passed",
        "passed",
    ]
    assert result["controls"][0]["incomplete"] is False
    assert result["controls"][0]["fact_ids"] == ["asan-observed"]
    assert documents == before


@pytest.mark.parametrize(
    "missing",
    [
        "fact",
        "job",
        "sanitizer",
        "expired",
        "import",
        "malformed",
        "unsupported",
        "missing",
    ],
)
def test_unavailable_sanitizer_never_creates_a_clean_or_definitive_failure(missing):
    from test_sanitizer_facts_contract import sanitizer_bundle

    documents = sanitizer_bundle()
    fail_sanitizer(documents)
    policy = sanitizer_policy(documents)
    fact = documents["sanitizer_facts"]
    if missing == "fact":
        documents.pop("sanitizer_facts")
    elif missing == "job":
        add_context(documents, "other")
        policy["contexts"] = ["other"]
    elif missing == "sanitizer":
        policy["controls"][0]["parameters"]["sanitizer"] = "tsan"
    elif missing == "expired":
        documents["evidence"]["records"][0]["expires_at"] = "2026-11-13T11:00:00Z"
    elif missing == "import":
        fact.update(
            origin="import",
            compiler_version_receipt_id=None,
            compile_receipt_ids=[],
            link_receipt_id=None,
            inspection_receipt_ids=[],
            proof_receipt_ids=[],
            binary_artifact_id=None,
            object_proofs=[],
            linked_components=[],
            runtime_proof=None,
            test_evidence_id=None,
            exercise_proofs=[],
        )
    else:
        fact.update(outcome="unsupported", usability=missing)
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True
    assert result["controls"][0]["fact_ids"] == (
        [] if missing == "fact" else ["asan-observed"]
    )


@pytest.mark.parametrize("gap", ["component", "job", "source", "named_fact"])
def test_credible_sanitizer_failure_with_scope_gaps_is_incomplete_and_not_waivable(gap):
    from test_sanitizer_facts_contract import sanitizer_bundle
    from verification_fixtures import artifact

    documents = sanitizer_bundle()
    fail_sanitizer(documents)
    policy = sanitizer_policy(documents)
    policy["controls"][0]["allow_deviation"] = True
    if gap == "component":
        artifact(documents, "unverified-component")
        documents["sanitizer_facts"]["linked_components"].append(
            {
                "subject_id": "prebuilt",
                "artifact_id": "unverified-component",
                "instrumentation": "unverified",
            }
        )
    elif gap == "job":
        add_context(documents, "unobserved")
        policy["contexts"].append("unobserved")
    elif gap == "source":
        add_unknown_analysis_cell(documents)
        policy["scope"]["include"] = ["**/*.cpp"]
    else:
        policy["controls"][0]["parameters"]["fact_ids"].append("absent")
    request = approval(
        documents, control_id="sanitizer", context_ids=policy["contexts"]
    )
    result = evaluate_policy(policy, documents, generated_at=NOW, deviations=[request])
    assert result["controls"][0]["status"] == "failed"
    assert result["controls"][0]["incomplete"] is True
    assert result["deviations"][0]["active"] is False


def test_missing_selected_source_in_clean_sanitizer_stays_unknown():
    from test_sanitizer_facts_contract import sanitizer_bundle

    documents = sanitizer_bundle()
    add_unknown_analysis_cell(documents)
    policy = sanitizer_policy(documents)
    policy["scope"]["include"] = ["**/*.cpp"]
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True


def test_unknown_sanitizer_scope_cannot_fail_unrelated_selected_source():
    from test_sanitizer_facts_contract import sanitizer_bundle

    documents = sanitizer_bundle()
    fail_sanitizer(documents)
    add_unknown_analysis_cell(documents)
    policy = sanitizer_policy(documents)
    policy["scope"]["include"] = ["unrequested.cpp"]
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"


def test_named_unrelated_failed_sanitizer_fact_keeps_clean_selected_scope_unknown():
    """Closed synthetic facts preserve an unrelated diagnostic without passing it."""
    from test_sanitizer_facts_contract import sanitizer_bundle
    from verification_fixtures import artifact

    documents = sanitizer_bundle()
    add_unknown_analysis_cell(documents)
    artifact(documents, "other-source", sha="b" * 64, size=10)
    compiled = next(
        row for row in documents["execution_facts"] if row["receipt"]["id"] == "compile"
    )
    source = {
        **compiled["input_facts"][0],
        "path": "unrequested.cpp",
        "sha256": "b" * 64,
        "size_bytes": 10,
    }
    compiled["input_facts"].append(source)
    compiled["input_after_facts"].append(deepcopy(source))
    compiled["binding"]["input_artifacts"].append(
        {"path": "unrequested.cpp", "artifact_id": "other-source"}
    )
    compiled["receipt"]["artifact_ids"].append("other-source")
    next(row for row in documents["execution_receipt"] if row["id"] == "compile")[
        "artifact_ids"
    ].append("other-source")
    plan = documents["collection_plan"]
    next(row for row in plan["recipe"]["steps"] if row["id"] == "compile")[
        "inputs"
    ].append("unrequested.cpp")
    documents["run_manifest"]["config_digest"] = digest_json(plan)
    clean = deepcopy(documents["sanitizer_facts"])
    fail_sanitizer(documents)
    unrelated = documents["sanitizer_facts"]
    unrelated.update(id="other-failed", requested_files=["unrequested.cpp"])
    unrelated["object_proofs"][0]["source_files"] = ["unrequested.cpp"]
    unrelated["diagnostics"][0].update(file="unrequested.cpp", line=1)
    documents["sanitizer_facts"] = [clean, unrelated]
    policy = sanitizer_policy({"sanitizer_facts": clean})
    policy["controls"][0]["parameters"]["fact_ids"].append(unrelated["id"])
    validate_bundle(documents)
    original = deepcopy(documents)
    result = evaluate_policy(policy, documents, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"] is True
    assert result["controls"][0]["fact_ids"] == [clean["id"], unrelated["id"]]
    assert "outside the selected source scope" in result["controls"][0]["reason"]
    assert documents == original


@pytest.fixture(scope="module")
def actual_sanitizers(tmp_path_factory):
    """Execute the accepted finite producer recipe, including operational gaps."""
    from test_sanitizer_normalization import actual_cases

    return actual_cases.__wrapped__(tmp_path_factory)


@pytest.mark.parametrize(
    "key",
    [
        "asan-clean",
        "asan-bad",
        "asan-plain-object",
        "asan-substituted-binary",
        "asan-zero-tests",
        "asan-all-skipped",
        "asan-prebuilt-gap",
        "asan-prebuilt-gap-bad",
        "ubsan-clean",
        "ubsan-bad",
        "tsan-clean",
        "tsan-bad",
    ],
)
def test_actual_sanitizer_producer_reaches_policy_with_raw_test_outcome_preserved(
    actual_sanitizers, key
):
    _, snapshot, fact = actual_sanitizers[key]
    documents = {"run_manifest": snapshot.manifest}
    for entry in snapshot.manifest["artifacts"]:
        reference = entry.get("contract", {})
        if reference.get("version") == "2.0.0":
            documents.setdefault(reference["kind"], []).append(
                snapshot.read_json(entry["id"])
            )
    documents["sanitizer_facts"] = fact
    policy = sanitizer_policy(documents)
    policy["scope"]["include"] = fact["requested_files"]
    before = deepcopy(fact)
    if key == "ubsan-bad":
        policy["controls"].append(control("tests", evidence_ids=["sanitizer-tests"]))
    result = evaluate_policy(
        policy, documents, generated_at=snapshot.manifest["finished_at"]
    )
    expected = fact["outcome"] if fact["usability"] == "usable" else "unknown"
    assert result["controls"][0]["status"] == expected
    assert result["controls"][0]["incomplete"] is (
        expected == "unknown" or key == "asan-prebuilt-gap-bad"
    )
    if key == "ubsan-bad":
        assert result["controls"][1]["status"] == "passed"
        receipt = next(
            row for row in documents["execution_receipt"] if row["id"] == "tests"
        )
        assert receipt["exit_code"] == 0
    assert fact == before


def test_packaged_verification_example_explicitly_selects_typed_profile_11():
    policy = json.loads(
        resources.files("cppulse")
        .joinpath("data/policies/verification-example.json")
        .read_text()
    )
    validate_evaluation_policy(policy)
    assert policy["evaluator_profile"] == "1.1.0"
    assert {row["kind"] for row in policy["controls"]} == {
        "test_outcomes",
        "minimum_coverage",
        "sanitizer_outcome",
    }
    assert not any(row.get("allow_deviation", False) for row in policy["controls"])
