"""Synthetic emitted-instrumentation and exercised-binary contract chains."""

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError
from verification_fixtures import (
    add_ctest_plan,
    artifact,
    coverage_execution_bundle,
    step,
)


def sanitizer_bundle():
    data = coverage_execution_bundle()
    data.pop("coverage_facts")
    source = data["run_manifest"]["source"]["files"][0]["path"]
    step(data, "compiler-version", {}, {})
    for name, aid, input_path, input_id in [
        ("nm-object", "nm-report", "build/main.o", "object"),
        ("elf-object", "object-elf-report", "build/main.o", "object"),
        ("elf-binary", "runtime-report", "build/app", "binary"),
    ]:
        artifact(
            data,
            aid,
            sha={"nm-report": "3", "object-elf-report": "4", "runtime-report": "5"}[aid]
            * 64,
        )
        step(
            data,
            name,
            {input_path: input_id},
            {"proof/" + aid: aid},
            depends=["compile" if input_id == "object" else "link"],
        )
    add_ctest_plan(data)
    context = data["run_manifest"]["contexts"][0]["id"]
    doc = {
        "version": "2.0.0",
        "id": "asan-observed",
        "source_digest": data["run_manifest"]["source"]["digest"],
        "context_id": context,
        "requested_files": [source],
        "origin": "execution",
        "producer": {"name": "gcc", "version": "14.2.0", "sha256": "e" * 64},
        "adapter": {"name": "gcc-sanitizer", "version": "1.0.0"},
        "sanitizer": "asan",
        "compiler_version_receipt_id": "compiler-version",
        "compile_receipt_ids": ["compile"],
        "link_receipt_id": "link",
        "inspection_receipt_ids": ["nm-object", "elf-object", "elf-binary"],
        "proof_receipt_ids": [row["id"] for row in data["execution_receipt"]],
        "binary_artifact_id": "binary",
        "object_proofs": [
            {
                "artifact_id": "object",
                "compile_receipt_id": "compile",
                "source_files": [source],
                "sanitizer": "asan",
                "method": "elf-relocations-v1",
                "observed_symbols": ["__asan_report_store4"],
                "inspection_artifact_ids": ["nm-report", "object-elf-report"],
                "elf": {"class": "ELF64", "machine": "x86_64", "type": "REL"},
            }
        ],
        "linked_components": [
            {
                "subject_id": "selected-tu",
                "artifact_id": "object",
                "instrumentation": "observed",
            }
        ],
        "runtime_proof": {
            "inspection_artifact_id": "runtime-report",
            "required_soname": "libasan.so.8",
            "observed_needed": ["libasan.so.8", "libc.so.6"],
            "elf": {"class": "ELF64", "machine": "x86_64", "type": "DYN"},
        },
        "test_evidence_id": "test-evidence",
        "exercise_proofs": [
            {
                "artifact_id": "binary",
                "test_receipt_id": "test",
                "test_case_ids": ["case"],
            }
        ],
        "diagnostic_artifact_ids": ["last-log"],
        "diagnostics": [],
        "outcome": "passed",
        "usability": "usable",
        "limitations": [
            "Synthetic proof identities, not actual compilation or runtime validation."
        ],
    }
    data["sanitizer_facts"] = doc
    return data


def test_clean_sanitizer_requires_closed_emission_linkage_and_actual_test_roles():
    validate_bundle(sanitizer_bundle())


def test_uncollected_version_probe_cannot_establish_observed_instrumentation():
    data = sanitizer_bundle()
    next(
        row
        for row in data["execution_facts"]
        if row["receipt"]["id"] == "compiler-version"
    )["material_status"] = "not_collected"
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_real_duration_version_probe_is_not_required_to_precede_itself():
    data = sanitizer_bundle()
    data["run_manifest"]["started_at"] = "2026-11-13T09:59:58Z"
    for receipt in [
        next(
            row for row in data["execution_receipt"] if row["id"] == "compiler-version"
        ),
        next(
            row
            for row in data["execution_facts"]
            if row["receipt"]["id"] == "compiler-version"
        )["receipt"],
    ]:
        receipt.update(
            started_at="2026-11-13T09:59:58Z", finished_at="2026-11-13T09:59:59Z"
        )
    validate_bundle(data)


