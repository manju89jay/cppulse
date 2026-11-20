"""Contract and semantic regressions for the additive S2 foundation."""

from __future__ import annotations

from copy import deepcopy
from importlib import resources
import json
import hashlib
from typing import Any

import jsonschema
import pytest

from cppulse.contracts import load_schema, validate, validate_bundle
from cppulse.errors import ContractError, UnsupportedVersion

SHA = "a" * 64
TIME = "2026-11-13T10:00:00Z"


def digest(value: Any) -> str:
    """Build deterministic fixture digests without relying on identity producers."""
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def source_document() -> dict[str, Any]:
    """Return a synthetic source-inventory contract fixture."""
    projection = {
        "kind": "application",
        "files": [{"path": "src/main.cpp", "sha256": SHA, "size_bytes": 10}],
        "inventory_complete": True,
    }
    return {
        "version": "2.0.0",
        "digest": digest(projection),
        **projection,
        "limitations": [],
    }


def context_document() -> dict[str, Any]:
    """Return a synthetic observed compile context."""
    projection = {
        "compiler": {"name": "gcc", "version": "14"},
        "argv": ["g++", "-std=c++17", "-c", "src/main.cpp"],
        "working_directory": "/repo",
        "language_standard": "c++17",
        "target": "x86_64-linux-gnu",
        "provenance": "observed",
        "dependencies": [],
    }
    return {
        "version": "2.0.0",
        "id": "gcc17",
        "digest": digest(projection),
        **projection,
        "limitations": [],
    }


def artifact_document() -> dict[str, Any]:
    """Return a persisted output identity."""
    return {
        "id": "findings",
        "path": "artifacts/findings.json",
        "sha256": SHA,
        "size_bytes": 10,
        "media_type": "application/json",
    }


def manifest_document() -> dict[str, Any]:
    """Return a synthetic completed collection, not a passed policy claim."""
    return {
        "version": "2.0.0",
        "run_id": "run-1",
        "status": "completed",
        "source": source_document(),
        "contexts": [context_document()],
        "stages": [
            {"id": "analysis", "status": "passed", "depends_on": [], "reason": ""}
        ],
        "artifacts": [artifact_document()],
        "started_at": TIME,
        "finished_at": TIME,
        "config_digest": SHA,
        "versions": {"cppulse": "0.2.0.dev0"},
        "limitations": [],
    }


def recipe_document() -> dict[str, Any]:
    """Return an explicitly bounded build recipe."""
    return {
        "version": "2.0.0",
        "id": "build",
        "jobs": 1,
        "contexts": ["gcc17"],
        "steps": [
            {
                "id": "compile",
                "context_id": "gcc17",
                "argv": ["cmake", "--build", "build"],
                "cwd": ".",
                "depends_on": [],
                "inputs": ["src/main.cpp"],
                "outputs": ["build/app"],
                "timeout_seconds": 30,
            }
        ],
    }


def receipt_document() -> dict[str, Any]:
    """Return a command receipt with independently structured test counts."""
    return {
        "version": "2.0.0",
        "id": "tests",
        "source_digest": source_document()["digest"],
        "context_id": "gcc17",
        "producer": {"name": "ctest", "version": "3.31"},
        "argv": ["ctest"],
        "cwd": "/repo/build",
        "status": "passed",
        "reason": "",
        "exit_code": 0,
        "signal": None,
        "started_at": TIME,
        "finished_at": TIME,
        "artifact_ids": ["findings"],
        "log_artifact_ids": [],
        "depends_on": [],
        "tests": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0},
    }


def evidence_document() -> dict[str, Any]:
    """Return one typed result linked to retained artifacts and a receipt."""
    return {
        "version": "2.0.0",
        "source_digest": source_document()["digest"],
        "records": [
            {
                "id": "unit-tests",
                "context_id": "gcc17",
                "producer": {"name": "ctest", "version": "3.31"},
                "origin": "execution",
                "kind": "tests",
                "status": "passed",
                "usability": "usable",
                "artifact_ids": ["findings"],
                "receipt_id": "tests",
                "scope": {"files": ["src/main.cpp"], "tests": ["sample"]},
                "limitations": [],
            }
        ],
    }


