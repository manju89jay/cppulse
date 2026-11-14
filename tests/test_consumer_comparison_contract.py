"""Imported configuration correspondence never replaces missing local checks."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate_bundle
from cppulse.errors import ContractError
from test_consumer_usage_contract import usage_bundle
from verification_fixtures import artifact


def comparison_bundle():
    data = usage_bundle()
    usage = data["consumer_usage"]
    source = data["run_manifest"]["source"]["digest"]
    config = deepcopy(usage["observed_configuration"])
    data["consumer_matrix"] = {
        "version": "2.0.0",
        "id": "local-matrix",
        "source_digest": source,
        "subject_id": "package",
        "cases": [
            {
                "id": "local-case",
                "required": True,
                "context_id": usage["context_id"],
                "configuration": config,
                "tests": [],
                "instantiations": [],
                "self_containment_headers": [],
                "usage_ids": [usage["id"]],
            }
        ],
        "limitations": ["Synthetic selected matrix."],
    }
    for identifier in [
        "upstream-manifest",
        "local-manifest",
        "upstream-subject",
        "upstream-matrix",
    ]:
        artifact(data, identifier, sha="8" * 64)
    data["consumer_comparison"] = {
        "version": "2.0.0",
        "id": "comparison",
        "source_digest": source,
        "local_source_digest": source,
        "upstream_source_digest": "f" * 64,
        "upstream_manifest_sha256": "8" * 64,
        "local_manifest_sha256": "8" * 64,
        "upstream_manifest_artifact_id": "upstream-manifest",
        "local_manifest_artifact_id": "local-manifest",
        "upstream_subject_artifact_id": "upstream-subject",
        "upstream_matrix_artifact_id": "upstream-matrix",
        "upstream_subject_id": "foreign-package",
        "local_subject_id": "package",
        "upstream_matrix_id": "foreign-matrix",
        "local_matrix_id": "local-matrix",
        "import_origin": "import",
        "authentication": "unverified",
        "producer": {"name": "cppulse.consumer-compare", "version": "1.0.0"},
        "generated_at": "2026-11-13T12:00:00Z",
        "cases": [
            {
                "case_id": "local-case",
                "upstream_case_id": "foreign-case",
                "status": "compatible",
                "reason": "Synthetic configuration correspondence only.",
                "matching_dimensions": list(config),
                "mismatches": [],
                "local_test_status": "unknown",
                "local_test_evidence_ids": [],
                "required_local_checks": [],
                "missing_local_checks": [],
            }
        ],
        "limitations": [
            "Synthetic raw artifact descriptors; real producer checks foreign bytes."
        ],
    }
    return data


def test_foreign_source_stays_separate_and_compatible_context_can_miss_local_tests():
    data = comparison_bundle()
    data["consumer_matrix"]["cases"][0]["tests"] = ["application-test"]
    case = data["consumer_comparison"]["cases"][0]
    case.update(
        required_local_checks=["application-test"],
        missing_local_checks=["application-test"],
    )
    validate_bundle(data)


def test_verified_usage_from_another_subject_cannot_establish_compatibility():
    data = comparison_bundle()
    original = data["distribution_subject"]
    selected = deepcopy(original)
    selected["id"] = "another-package"
    selected["distribution_files"][0]["path"] = "include/other.hpp"
    data["distribution_subject"] = [original, selected]
    data["consumer_matrix"]["subject_id"] = selected["id"]
    data["consumer_comparison"]["local_subject_id"] = selected["id"]
    # Same compiler and even identical distributed bytes do not transfer a
    # proof whose explicit selected subject remains the original package.
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize("difference", ["kind", "bytes", "path"])
def test_distribution_mismatch_is_distinct_from_configuration_dimensions(difference):
    data = comparison_bundle()
    case = data["consumer_comparison"]["cases"][0]
    case.update(
        status="incompatible",
        mismatches=["distribution"],
        reason="Selected distribution "
        + difference
        + " differs; compiler configuration still matches.",
    )
    validate_bundle(data)
    assert "compiler" not in case["mismatches"]


def test_distribution_is_not_a_configuration_matching_dimension():
    data = comparison_bundle()
    data["consumer_comparison"]["cases"][0]["matching_dimensions"].append(
        "distribution"
    )
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_role",
        "manifest_hash",
        "local_source",
        "missing_matrix",
        "missing_usage",
        "unknown_dimension",
        "unknown_dependency",
        "mismatching_usage",
        "empty_matching",
        "hidden_required_test",
        "false_passed_test",
        "authentication",
    ],
)
def test_comparison_refuses_identity_or_false_local_applicability(mutation):
    data = comparison_bundle()
    doc = data["consumer_comparison"]
    case = doc["cases"][0]
    if mutation == "foreign_role":
        doc["upstream_subject_artifact_id"] = "absent"
    elif mutation == "manifest_hash":
        doc["upstream_manifest_sha256"] = "f" * 64
    elif mutation == "local_source":
        doc["local_source_digest"] = "f" * 64
    elif mutation == "missing_matrix":
        doc["local_matrix_id"] = "absent"
    elif mutation == "missing_usage":
        data["consumer_matrix"]["cases"][0]["usage_ids"] = ["absent"]
    elif mutation == "unknown_dimension":
        data["consumer_matrix"]["cases"][0]["configuration"]["abi"] = None
        data["consumer_usage"]["observed_configuration"]["abi"] = None
    elif mutation == "unknown_dependency":
        dependency = {
            "id": "external-prebuilt",
            "sha256": None,
            "availability": "unavailable",
        }
        data["consumer_matrix"]["cases"][0]["configuration"]["dependencies"] = [
            dependency
        ]
        data["consumer_usage"]["observed_configuration"]["dependencies"] = [
            deepcopy(dependency)
        ]
    elif mutation == "mismatching_usage":
        data["consumer_matrix"]["cases"][0]["configuration"]["exceptions"] = False
    elif mutation == "empty_matching":
        case["matching_dimensions"] = []
    elif mutation == "hidden_required_test":
        data["consumer_matrix"]["cases"][0]["tests"] = ["application-test"]
    elif mutation == "false_passed_test":
        case["local_test_status"] = "passed"
    else:
        doc["authentication"] = "verified"
    with pytest.raises(ContractError):
        validate_bundle(data)
