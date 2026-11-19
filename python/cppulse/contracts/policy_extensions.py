"""Structural and semantic additions for explicit evaluator profile 1.2.

These checks validate caller-supplied data. They never authenticate reviewers,
read project material, collect observations or perform policy evaluation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from cppulse.errors import ContractError

METRIC_PARAMETERS = {
    "metric",
    "metric_version",
    "units",
    "operator",
    "threshold",
    "level",
    "aggregation",
}
REVIEW_PARAMETERS = {
    "evidence_ids",
    "reviewer_ids",
    "minimum_reviewers",
    "required_artifact_ids",
    "identity_requirement",
}


def validate_profile_12_control(control: dict[str, Any], path: str) -> None:
    """Reject blank metric identities and impossible declared-review quorums."""
    parameters = control["parameters"]
    if control["kind"] == "metric_threshold":
        for name in ["metric", "metric_version", "units"]:
            if not parameters[name].strip():
                raise ContractError(
                    f"Metric {name} must not be blank", path=f"{path}/parameters/{name}"
                )
    elif control["kind"] == "reviewed_evidence":
        if any(not value.strip() for value in parameters["reviewer_ids"]):
            raise ContractError(
                "Declared reviewer IDs must not be blank",
                path=path + "/parameters/reviewer_ids",
            )
        if parameters["minimum_reviewers"] > len(set(parameters["reviewer_ids"])):
            raise ContractError(
                "minimum_reviewers exceeds the configured distinct declared reviewer IDs",
                path=path + "/parameters/minimum_reviewers",
            )
        if parameters["minimum_reviewers"] > len(parameters["evidence_ids"]):
            raise ContractError(
                "minimum_reviewers exceeds the selected review evidence record count",
                path=path + "/parameters/minimum_reviewers",
            )


def _utc(value: str, path: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
    if parsed.utcoffset() != timedelta(0):
        raise ContractError("Review provenance times must use UTC", path=path)
    return parsed


def validate_review_details(record: dict[str, Any], path: str) -> None:
    """Check consistent scope, expiry and provenance of a declared review claim."""
    details = record.get("review_details")
    if details is None:
        return
    if (
        record["origin"] != "attestation"
        or record["kind"] != "review"
        or record["receipt_id"] is not None
    ):
        raise ContractError(
            "review_details requires an attestation review with no execution receipt",
            path=path + "/review_details",
        )
    for name in ["statement", "rationale", "recorded_by"]:
        if not details[name].strip():
            raise ContractError(
                f"Review {name} must not be blank", path=f"{path}/review_details/{name}"
            )
    if not record["reviewer"].strip():
        raise ContractError(
            "Declared reviewer must not be blank", path=path + "/reviewer"
        )
    if not set(details["reviewed_artifact_ids"]) <= set(record["artifact_ids"]):
        raise ContractError(
            "reviewed_artifact_ids must refer to this evidence record's retained artifacts",
            path=path + "/review_details/reviewed_artifact_ids",
        )
    if not set(details.get("reviewed_artifact_sha256", {})) <= set(
        details["reviewed_artifact_ids"]
    ):
        raise ContractError(
            "Reviewed artifact hashes must name this review's declared artifacts",
            path=path + "/review_details/reviewed_artifact_sha256",
        )
    reviewed = _utc(details["reviewed_at"], path + "/review_details/reviewed_at")
    recorded = _utc(details["recorded_at"], path + "/review_details/recorded_at")
    expires = _utc(record["expires_at"], path + "/expires_at")
    if recorded < reviewed:
        raise ContractError(
            "Review recorded_at precedes reviewed_at",
            path=path + "/review_details/recorded_at",
        )
    if reviewed >= expires or recorded >= expires:
        raise ContractError(
            "Review provenance is at or after its expiry", path=path + "/expires_at"
        )


def validate_profile_12_assessment(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    policy: dict[str, Any],
    assessment: dict[str, Any],
) -> None:
    """Reject stored new-predicate outcomes/links that contradict supplied facts."""
    if policy.get("evaluator_profile") != "1.2.0":
        return
    from cppulse.policy_extensions import metric_threshold, reviewed_evidence
    from .validation import policy_scope_paths

    bundle: dict[str, Any] = {"run_manifest": manifest}
    for kind, document in flat:
        if kind == "run_manifest":
            continue
        bundle.setdefault(kind, []).append(document)
    if "native_input_binding" not in assessment:
        # Replay the historical predicate semantics only for unmarked stored
        # assessments. Never promote or mutate supplied facts for fresh compute.
        from copy import deepcopy

        bundle = deepcopy(bundle)
        for inventory in bundle.get("analysis_inventory", []):
            for row in inventory["items"]:
                row["buffer_coherence"] = "verified"
    selected = set(
        policy_scope_paths(policy, [row["path"] for row in manifest["source"]["files"]])
    )
    results = {row["id"]: row for row in assessment["controls"]}
    now = _utc(assessment["generated_at"], "/assessment/generated_at")
    for control in policy["controls"]:
        if control["kind"] not in {"metric_threshold", "reviewed_evidence"}:
            continue
        if manifest["source"]["kind"] not in control.get(
            "applicable_to", ["application", "library", "header-only"]
        ):
            continue
        if control["id"] not in results:
            continue  # The enclosing validator reports the missing control.
        actual = results[control["id"]]
        contexts = control["parameters"].get("contexts", policy["contexts"])
        raw = (
            metric_threshold(control, bundle, selected, contexts)
            if control["kind"] == "metric_threshold"
            else reviewed_evidence(control, bundle, selected, contexts, now)
        )
        status, incomplete = raw.status, raw.incomplete
        if manifest.get("input_verification") != "verified":
            status, incomplete = "unknown", True
        prerequisites = [
            results[key] for key in control["depends_on"] if key in results
        ]
        blocked = any(
            row["status"] in {"failed", "unknown"} or row.get("incomplete", False)
            for row in prerequisites
        )
        missing = any(
            row["status"] == "unknown" or row.get("incomplete", False)
            for row in prerequisites
        )
        if blocked or missing:
            incomplete = incomplete or missing or status == "passed"
            status = "unknown" if status == "passed" else status
        if (
            actual["status"] != status
            or actual.get("incomplete") != incomplete
            or set(actual["evidence_ids"]) != set(raw.evidence_ids)
            or set(actual["references"]) != set(raw.references)
            or set(actual.get("fact_ids", [])) != set(raw.fact_ids)
        ):
            raise ContractError(
                "Stored profile 1.2 control contradicts its scoped observed metric/review facts",
                path="/assessment/controls/" + control["id"],
                code="SUBJECT_MISMATCH",
            )
