"""Validate finite declared scope independently of successful work-unit facts."""

from __future__ import annotations

from typing import Any

from cppulse.errors import ContractError
from cppulse.work_units import _check


def validate_analysis_scope(document: dict[str, Any]) -> None:
    """Reject duplicate ownership and invented success for absent executions."""
    _check("analysis_scope", document)
    rows = document["units"]
    paths = [row["primary_file"] for row in rows]
    if paths != sorted(set(paths)) or len({row["unit_id"] for row in rows}) != len(
        rows
    ):
        raise ContractError(
            "Analysis scope must own sorted selected files exactly once"
        )
    if document["inventory_complete"] and document["discovery_gaps"]:
        raise ContractError("Discovery gaps cannot be a complete analysis inventory")
    for row in rows:
        binding = row["execution"]
        if binding is None:
            if (
                row["outcome"] not in {"not_attempted", "invalid_output"}
                or row["parse_status"] is not None
            ):
                raise ContractError(
                    "Absent original execution cannot supply parse facts"
                )
        elif binding["receipt_id"] != "native-" + binding["request_sha256"]:
            raise ContractError("Scope receipt does not identify the original request")


def semantic(kind: str, document: dict[str, Any]) -> None:
    """Check public scope/binding semantics without executing or reading a project."""
    from cppulse.contracts import validate
    from cppulse.identities import digest_json

    if kind == "analysis_scope":
        private = {
            key: value
            for key, value in document.items()
            if key not in {"id", "job_context_id"}
        }
        private["version"] = "1.0.0"
        validate_analysis_scope(private)
    elif kind == "work_unit_analysis_binding":
        request, result = document["request"], document["result"]
        _check("work_request", request)
        _check("work_result", result)
        if (
            request["unit_id"] != document["unit_id"]
            or result["unit_id"] != document["unit_id"]
            or result["request_sha256"] != digest_json(request)
        ):
            raise ContractError(
                "Bounded analysis binding changes original request/result identity"
            )
        receipt = result["execution_receipt"]
        if receipt is None:
            raise ContractError(
                "Bounded normalized facts require a genuine original receipt"
            )
        validate("execution_receipt", receipt)
        if (
            request["source_digest"] != document["source_digest"]
            or receipt["source_digest"] != document["source_digest"]
            or receipt["id"] != "native-" + digest_json(request)
        ):
            raise ContractError(
                "Bounded analysis receipt identifies another source/request"
            )


