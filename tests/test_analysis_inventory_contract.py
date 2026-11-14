"""Typed source, execution and per-file analysis provenance without running tools."""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError
from cppulse.identities import digest_json
from test_policy_contracts import bundle as policy_bundle
from test_policy_contracts import policy as policy_fixture


def json_bytes(document: dict[str, Any]) -> bytes:
    """Use explicit fixture bytes; raw artifact hashes are not semantic digests."""
    return (json.dumps(document, indent=2) + "\n").encode()


def stat_fact(inode: int = 1) -> dict[str, int]:
    """Return clearly synthetic POSIX stat observations."""
    return {"device": 1, "inode": inode, "mtime_ns": 1, "ctime_ns": 1}


@pytest.fixture
def analysis_bundle() -> dict[str, Any]:
    """Build a closed synthetic native-analysis lineage, not execution evidence."""
    data = policy_bundle.__wrapped__(policy_fixture.__wrapped__())
    data.pop("policy")
    data.pop("assessment")
    manifest = data["run_manifest"]
    data["execution_receipt"] = [data["execution_receipt"]]
    rules = {
        "version": "2.0.0",
        "rules": [
            {
                "id": "CPP-MOD-001",
                "version": "prototype-1",
                "maturity": "experimental",
                "category": "modernization",
                "required_capabilities": ["libclang_ast"],
                "supported_inputs": ["c++_translation_unit"],
                "configuration_schema": {"type": "object"},
                "documentation": "Synthetic registry entry.",
            }
        ],
    }
    import hashlib

    files = [
        ("config.json", b"{}\n"),
        ("registry.json", json_bytes(rules)),
        ("compile_commands.json", b"[]\n"),
    ]
    input_facts = [
        {
            "path": "src/main.cpp",
            "sha256": manifest["source"]["files"][0]["sha256"],
            "size_bytes": 10,
            "stat": stat_fact(),
        }
    ]
    links = [{"path": "src/main.cpp", "artifact_id": "source-cpp"}]
    manifest["artifacts"].append(
        {
            "id": "source-cpp",
            "path": "inputs/main.cpp",
            "sha256": "a" * 64,
            "size_bytes": 10,
            "media_type": "application/octet-stream",
        }
    )
    for index, (path, content) in enumerate(files):
        sha = hashlib.sha256(content).hexdigest()
        record = {"path": path, "sha256": sha, "size_bytes": len(content)}
        manifest["source"]["files"].append(record)
        identifier = ["config", "registry", "database"][index]
        input_facts.append({**record, "stat": stat_fact(index + 2)})
        links.append({"path": path, "artifact_id": identifier})
        manifest["artifacts"].append(
            {
                "id": identifier,
                "path": "inputs/" + identifier,
                "sha256": sha,
                "size_bytes": len(content),
                "media_type": "application/octet-stream",
            }
        )
    manifest["source"]["digest"] = digest_json(
        {
            key: manifest["source"][key]
            for key in ["kind", "files", "inventory_complete"]
        }
        | {"files": sorted(manifest["source"]["files"], key=lambda row: row["path"])}
    )
    # Existing synthetic test facts follow the newly selected subject identity.
    data["execution_receipt"][0]["source_digest"] = manifest["source"]["digest"]
    data["evidence"]["source_digest"] = manifest["source"]["digest"]
    registry_descriptor = deepcopy(
        next(a for a in manifest["artifacts"] if a["id"] == "registry")
    )
    registry_descriptor.update(
        id="typed-registry",
        path="documents/registry.json",
        media_type="application/json",
        contract={"kind": "rule_registry", "version": "2.0.0"},
    )
    manifest["artifacts"].append(registry_descriptor)
    parse_context = {
        "compiler": {"name": "libclang", "version": "19.1.7"},
        "argv": ["-std=c++17", "-x", "c++"],
        "working_directory": "/synthetic",
        "language_standard": "c++17",
        "target": None,
        "provenance": "observed",
        "dependencies": [],
    }
    manifest["contexts"].append(
        {
            "version": "2.0.0",
            "id": "parse-main",
            "digest": digest_json(parse_context),
            **parse_context,
            "limitations": [],
        }
    )
    report_bytes = b'{"synthetic_native_report":true}\n'
    report_fact = {
        "path": "findings.json",
        "sha256": hashlib.sha256(report_bytes).hexdigest(),
        "size_bytes": len(report_bytes),
        "stat": stat_fact(9),
        "freshness": "created",
    }
    manifest["artifacts"].append(
        {
            "id": "native-report",
            "path": "outputs/findings.json",
            "sha256": report_fact["sha256"],
            "size_bytes": report_fact["size_bytes"],
            "media_type": "application/octet-stream",
        }
    )
    for stream in ["stdout", "stderr"]:
        manifest["artifacts"].append(
            {
                "id": "native-" + stream,
                "path": "logs/native-" + stream,
                "sha256": hashlib.sha256(b"").hexdigest(),
                "size_bytes": 0,
                "media_type": "text/plain",
            }
        )
    receipt = deepcopy(data["execution_receipt"][0])
    receipt.update(
        id="analyze",
        argv=[
            "/host/native-analyzer",
            "--config",
            "config.json",
            "--output",
            "findings.json",
        ],
        artifact_ids=[link["artifact_id"] for link in links] + ["native-report"],
        log_artifact_ids=["native-stdout", "native-stderr"],
    )
    receipt.pop("tests")
    data["execution_receipt"].append(receipt)
    facts = {
        "version": "2.0.0",
        "collector_version": "1.0.0",
        "receipt": deepcopy(receipt),
        "input_facts": input_facts,
        "input_after_facts": deepcopy(input_facts),
        "output_facts": [report_fact],
        "preexisting_output_facts": [],
        "executable_fact": {
            "path": "/host/native-analyzer",
            "sha256": "e" * 64,
            "size_bytes": 100,
            "stat": stat_fact(10),
        },
        "material_status": "available",
        "limitations": [],
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "captured_bytes": 0,
        "logs_truncated": False,
        "snapshot_limitations": [],
        "binding": {
            "status": "verified",
            "limitations": [],
            "input_artifacts": links,
            "output_artifacts": [
                {"path": "findings.json", "artifact_id": "native-report"}
            ],
            "log_artifacts": {"stdout": "native-stdout", "stderr": "native-stderr"},
        },
    }
    producer = {"name": "cppulse.native-normalizer", "version": "1.0.0"}
    inventory = {
        "version": "2.0.0",
        "id": "native-inventory",
        "source_digest": manifest["source"]["digest"],
        "producer": producer,
        "receipt_id": "analyze",
        "job_context_id": "native",
        "report_artifact_id": "native-report",
        "registry_artifact_id": "registry",
        "config_artifact_id": "config",
        "compilation_database_artifact_id": "database",
        "registry_sha256": registry_descriptor["sha256"],
        "requested_files": ["src/main.cpp"],
        "requested_rules": ["CPP-MOD-001"],
        "enabled_rules": ["CPP-MOD-001"],
        "items": [
            {
                "file": "src/main.cpp",
                "parse_context_id": "parse-main",
                "status": "analyzed",
                "error_count": 0,
                "context_source": "database",
                "context_match": "matched",
                "executed_rules": ["CPP-MOD-001"],
                "finding_count": 1,
                "limitations": [],
            }
        ],
        "limitations": [],
    }
    observations = {
        "version": "2.0.0",
        "source_digest": manifest["source"]["digest"],
        "analysis_inventory_id": inventory["id"],
        "items": [
            {
                "id": "native-observation",
                "producer": producer,
                "rule_id": "CPP-MOD-001",
                "rule_version": "prototype-1",
                "file": "src/main.cpp",
                "context_id": "parse-main",
                "line": 1,
                "severity": "warning",
                "message": "Synthetic C-style cast trigger",
                "fingerprint": "f" * 64,
                "fingerprint_version": "1",
                "evidence_ids": [],
            }
        ],
    }
    data.update(
        execution_facts=facts,
        analysis_inventory=inventory,
        observations=observations,
        rule_registry=rules,
    )
    return with_resources(data)