def policy_document() -> dict[str, Any]:
    """Return a general policy using a recognized evaluator, not executable code."""
    return {
        "version": "2.0.0",
        "id": "local",
        "policy_version": "1.0.0",
        "standards": [],
        "scope": {"include": ["src/**"], "exclude": []},
        "contexts": ["gcc17"],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": "unit-tests",
                "title": "Tests pass",
                "kind": "test_outcomes",
                "weight": 1,
                "required": True,
                "parameters": {"evidence_ids": ["unit-tests"]},
                "depends_on": [],
            }
        ],
    }


def assessment_document() -> dict[str, Any]:
    """Return exact proposed score arithmetic with no rounded gate inputs."""
    statuses = [("good", "passed", 4), ("bad", "failed", 2), ("missing", "unknown", 4)]
    return {
        "version": "2.0.0",
        "run_id": "run-1",
        "source_digest": source_document()["digest"],
        "policy": {"id": "local", "policy_version": "1.0.0", "sha256": SHA},
        "gate": "failed",
        "generated_at": TIME,
        "weights": {"passed": 4, "failed": 2, "unknown": 4},
        "scores": {
            "readiness": 40,
            "evidence_completeness": 60,
            "observed_satisfaction": 100 * 4 / 6,
            "maximum_possible_readiness": 80,
        },
        "controls": [
            {
                "id": key,
                "title": key,
                "status": status,
                "reason": "synthetic fixture",
                "weight": weight,
                "required": True,
                "evidence_ids": [],
                "references": [],
            }
            for key, status, weight in statuses
        ],
        "deviations": [],
        "limitations": [],
    }


def risk_document() -> dict[str, Any]:
    """Return a v2 heuristic rank with no defect-probability claim."""
    return {
        "version": "2.0.0",
        "metadata": {
            "generated_at": TIME,
            "method": "heuristic",
            "score_kind": "heuristic_rank",
            "experimental": True,
            "feature_count": 1,
            "active_features": ["memory_findings"],
            "training_samples": 1,
            "label_source": "feature_derived_heuristic",
            "evaluation_status": "not_evaluated",
            "f1_score": None,
            "limitations": [],
        },
        "health_score": {
            "overall": 100,
            "by_category": {},
            "availability": "scored",
            "scorer_version": "weighted-eligible-file-v2",
            "denominator": 1,
            "limitations": [],
        },
        "file_risks": [
            {
                "file": "src/main.cpp",
                "score": 0.2,
                "risk_level": "low",
                "top_factors": [],
                "explanation_kind": "heuristic_weights",
            }
        ],
        "hotspots": [],
    }


@pytest.mark.parametrize(
    "kind,factory",
    [
        ("source", source_document),
        ("context", context_document),
        ("artifact", artifact_document),
        ("run_manifest", manifest_document),
        ("recipe", recipe_document),
        ("execution_receipt", receipt_document),
        ("evidence", evidence_document),
        ("policy", policy_document),
        ("assessment", assessment_document),
        ("risk_scores", risk_document),
    ],
)
def test_valid_contracts(kind: str, factory: Any) -> None:
    validate(kind, factory())


def test_all_packaged_schemas_are_draft_seven() -> None:
    directory = resources.files("cppulse.contracts").joinpath("schemas", "v2")
    for path in directory.iterdir():
        schema = json.loads(path.read_text())
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        jsonschema.Draft7Validator.check_schema(schema)


def test_loaded_schema_is_not_mutable_global_state() -> None:
    first = load_schema("recipe")
    first["properties"].clear()
    assert load_schema("recipe")["properties"]


@pytest.mark.parametrize(
    "kind,version",
    [
        ("recipe", "3.0.0"),
        ("recipe", "2.1.0"),
        ("unknown", "2.0.0"),
        ("findings", "1.0.0"),
    ],
)
def test_unsupported_kind_or_version_is_actionable(kind: str, version: str) -> None:
    with pytest.raises(UnsupportedVersion) as caught:
        load_schema(kind, version)
    assert caught.value.code == "UNSUPPORTED_VERSION"


