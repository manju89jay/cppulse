"""Selected distributed bytes need actual compiler proof rather than -I intent."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError
from test_consumer_contracts import configuration
from verification_fixtures import (
    add_ctest_plan,
    artifact,
    coverage_execution_bundle,
    step,
)


def usage_bundle():
    data = coverage_execution_bundle()
    data.pop("coverage_facts")
    source = data["run_manifest"]["source"]["files"][0]
    artifact(data, "depfile", sha="7" * 64)
    compile = next(
        row for row in data["execution_facts"] if row["receipt"]["id"] == "compile"
    )
    compile["binding"]["output_artifacts"].append(
        {"path": "build/main.d", "artifact_id": "depfile"}
    )
    compile["output_facts"].append(
        {
            **deepcopy(compile["output_facts"][0]),
            "path": "build/main.d",
            "sha256": "7" * 64,
        }
    )
    for receipt in [
        compile["receipt"],
        next(row for row in data["execution_receipt"] if row["id"] == "compile"),
    ]:
        receipt["artifact_ids"].append("depfile")
    step(data, "configuration-probe", {source["path"]: "source"}, {})
    step(data, "target-probe", {}, {})
    add_ctest_plan(data)
    data["distribution_subject"] = {
        "version": "2.0.0",
        "id": "package",
        "source_digest": data["run_manifest"]["source"]["digest"],
        "kind": "header-only",
        "source_relation": "selected_sources",
        "source_files": [deepcopy(source)],
        "distribution_files": [
            {
                "path": "include/demo.hpp",
                "artifact_id": "source",
                "sha256": source["sha256"],
                "size_bytes": source["size_bytes"],
            }
        ],
        "limitations": ["Synthetic finite selected package."],
    }
    config = configuration()
    config["linking"] = "header-only"
    data["consumer_usage"] = {
        "version": "2.0.0",
        "id": "header-use",
        "source_digest": data["run_manifest"]["source"]["digest"],
        "subject_id": "package",
        "context_id": data["run_manifest"]["contexts"][0]["id"],
        "receipt_id": "compile",
        "producer": {"name": "cppulse.consumer-use", "version": "1.0.0"},
        "status": "verified",
        "required_artifact_ids": ["source"],
        "records": [
            {
                "distribution_artifact_id": "source",
                "proof_kind": "depfile",
                "proof_artifact_id": "depfile",
                "members": ["include/demo.hpp"],
            }
        ],
        "proof_receipt_ids": ["compile", "configuration-probe", "target-probe"],
        "observed_configuration": config,
        "configuration_probe_receipt_id": "configuration-probe",
        "target_probe_receipt_id": "target-probe",
        "compiler_version": "14.2.0",
        "linker_version": None,
        "self_containment_headers": [],
        "limitations": [
            "Synthetic transformation fixture; does not compile a real package."
        ],
    }
    return data


def test_distributed_header_usage_needs_source_and_generated_dependency_roles():
    validate_bundle(usage_bundle())


def test_uncollected_configuration_probe_is_not_actual_configuration_proof():
    data = usage_bundle()
    next(
        row
        for row in data["execution_facts"]
        if row["receipt"]["id"] == "configuration-probe"
    )["material_status"] = "not_collected"
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "empty_records",
        "missing_required",
        "missing_configuration",
        "no_probe",
        "wrong_source",
        "missing_subject",
        "not_input",
        "not_proof_output",
        "different_probe_tool",
        "missing_proof_receipt",
    ],
)
def test_consumer_use_refuses_declared_only_or_wrong_distributed_artifacts(mutation):
    data = usage_bundle()
    doc = data["consumer_usage"]
    if mutation == "empty_records":
        doc["records"] = []
    elif mutation == "missing_required":
        doc["required_artifact_ids"] = ["binary"]
    elif mutation == "missing_configuration":
        doc["observed_configuration"] = None
    elif mutation == "no_probe":
        doc["configuration_probe_receipt_id"] = None
    elif mutation == "wrong_source":
        doc["source_digest"] = "f" * 64
    elif mutation == "missing_subject":
        doc["subject_id"] = "absent"
    elif mutation == "not_input":
        doc["records"][0]["distribution_artifact_id"] = "binary"
    elif mutation == "not_proof_output":
        doc["records"][0]["proof_artifact_id"] = "binary"
    elif mutation == "different_probe_tool":
        next(
            row
            for row in data["execution_facts"]
            if row["receipt"]["id"] == "configuration-probe"
        )["executable_fact"]["sha256"] = ("f" * 64)
    else:
        doc["proof_receipt_ids"].remove("compile")
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_unavailable_usage_preserves_required_artifacts_without_faking_execution():
    doc = usage_bundle()["consumer_usage"]
    doc.update(
        status="unverified",
        receipt_id=None,
        records=[],
        proof_receipt_ids=[],
        observed_configuration=None,
        configuration_probe_receipt_id=None,
        target_probe_receipt_id=None,
        compiler_version=None,
        linker_version=None,
    )
    validate("consumer_usage", doc)