def test_typed_analysis_chain_separates_job_and_observed_parse_context(
    analysis_bundle: dict[str, Any]
) -> None:
    validate("execution_facts", analysis_bundle["execution_facts"])
    validate("analysis_inventory", analysis_bundle["analysis_inventory"])
    validate_bundle(analysis_bundle)


@pytest.mark.parametrize(
    "change", ["source-not-observed", "report-unchanged", "resource-role-missing"]
)
def test_matched_inventory_does_not_promote_omitted_source_stale_report_or_unbound_resources(
    analysis_bundle: dict[str, Any], change: str
) -> None:
    facts = analysis_bundle["execution_facts"]
    if change == "source-not-observed":
        for key in ["input_facts", "input_after_facts"]:
            facts[key] = [row for row in facts[key] if row["path"] != "src/main.cpp"]
        facts["binding"]["input_artifacts"] = [
            row
            for row in facts["binding"]["input_artifacts"]
            if row["path"] != "src/main.cpp"
        ]
    elif change == "report-unchanged":
        facts["output_facts"][0]["freshness"] = "unchanged"
    else:
        analysis_bundle["analysis_inventory"].pop("resource_manifest_artifact_id")
    with pytest.raises(ContractError):
        validate_bundle(analysis_bundle)


@pytest.mark.parametrize("kind", ["execution_facts", "analysis_inventory"])
def test_unversioned_debug_is_never_an_implicit_trusted_fact(
    analysis_bundle: dict[str, Any], kind: str
) -> None:
    document = deepcopy(analysis_bundle[kind])
    del document["version"]
    with pytest.raises(ContractError):
        validate(kind, document)