@pytest.mark.parametrize(
    "mutation",
    [
        "init_only",
        "wrong_sanitizer",
        "missing_objects",
        "missing_runtime",
        "wrong_runtime",
        "unverified_component",
        "missing_scope",
        "diagnostic_clean",
        "no_version",
        "no_binary",
        "empty_exercise",
        "empty_inspections",
    ],
)
def test_clean_sanitizer_rejects_intent_or_incomplete_instrumentation(mutation):
    doc = sanitizer_bundle()["sanitizer_facts"]
    if mutation == "init_only":
        doc["object_proofs"][0]["observed_symbols"] = ["__asan_init"]
    elif mutation == "wrong_sanitizer":
        doc["object_proofs"][0]["sanitizer"] = "tsan"
    elif mutation == "missing_objects":
        doc["object_proofs"] = []
    elif mutation == "missing_runtime":
        doc["runtime_proof"] = None
    elif mutation == "wrong_runtime":
        doc["runtime_proof"]["observed_needed"] = ["libc.so.6"]
    elif mutation == "unverified_component":
        doc["linked_components"][0]["instrumentation"] = "unverified"
    elif mutation == "missing_scope":
        doc["object_proofs"][0]["source_files"] = ["other.cpp"]
    elif mutation == "diagnostic_clean":
        doc["diagnostics"] = [
            {
                "id": "diag",
                "kind": "heap-buffer-overflow",
                "message": "Synthetic failure.",
                "file": None,
                "line": None,
                "artifact_id": "last-log",
                "test_case_id": "case",
            }
        ]
    elif mutation == "no_version":
        doc["compiler_version_receipt_id"] = None
    elif mutation == "no_binary":
        doc["binary_artifact_id"] = None
    elif mutation == "empty_exercise":
        doc["exercise_proofs"] = []
    else:
        doc["object_proofs"][0]["inspection_artifact_ids"] = []
    with pytest.raises(ContractError):
        validate("sanitizer_facts", doc)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_plan",
        "wrong_test_binary",
        "wrong_case",
        "different_compiler",
        "no_source",
        "invalid_link",
        "missing_diagnostic_log",
        "missing_proof_receipt",
    ],
)
def test_sanitizer_bundle_refuses_unbound_actual_proof(mutation):
    data = sanitizer_bundle()
    doc = data["sanitizer_facts"]
    if mutation == "missing_plan":
        data.pop("collection_plan")
    elif mutation == "wrong_test_binary":
        doc["exercise_proofs"][0]["artifact_id"] = "object"
    elif mutation == "wrong_case":
        doc["exercise_proofs"][0]["test_case_ids"] = ["absent"]
    elif mutation == "different_compiler":
        next(
            row
            for row in data["execution_facts"]
            if row["receipt"]["id"] == "compiler-version"
        )["executable_fact"]["sha256"] = ("f" * 64)
    elif mutation == "no_source":
        doc["object_proofs"][0]["source_files"] = ["not-selected.cpp"]
    elif mutation == "invalid_link":
        next(row for row in data["execution_facts"] if row["receipt"]["id"] == "link")[
            "binding"
        ].update(status="invalid", limitations=["Synthetic failed binding."])
    elif mutation == "missing_diagnostic_log":
        doc["diagnostic_artifact_ids"] = ["absent"]
    else:
        doc["proof_receipt_ids"].remove("link")
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_credible_failure_preserves_gap_in_another_component():
    data = sanitizer_bundle()
    doc = data["sanitizer_facts"]
    doc.update(
        outcome="failed",
        diagnostics=[
            {
                "id": "diag",
                "kind": "heap-buffer-overflow",
                "message": "Synthetic observed failure.",
                "file": None,
                "line": None,
                "artifact_id": "last-log",
                "test_case_id": "case",
            }
        ],
    )
    artifact(data, "prebuilt", sha="6" * 64)
    doc["linked_components"].append(
        {
            "subject_id": "prebuilt",
            "artifact_id": "prebuilt",
            "instrumentation": "unverified",
        }
    )
    validate_bundle(data)


def test_imported_runtime_diagnostic_never_implies_locally_observed_clean_execution():
    doc = sanitizer_bundle()["sanitizer_facts"]
    doc.update(
        origin="import",
        outcome="unsupported",
        usability="unsupported",
        compiler_version_receipt_id=None,
        compile_receipt_ids=[],
        link_receipt_id=None,
        inspection_receipt_ids=[],
        proof_receipt_ids=[],
        binary_artifact_id=None,
        object_proofs=[],
        linked_components=[],
        runtime_proof=None,
        test_evidence_id=None,
        exercise_proofs=[],
        diagnostic_artifact_ids=[],
        diagnostics=[],
    )
    validate("sanitizer_facts", doc)
    doc["outcome"] = "passed"
    with pytest.raises(ContractError):
        validate("sanitizer_facts", doc)