@pytest.mark.parametrize(
    "path",
    [
        "/etc/passwd",
        "../outside.cpp",
        "src/../outside.cpp",
        "C:\\repo\\source.cpp",
        "./src/main.cpp",
        "src//main.cpp",
    ],
)
def test_source_paths_cannot_escape_or_alias(path: str) -> None:
    document = source_document()
    document["files"][0]["path"] = path
    with pytest.raises(ContractError) as caught:
        validate("source", document)
    assert caught.value.code == "UNSAFE_PATH"


def test_source_duplicate_and_casefold_collisions() -> None:
    document = source_document()
    document["files"].append(deepcopy(document["files"][0]))
    with pytest.raises(ContractError, match="Duplicate"):
        validate("source", document)
    document["files"][1]["path"] = "src/MAIN.cpp"
    document["digest"] = digest(
        {key: document[key] for key in ["kind", "files", "inventory_complete"]}
        | {"files": sorted(document["files"], key=lambda entry: entry["path"])}
    )
    validate("source", document)
    document["path_case_sensitive"] = False
    with pytest.raises(ContractError, match="Case-folded"):
        validate("source", document)


def test_dependency_availability_does_not_invent_digest() -> None:
    document = context_document()
    document["dependencies"] = [
        {"id": "sysroot", "availability": "available", "sha256": None}
    ]
    with pytest.raises(ContractError, match="availability"):
        validate("context", document)


@pytest.mark.parametrize(
    "mutation",
    ["duplicate", "missing", "cycle", "outside", "zero_timeout", "undeclared_context"],
)
def test_recipe_graph_and_execution_contract(mutation: str) -> None:
    document = recipe_document()
    if mutation == "duplicate":
        document["steps"].append(deepcopy(document["steps"][0]))
    if mutation == "missing":
        document["steps"][0]["depends_on"] = ["absent"]
    if mutation == "cycle":
        document["steps"][0]["depends_on"] = ["compile"]
    if mutation == "outside":
        document["steps"][0]["outputs"] = ["../report"]
    if mutation == "zero_timeout":
        document["steps"][0]["timeout_seconds"] = 0
    if mutation == "undeclared_context":
        document["steps"][0]["context_id"] = "unknown"
    with pytest.raises(ContractError):
        validate("recipe", document)


@pytest.mark.parametrize("field,value", [("exit_code", 1), ("signal", 9)])
def test_passed_execution_cannot_have_failed_process(field: str, value: int) -> None:
    document = receipt_document()
    document[field] = value
    with pytest.raises(ContractError, match="Passed execution"):
        validate("execution_receipt", document)


def test_receipt_test_counts_are_independent_invariant() -> None:
    document = receipt_document()
    document["tests"]["total"] = 2
    with pytest.raises(ContractError, match="Test total"):
        validate("execution_receipt", document)


def test_bad_or_reversed_timestamps_fail() -> None:
    document = manifest_document()
    document["finished_at"] = "2026-11-13T09:00:00Z"
    with pytest.raises(ContractError, match="precedes"):
        validate("run_manifest", document)
    document["finished_at"] = "not-a-date"
    with pytest.raises(ContractError):
        validate("run_manifest", document)


@pytest.mark.parametrize("mutation", ["weight", "kind", "parameters", "cycle"])
def test_policy_semantic_errors(mutation: str) -> None:
    document = policy_document()
    control = document["controls"][0]
    if mutation == "weight":
        control["weight"] = 0
    if mutation == "kind":
        control["kind"] = "execute_shell"
    if mutation == "parameters":
        control["parameters"] = {"max_findings": 3}
    if mutation == "cycle":
        control["depends_on"] = [control["id"]]
    with pytest.raises(ContractError):
        validate("policy", document)


def test_required_unknown_or_failed_cannot_hide_behind_average() -> None:
    document = assessment_document()
    document["gate"] = "passed"
    with pytest.raises(ContractError, match="masks"):
        validate("assessment", document)


def test_weights_and_unrounded_scores_are_verified() -> None:
    document = assessment_document()
    document["weights"]["unknown"] = 3
    with pytest.raises(ContractError, match="weights"):
        validate("assessment", document)
    document = assessment_document()
    document["scores"]["observed_satisfaction"] = 66.67
    with pytest.raises(ContractError, match="unrounded"):
        validate("assessment", document)