def validate_work_unit_analysis_bundle(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
) -> set[str]:
    """Validate genuine bounded bindings without manufacturing execution facts."""
    from cppulse.identities import digest_json, canonical_json_bytes

    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    contexts = {row["id"]: row for row in manifest["contexts"]}
    sources = {row["path"]: row for row in manifest["source"]["files"]}

    def unique(rows: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
        mapped = {row[field]: row for row in rows}
        if len(mapped) != len(rows):
            raise ContractError("Duplicate bounded analysis " + field)
        return mapped

    scopes = unique([doc for kind, doc in flat if kind == "analysis_scope"], "id")
    inventories = unique(
        [doc for kind, doc in flat if kind == "analysis_inventory"], "id"
    )
    bindings = unique(
        [doc for kind, doc in flat if kind == "work_unit_analysis_binding"],
        "analysis_inventory_id",
    )
    if not scopes and not bindings:
        return set()
    unique(list(scopes.values()), "job_context_id")
    for scope in scopes.values():
        if (
            scope["source_digest"] != manifest["source"]["digest"]
            or scope["job_context_id"] not in contexts
            or contexts[scope["job_context_id"]]["provenance"] != "inferred"
        ):
            raise ContractError(
                "Bounded declared scope differs from selected source/context"
            )
        if {row["primary_file"] for row in scope["units"]} != sources.keys():
            raise ContractError("Bounded declared scope omits selected source files")
        for identifier, sha in (
            ("analysis-plan", scope["plan_sha256"]),
            ("analysis-summary", scope["summary_sha256"]),
            ("analysis-bindings", scope["bindings_sha256"]),
        ):
            if identifier not in artifacts or artifacts[identifier]["sha256"] != sha:
                raise ContractError(
                    "Bounded scope differs from retained original execution metadata"
                )
    registry_docs = [doc for kind, doc in flat if kind == "rule_registry"]
    registry_by_sha = {digest_json(doc): doc for doc in registry_docs}
    ownership = set()
    for inventory_id, binding in bindings.items():
        inventory = inventories.get(inventory_id)
        scope = scopes.get(binding["analysis_scope_id"])
        if inventory is None or scope is None:
            raise ContractError("Bounded analysis binding lacks its scope/inventory")
        request, result = binding["request"], binding["result"]
        receipt = result["execution_receipt"]
        path = request["primary_file"]
        ownership_key = (scope["id"], request["unit_id"])
        if ownership_key in ownership:
            raise ContractError("Original unit supplies more than one inventory")
        ownership.add(ownership_key)
        selected = [
            row for row in scope["units"] if row["unit_id"] == request["unit_id"]
        ]
        if (
            len(selected) != 1
            or selected[0]["primary_file"] != path
            or selected[0]["execution"] is None
        ):
            raise ContractError(
                "Bounded inventory has no original execution in declared scope"
            )
        selected = selected[0]
        execution = selected["execution"]
        if (
            selected["outcome"] != result["outcome"]
            or selected["parse_status"] != result["parse_status"]
        ):
            raise ContractError("Scope outcome differs from original result")
        for field, value in (
            ("request_sha256", digest_json(request)),
            ("result_sha256", digest_json(result)),
            ("receipt_id", receipt["id"]),
            ("invocation_context_id", receipt["context_id"]),
            ("declared_context_id", request["context"]["id"]),
        ):
            if execution[field] != value:
                raise ContractError(
                    "Scope original execution identity differs from binding"
                )
        for field in (
            "request_artifact_id",
            "result_artifact_id",
            "receipt_artifact_id",
        ):
            if binding[field] != execution[field]:
                raise ContractError("Scope retained artifact role differs from binding")
        for field, document in (
            ("request_artifact_id", request),
            ("result_artifact_id", result),
        ):
            artifact = artifacts.get(binding[field])
            if (
                artifact is None
                or artifact["sha256"] != digest_json(document)
                or artifact["size_bytes"] != len(canonical_json_bytes(document))
            ):
                raise ContractError(
                    "Embedded original execution metadata differs from retained artifact"
                )
        if (
            receipts.get(receipt["id"]) != receipt
            or receipt["context_id"] not in contexts
        ):
            raise ContractError(
                "Bounded inventory lacks its separately retained original receipt/context"
            )
        invocation = contexts[receipt["context_id"]]
        if (
            invocation["argv"] != receipt["argv"]
            or invocation["working_directory"] != receipt["cwd"]
            or invocation["compiler"] != request["native"]
            or invocation["provenance"] != "observed"
        ):
            raise ContractError(
                "Original bounded receipt differs from its retained invocation context"
            )
        receipt_artifact = artifacts.get(binding["receipt_artifact_id"])
        if (
            receipt_artifact is None
            or receipt_artifact.get("contract", {}).get("kind") != "execution_receipt"
        ):
            raise ContractError("Original receipt role is not a typed retained receipt")
        if (
            request["source_digest"] != manifest["source"]["digest"]
            or path not in sources
            or request["primary_sha256"] != sources[path]["sha256"]
        ):
            raise ContractError("Bounded request identifies another selected source")
        if (
            inventory["receipt_id"] != receipt["id"]
            or inventory["job_context_id"] != scope["job_context_id"]
            or inventory["requested_files"] != [path]
        ):
            raise ContractError(
                "Bounded inventory changes original receipt, global declaration, or file"
            )
        declaration = contexts[scope["job_context_id"]]
        declaration_dependencies = {
            row["id"]: row for row in declaration["dependencies"]
        }
        requested_resource_dependencies = [
            row
            for row in request["context"]["dependencies"]
            if row["id"] == "builtin-resources"
        ]
        if (
            declaration["working_directory"] != request["source_root"]
            or declaration_dependencies.get("native-binary", {}).get("sha256")
            != request["native"]["sha256"]
            or declaration_dependencies.get("analysis-configuration", {}).get("sha256")
            != request["inputs"]["configuration"]["sha256"]
            or declaration_dependencies.get("compilation-database", {}).get("sha256")
            != (
                request["inputs"]["compilation_database"]["sha256"]
                if request["inputs"]["compilation_database"] is not None
                else None
            )
            or len(requested_resource_dependencies) > 1
            or (
                "builtin-resources" in declaration_dependencies
                and declaration_dependencies["builtin-resources"]["sha256"]
                != (
                    requested_resource_dependencies[0]["sha256"]
                    if requested_resource_dependencies
                    else None
                )
            )
        ):
            raise ContractError(
                "Original bounded request differs from the global native/configuration declaration"
            )
        expected_roles = {
            role: record
            for role, record in request["inputs"].items()
            if record is not None
        }
        if set(expected_roles) != set(binding["inputs"]):
            raise ContractError("Bounded input roles do not match original request")
        for role, record in expected_roles.items():
            artifact = artifacts.get(binding["inputs"][role])
            if artifact is None or any(
                artifact[key] != record[key]
                for key in ("sha256", "size_bytes", "media_type")
            ):
                raise ContractError("Bounded input pin differs from original request")
        outputs = unique(result["artifacts"], "id")
        if set(binding["outputs"]) != set(outputs):
            raise ContractError("Bounded output roles differ from original result")
        for identifier, record in outputs.items():
            if identifier not in artifacts or any(
                artifacts[identifier][key] != record[key]
                for key in ("sha256", "size_bytes", "media_type")
            ):
                raise ContractError("Bounded output pin differs from original result")
        if (
            inventory["report_artifact_id"] not in outputs
            or outputs[inventory["report_artifact_id"]]["path"]
            != "output/findings.json"
        ):
            raise ContractError(
                "Bounded native report is not original output/findings.json"
            )
        for field, role in (
            ("registry_artifact_id", "rule_registry"),
            ("config_artifact_id", "configuration"),
            ("compilation_database_artifact_id", "compilation_database"),
        ):
            if inventory.get(field) != binding["inputs"].get(role):
                raise ContractError(
                    "Bounded native input role differs from original request"
                )
        if inventory.get("resource_manifest_artifact_id") is not None:
            raise ContractError(
                "SDK hash inventory is not a typed retained SDK byte inventory"
            )
        registry = registry_by_sha.get(inventory["registry_sha256"])
        if (
            registry is None
            or inventory["registry_sha256"]
            != artifacts[inventory["registry_artifact_id"]]["sha256"]
        ):
            raise ContractError(
                "Bounded analysis lacks byte-identical typed rule registry"
            )
        rules = {row["id"]: row for row in registry["rules"]}
        if (
            not set(inventory["requested_rules"] + inventory["enabled_rules"])
            <= rules.keys()
        ):
            raise ContractError("Bounded inventory refers to unknown rule")
        rows = {row["file"]: row for row in inventory["items"]}
        for row in rows.values():
            parse = contexts.get(row["parse_context_id"])
            if row["parse_context_id"] is not None and (
                parse is None
                or parse["provenance"] != "observed"
                or parse["compiler"]["name"] != "libclang"
            ):
                raise ContractError(
                    "Bounded inventory lacks actual observed libclang context"
                )
            if (
                row["context_match"] == "matched"
                or row.get("buffer_coherence") == "verified"
            ):
                if (
                    manifest.get("input_verification") != "verified"
                    or scope["input_verification"] != "verified"
                    or result["outcome"] != "complete"
                    or receipt["status"] != "passed"
                ):
                    raise ContractError(
                        "Bounded qualified parse requires successful original execution/current binding"
                    )
            if (
                row["context_match"] == "matched"
                and inventory["compilation_database_artifact_id"] is None
            ):
                raise ContractError(
                    "Matched bounded parse requires retained compilation command"
                )
        counts = dict.fromkeys(rows, 0)
        for kind, document in flat:
            if (
                kind != "observations"
                or document.get("analysis_inventory_id") != inventory_id
            ):
                continue
            for observation in document["items"]:
                row = rows.get(observation["file"])
                rule = rules.get(observation["rule_id"])
                if (
                    row is None
                    or row["status"] not in {"analyzed", "partial"}
                    or rule is None
                    or observation["context_id"] != row["parse_context_id"]
                    or observation["producer"] != inventory["producer"]
                    or observation["rule_id"] not in inventory["enabled_rules"]
                    or observation["rule_version"] != rule["version"]
                ):
                    raise ContractError(
                        "Bounded observation differs from original inventory/context/rule"
                    )
                counts[observation["file"]] += 1
        if any(counts[path] != row["finding_count"] for path, row in rows.items()):
            raise ContractError("Bounded observation counts differ from inventory")
    return set(bindings)
