"""Profile 1.2 contracts add explicit numeric and declared-review semantics."""

from __future__ import annotations

from copy import deepcopy
from importlib import resources
import json
from typing import Any

import pytest

from cppulse.contracts import validate, validate_evaluation_policy
from cppulse.errors import ContractError, UnsupportedVersion
from test_contracts_v2 import (
    artifact_document,
    evidence_document,
    policy_document,
    source_document,
)


def metric_policy() -> dict[str, Any]:
    """An organization explicitly selects units, metric method and aggregation."""
    policy = policy_document()
    policy["evaluator_profile"] = "1.2.0"
    policy["controls"][0].update(
        kind="metric_threshold",
        parameters={
            "metric": "cyclomatic_complexity",
            "metric_version": "cppulse-metrics-1",
            "units": "count",
            "operator": "lte",
            "threshold": 10,
            "level": "symbol",
            "aggregation": "each",
        },
    )
    return policy


def review_policy() -> dict[str, Any]:
    """Named reviewers are allowed identities, not authenticated human actors."""
    policy = policy_document()
    policy["evaluator_profile"] = "1.2.0"
    policy["controls"][0].update(
        kind="reviewed_evidence",
        parameters={
            "evidence_ids": ["review"],
            "reviewer_ids": ["reviewer-alice", "reviewer-bob"],
            "minimum_reviewers": 1,
            "required_artifact_ids": ["findings"],
            "identity_requirement": "declared",
        },
    )
    return policy


def declared_review() -> dict[str, Any]:
    """A synthetic caller-supplied review claim, never an authenticated approval."""
    document = evidence_document()
    record = document["records"][0]
    record.update(
        id="review",
        origin="attestation",
        kind="review",
        receipt_id=None,
        reviewer="reviewer-alice",
        expires_at="2026-12-13T12:00:00Z",
        review_details={
            "version": "1.0.0",
            "source_digest": source_document()["digest"],
            "statement": "The declared selected evidence was reviewed.",
            "rationale": "Synthetic controlled-review fixture, not a real approval.",
            "reviewed_at": "2026-11-13T10:00:00Z",
            "recorded_at": "2026-11-13T10:01:00Z",
            "recorded_by": "fixture-author",
            "reviewed_artifact_ids": ["findings"],
            "reviewed_artifact_sha256": {"findings": artifact_document()["sha256"]},
            "identity_assurance": "self_declared",
            "limitations": ["Reviewer identity has not been authenticated."],
        },
    )
    return document


@pytest.mark.parametrize("factory", [metric_policy, review_policy])
def test_profile_12_accepts_explicit_new_predicate_contracts(factory: Any) -> None:
    validate_evaluation_policy(factory(), profile_version="1.2.0")


@pytest.mark.parametrize("field", ["metric_version", "units", "level", "aggregation"])
def test_metric_contract_does_not_assume_method_units_or_aggregation(
    field: str,
) -> None:
    policy = metric_policy()
    del policy["controls"][0]["parameters"][field]

    with pytest.raises(ContractError) as raised:
        validate_evaluation_policy(policy)

    assert raised.value.code == "INVALID_CONTRACT"
    assert "/parameters" in raised.value.path


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_numeric_thresholds_must_be_finite(value: float) -> None:
    policy = metric_policy()
    policy["controls"][0]["parameters"]["threshold"] = value

    with pytest.raises(ContractError, match="finite"):
        validate_evaluation_policy(policy)


@pytest.mark.parametrize(
    "parameters",
    [
        {"minimum_reviewers": 0},
        {"minimum_reviewers": 3},
        {"reviewer_ids": []},
        {"reviewer_ids": ["reviewer-alice", "reviewer-alice"]},
        {"required_artifact_ids": []},
        {"identity_requirement": "authenticated"},
    ],
)
def test_declared_review_contract_rejects_unmet_or_invented_identity_requirements(
    parameters: dict[str, Any],
) -> None:
    policy = review_policy()
    policy["controls"][0]["parameters"].update(parameters)

    with pytest.raises(ContractError) as raised:
        validate_evaluation_policy(policy)

    assert raised.value.code == "INVALID_CONTRACT"