def test_no_controls_require_null_scores_and_incomplete_gate() -> None:
    document = assessment_document()
    document["controls"] = []
    document["weights"] = {"passed": 0, "failed": 0, "unknown": 0}
    document["scores"] = {key: None for key in document["scores"]}
    document["gate"] = "insufficient_evidence"
    validate("assessment", document)
    document["gate"] = "passed"
    with pytest.raises(ContractError, match="No applicable"):
        validate("assessment", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "partial_numeric",
        "wrong_method",
        "fake_metric",
        "feature_count",
        "duplicate_file",
        "orphan_hotspot",
    ],
)
def test_risk_v2_does_not_invent_availability_or_method(mutation: str) -> None:
    document = risk_document()
    if mutation == "partial_numeric":
        document["health_score"]["availability"] = "partial"
    if mutation == "wrong_method":
        document["metadata"]["score_kind"] = "model_rank"
    if mutation == "fake_metric":
        document["metadata"]["f1_score"] = 0
    if mutation == "feature_count":
        document["metadata"]["feature_count"] = 10
    if mutation == "duplicate_file":
        document["file_risks"].append(deepcopy(document["file_risks"][0]))
    if mutation == "orphan_hotspot":
        document["hotspots"] = [
            {"file": "missing.cpp", "score": 1, "method": "proxy", "finding_count": 1}
        ]
    with pytest.raises(ContractError):
        validate("risk_scores", document)


def test_closed_bundle_references_validate() -> None:
    validate_bundle(
        {
            "run_manifest": manifest_document(),
            "execution_receipt": receipt_document(),
            "evidence": evidence_document(),
        }
    )


@pytest.mark.parametrize(
    "mutation", ["context", "source", "artifact", "receipt", "duplicate_receipt"]
)
def test_bundle_does_not_accept_unresolved_or_mismatched_references(
    mutation: str,
) -> None:
    receipt = receipt_document()
    documents = {
        "run_manifest": manifest_document(),
        "execution_receipt": receipt,
        "evidence": evidence_document(),
    }
    if mutation == "context":
        receipt["context_id"] = "clang20"
    if mutation == "source":
        receipt["source_digest"] = "b" * 64
    if mutation == "artifact":
        receipt["artifact_ids"] = ["absent"]
    if mutation == "receipt":
        documents.pop("execution_receipt")
    if mutation == "duplicate_receipt":
        documents["execution_receipt"] = [receipt, deepcopy(receipt)]
    with pytest.raises(ContractError):
        validate_bundle(documents)


def test_no_additional_executable_payload_is_accepted() -> None:
    document = policy_document()
    document["shell_command"] = "run arbitrary code"
    with pytest.raises(ContractError) as caught:
        validate("policy", document)
    assert caught.value.as_dict()["code"] == "INVALID_CONTRACT"


