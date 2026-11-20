"""Bounded assessment provenance preserves parent and original facts pins."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate_bundle
from cppulse.errors import ContractError
from test_public_workflow_contracts import run_ref
from test_verification_policy_contract import verification_assessment_bundle
from verification_fixtures import artifact


def lineage_bundle():
    data = verification_assessment_bundle()
    source = data["run_manifest"]["source"]["digest"]
    for identifier in [
        "base-manifest",
        "parent-manifest",
        "policy-document",
        "assessment-document",
        "old-history",
    ]:
        artifact(
            data,
            identifier,
            sha={
                "base-manifest": "a",
                "parent-manifest": "b",
                "policy-document": "c",
                "assessment-document": "d",
                "old-history": "e",
            }[identifier]
            * 64,
        )
    for row in data["run_manifest"]["artifacts"]:
        if row["id"] in {"policy-document", "assessment-document"}:
            row["contract"] = {
                "kind": "policy" if row["id"] == "policy-document" else "assessment",
                "version": "2.0.0",
            }
    base = run_ref(source=source)
    base.update(run_id="original-facts", manifest_sha256="a" * 64)
    parent = run_ref(source=source)
    parent.update(run_id="selected-parent", manifest_sha256="b" * 64)
    data["assessment_lineage"] = {
        "version": "2.0.0",
        "id": "lineage",
        "source_digest": source,
        "facts_base_run": base,
        "selected_parent_run": parent,
        "base_manifest_artifact_id": "base-manifest",
        "parent_manifest_artifact_id": "parent-manifest",
        "policy_artifact_id": "policy-document",
        "assessment_artifact_id": "assessment-document",
        "history_artifact_ids": ["old-history"],
        "created_at": "2026-11-13T12:00:00Z",
    }
    return data


def test_lineage_keeps_original_facts_and_selected_parent_separate():
    validate_bundle(lineage_bundle())


def test_first_assessment_may_select_the_original_facts_as_parent():
    data = lineage_bundle()
    doc = data["assessment_lineage"]
    doc["selected_parent_run"] = deepcopy(doc["facts_base_run"])
    doc["parent_manifest_artifact_id"] = doc["base_manifest_artifact_id"]
    validate_bundle(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "base_source",
        "parent_source",
        "base_sha",
        "parent_sha",
        "missing_base",
        "missing_parent",
        "wrong_policy",
        "wrong_assessment",
        "typed_history",
        "missing_history",
        "active_history",
        "duplicate_lineage",
        "invalid_created",
        "self_parent",
        "multiple_active_assessments",
    ],
)
def test_lineage_rejects_unbound_or_ambiguous_reassessment_metadata(mutation):
    data = lineage_bundle()
    doc = data["assessment_lineage"]
    if mutation == "base_source":
        doc["facts_base_run"]["source_digest"] = "f" * 64
    elif mutation == "parent_source":
        doc["selected_parent_run"]["source_digest"] = "f" * 64
    elif mutation == "base_sha":
        doc["facts_base_run"]["manifest_sha256"] = "f" * 64
    elif mutation == "parent_sha":
        doc["selected_parent_run"]["manifest_sha256"] = "f" * 64
    elif mutation == "missing_base":
        doc["base_manifest_artifact_id"] = "absent"
    elif mutation == "missing_parent":
        doc["parent_manifest_artifact_id"] = "absent"
    elif mutation == "wrong_policy":
        doc["policy_artifact_id"] = "assessment-document"
    elif mutation == "wrong_assessment":
        doc["assessment_artifact_id"] = "policy-document"
    elif mutation == "typed_history":
        next(
            row
            for row in data["run_manifest"]["artifacts"]
            if row["id"] == "old-history"
        )["contract"] = {"kind": "assessment", "version": "2.0.0"}
    elif mutation == "missing_history":
        doc["history_artifact_ids"] = ["absent"]
    elif mutation == "active_history":
        doc["history_artifact_ids"] = ["assessment-document"]
    elif mutation == "duplicate_lineage":
        second = deepcopy(doc)
        second["id"] = "other"
        data["assessment_lineage"] = [doc, second]
    elif mutation == "self_parent":
        doc["selected_parent_run"]["run_id"] = data["run_manifest"]["run_id"]
    elif mutation == "multiple_active_assessments":
        row = deepcopy(
            next(
                row
                for row in data["run_manifest"]["artifacts"]
                if row["id"] == "assessment-document"
            )
        )
        row.update(id="another-assessment", path="documents/another-assessment.json")
        data["run_manifest"]["artifacts"].append(row)
    else:
        doc["created_at"] = "invalid"
    with pytest.raises(ContractError):
        validate_bundle(data)
