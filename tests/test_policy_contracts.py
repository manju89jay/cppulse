"""Pure S5 policy boundary, exact gate and scoped deviation regressions."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import (
    policy_gate,
    policy_scope_paths,
    validate,
    validate_bundle,
    validate_evaluation_policy,
    validate_deviation_request,
)
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.identities import digest_json


@pytest.fixture
def policy() -> dict[str, Any]:
    """A selected policy uses named job contexts and four supported predicates."""
    return {
        "version": "2.0.0",
        "id": "general",
        "policy_version": "1.0.0",
        "standards": [],
        "scope": {"include": ["**/*.cpp"], "exclude": []},
        "contexts": ["native"],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": "tests",
                "title": "Selected tests",
                "kind": "test_outcomes",
                "weight": 1,
                "required": True,
                "parameters": {"evidence_ids": ["tests"]},
                "depends_on": [],
            }
        ],
    }


def control(status: str, weight: float, *, required: bool = False) -> dict[str, Any]:
    """Make a gate input without claiming an underlying predicate was evaluated."""
    return {
        "id": status,
        "title": status,
        "status": status,
        "weight": weight,
        "required": required,
        "context_ids": ["native"],
        "incomplete": status == "unknown",
        "reason": "Synthetic arithmetic input",
        "evidence_ids": [],
        "references": [],
    }


def arithmetic_policy(
    policy: dict[str, Any],
    controls: list[dict[str, Any]],
    readiness: float,
    completeness: float,
) -> dict[str, Any]:
    """Bind the arithmetic control metadata to explicit policy permissions."""
    result = deepcopy(policy)
    result["gates"] = {
        "minimum_readiness": readiness,
        "minimum_completeness": completeness,
    }
    result["controls"] = [
        {
            "id": item["id"],
            "title": item["title"],
            "kind": "required_contexts",
            "weight": item["weight"],
            "required": item["required"],
            "parameters": {"contexts": ["native"]},
            "depends_on": [],
        }
        for item in controls
    ]
    return result


@pytest.mark.parametrize(
    "kind,parameters",
    [
        ("finding_limit", {"rule_ids": ["CPP-MOD-001"], "max_findings": 0}),
        ("minimum_analysis_coverage", {"minimum": 100}),
        ("test_outcomes", {"evidence_ids": ["tests"]}),
        ("required_contexts", {"contexts": ["native"]}),
    ],
)
def test_four_evaluator_predicates_have_an_explicit_profile(
    policy: dict[str, Any], kind: str, parameters: dict[str, Any]
) -> None:
    policy["controls"][0].update(kind=kind, parameters=parameters)
    validate_evaluation_policy(policy)


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
def test_future_descriptive_predicates_are_not_silently_evaluated(
    policy: dict[str, Any], kind: str, parameters: dict[str, Any]
) -> None:
    policy["controls"][0].update(kind=kind, parameters=parameters)
    validate("policy", policy)
    with pytest.raises(UnsupportedVersion):
        validate_evaluation_policy(policy)


def test_unknown_evaluator_profile_and_ambiguous_job_defaults_are_rejected(
    policy: dict[str, Any]
) -> None:
    with pytest.raises(UnsupportedVersion):
        validate_evaluation_policy(policy, profile_version="2.0.0")
    policy["contexts"] = []
    validate("policy", policy)
    with pytest.raises(ContractError):
        validate_evaluation_policy(policy)


def test_control_context_selector_must_be_in_explicit_policy_job_scope(
    policy: dict[str, Any]
) -> None:
    policy["controls"][0].update(
        kind="required_contexts", parameters={"contexts": ["other"]}
    )
    with pytest.raises(ContractError):
        validate_evaluation_policy(policy)


def test_mixed_job_policy_selects_test_and_analysis_roles_explicitly(
    policy: dict[str, Any]
) -> None:
    policy["contexts"] = ["build", "analysis"]
    policy["controls"][0]["parameters"]["contexts"] = ["build"]
    for identifier, kind, parameters in [
        ("findings", "finding_limit", {"rule_ids": ["CPP-MOD-001"], "max_findings": 0}),
        ("coverage", "minimum_analysis_coverage", {"minimum": 100}),
    ]:
        policy["controls"].append(
            {
                "id": identifier,
                "title": identifier,
                "kind": kind,
                "weight": 1,
                "required": True,
                "parameters": {**parameters, "contexts": ["analysis"]},
                "depends_on": [],
            }
        )
    validate_evaluation_policy(policy)


@pytest.mark.parametrize(
    "kind,parameters",
    [
        ("test_outcomes", {"evidence_ids": ["tests"]}),
        ("finding_limit", {"rule_ids": ["CPP-MOD-001"], "max_findings": 0}),
        ("minimum_analysis_coverage", {"minimum": 100}),
    ],
)
@pytest.mark.parametrize("contexts", [[], ["outside"]])
def test_every_initial_predicate_rejects_empty_or_outside_job_selection(
    policy: dict[str, Any], kind: str, parameters: dict[str, Any], contexts: list[str]
) -> None:
    policy["controls"][0].update(
        kind=kind, parameters={**parameters, "contexts": contexts}
    )
    with pytest.raises(ContractError):
        validate_evaluation_policy(policy)


@pytest.mark.parametrize(
    "pattern,path,matched",
    [
        ("**/*.cpp", "main.cpp", True),
        ("**/*.cpp", "src/a/main.cpp", True),
        ("*.cpp", "src/main.cpp", False),
        ("src/*.cpp", "src/main.cpp", True),
        ("src/*.cpp", "src/a/main.cpp", False),
        ("src/**/test?.cpp", "src/test1.cpp", True),
        ("src/**/test?.cpp", "src/a/testx.cpp", True),
        ("src/**/test?.cpp", "src/test.cpp", False),
        ("src/**", "src/a/b.hpp", True),
        ("src/**", "src2/main.cpp", False),
    ],
)
def test_posix_glob_meaning_is_shared_and_case_sensitive(
    policy: dict[str, Any], pattern: str, path: str, matched: bool
) -> None:
    policy["scope"]["include"] = [pattern]
    assert bool(policy_scope_paths(policy, [path])) is matched


def test_glob_exclusions_and_unsupported_inline_double_star(
    policy: dict[str, Any]
) -> None:
    policy["scope"]["exclude"] = ["vendor/**", "**/generated?.cpp"]
    assert policy_scope_paths(
        policy, ["main.cpp", "vendor/v.cpp", "src/generated1.cpp", "src/m.cpp"]
    ) == ["main.cpp", "src/m.cpp"]
    policy["scope"]["include"] = ["src/a**b.cpp"]
    with pytest.raises(ContractError):
        validate_evaluation_policy(policy)


@pytest.mark.parametrize(
    "states,minimum_r,minimum_c,expected",
    [
        ((8, 2, 0), 80, 100, "passed"),
        ((8, 2, 0), 81, 100, "failed"),
        ((4, 2, 4), 80, 0, "insufficient_evidence"),
        ((4, 2, 4), 81, 0, "failed"),
        ((4, 2, 4), 40, 61, "insufficient_evidence"),
        ((4, 2, 4), 40, 60, "passed"),
        ((0, 0, 10), 100, 100, "insufficient_evidence"),
    ],
)
def test_gate_precedence_uses_exact_unrounded_weights(
    policy: dict[str, Any],
    states: tuple[int, int, int],
    minimum_r: float,
    minimum_c: float,
    expected: str,
) -> None:
    controls = [
        control(status, weight)
        for status, weight in zip(("passed", "failed", "unknown"), states)
        if weight
    ]
    selected = arithmetic_policy(policy, controls, minimum_r, minimum_c)
    assert policy_gate(selected, controls, source_scope_empty=False) == expected


def test_required_failure_precedes_required_unknown_and_empty_scope(
    policy: dict[str, Any]
) -> None:
    controls = [
        control("passed", 98),
        control("failed", 1, required=True),
        control("unknown", 1, required=True),
    ]
    selected = arithmetic_policy(policy, controls, 0, 0)
    assert policy_gate(selected, controls, source_scope_empty=True) == "failed"
    controls[1]["required"] = False
    selected["controls"][1]["required"] = False
    assert (
        policy_gate(selected, controls, source_scope_empty=False)
        == "insufficient_evidence"
    )


def test_empty_source_or_no_applicable_control_cannot_pass(
    policy: dict[str, Any]
) -> None:
    controls = [control("passed", 1)]
    selected = arithmetic_policy(policy, controls, 0, 0)
    assert (
        policy_gate(selected, controls, source_scope_empty=True)
        == "insufficient_evidence"
    )
    controls[0].update(status="not_applicable", incomplete=False)
    assert (
        policy_gate(selected, controls, source_scope_empty=False)
        == "insufficient_evidence"
    )


def test_decimal_threshold_boundary_is_not_a_binary_float_comparison(
    policy: dict[str, Any]
) -> None:
    controls = [control("passed", 1), control("failed", 2)]
    selected = arithmetic_policy(policy, controls, 33.333333333333336, 100)
    assert policy_gate(selected, controls, source_scope_empty=False) == "failed"
    selected["gates"]["minimum_readiness"] = 33.33333333333333
    assert policy_gate(selected, controls, source_scope_empty=False) == "passed"


def test_exception_permission_does_not_change_raw_thresholds_or_unknowns(
    policy: dict[str, Any]
) -> None:
    controls = [control("passed", 8), control("failed", 2, required=True)]
    selected = arithmetic_policy(policy, controls, 70, 100)
    approved = {"failed"}
    assert (
        policy_gate(
            selected, controls, source_scope_empty=False, excepted_control_ids=approved
        )
        == "failed"
    )
    selected["controls"][1]["allow_deviation"] = True
    assert (
        policy_gate(
            selected, controls, source_scope_empty=False, excepted_control_ids=approved
        )
        == "passed"
    )
    selected["gates"]["minimum_readiness"] = 90
    assert (
        policy_gate(
            selected, controls, source_scope_empty=False, excepted_control_ids=approved
        )
        == "failed"
    )
    selected["gates"]["minimum_readiness"] = 70
    controls[1]["incomplete"] = True
    assert (
        policy_gate(
            selected, controls, source_scope_empty=False, excepted_control_ids=approved
        )
        == "failed"
    )
    controls[1].update(status="unknown", incomplete=True)
    assert (
        policy_gate(
            selected, controls, source_scope_empty=False, excepted_control_ids=approved
        )
        == "insufficient_evidence"
    )


@pytest.fixture
def bundle(policy: dict[str, Any]) -> dict[str, Any]:
    """Synthetic closed contract facts; no execution is claimed by this test."""
    source = {
        "kind": "application",
        "files": [{"path": "src/main.cpp", "sha256": "a" * 64, "size_bytes": 10}],
        "inventory_complete": True,
    }
    source = {
        "version": "2.0.0",
        "digest": digest_json(source),
        **source,
        "limitations": [],
    }
    context = {
        "compiler": {"name": "fixture", "version": "1"},
        "argv": [],
        "working_directory": "/synthetic",
        "language_standard": None,
        "target": None,
        "provenance": "observed",
        "dependencies": [],
    }
    context = {
        "version": "2.0.0",
        "id": "native",
        "digest": digest_json(context),
        **context,
        "limitations": [],
    }
    receipt = {
        "version": "2.0.0",
        "id": "test-command",
        "source_digest": source["digest"],
        "context_id": "native",
        "producer": {"name": "fixture", "version": "1"},
        "argv": ["ctest"],
        "cwd": "/synthetic",
        "status": "passed",
        "reason": "",
        "exit_code": 0,
        "signal": None,
        "started_at": "2026-11-13T10:00:00Z",
        "finished_at": "2026-11-13T10:00:00Z",
        "artifact_ids": ["raw"],
        "log_artifact_ids": [],
        "depends_on": [],
        "tests": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0},
    }
    evidence = {
        "version": "2.0.0",
        "source_digest": source["digest"],
        "records": [
            {
                "id": "tests",
                "context_id": "native",
                "producer": {"name": "fixture", "version": "1"},
                "origin": "execution",
                "kind": "tests",
                "status": "passed",
                "usability": "usable",
                "artifact_ids": ["raw"],
                "receipt_id": "test-command",
                "scope": {"files": ["src/main.cpp"]},
                "limitations": [],
            }
        ],
    }
    assessment = {
        "evaluator": {"name": "cppulse.policy", "version": "1.0.0"},
        "version": "2.0.0",
        "run_id": "synthetic",
        "source_digest": source["digest"],
        "policy": {
            "id": policy["id"],
            "policy_version": policy["policy_version"],
            "sha256": digest_json(policy),
        },
        "gate": "passed",
        "generated_at": "2026-11-13T10:00:00Z",
        "weights": {"passed": 1, "failed": 0, "unknown": 0},
        "scores": dict.fromkeys(
            [
                "readiness",
                "evidence_completeness",
                "observed_satisfaction",
                "maximum_possible_readiness",
            ],
            100,
        ),
        "controls": [
            {
                **control("passed", 1, required=True),
                "id": "tests",
                "title": "Selected tests",
                "evidence_ids": ["tests"],
            }
        ],
        "deviations": [],
        "limitations": [],
    }
    manifest = {
        "version": "2.0.0",
        "run_id": "synthetic",
        "status": "completed",
        "source": source,
        "contexts": [context],
        "stages": [],
        "artifacts": [
            {
                "id": "raw",
                "path": "raw.bin",
                "sha256": "a" * 64,
                "size_bytes": 10,
                "media_type": "application/octet-stream",
            }
        ],
        "started_at": "2026-11-13T10:00:00Z",
        "finished_at": "2026-11-13T10:00:00Z",
        "config_digest": "a" * 64,
        "versions": {"fixture": "1"},
        "limitations": [],
        "input_verification": "verified",
    }
    return {
        "run_manifest": manifest,
        "policy": deepcopy(policy),
        "assessment": assessment,
        "execution_receipt": receipt,
        "evidence": evidence,
    }


def test_closed_positive_policy_bundle_remains_valid(bundle: dict[str, Any]) -> None:
    validate_bundle(bundle)


def test_unknown_evaluator_identity_is_not_silently_read_as_current(
    bundle: dict[str, Any]
) -> None:
    bundle["assessment"]["evaluator"]["version"] = "2.0.0"
    with pytest.raises(UnsupportedVersion):
        validate("assessment", bundle["assessment"])


@pytest.mark.parametrize("weight", [1e306, 1e307, 1e308, 2 * 10**308])
def test_finite_weight_scale_does_not_overflow_assessment_ratios(
    bundle: dict[str, Any], weight: float
) -> None:
    bundle["policy"]["controls"][0]["weight"] = weight
    bundle["assessment"]["controls"][0]["weight"] = weight
    bundle["assessment"]["weights"]["passed"] = weight
    bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    validate_bundle(bundle)


@pytest.mark.parametrize("target", ["manifest", "used_receipt"])
def test_current_evaluator_cannot_predate_its_used_facts(
    bundle: dict[str, Any], target: str
) -> None:
    if target == "manifest":
        bundle["assessment"]["generated_at"] = "2000-01-01T00:00:00Z"
    else:
        bundle["execution_receipt"]["finished_at"] = "2026-11-13T11:00:00Z"
    with pytest.raises(ContractError, match="predates"):
        validate_bundle(bundle)


def test_expired_named_positive_evidence_is_not_current(bundle: dict[str, Any]) -> None:
    bundle["evidence"]["records"][0]["expires_at"] = bundle["assessment"][
        "generated_at"
    ]
    with pytest.raises(ContractError):
        validate_bundle(bundle)


def test_empty_selected_scope_cannot_be_asserted_as_passed(
    bundle: dict[str, Any]
) -> None:
    bundle["policy"]["scope"]["include"] = ["not-selected.cpp"]
    bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    with pytest.raises(ContractError):
        validate_bundle(bundle)


@pytest.mark.parametrize("field,value", [("context_ids", []), ("incomplete", True)])
def test_passed_control_cannot_hide_its_declared_context_or_incompleteness(
    bundle: dict[str, Any], field: str, value: Any
) -> None:
    bundle["assessment"]["controls"][0][field] = value
    with pytest.raises(ContractError):
        validate_bundle(bundle)


def failed_component(bundle: dict[str, Any], *, required: bool = False) -> None:
    """Add a credible synthetic failed test result without changing passing facts."""
    declared = deepcopy(bundle["policy"]["controls"][0])
    declared.update(id="failed", title="Failed tests", required=required)
    declared["parameters"] = {"evidence_ids": ["failed-tests"]}
    bundle["policy"]["controls"].append(declared)
    receipt = deepcopy(bundle["execution_receipt"])
    receipt.update(id="failed-command", status="failed", exit_code=1)
    receipt["tests"] = {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0}
    bundle["execution_receipt"] = [bundle["execution_receipt"], receipt]
    evidence = deepcopy(bundle["evidence"]["records"][0])
    evidence.update(id="failed-tests", receipt_id="failed-command", status="failed")
    bundle["evidence"]["records"].append(evidence)
    result = control("failed", 1, required=required)
    result.update(id="failed", title="Failed tests", evidence_ids=["failed-tests"])
    bundle["assessment"]["controls"].append(result)
    bundle["assessment"]["weights"] = {"passed": 1, "failed": 1, "unknown": 0}
    bundle["assessment"]["scores"] = {
        "readiness": 50,
        "evidence_completeness": 100,
        "observed_satisfaction": 50,
        "maximum_possible_readiness": 50,
    }
    bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])


def test_bundle_rejects_threshold_false_pass_using_actual_policy(
    bundle: dict[str, Any]
) -> None:
    failed_component(bundle)
    with pytest.raises(ContractError, match="gate"):
        validate_bundle(bundle)
    bundle["assessment"]["gate"] = "failed"
    validate_bundle(bundle)


@pytest.mark.parametrize(
    "change", ["missing_id", "missing_context", "unverified", "scope"]
)
def test_passed_tests_must_cover_named_ids_jobs_source_and_declared_scope(
    bundle: dict[str, Any], change: str
) -> None:
    if change == "missing_id":
        bundle["policy"]["controls"][0]["parameters"]["evidence_ids"].append("missing")
        bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    elif change == "missing_context":
        bundle["policy"]["contexts"].append("not-configured")
        bundle["assessment"]["controls"][0]["context_ids"].append("not-configured")
        bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    elif change == "unverified":
        bundle["run_manifest"]["input_verification"] = "unverified"
    else:
        bundle["evidence"]["records"][0]["scope"]["files"] = []
    with pytest.raises(ContractError):
        validate_bundle(bundle)


def test_declared_context_alone_does_not_prove_observed_context_coverage(
    bundle: dict[str, Any]
) -> None:
    bundle["policy"]["controls"][0].update(
        kind="required_contexts", parameters={"contexts": ["native"]}
    )
    bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    bundle["assessment"]["controls"][0]["evidence_ids"] = []
    del bundle["evidence"]
    del bundle["execution_receipt"]
    with pytest.raises(ContractError):
        validate_bundle(bundle)


@pytest.mark.parametrize(
    "kind,parameters",
    [
        ("finding_limit", {"rule_ids": ["CPP-MOD-001"], "max_findings": 0}),
        ("minimum_analysis_coverage", {"minimum": 0}),
    ],
)
def test_flat_or_absent_analysis_cannot_manufacture_a_positive_control(
    bundle: dict[str, Any], kind: str, parameters: dict[str, Any]
) -> None:
    bundle["policy"]["controls"][0].update(kind=kind, parameters=parameters)
    bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    with pytest.raises(ContractError, match="typed job inventory"):
        validate_bundle(bundle)


def deviation(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return an explicit scoped approval of a complete required failure."""
    return {
        "id": "temporary",
        "control_id": "failed",
        "source_digest": bundle["run_manifest"]["source"]["digest"],
        "context_ids": ["native"],
        "reason": "Reviewed bounded exception",
        "owner": "Fixture owner",
        "reviewer": "Fixture reviewer",
        "approved_at": "2026-11-12T10:00:00Z",
        "expires_at": "2026-11-14T10:00:00Z",
        "active": True,
        "gate": "required_controls",
        "inactive_reason": None,
    }


