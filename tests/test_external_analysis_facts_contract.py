"""External diagnostics keep namespaces, occurrence identity and import origin."""

from copy import deepcopy
import hashlib

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError
from test_contracts_v2 import manifest_document


def external_document():
    manifest = manifest_document()
    return {
        "version": "2.0.0",
        "id": "gcc-import",
        "source_digest": manifest["source"]["digest"],
        "context_id": manifest["contexts"][0]["id"],
        "origin": "import",
        "producer": {"name": "GNU-G++", "version": "14.2.0"},
        "adapter": {"name": "gcc-json", "version": "1.0.0"},
        "producer_namespace": "gcc",
        "report_artifact_id": "gcc-report",
        "receipt_id": None,
        "producer_version_receipt_id": None,
        "proof_receipt_ids": [],
        "scope_files": [manifest["source"]["files"][0]["path"]],
        "scope_completeness": "unverified",
        "usability": "usable",
        "observations": [
            {
                "id": "gcc-1",
                "original_rule_id": "-Wunused-variable",
                "namespaced_rule_id": "gcc:-Wunused-variable",
                "rule_version": "14.2.0",
                "file": manifest["source"]["files"][0]["path"],
                "line": 1,
                "column": None,
                "severity": "warning",
                "message": "Synthetic GCC warning.",
                "fingerprint": "a" * 64,
            }
        ],
        "limitations": ["Synthetic imported diagnostics; no completed-scan assertion."],
    }


def test_external_diagnostics_preserve_import_namespace_and_multiplicity():
    document = external_document()
    repeated = deepcopy(document["observations"][0])
    repeated["id"] = "gcc-2"
    document["observations"].append(repeated)
    validate("external_analysis_facts", document)


def test_empty_external_report_stays_unverified_scope():
    document = external_document()
    document["observations"] = []
    validate("external_analysis_facts", document)
    document["scope_completeness"] = "explicit"
    with pytest.raises(ContractError):
        validate("external_analysis_facts", document)


def test_unsafe_original_rule_uses_full_hash_without_losing_original():
    document = external_document()
    row = document["observations"][0]
    row["original_rule_id"] = "-Wodd option/☃"
    row["namespaced_rule_id"] = (
        "gcc:option-" + hashlib.sha256(row["original_rule_id"].encode()).hexdigest()
    )
    validate("external_analysis_facts", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "namespace",
        "rule",
        "version",
        "duplicate",
        "unsafe",
        "column",
        "origin",
        "producer",
    ],
)
def test_external_diagnostics_reject_relabeling_or_invalid_locations(mutation):
    document = external_document()
    row = document["observations"][0]
    if mutation == "namespace":
        document["producer_namespace"] = "cppulse"
    elif mutation == "rule":
        row["namespaced_rule_id"] = "CPP-MEM-001"
    elif mutation == "version":
        row["rule_version"] = "future"
    elif mutation == "duplicate":
        document["observations"].append(deepcopy(row))
    elif mutation == "unsafe":
        row["file"] = "../main.cpp"
    elif mutation == "column":
        row["column"] = 0
    elif mutation == "origin":
        document["receipt_id"] = "invented"
    else:
        document["producer"]["version"] = "99.0.0"
    with pytest.raises(ContractError):
        validate("external_analysis_facts", document)


def test_external_bundle_binds_report_and_selected_file_scope():
    manifest = manifest_document()
    manifest["artifacts"].append(
        {
            "id": "gcc-report",
            "path": "reports/gcc.json",
            "sha256": "b" * 64,
            "size_bytes": 12,
            "media_type": "application/json",
        }
    )
    document = external_document()
    validate_bundle({"run_manifest": manifest, "external_analysis_facts": document})
    document["observations"][0]["file"] = "other.cpp"
    with pytest.raises(ContractError):
        validate_bundle({"run_manifest": manifest, "external_analysis_facts": document})
