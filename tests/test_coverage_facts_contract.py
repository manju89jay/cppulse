"""Coverage contract arithmetic and provenance; synthetic records do not run tools."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import load_schema, validate, validate_bundle
from cppulse.errors import ContractError
from test_contracts_v2 import manifest_document


def coverage_document() -> dict[str, Any]:
    manifest = manifest_document()
    source = manifest["source"]["files"][0]
    return {
        "version": "2.0.0",
        "id": "coverage-import",
        "source_digest": manifest["source"]["digest"],
        "context_id": manifest["contexts"][0]["id"],
        "origin": "import",
        "producer": {"name": "gcov", "version": "14.2.0"},
        "adapter": {"name": "lcov", "version": "1.0.0"},
        "report_artifact_id": "coverage-report",
        "receipt_id": None,
        "proof_receipt_ids": [],
        "test_evidence_ids": [],
        "instrumentation": [],
        "profiles": [],
        "usability": "usable",
        "files": [
            {
                "file": source["path"],
                "source_sha256": source["sha256"],
                "measurements": [
                    {
                        "kind": "line",
                        "method": "lcov-da-v1",
                        "covered": 1,
                        "total": 2,
                        "units": [
                            {"id": "line:1", "covered": 1, "total": 1},
                            {"id": "line:2", "covered": 0, "total": 1},
                        ],
                    }
                ],
            }
        ],
        "limitations": [
            "Synthetic imported counts; no execution or authenticity claim."
        ],
    }


def coverage_bundle() -> dict[str, Any]:
    manifest = manifest_document()
    manifest["artifacts"].append(
        {
            "id": "coverage-report",
            "path": "reports/coverage.info",
            "sha256": "b" * 64,
            "size_bytes": 10,
            "media_type": "text/plain",
        }
    )
    return {"run_manifest": manifest, "coverage_facts": coverage_document()}


def test_coverage_counts_are_a_packaged_distinct_contract() -> None:
    assert load_schema("coverage_facts")["title"]
    validate_bundle(coverage_bundle())


def test_cobertura_branch_groups_do_not_invent_individual_branch_identities() -> None:
    document = coverage_document()
    document["adapter"]["name"] = "cobertura"
    document["files"][0]["measurements"] = [
        {
            "kind": "branch",
            "method": "cobertura-condition-counts-v1",
            "covered": 2,
            "total": 3,
            "units": [{"id": "line:5:conditions", "covered": 2, "total": 3}],
        }
    ]
    validate("coverage_facts", document)


@pytest.mark.parametrize("kind", ["line", "branch", "function"])
def test_measurement_kinds_stay_distinct(kind: str) -> None:
    document = coverage_document()
    document["files"][0]["measurements"][0]["kind"] = kind
    document["files"][0]["measurements"][0]["method"] = {
        "line": "lcov-da-v1",
        "branch": "lcov-brda-v1",
        "function": "lcov-fnda-v1",
    }[kind]
    validate("coverage_facts", document)


@pytest.mark.parametrize(
    "kind,method",
    [("line", "lcov-da-v1"), ("branch", "lcov-brda-v1"), ("function", "lcov-fnda-v1")],
)
def test_individual_measurement_points_cannot_invent_group_denominators(kind, method):
    document = coverage_document()
    measurement = document["files"][0]["measurements"][0]
    measurement.update(
        kind=kind,
        method=method,
        units=[{"id": "invented-group", "covered": 1, "total": 2}],
    )
    with pytest.raises(ContractError):
        validate("coverage_facts", document)


@pytest.mark.parametrize(
    "adapter,kind,method",
    [("lcov", "branch", "lcov-da-v1"), ("cobertura", "function", "lcov-fnda-v1")],
)
def test_coverage_method_cannot_relabel_measurement_semantics(adapter, kind, method):
    document = coverage_document()
    document["adapter"]["name"] = adapter
    measurement = document["files"][0]["measurements"][0]
    measurement.update(kind=kind, method=method)
    with pytest.raises(ContractError):
        validate("coverage_facts", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "covered",
        "total",
        "negative",
        "unit_duplicate",
        "measurement_duplicate",
        "file_duplicate",
        "unsafe",
        "mcdc",
        "decision",
        "unknown_field",
    ],
)
def test_coverage_rejects_inconsistent_or_unsupported_counts(mutation: str) -> None:
    document = coverage_document()
    file = document["files"][0]
    measurement = file["measurements"][0]
    if mutation in {"covered", "total"}:
        measurement[mutation] = 3
    elif mutation == "negative":
        measurement["units"][0]["covered"] = -1
    elif mutation == "unit_duplicate":
        measurement["units"][1]["id"] = measurement["units"][0]["id"]
    elif mutation == "measurement_duplicate":
        file["measurements"].append(deepcopy(measurement))
    elif mutation == "file_duplicate":
        document["files"].append(deepcopy(file))
    elif mutation == "unsafe":
        file["file"] = "../main.cpp"
    elif mutation in {"mcdc", "decision"}:
        measurement["kind"] = mutation
    else:
        measurement["confidence"] = 1
    with pytest.raises(ContractError):
        validate("coverage_facts", document)


def test_import_can_preserve_unknown_source_binding_without_observed_execution() -> (
    None
):
    document = coverage_document()
    document["files"][0]["source_sha256"] = None
    document["usability"] = "mismatched"
    validate("coverage_facts", document)
    document["receipt_id"] = "claim"
    with pytest.raises(ContractError):
        validate("coverage_facts", document)


@pytest.mark.parametrize(
    "mutation", ["report", "source", "context", "file", "sha", "duplicate"]
)
def test_coverage_bundle_rejects_broken_material_identity(mutation: str) -> None:
    data = coverage_bundle()
    document = data["coverage_facts"]
    if mutation == "report":
        document["report_artifact_id"] = "absent"
    elif mutation == "source":
        document["source_digest"] = "f" * 64
    elif mutation == "context":
        document["context_id"] = "absent"
    elif mutation == "file":
        document["files"][0]["file"] = "not-selected.cpp"
    elif mutation == "sha":
        document["files"][0]["source_sha256"] = "f" * 64
    else:
        data["coverage_facts"] = [document, deepcopy(document)]
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_execution_claim_requires_typed_instrumented_profile_and_test_proof() -> None:
    document = coverage_document()
    document.update(origin="execution", receipt_id="report-step")
    with pytest.raises(ContractError):
        validate("coverage_facts", document)


def test_zero_denominator_is_preserved_as_counts_not_a_success_percentage() -> None:
    document = coverage_document()
    measurement = document["files"][0]["measurements"][0]
    measurement.update(covered=0, total=0, units=[])
    validate("coverage_facts", document)


def test_execution_coverage_has_a_closed_synthetic_material_and_ctest_chain() -> None:
    from verification_fixtures import coverage_execution_bundle

    validate_bundle(coverage_execution_bundle())


def test_step_input_copies_keep_original_role_identity_by_exact_bytes() -> None:
    from verification_fixtures import coverage_execution_bundle

    data = coverage_execution_bundle()
    original = next(
        row for row in data["run_manifest"]["artifacts"] if row["id"] == "mapping"
    )
    copied = {**original, "id": "mapping-copy", "path": "copies/mapping"}
    data["run_manifest"]["artifacts"].append(copied)
    report = next(
        row for row in data["execution_facts"] if row["receipt"]["id"] == "report"
    )
    next(
        row
        for row in report["binding"]["input_artifacts"]
        if row["artifact_id"] == "mapping"
    )["artifact_id"] = "mapping-copy"
    for receipt in [
        report["receipt"],
        next(row for row in data["execution_receipt"] if row["id"] == "report"),
    ]:
        receipt["artifact_ids"] = [
            "mapping-copy" if value == "mapping" else value
            for value in receipt["artifact_ids"]
        ]
    validate_bundle(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "proof_omitted",
        "no_plan",
        "no_source",
        "profile_reused",
        "no_link",
        "zero_tests",
        "all_skipped",
        "unrelated_binary",
        "wrong_profile",
        "unverified_source",
    ],
)
def test_execution_coverage_rejects_unobserved_or_accumulated_material(
    mutation: str,
) -> None:
    from verification_fixtures import coverage_execution_bundle

    data = coverage_execution_bundle()
    doc = data["coverage_facts"]
    facts = {row["receipt"]["id"]: row for row in data["execution_facts"]}
    if mutation == "proof_omitted":
        doc["proof_receipt_ids"] = ["report"]
    elif mutation == "no_plan":
        data.pop("collection_plan")
    elif mutation == "no_source":
        facts["compile"]["input_facts"] = []
        facts["compile"]["input_after_facts"] = []
        facts["compile"]["binding"]["input_artifacts"] = []
    elif mutation == "profile_reused":
        facts["test"]["output_facts"][0]["freshness"] = "modified"
    elif mutation == "no_link":
        facts["link"]["binding"]["status"] = "invalid"
        facts["link"]["binding"]["limitations"] = ["Synthetic link binding problem."]
    elif mutation in {"zero_tests", "all_skipped"}:
        counts = {
            "total": 0 if mutation == "zero_tests" else 1,
            "passed": 0,
            "failed": 0,
            "skipped": 0 if mutation == "zero_tests" else 1,
            "errors": 0,
        }
        facts["test"]["receipt"]["tests"] = counts
        next(row for row in data["execution_receipt"] if row["id"] == "test")[
            "tests"
        ] = deepcopy(counts)
    elif mutation == "unrelated_binary":
        doc["profiles"][0]["binary_artifact_id"] = "object"
    elif mutation == "wrong_profile":
        doc["profiles"][0]["artifact_id"] = "junit"
    else:
        data["run_manifest"]["input_verification"] = "unverified"
    with pytest.raises(ContractError):
        validate_bundle(data)