def test_remaining_contract_families_have_concrete_valid_documents() -> None:
    """Metric/observation/baseline/registry contracts represent facts, not engines."""
    source_digest = source_document()["digest"]
    documents = {
        "analysis_metrics": {
            "version": "2.0.0",
            "source_digest": source_digest,
            "items": [
                {
                    "id": "complexity-main",
                    "file": "src/main.cpp",
                    "symbol": "main",
                    "context_id": "gcc17",
                    "metric": "cyclomatic_complexity",
                    "metric_version": "1",
                    "value": 1,
                    "units": "decisions_plus_one",
                    "availability": "available",
                    "limitations": [],
                }
            ],
        },
        "observations": {
            "version": "2.0.0",
            "source_digest": source_digest,
            "items": [
                {
                    "id": "finding-1",
                    "producer": {"name": "cppulse-analyzer", "version": "0.2"},
                    "rule_id": "cppulse:CPP-MOD-001",
                    "rule_version": "1",
                    "file": "src/main.cpp",
                    "context_id": "gcc17",
                    "line": 1,
                    "severity": "warning",
                    "message": "C-style cast",
                    "fingerprint": SHA,
                    "fingerprint_version": "1",
                    "evidence_ids": [],
                }
            ],
        },
        "baseline": {
            "version": "2.0.0",
            "id": "baseline-1",
            "run_id": "run-1",
            "source_digest": source_digest,
            "context_ids": ["gcc17"],
            "scope_digest": SHA,
            "fingerprint_version": "1",
            "scorer_version": "eligible-file-v2",
            "policy_digest": None,
            "findings": [{"fingerprint": SHA, "count": 2}],
            "reason": "Existing debt",
            "created_at": TIME,
        },
        "rule_registry": {
            "version": "2.0.0",
            "rules": [
                {
                    "id": "cppulse:CPP-MOD-001",
                    "version": "1",
                    "maturity": "experimental",
                    "category": "modernization",
                    "required_capabilities": ["ast"],
                    "supported_inputs": ["c++17"],
                    "configuration_schema": {"type": "object"},
                    "documentation": "rules/c-style-cast.md",
                }
            ],
        },
    }
    for kind, document in documents.items():
        validate(kind, document)
    validate_bundle({"run_manifest": manifest_document(), **documents})
    documents["analysis_metrics"]["items"][0]["availability"] = "unavailable"
    with pytest.raises(ContractError, match="availability"):
        validate("analysis_metrics", documents["analysis_metrics"])


def test_source_and_context_digest_changes_are_detected() -> None:
    source = source_document()
    source["files"][0]["sha256"] = "b" * 64
    with pytest.raises(ContractError) as caught:
        validate("source", source)
    assert caught.value.code == "IDENTITY_MISMATCH"
    context = context_document()
    context["argv"].append("-DMODE=2")
    with pytest.raises(ContractError) as caught:
        validate("context", context)
    assert caught.value.code == "IDENTITY_MISMATCH"


@pytest.mark.parametrize("status", ["error", "timed_out", "cancelled", "not_attempted"])
def test_operationally_partial_stage_cannot_be_completed(status: str) -> None:
    document = manifest_document()
    document["stages"][0]["status"] = status
    with pytest.raises(ContractError, match="operationally"):
        validate("run_manifest", document)
    document["status"] = "partial"
    validate("run_manifest", document)


@pytest.mark.parametrize("name", ["run_manifest.json", "latest.json", "../latest.json"])
def test_artifact_paths_cannot_overwrite_publication_metadata(name: str) -> None:
    artifact = artifact_document()
    artifact["path"] = name
    with pytest.raises(ContractError):
        validate("artifact", artifact)


def test_unknown_properties_fail_even_inside_nested_contracts() -> None:
    document = manifest_document()
    document["contexts"][0]["execute"] = "hidden command"
    with pytest.raises(ContractError):
        validate("run_manifest", document)


def test_nonfinite_numbers_are_not_json_contract_values() -> None:
    document = risk_document()
    document["file_risks"][0]["score"] = float("nan")
    with pytest.raises(ContractError, match="finite JSON"):
        validate("risk_scores", document)


def test_stale_evidence_remains_a_historical_fact_not_a_fresh_pass() -> None:
    document = evidence_document()
    document["records"][0]["usability"] = "stale"
    validate("evidence", document)
    assert document["records"][0]["status"] == "passed"
    document["records"][0]["measurement"] = {
        "kind": "branch",
        "covered": 11,
        "total": 10,
    }
    with pytest.raises(ContractError, match="Covered count"):
        validate("evidence", document)


def test_expired_deviation_cannot_be_active() -> None:
    document = assessment_document()
    document["deviations"] = [
        {
            "id": "deviation-1",
            "control_id": "bad",
            "source_digest": document["source_digest"],
            "context_ids": ["gcc17"],
            "reason": "temporary fixture",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-11-12T10:00:00Z",
            "expires_at": TIME,
            "active": True,
        }
    ]
    with pytest.raises(ContractError, match="expired"):
        validate("assessment", document)