@pytest.mark.parametrize(
    "change",
    [
        "receipt",
        "missing_artifact",
        "wrong_descriptor_hash",
        "wrong_descriptor_size",
        "duplicate_input",
        "unknown_input_path",
        "negative_capture",
        "capture_over_total",
        "false_truncation",
        "changed_inputs_verified",
        "relative_executable",
        "duplicate_facts",
    ],
)
def test_execution_facts_do_not_hide_receipt_or_material_disagreement(
    analysis_bundle: dict[str, Any], change: str
) -> None:
    data = analysis_bundle
    facts = data["execution_facts"]
    if change == "receipt":
        facts["receipt"]["argv"].append("different")
    elif change == "missing_artifact":
        facts["binding"]["output_artifacts"][0]["artifact_id"] = "absent"
    elif change in {"wrong_descriptor_hash", "wrong_descriptor_size"}:
        descriptor = next(
            a for a in data["run_manifest"]["artifacts"] if a["id"] == "native-report"
        )
        descriptor["sha256" if change.endswith("hash") else "size_bytes"] = (
            "0" * 64 if change.endswith("hash") else 123
        )
    elif change == "duplicate_input":
        facts["input_facts"].append(deepcopy(facts["input_facts"][0]))
    elif change == "unknown_input_path":
        facts["binding"]["input_artifacts"][0]["path"] = "not-observed.cpp"
    elif change == "negative_capture":
        facts["captured_bytes"] = -1
    elif change == "capture_over_total":
        facts["captured_bytes"] = 1
    elif change == "false_truncation":
        facts["logs_truncated"] = True
    elif change == "changed_inputs_verified":
        facts["input_after_facts"][0]["sha256"] = "0" * 64
    elif change == "relative_executable":
        facts["executable_fact"]["path"] = "relative/native"
    else:
        data["execution_facts"] = [facts, deepcopy(facts)]
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize(
    "change",
    [
        "unknown_source",
        "missing_requested_row",
        "duplicate_file",
        "unknown_parse_context",
        "wrong_job_context",
        "wrong_report_role",
        "wrong_registry_role",
        "wrong_registry_hash",
        "wrong_config_role",
        "wrong_database_role",
        "unknown_rule",
        "disabled_completion",
        "analyzed_errors",
        "partial_zero_errors",
        "partial_claims_completion",
        "unattempted_has_context",
        "fallback_matches",
        "unverified_source_matches",
        "invalid_facts_match",
        "dropped_observation",
        "wrong_finding_count",
    ],
)
def test_inventory_requires_explicit_complete_consistent_provenance(
    analysis_bundle: dict[str, Any], change: str
) -> None:
    data = analysis_bundle
    inventory = data["analysis_inventory"]
    row = inventory["items"][0]
    if change == "unknown_source":
        inventory["requested_files"] = ["unselected.cpp"]
        row["file"] = "unselected.cpp"
    elif change == "missing_requested_row":
        inventory["requested_files"].append("registry.json")
    elif change == "duplicate_file":
        inventory["items"].append(deepcopy(row))
    elif change == "unknown_parse_context":
        row["parse_context_id"] = "absent"
    elif change == "wrong_job_context":
        inventory["job_context_id"] = "parse-main"
    elif change == "wrong_report_role":
        inventory["report_artifact_id"] = "config"
    elif change == "wrong_registry_role":
        inventory["registry_artifact_id"] = "native-report"
    elif change == "wrong_registry_hash":
        inventory["registry_sha256"] = "0" * 64
    elif change == "wrong_config_role":
        inventory["config_artifact_id"] = "native-report"
    elif change == "wrong_database_role":
        inventory["compilation_database_artifact_id"] = "native-report"
    elif change == "unknown_rule":
        inventory["requested_rules"] = ["UNKNOWN-001"]
    elif change == "disabled_completion":
        inventory["enabled_rules"] = []
    elif change == "analyzed_errors":
        row["error_count"] = 1
    elif change == "partial_zero_errors":
        row["status"] = "partial"
        row["executed_rules"] = []
    elif change == "partial_claims_completion":
        row["status"] = "partial"
        row["error_count"] = 1
    elif change == "unattempted_has_context":
        row["status"] = "missing"
        row["executed_rules"] = []
    elif change == "fallback_matches":
        row["context_source"] = "fallback"
    elif change == "unverified_source_matches":
        data["run_manifest"]["input_verification"] = "unverified"
    elif change == "invalid_facts_match":
        data["execution_facts"]["binding"].update(
            status="invalid", limitations=["Tool changed"]
        )
    elif change == "dropped_observation":
        data["observations"]["items"] = []
    else:
        row["finding_count"] = 2
    with pytest.raises(ContractError):
        validate_bundle(data)


