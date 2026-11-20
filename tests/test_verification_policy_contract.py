"""Explicit evaluator 1.1 selects typed verification without changing 1.0."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate_bundle, validate_evaluation_policy
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.identities import digest_json
from test_policy_contracts import policy as base_policy
from verification_fixtures import coverage_execution_bundle


def verification_policy(kind="minimum_coverage"):
    policy = base_policy.__wrapped__()
    policy["evaluator_profile"] = "1.1.0"
    policy["controls"][0].update(
        id="verification",
        kind=kind,
        parameters=(
            {
                "minimum": 50,
                "fact_ids": ["coverage-observed"],
                "measurement_kind": "line",
                "method": "lcov-da-v1",
            }
            if kind == "minimum_coverage"
            else {"fact_ids": ["asan-observed"], "sanitizer": "asan"}
        ),
    )
    return policy


def verification_assessment_bundle():
    data = coverage_execution_bundle()
    policy = verification_policy()
    context = data["run_manifest"]["contexts"][0]["id"]
    policy["contexts"] = [context]
    data["policy"] = policy
    data["assessment"] = {
        "version": "2.0.0",
        "run_id": data["run_manifest"]["run_id"],
        "source_digest": data["run_manifest"]["source"]["digest"],
        "policy": {
            "id": policy["id"],
            "policy_version": policy["policy_version"],
            "sha256": digest_json(policy),
        },
        "evaluator": {"name": "cppulse.policy", "version": "1.1.0"},
        "gate": "passed",
        "generated_at": "2026-11-13T12:00:00Z",
        "weights": {"passed": 1, "failed": 0, "unknown": 0},
        "scores": {
            key: 100
            for key in [
                "readiness",
                "evidence_completeness",
                "observed_satisfaction",
                "maximum_possible_readiness",
            ]
        },
        "controls": [
            {
                "id": "verification",
                "title": policy["controls"][0]["title"],
                "status": "passed",
                "weight": 1,
                "required": True,
                "context_ids": [context],
                "incomplete": False,
                "reason": "Synthetic exact typed coverage boundary.",
                "evidence_ids": [],
                "fact_ids": ["coverage-observed"],
                "references": [],
            }
        ],
        "deviations": [],
        "limitations": ["Synthetic contract fixture, not execution."],
    }
    return data


def sanitizer_assessment_bundle():
    from test_sanitizer_facts_contract import sanitizer_bundle

    data = sanitizer_bundle()
    template = verification_assessment_bundle()
    policy = verification_policy("sanitizer_outcome")
    policy["contexts"] = [data["run_manifest"]["contexts"][0]["id"]]
    assessment = template["assessment"]
    assessment["policy"]["sha256"] = digest_json(policy)
    assessment["controls"][0]["fact_ids"] = ["asan-observed"]
    data.update(policy=policy, assessment=assessment)
    return data


def failed_sanitizer_assessment_bundle(*, gap=False):
    from verification_fixtures import artifact

    data = sanitizer_assessment_bundle()
    data["sanitizer_facts"].update(
        outcome="failed",
        diagnostics=[
            {
                "id": "diag",
                "kind": "heap-buffer-overflow",
                "message": "Synthetic observed diagnostic.",
                "file": None,
                "line": None,
                "artifact_id": "last-log",
                "test_case_id": "case",
            }
        ],
    )
    if gap:
        artifact(data, "prebuilt", sha="6" * 64)
        data["sanitizer_facts"]["linked_components"].append(
            {
                "subject_id": "prebuilt",
                "artifact_id": "prebuilt",
                "instrumentation": "unverified",
            }
        )
    result = data["assessment"]
    result["controls"][0].update(status="failed", incomplete=gap)
    result.update(
        gate="failed",
        weights={"passed": 0, "failed": 1, "unknown": 0},
        scores={
            "readiness": 0,
            "evidence_completeness": 100,
            "observed_satisfaction": 0,
            "maximum_possible_readiness": 0,
        },
    )
    return data


def test_sanitizer_profile_preserves_known_failure_and_uninstrumented_gap():
    validate_bundle(sanitizer_assessment_bundle())
    validate_bundle(failed_sanitizer_assessment_bundle())
    validate_bundle(failed_sanitizer_assessment_bundle(gap=True))


@pytest.mark.parametrize(
    "mutation",
    [
        "hidden_gap",
        "unexpired_failure",
        "future_inspection",
        "wrong_sanitizer",
        "omitted_fact",
        "false_failure",
    ],
)
def test_sanitizer_profile_refuses_false_clean_or_waivable_current_results(mutation):
    data = failed_sanitizer_assessment_bundle(gap=mutation == "hidden_gap")
    if mutation == "hidden_gap":
        data["assessment"]["controls"][0]["incomplete"] = False
    elif mutation == "unexpired_failure":
        data["evidence"]["records"][0]["expires_at"] = "2026-11-13T11:00:00Z"
    elif mutation == "future_inspection":
        for receipt in [
            next(row for row in data["execution_receipt"] if row["id"] == "elf-binary"),
            next(
                row
                for row in data["execution_facts"]
                if row["receipt"]["id"] == "elf-binary"
            )["receipt"],
        ]:
            receipt.update(
                started_at="2026-11-13T12:59:59Z", finished_at="2026-11-13T13:00:00Z"
            )
    elif mutation == "wrong_sanitizer":
        data["policy"]["controls"][0]["parameters"]["sanitizer"] = "ubsan"
    elif mutation == "omitted_fact":
        data["assessment"]["controls"][0]["fact_ids"] = []
    else:
        data["sanitizer_facts"].update(outcome="passed", diagnostics=[])
    data["assessment"]["policy"]["sha256"] = digest_json(data["policy"])
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_identical_coverage_units_deduplicate_but_conflicts_cannot_average():
    data = verification_assessment_bundle()
    copy = deepcopy(data["coverage_facts"])
    copy["id"] = "coverage-copy"
    data["coverage_facts"] = [data["coverage_facts"], copy]
    data["policy"]["controls"][0]["parameters"]["fact_ids"].append(copy["id"])
    data["assessment"]["controls"][0]["fact_ids"].append(copy["id"])
    data["assessment"]["policy"]["sha256"] = digest_json(data["policy"])
    validate_bundle(data)
    measurement = copy["files"][0]["measurements"][0]
    measurement["covered"] = 0
    measurement["units"][0]["covered"] = 0
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize("kind", ["minimum_coverage", "sanitizer_outcome"])
def test_explicit_profile_11_accepts_only_the_new_typed_predicates(kind):
    policy = verification_policy(kind)
    validate_evaluation_policy(policy)


def test_profile_absence_preserves_four_kind_version_10():
    policy = base_policy.__wrapped__()
    validate_evaluation_policy(policy)
    policy["evaluator_profile"] = "1.1.0"
    validate_evaluation_policy(policy)
    policy["evaluator_profile"] = "1.0.0"
    validate_evaluation_policy(policy)


@pytest.mark.parametrize("profile", [[], {}, None])
def test_malformed_profile_does_not_escape_as_an_unhashable_python_error(profile):
    policy = verification_policy()
    policy["evaluator_profile"] = profile
    with pytest.raises(ContractError):
        validate_evaluation_policy(policy)


@pytest.mark.parametrize("profile", [[], {}, None])
def test_public_evaluator_reports_structured_invalid_profile_before_bundle_lookup(
    profile,
):
    from cppulse.policy import evaluate_policy

    policy = verification_policy()
    policy["evaluator_profile"] = profile
    with pytest.raises(ContractError) as caught:
        evaluate_policy(policy, {}, generated_at="2026-11-13T12:00:00Z")
    assert caught.value.as_dict() == {
        "code": "INVALID_CONTRACT",
        "message": "Evaluator profile must be a version string",
        "path": "/evaluator_profile",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_profile",
        "implicit_upgrade",
        "explicit_override",
        "metric",
        "review",
        "empty_facts",
        "outside_context",
        "missing_kind",
        "empty_method",
    ],
)
def test_profile_11_refuses_unsupported_or_ambiguous_evaluation(mutation):
    policy = verification_policy()
    if mutation == "unknown_profile":
        policy["evaluator_profile"] = "2.0.0"
    elif mutation == "implicit_upgrade":
        policy.pop("evaluator_profile")
    elif mutation == "explicit_override":
        with pytest.raises(ContractError):
            validate_evaluation_policy(policy, profile_version="1.0.0")
        return
    elif mutation in {"metric", "review"}:
        policy["controls"][0].update(
            kind="metric_threshold" if mutation == "metric" else "reviewed_evidence",
            parameters=(
                {"metric": "complexity", "operator": "lte", "threshold": 10}
                if mutation == "metric"
                else {"evidence_ids": ["review"]}
            ),
        )
    elif mutation == "empty_facts":
        policy["controls"][0]["parameters"]["fact_ids"] = []
    elif mutation == "outside_context":
        policy["controls"][0]["parameters"]["contexts"] = ["absent"]
    elif mutation == "missing_kind":
        policy["controls"][0]["parameters"].pop("measurement_kind")
    else:
        policy["controls"][0]["parameters"]["method"] = ""
    with pytest.raises((ContractError, UnsupportedVersion)):
        validate_evaluation_policy(policy)


def test_current_11_assessment_binds_typed_fact_ids_and_unrounded_counts():
    validate_bundle(verification_assessment_bundle())


def test_schema_valid_integral_float_counts_keep_json_without_runtime_type_error():
    data = verification_assessment_bundle()
    measurement = data["coverage_facts"]["files"][0]["measurements"][0]
    for row in [measurement, *measurement["units"]]:
        for key in ["covered", "total"]:
            row[key] = float(row[key])
    validate_bundle(data)
    assert isinstance(measurement["covered"], float)


@pytest.mark.parametrize(
    "mutation",
    [
        "profile_mismatch",
        "missing_fact_reference",
        "wrong_kind",
        "below_minimum",
        "zero_denominator",
        "expired_test",
        "future_proof",
        "imported_fact",
    ],
)
def test_passed_verification_assessment_refuses_false_positive_provenance(mutation):
    data = verification_assessment_bundle()
    policy = data["policy"]
    if mutation == "profile_mismatch":
        data["assessment"]["evaluator"]["version"] = "1.0.0"
    elif mutation == "missing_fact_reference":
        data["assessment"]["controls"][0]["fact_ids"] = []
    elif mutation == "wrong_kind":
        policy["controls"][0]["parameters"]["measurement_kind"] = "branch"
    elif mutation == "below_minimum":
        policy["controls"][0]["parameters"]["minimum"] = 50.00000000000001
    elif mutation == "zero_denominator":
        data["coverage_facts"]["files"][0]["measurements"][0].update(
            covered=0, total=0, units=[]
        )
    elif mutation == "expired_test":
        data["evidence"]["records"][0]["expires_at"] = "2026-11-13T11:00:00Z"
    elif mutation == "future_proof":
        data["coverage_facts"]["proof_receipt_ids"].append("ctest-version")
        for receipt in [
            next(
                row for row in data["execution_receipt"] if row["id"] == "ctest-version"
            ),
            next(
                row
                for row in data["execution_facts"]
                if row["receipt"]["id"] == "ctest-version"
            )["receipt"],
        ]:
            receipt.update(
                started_at="2026-11-13T12:59:59Z", finished_at="2026-11-13T13:00:00Z"
            )
    else:
        data["coverage_facts"].update(
            origin="import",
            receipt_id=None,
            proof_receipt_ids=[],
            test_evidence_ids=[],
            instrumentation=[],
            profiles=[],
        )
    data["assessment"]["policy"]["sha256"] = digest_json(policy)
    with pytest.raises(ContractError):
        validate_bundle(data)