def test_bundle_rejects_valid_but_different_standalone_subject() -> None:
    source = source_document()
    source["kind"] = "library"
    source["digest"] = digest(
        {key: source[key] for key in ["kind", "files", "inventory_complete"]}
    )
    with pytest.raises(ContractError, match="Source inventory"):
        validate_bundle({"run_manifest": manifest_document(), "source": source})
    artifact = artifact_document()
    artifact["sha256"] = "b" * 64
    with pytest.raises(ContractError, match="Artifact differs"):
        validate_bundle({"run_manifest": manifest_document(), "artifact": artifact})


def test_structured_diagnostics_include_json_pointer() -> None:
    document = recipe_document()
    document["jobs"] = 0
    with pytest.raises(ContractError) as caught:
        validate("recipe", document)
    assert caught.value.as_dict()["path"] == "/jobs"


def test_bundle_observations_must_belong_to_selected_source() -> None:
    observations = {
        "version": "2.0.0",
        "source_digest": source_document()["digest"],
        "items": [
            {
                "id": "f1",
                "producer": {"name": "cppulse", "version": "0.2"},
                "rule_id": "cppulse:CPP-MOD-001",
                "rule_version": "1",
                "file": "unselected.cpp",
                "context_id": "gcc17",
                "line": 1,
                "severity": "warning",
                "message": "finding",
                "fingerprint": SHA,
                "fingerprint_version": "1",
                "evidence_ids": [],
            }
        ],
    }
    with pytest.raises(ContractError, match="outside selected"):
        validate_bundle(
            {"run_manifest": manifest_document(), "observations": observations}
        )


def test_inactive_mismatched_deviation_is_retained_without_effect() -> None:
    document = assessment_document()
    document["deviations"] = [
        {
            "id": "old",
            "control_id": "bad",
            "source_digest": "b" * 64,
            "context_ids": ["old-context"],
            "reason": "old source",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-11-12T10:00:00Z",
            "expires_at": TIME,
            "active": False,
        }
    ]
    validate("assessment", document)
    document["deviations"][0]["active"] = True
    with pytest.raises(ContractError, match="source"):
        validate("assessment", document)


def test_input_verification_is_explicit_and_optional() -> None:
    document = manifest_document()
    validate("run_manifest", document)
    for status in ["verified", "unverified"]:
        document["input_verification"] = status
        validate("run_manifest", document)
    document["input_verification"] = "probably"
    with pytest.raises(ContractError):
        validate("run_manifest", document)


@pytest.mark.parametrize(
    "outcome", ["failed_process", "failed_tests", "zero_tests", "all_skipped"]
)
def test_passed_usable_evidence_cannot_contradict_receipt(outcome: str) -> None:
    receipt = receipt_document()
    if outcome == "failed_process":
        receipt.update(status="failed", exit_code=1)
    elif outcome == "failed_tests":
        receipt["tests"].update(passed=0, failed=1)
    elif outcome == "zero_tests":
        receipt["tests"].update(total=0, passed=0)
    else:
        receipt["tests"].update(passed=0, skipped=1)
    with pytest.raises(ContractError):
        validate_bundle(
            {
                "run_manifest": manifest_document(),
                "execution_receipt": receipt,
                "evidence": evidence_document(),
            }
        )


def test_evidence_scope_must_be_selected_source() -> None:
    evidence = evidence_document()
    evidence["records"][0]["scope"]["files"] = ["not-in-source.cpp"]
    with pytest.raises(ContractError, match="source"):
        validate_bundle(
            {
                "run_manifest": manifest_document(),
                "execution_receipt": receipt_document(),
                "evidence": evidence,
            }
        )


def test_receipt_dependencies_cannot_cycle() -> None:
    receipt = receipt_document()
    receipt["depends_on"] = [receipt["id"]]
    with pytest.raises(ContractError, match="cycle"):
        validate_bundle(
            {"run_manifest": manifest_document(), "execution_receipt": receipt}
        )


def passed_policy_assessment() -> tuple[dict[str, Any], dict[str, Any]]:
    """A report tied to exactly one required policy control."""
    policy = policy_document()
    assessment = assessment_document()
    assessment["policy"]["sha256"] = digest(policy)
    assessment["gate"] = "passed"
    assessment["controls"] = [
        {
            "id": "unit-tests",
            "title": "Tests pass",
            "status": "passed",
            "reason": "Observed tests",
            "weight": 1,
            "required": True,
            "evidence_ids": ["unit-tests"],
            "references": [],
        }
    ]
    assessment["weights"] = {"passed": 1, "failed": 0, "unknown": 0}
    assessment["scores"] = {key: 100 for key in assessment["scores"]}
    return policy, assessment