@pytest.mark.parametrize(
    "change",
    [
        "unlinked",
        "wrong_inventory",
        "wrong_context",
        "unknown_rule",
        "wrong_version",
        "wrong_producer",
    ],
)
def test_observation_link_must_preserve_actual_file_rule_parse_context_and_producer(
    analysis_bundle: dict[str, Any], change: str
) -> None:
    data = analysis_bundle
    document = data["observations"]
    finding = document["items"][0]
    if change == "unlinked":
        del document["analysis_inventory_id"]
    elif change == "wrong_inventory":
        document["analysis_inventory_id"] = "absent"
    elif change == "wrong_context":
        finding["context_id"] = "native"
    elif change == "unknown_rule":
        finding["rule_id"] = "UNKNOWN-001"
    elif change == "wrong_version":
        finding["rule_version"] = "future"
    else:
        finding["producer"] = {"name": "unrelated", "version": "1"}
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_matching_partial_findings_survive_without_claimed_rule_completion(
    analysis_bundle: dict[str, Any]
) -> None:
    row = analysis_bundle["analysis_inventory"]["items"][0]
    row.update(status="partial", error_count=1, executed_rules=[])
    validate_bundle(analysis_bundle)


def test_unrequested_but_enabled_known_findings_are_not_silently_dropped(
    analysis_bundle: dict[str, Any]
) -> None:
    data = analysis_bundle
    original = data["rule_registry"]["rules"][0]
    extra = deepcopy(original)
    extra["id"] = "CPP-MEM-001"
    data["rule_registry"]["rules"].append(extra)
    import hashlib

    content = json_bytes(data["rule_registry"])
    sha = hashlib.sha256(content).hexdigest()
    for artifact in data["run_manifest"]["artifacts"]:
        if artifact["id"] in {"registry", "typed-registry"}:
            artifact.update(sha256=sha, size_bytes=len(content))
    for source in data["run_manifest"]["source"]["files"]:
        if source["path"] == "registry.json":
            source.update(sha256=sha, size_bytes=len(content))
    for key in ["input_facts", "input_after_facts"]:
        next(
            row
            for row in data["execution_facts"][key]
            if row["path"] == "registry.json"
        ).update(sha256=sha, size_bytes=len(content))
    source = data["run_manifest"]["source"]
    source["digest"] = digest_json(
        {key: source[key] for key in ["kind", "inventory_complete"]}
        | {"files": sorted(source["files"], key=lambda row: row["path"])}
    )
    data["analysis_inventory"]["source_digest"] = source["digest"]
    data["observations"]["source_digest"] = source["digest"]
    data["evidence"]["source_digest"] = source["digest"]
    for receipt in data["execution_receipt"]:
        receipt["source_digest"] = source["digest"]
    data["execution_facts"]["receipt"]["source_digest"] = source["digest"]
    inventory = data["analysis_inventory"]
    inventory["registry_sha256"] = sha
    inventory["enabled_rules"].append("CPP-MEM-001")
    inventory["items"][0]["executed_rules"].append("CPP-MEM-001")
    data["observations"]["items"][0]["rule_id"] = "CPP-MEM-001"
    validate_bundle(data)