def test_declared_review_quorum_cannot_exceed_selected_record_count() -> None:
    policy = review_policy()
    policy["controls"][0]["parameters"]["minimum_reviewers"] = 2
    with pytest.raises(ContractError, match="evidence"):
        validate_evaluation_policy(policy)


def test_complete_declared_review_metadata_is_retained_as_data() -> None:
    document = declared_review()
    before = deepcopy(document)

    validate("evidence", document)

    assert document == before
    assert document["records"][0]["origin"] == "attestation"
    assert (
        document["records"][0]["review_details"]["identity_assurance"]
        == "self_declared"
    )


@pytest.mark.parametrize(
    "change, message",
    [
        ({"rationale": " "}, "rationale"),
        ({"statement": ""}, "statement"),
        ({"reviewed_artifact_ids": ["not-retained"]}, "reviewed_artifact_ids"),
        ({"recorded_at": "2026-11-13T09:59:00Z"}, "recorded"),
        (
            {
                "reviewed_at": "2026-12-14T10:00:00Z",
                "recorded_at": "2026-12-14T10:01:00Z",
            },
            "expiry",
        ),
        ({"identity_assurance": "authenticated"}, "identity_assurance"),
    ],
)
def test_declared_review_metadata_rejects_inconsistent_scope_or_provenance(
    change: dict[str, Any], message: str
) -> None:
    document = declared_review()
    document["records"][0]["review_details"].update(change)

    with pytest.raises(ContractError) as raised:
        validate("evidence", document)

    assert message in str(raised.value) or message in raised.value.path


def test_earlier_attestation_records_remain_readable_without_implicit_upgrade() -> None:
    document = declared_review()
    del document["records"][0]["review_details"]

    validate("evidence", document)


@pytest.mark.parametrize(
    "change",
    [
        {"reviewed_artifact_sha256": {"not-reviewed": "a" * 64}},
        {"reviewed_artifact_sha256": {"findings": "not-a-sha256"}},
        {"reviewed_artifact_sha256": {}},
    ],
)
def test_review_hashes_are_valid_identities_of_declared_artifacts(
    change: dict[str, Any],
) -> None:
    document = declared_review()
    document["records"][0]["review_details"].update(change)
    with pytest.raises(ContractError):
        validate("evidence", document)


def test_review_metadata_without_hash_binding_remains_readable() -> None:
    document = declared_review()
    del document["records"][0]["review_details"]["reviewed_artifact_sha256"]
    validate("evidence", document)


@pytest.mark.parametrize(
    "name", ["measured-library-example.json", "organization-reviewed-example.json"]
)
def test_packaged_measured_policy_examples_select_profile12_explicitly(
    name: str,
) -> None:
    policy = json.loads(
        resources.files("cppulse").joinpath("data", "policies", name).read_text()
    )
    validate_evaluation_policy(policy)
    assert policy["evaluator_profile"] == "1.2.0"
    assert policy["standards"] == []


@pytest.mark.parametrize("profile", ["1.0.0", "1.1.0"])
@pytest.mark.parametrize("kind", ["metric_threshold", "reviewed_evidence"])
def test_earlier_profiles_do_not_silently_gain_new_evaluators(
    profile: str, kind: str
) -> None:
    policy = policy_document()
    policy["evaluator_profile"] = profile
    policy["controls"][0].update(
        kind=kind,
        parameters=(
            {"metric": "cyclomatic_complexity", "operator": "lte", "threshold": 10}
            if kind == "metric_threshold"
            else {"evidence_ids": ["review"]}
        ),
    )

    with pytest.raises(UnsupportedVersion):
        validate_evaluation_policy(policy)
