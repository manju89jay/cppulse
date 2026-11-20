"""Declared library subjects/matrices preserve partial selected applicability."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError
from test_contracts_v2 import manifest_document


def configuration():
    return {
        "compiler": {"name": "gcc", "version": "14.2.0", "sha256": "e" * 64},
        "os": "linux",
        "target": "x86_64-linux-gnu",
        "abi": "observed-macros-v1:test",
        "language_standard": "c++17",
        "macros": {},
        "exceptions": True,
        "rtti": True,
        "linking": "static",
        "dependencies": [],
        "sanitizers": [],
    }


def subject_document():
    manifest = manifest_document()
    source = manifest["source"]["files"][0]
    return {
        "version": "2.0.0",
        "id": "library-package",
        "source_digest": manifest["source"]["digest"],
        "kind": "compiled",
        "source_relation": "selected_sources",
        "source_files": [deepcopy(source)],
        "distribution_files": [
            {
                "path": "lib/libdemo.a",
                "artifact_id": "package",
                "sha256": "b" * 64,
                "size_bytes": 10,
            }
        ],
        "limitations": ["Synthetic finite subject; no whole-library qualification."],
    }


def matrix_document():
    return {
        "version": "2.0.0",
        "id": "consumers",
        "source_digest": manifest_document()["source"]["digest"],
        "subject_id": "library-package",
        "cases": [
            {
                "id": "linux-cpp17",
                "required": True,
                "context_id": "expected-job",
                "configuration": configuration(),
                "tests": ["consumer-test"],
                "instantiations": ["selected<int>"],
                "self_containment_headers": [],
                "usage_ids": [],
            }
        ],
        "limitations": ["Declared expected case, not observed execution."],
    }


def consumer_bundle():
    manifest = manifest_document()
    manifest["artifacts"].append(
        {
            "id": "package",
            "path": "inputs/libdemo.a",
            "sha256": "b" * 64,
            "size_bytes": 10,
            "media_type": "application/octet-stream",
        }
    )
    return {
        "run_manifest": manifest,
        "distribution_subject": subject_document(),
        "consumer_matrix": matrix_document(),
    }


def test_declared_missing_context_remains_a_valid_unobserved_requirement():
    validate_bundle(consumer_bundle())


def test_distribution_only_subject_does_not_invent_upstream_source_identity():
    document = subject_document()
    document.update(source_relation="distribution_only", source_files=[])
    validate("distribution_subject", document)
    document["limitations"] = []
    with pytest.raises(ContractError):
        validate("distribution_subject", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_source",
        "duplicate_distribution",
        "unsafe_source",
        "unsafe_distribution",
        "nul_distribution",
        "empty_selected",
        "distribution_only_claim",
    ],
)
def test_subject_rejects_ambiguous_or_unbounded_identities(mutation):
    document = subject_document()
    if mutation == "duplicate_source":
        document["source_files"].append(deepcopy(document["source_files"][0]))
    elif mutation == "duplicate_distribution":
        document["distribution_files"].append(
            deepcopy(document["distribution_files"][0])
        )
    elif mutation == "unsafe_source":
        document["source_files"][0]["path"] = "../main.cpp"
    elif mutation == "unsafe_distribution":
        document["distribution_files"][0]["path"] = "/libdemo.a"
    elif mutation == "nul_distribution":
        document["distribution_files"][0]["path"] = "lib/invalid\x00.a"
    elif mutation == "empty_selected":
        document["source_files"] = []
    else:
        document["source_relation"] = "distribution_only"
    with pytest.raises(ContractError):
        validate("distribution_subject", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "source_sha",
        "distribution_sha",
        "missing_artifact",
        "missing_subject",
        "duplicate_subject",
        "duplicate_case",
        "unsafe_header",
    ],
)
def test_subject_matrix_bundle_rejects_actual_identity_errors(mutation):
    data = consumer_bundle()
    if mutation == "source_sha":
        data["distribution_subject"]["source_files"][0]["sha256"] = "f" * 64
    elif mutation == "distribution_sha":
        data["distribution_subject"]["distribution_files"][0]["sha256"] = "f" * 64
    elif mutation == "missing_artifact":
        data["distribution_subject"]["distribution_files"][0]["artifact_id"] = "absent"
    elif mutation == "missing_subject":
        data["consumer_matrix"]["subject_id"] = "absent"
    elif mutation == "duplicate_subject":
        data["distribution_subject"] = [
            data["distribution_subject"],
            deepcopy(data["distribution_subject"]),
        ]
    elif mutation == "duplicate_case":
        data["consumer_matrix"]["cases"].append(
            deepcopy(data["consumer_matrix"]["cases"][0])
        )
    else:
        data["consumer_matrix"]["cases"][0]["self_containment_headers"] = [
            "../header.hpp"
        ]
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_null_configuration_is_unknown_without_erasing_declared_requirement():
    document = matrix_document()
    document["cases"][0]["configuration"]["compiler"] = None
    document["cases"][0]["configuration"]["exceptions"] = None
    validate("consumer_matrix", document)