@pytest.fixture
def excepted_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """A permitted required-controls exception leaves its raw failed score intact."""
    failed_component(bundle, required=True)
    bundle["policy"]["controls"][1]["allow_deviation"] = True
    bundle["policy"]["gates"]["minimum_readiness"] = 50
    bundle["assessment"]["policy"]["sha256"] = digest_json(bundle["policy"])
    bundle["assessment"]["deviations"] = [deviation(bundle)]
    return bundle


def test_permitted_scoped_exception_preserves_raw_failure_and_scores(
    excepted_bundle: dict[str, Any]
) -> None:
    validate_bundle(excepted_bundle)
    assert excepted_bundle["assessment"]["controls"][1]["status"] == "failed"
    assert excepted_bundle["assessment"]["scores"]["readiness"] == 50


def test_failed_label_without_failed_testcases_is_not_a_waivable_defect(
    excepted_bundle: dict[str, Any]
) -> None:
    excepted_bundle["execution_receipt"][1]["tests"] = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    with pytest.raises(ContractError, match="failed testcase"):
        validate_bundle(excepted_bundle)


@pytest.mark.parametrize(
    "change",
    [
        "denied",
        "empty",
        "wrong_scope",
        "incomplete",
        "unknown",
        "future",
        "expired",
        "wrong_source",
        "unsupported_gate",
        "threshold",
        "inactive_reason",
    ],
)
def test_active_exception_cannot_hide_denial_missing_scope_or_raw_thresholds(
    excepted_bundle: dict[str, Any], change: str
) -> None:
    data = excepted_bundle
    row = data["assessment"]["deviations"][0]
    if change == "denied":
        data["policy"]["controls"][1].pop("allow_deviation")
    elif change == "empty":
        row["context_ids"] = []
    elif change == "wrong_scope":
        row["context_ids"] = ["other"]
    elif change == "incomplete":
        data["assessment"]["controls"][1]["incomplete"] = True
    elif change == "unknown":
        data["assessment"]["controls"][1].update(status="unknown", incomplete=True)
    elif change == "future":
        row["approved_at"] = "2026-11-13T11:00:00Z"
    elif change == "expired":
        row["expires_at"] = data["assessment"]["generated_at"]
    elif change == "wrong_source":
        row["source_digest"] = "b" * 64
    elif change == "unsupported_gate":
        row["gate"] = "readiness"
    elif change == "threshold":
        data["policy"]["gates"]["minimum_readiness"] = 51
    else:
        row["inactive_reason"] = "Denied"
    data["assessment"]["policy"]["sha256"] = digest_json(data["policy"])
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_request_active_is_optional_and_expiry_is_not_an_input_parse_error(
    excepted_bundle: dict[str, Any]
) -> None:
    request = deepcopy(excepted_bundle["assessment"]["deviations"][0])
    request.pop("active")
    request["expires_at"] = "2026-11-12T11:00:00Z"
    original = deepcopy(request)
    validate_deviation_request(request)
    assert request == original


@pytest.mark.parametrize("field", ["owner", "reviewer", "reason"])
def test_approval_identity_and_reason_cannot_be_blank(
    excepted_bundle: dict[str, Any], field: str
) -> None:
    request = deepcopy(excepted_bundle["assessment"]["deviations"][0])
    request[field] = " "
    with pytest.raises(ContractError):
        validate_deviation_request(request)