@pytest.mark.parametrize(
    "mutation",
    [
        "digest",
        "omitted_control",
        "required",
        "title",
        "missing_evidence",
        "false_not_applicable",
    ],
)
def test_assessment_must_be_bound_to_actual_policy(mutation: str) -> None:
    policy, assessment = passed_policy_assessment()
    if mutation == "digest":
        assessment["policy"]["sha256"] = "b" * 64
    if mutation == "omitted_control":
        assessment["controls"][0]["id"] = "unrelated"
    if mutation == "required":
        assessment["controls"][0]["required"] = False
    if mutation == "title":
        assessment["controls"][0]["title"] = "Unrelated title"
    if mutation == "missing_evidence":
        assessment["controls"][0]["evidence_ids"] = []
    if mutation == "false_not_applicable":
        assessment["controls"][0]["status"] = "not_applicable"
        assessment["gate"] = "insufficient_evidence"
        assessment["weights"] = {"passed": 0, "failed": 0, "unknown": 0}
        assessment["scores"] = {key: None for key in assessment["scores"]}
    with pytest.raises(ContractError):
        validate_bundle(
            {
                "run_manifest": manifest_document(),
                "execution_receipt": receipt_document(),
                "evidence": evidence_document(),
                "policy": policy,
                "assessment": assessment,
            }
        )


def test_rfc3339_lowercase_utc_is_consistent() -> None:
    document = manifest_document()
    document["started_at"] = document["started_at"].replace("Z", "z")
    document["finished_at"] = document["finished_at"].replace("Z", "z")
    validate("run_manifest", document)


def test_active_deviation_cannot_be_approved_in_future() -> None:
    document = assessment_document()
    document["deviations"] = [
        {
            "id": "future",
            "control_id": "bad",
            "source_digest": document["source_digest"],
            "context_ids": ["gcc17"],
            "reason": "future",
            "owner": "owner",
            "reviewer": "reviewer",
            "approved_at": "2026-11-14T10:00:00Z",
            "expires_at": "2026-11-15T10:00:00Z",
            "active": True,
        }
    ]
    with pytest.raises(ContractError, match="future"):
        validate("assessment", document)


@pytest.mark.parametrize("process_failed", [False, True])
def test_observed_failed_test_evidence_remains_usable(process_failed: bool) -> None:
    receipt = receipt_document()
    receipt["tests"].update(passed=0, failed=1)
    if process_failed:
        receipt.update(status="failed", exit_code=1)
    evidence = evidence_document()
    evidence["records"][0]["status"] = "failed"
    validate_bundle(
        {
            "run_manifest": manifest_document(),
            "execution_receipt": receipt,
            "evidence": evidence,
        }
    )


def test_actual_policy_assessment_has_positive_consistent_case() -> None:
    policy, assessment = passed_policy_assessment()
    validate_bundle(
        {
            "run_manifest": manifest_document(),
            "execution_receipt": receipt_document(),
            "evidence": evidence_document(),
            "policy": policy,
            "assessment": assessment,
        }
    )


def test_passed_evidence_control_cannot_reference_failed_fact() -> None:
    policy, assessment = passed_policy_assessment()
    receipt = receipt_document()
    receipt.update(status="failed", exit_code=1)
    receipt["tests"].update(passed=0, failed=1)
    evidence = evidence_document()
    evidence["records"][0]["status"] = "failed"
    with pytest.raises(ContractError, match="contradicts"):
        validate_bundle(
            {
                "run_manifest": manifest_document(),
                "execution_receipt": receipt,
                "evidence": evidence,
                "policy": policy,
                "assessment": assessment,
            }
        )


def test_identical_primary_source_artifact_matches_manifest_subject() -> None:
    source = source_document()
    validate_bundle({"run_manifest": manifest_document(), "source": source})