def sync_subject(data: dict[str, Any]) -> None:
    """Update synthetic selected subject references after adding explicit inputs."""
    source = data["run_manifest"]["source"]
    source["digest"] = digest_json(
        {
            "kind": source["kind"],
            "inventory_complete": source["inventory_complete"],
            "files": sorted(source["files"], key=lambda row: row["path"]),
        }
    )
    for receipt in data["execution_receipt"]:
        receipt["source_digest"] = source["digest"]
    data["execution_facts"]["receipt"]["source_digest"] = source["digest"]
    for key in ["analysis_inventory", "observations", "evidence"]:
        data[key]["source_digest"] = source["digest"]


def add_input(
    data: dict[str, Any], path: str, content: bytes, identifier: str
) -> dict[str, Any]:
    """Add one selected, retained input with matching observed byte identities."""
    import hashlib

    record = {
        "path": path,
        "sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    data["run_manifest"]["source"]["files"].append(record)
    descriptor = {
        "id": identifier,
        "path": "inputs/" + identifier,
        "sha256": record["sha256"],
        "size_bytes": len(content),
        "media_type": "application/octet-stream",
    }
    data["run_manifest"]["artifacts"].append(descriptor)
    facts = data["execution_facts"]
    fact = {**record, "stat": stat_fact(len(facts["input_facts"]) + 100)}
    for key in ["input_facts", "input_after_facts"]:
        facts[key].append(deepcopy(fact))
    facts["binding"]["input_artifacts"].append(
        {"path": path, "artifact_id": identifier}
    )
    facts["receipt"]["artifact_ids"].append(identifier)
    data["execution_receipt"][1]["artifact_ids"].append(identifier)
    sync_subject(data)
    return descriptor


def with_resources(data: dict[str, Any]) -> dict[str, Any]:
    """Bind a finite selected resource inventory, not a claim of all host inputs."""
    add_input(
        data,
        "resources/include/stddef.h",
        b"// synthetic builtin sentinel\n",
        "resource-header",
    )
    header = next(
        row
        for row in data["run_manifest"]["source"]["files"]
        if row["path"].startswith("resources/")
    )
    resource = {
        "version": "2.0.0",
        "root": "resources",
        "files": [deepcopy(header)],
        "limitations": [
            "This declares only the explicitly selected finite resource inputs."
        ],
    }
    original = add_input(
        data, "resource_manifest.json", json_bytes(resource), "resource-data"
    )
    typed = deepcopy(original)
    typed.update(
        id="typed-resources",
        path="documents/resources.json",
        media_type="application/json",
        contract={"kind": "resource_manifest", "version": "2.0.0"},
    )
    data["run_manifest"]["artifacts"].append(typed)
    data["resource_manifest"] = resource
    data["analysis_inventory"]["resource_manifest_artifact_id"] = "resource-data"
    context = data["run_manifest"]["contexts"][1]
    context["argv"].append("-resource-dir=/synthetic/resources")
    context["dependencies"].append(
        {
            "id": "selected-resources",
            "availability": "available",
            "sha256": original["sha256"],
        }
    )
    context["digest"] = digest_json(
        {
            key: value
            for key, value in context.items()
            if key not in {"id", "digest", "version", "limitations"}
        }
    )
    return data


@pytest.fixture
def resource_bundle(analysis_bundle: dict[str, Any]) -> dict[str, Any]:
    """Return the fully resource-bound positive baseline."""
    return analysis_bundle


def test_selected_resource_manifest_is_byte_bound_to_source_and_native_inputs(
    resource_bundle: dict[str, Any]
) -> None:
    validate_bundle(resource_bundle)


@pytest.mark.parametrize(
    "change",
    [
        "escape",
        "missing_sentinel",
        "wrong_source_bytes",
        "wrong_typed_copy",
        "unretained_role",
        "unlisted_selected_resource",
    ],
)
def test_resource_manifest_cannot_claim_unbound_or_unlisted_selected_inputs(
    resource_bundle: dict[str, Any], change: str
) -> None:
    data = resource_bundle
    resource = data["resource_manifest"]
    if change == "escape":
        resource["files"][0]["path"] = "../outside.h"
    elif change == "missing_sentinel":
        resource["files"][0]["path"] = "resources/include/other.h"
    elif change == "wrong_source_bytes":
        resource["files"][0]["sha256"] = "0" * 64
    elif change == "wrong_typed_copy":
        next(
            row
            for row in data["run_manifest"]["artifacts"]
            if row["id"] == "typed-resources"
        )["sha256"] = ("0" * 64)
    elif change == "unretained_role":
        data["analysis_inventory"]["resource_manifest_artifact_id"] = "absent"
    else:
        add_input(data, "resources/include/extra.h", b"unlisted\n", "resource-extra")
    with pytest.raises(ContractError):
        validate_bundle(data)


def test_fallback_context_and_unverified_source_are_retained_without_match_claim(
    analysis_bundle: dict[str, Any]
) -> None:
    row = analysis_bundle["analysis_inventory"]["items"][0]
    row.update(context_source="fallback", context_match="unverified")
    analysis_bundle["analysis_inventory"]["compilation_database_artifact_id"] = None
    analysis_bundle["run_manifest"]["input_verification"] = "unverified"
    validate_bundle(analysis_bundle)


def test_database_context_cannot_match_without_the_observed_database_input(
    analysis_bundle: dict[str, Any]
) -> None:
    analysis_bundle["analysis_inventory"]["compilation_database_artifact_id"] = None
    with pytest.raises(ContractError):
        validate_bundle(analysis_bundle)


def test_verified_generated_input_requires_a_typed_ancestor_producer(
    analysis_bundle: dict[str, Any]
) -> None:
    data = analysis_bundle
    data["run_manifest"]["source"]["files"] = [
        row
        for row in data["run_manifest"]["source"]["files"]
        if row["path"] != "compile_commands.json"
    ]
    sync_subject(data)
    with pytest.raises(ContractError, match="typed ancestor"):
        validate_bundle(data)
    child = data["execution_facts"]
    parent = deepcopy(child)
    parent["receipt"].update(
        id="configure-db",
        argv=["/host/native-analyzer"],
        artifact_ids=["database"],
        depends_on=[],
    )
    parent["input_facts"] = []
    parent["input_after_facts"] = []
    database = next(
        row for row in child["input_facts"] if row["path"] == "compile_commands.json"
    )
    parent["output_facts"] = [{**deepcopy(database), "freshness": "created"}]
    parent["binding"]["input_artifacts"] = []
    parent["binding"]["output_artifacts"] = [
        {"path": "compile_commands.json", "artifact_id": "database"}
    ]
    child["receipt"]["depends_on"] = ["configure-db"]
    data["execution_receipt"][1]["depends_on"] = ["configure-db"]
    data["execution_receipt"].append(deepcopy(parent["receipt"]))
    data["execution_facts"] = [parent, child]
    validate_bundle(data)


@pytest.mark.parametrize(
    "change", ["invalid", "unchanged", "failed", "other-context", "after-child"]
)
def test_verified_child_cannot_promote_an_unusable_or_future_generated_ancestor(
    analysis_bundle: dict[str, Any], change: str
) -> None:
    # Exercise the independently validated complete generated-lineage fixture first.
    test_verified_generated_input_requires_a_typed_ancestor_producer(analysis_bundle)
    parent = analysis_bundle["execution_facts"][0]
    receipt = analysis_bundle["execution_receipt"][-1]
    if change == "invalid":
        parent["binding"].update(
            status="invalid", limitations=["Observed binding failed"]
        )
    elif change == "unchanged":
        parent["material_status"] = "invalid"
        parent["output_facts"][0]["freshness"] = "unchanged"
    elif change == "failed":
        parent["receipt"].update(status="failed", exit_code=1)
        receipt.update(status="failed", exit_code=1)
    elif change == "other-context":
        parent["receipt"]["context_id"] = "parse-main"
        receipt["context_id"] = "parse-main"
    else:
        parent["receipt"]["finished_at"] = "2026-11-14T11:00:00Z"
        receipt["finished_at"] = parent["receipt"]["finished_at"]
        analysis_bundle["run_manifest"]["finished_at"] = "2026-11-15T11:00:00Z"
    with pytest.raises(ContractError):
        validate_bundle(analysis_bundle)


def coverage_assessment(data: dict[str, Any], minimum: int) -> None:
    """Compose policy metadata over the synthetic provenance fixture."""
    policy = policy_fixture.__wrapped__()
    policy["controls"][0].update(
        kind="minimum_analysis_coverage", parameters={"minimum": minimum}
    )
    assessment = policy_bundle.__wrapped__(policy)["assessment"]
    assessment["source_digest"] = data["run_manifest"]["source"]["digest"]
    assessment["controls"][0]["evidence_ids"] = []
    data.update(policy=policy, assessment=assessment)


def test_positive_parse_coverage_checks_measured_percentage(
    analysis_bundle: dict[str, Any]
) -> None:
    data = analysis_bundle
    coverage_assessment(data, 100)
    validate_bundle(data)
    data["analysis_inventory"]["items"][0].update(
        status="partial", error_count=1, executed_rules=[]
    )
    with pytest.raises(ContractError, match="coverage"):
        validate_bundle(data)
    data["policy"]["controls"][0]["parameters"]["minimum"] = 0
    data["assessment"]["policy"]["sha256"] = digest_json(data["policy"])
    validate_bundle(data)


def test_rule_disabled_parse_coverage_is_separate_from_finding_completeness(
    analysis_bundle: dict[str, Any]
) -> None:
    data = analysis_bundle
    data["analysis_inventory"]["enabled_rules"] = []
    data["analysis_inventory"]["items"][0].update(executed_rules=[], finding_count=0)
    data["observations"]["items"] = []
    coverage_assessment(data, 100)
    validate_bundle(data)
    data["policy"]["controls"][0].update(
        kind="finding_limit",
        parameters={"rule_ids": ["CPP-MOD-001"], "max_findings": 0},
    )
    data["assessment"]["policy"]["sha256"] = digest_json(data["policy"])
    with pytest.raises(ContractError, match="consideration"):
        validate_bundle(data)


@pytest.mark.parametrize("status,errors", [("analyzed", 0), ("partial", 1)])
def test_observed_analysis_context_does_not_require_a_passing_ast(
    analysis_bundle: dict[str, Any], status: str, errors: int
) -> None:
    data = analysis_bundle
    coverage_assessment(data, 100)
    data["policy"]["controls"][0].update(
        kind="required_contexts", parameters={"contexts": ["native"]}
    )
    data["assessment"]["policy"]["sha256"] = digest_json(data["policy"])
    data["analysis_inventory"]["items"][0].update(
        status=status,
        error_count=errors,
        executed_rules=["CPP-MOD-001"] if status == "analyzed" else [],
    )
    # Only the observed analysis job proves this context in this case.
    data["evidence"]["records"] = []
    validate_bundle(data)
