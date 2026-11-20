"""Static public workflow declarations and result/exit consistency, without I/O."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import PurePosixPath
from typing import Any


def _absolute(value: str, path: str) -> None:
    from .validation import _fail

    pure = PurePosixPath(value)
    if (
        "\x00" in value
        or "\\" in value
        or not pure.is_absolute()
        or ".." in pure.parts
        or pure.as_posix() != value
    ):
        _fail("Expected a canonical absolute POSIX path", path, "UNSAFE_PATH")


def _request(document: dict[str, Any]) -> None:
    from .validation import (
        _collection_bundle,
        _collection_path,
        _digest,
        _fail,
        _unique,
        validate,
    )

    plan = document["plan"]
    validate("collection_plan", plan)
    contexts = _unique(document["contexts"], "id", "/contexts")
    for context in contexts.values():
        validate("context", context)
    files = set(document["source"]["files"])
    for path in files:
        _collection_path(path, "/source/files")
    # Reuse the already accepted plan/source/context relationship checks. This
    # projection needs no source bytes or fabricated source hashes.
    _collection_bundle(
        [plan],
        {
            "source": {"files": [{"path": path} for path in files]},
            "contexts": document["contexts"],
            "config_digest": _digest(plan),
        },
        [],
    )
    steps = {step["id"]: step for step in plan["recipe"]["steps"]}
    bindings = {binding["id"]: binding for binding in plan["bindings"]}
    _unique(document["normalizers"], "id", "/normalizers")
    known_rules = {
        row["id"]
        for row in json.loads(
            resources.files("cppulse").joinpath("data/rule_registry.json").read_text()
        )["rules"]
    }
    seen = set()

    def step(identifier):
        if identifier not in steps:
            _fail(
                "Normalizer refers to an undeclared recipe step",
                "/normalizers",
                "UNRESOLVED_REFERENCE",
            )
        return steps[identifier]

    def selected(role):
        producer = step(role["step_id"])
        if (
            role["role"] in {"input", "output"}
            and role["path"] not in producer[role["role"] + "s"]
        ):
            _fail(
                "Normalizer path is not an explicit selected step role",
                "/normalizers",
                "UNRESOLVED_REFERENCE",
            )
        return producer

    def scope(paths):
        if not set(paths) <= files:
            _fail(
                "Normalizer scope is outside selected source inventory",
                "/normalizers",
                "SUBJECT_MISMATCH",
            )

    def tests(identifier):
        binding = bindings.get(identifier)
        if binding is None or binding["kind"] != "tests":
            _fail(
                "Normalizer requires a declared test binding",
                "/normalizers",
                "UNRESOLVED_REFERENCE",
            )
        return binding

    def same_job(ids):
        if len({step(identifier)["context_id"] for identifier in ids}) != 1:
            _fail(
                "Normalizer proof steps belong to different job contexts",
                "/normalizers",
                "SUBJECT_MISMATCH",
            )

    for item in document["normalizers"]:
        kind = item["kind"]
        if kind == "native_analysis":
            role_ids = []
            for key in [
                "report",
                "registry",
                "config",
                "compilation_database",
                "resource_manifest",
            ]:
                role = item[key]
                if role is not None:
                    selected(role)
                    role_ids.append(role["step_id"])
            step(item["step_id"])
            if set(role_ids) != {item["step_id"]}:
                _fail(
                    "Native roles must belong to the selected native step",
                    "/normalizers",
                )
            scope(item["requested_files"])
            if not set(item["requested_rules"]) <= known_rules:
                _fail(
                    "Native request contains an unknown packaged rule ID",
                    "/normalizers/requested_rules",
                    "UNRESOLVED_REFERENCE",
                )
            signature = (kind, item["step_id"])
        elif kind == "coverage":
            primary = step(item["step_id"])
            for collection, role_name in [
                ("instrumentation", "object"),
                ("instrumentation", "mapping"),
                ("profiles", "profile"),
            ]:
                identities = [_digest(row[role_name]) for row in item[collection]]
                if len(identities) != len(set(identities)):
                    _fail(
                        "Coverage request repeats a selected material role",
                        "/normalizers/" + collection,
                        "DUPLICATE_ID",
                    )
            for key in ["report", "configuration", "gcov"]:
                selected(item[key])
                if item[key]["step_id"] != item["step_id"]:
                    _fail(
                        "Coverage report/configuration/gcov must select the report step",
                        "/normalizers",
                    )
            needed = {
                item["step_id"],
                item["producer_version_step_id"],
                item["gcov_version_step_id"],
                item["compiler_version_step_id"],
            }
            for object in item["instrumentation"]:
                for key in ["object", "mapping"]:
                    selected(object[key])
                if object["object"]["step_id"] != object["mapping"]["step_id"]:
                    _fail(
                        "Coverage object and mapping require the same compile producer",
                        "/normalizers/instrumentation",
                    )
                scope(object["source_files"])
                needed.add(object["object"]["step_id"])
            test_steps = {
                tests(identifier)["step_id"] for identifier in item["test_binding_ids"]
            }
            for profile in item["profiles"]:
                selected(profile["profile"])
                selected(profile["binary"])
                if (
                    profile["profile"]["step_id"] != profile["test_step_id"]
                    or profile["test_step_id"] not in test_steps
                ):
                    _fail(
                        "Coverage profile must select its actual declared test producer",
                        "/normalizers/profiles",
                    )
                matching_bindings = [
                    tests(identifier)
                    for identifier in item["test_binding_ids"]
                    if tests(identifier)["step_id"] == profile["test_step_id"]
                ]
                binary_path = profile["binary"]["path"]
                if binary_path not in step(profile["test_step_id"])[
                    "inputs"
                ] or not any(
                    binary_path in binding["exercised_inputs"]
                    for binding in matching_bindings
                ):
                    _fail(
                        "Coverage binary role is not the selected exercised test input",
                        "/normalizers/profiles/binary",
                        "SUBJECT_MISMATCH",
                    )
                needed.update([profile["test_step_id"], profile["binary"]["step_id"]])
            if not needed <= set(item["proof_step_ids"]):
                _fail(
                    "Coverage proof list omits a declared material/version step",
                    "/normalizers/proof_step_ids",
                )
            same_job(item["proof_step_ids"])
            if primary["context_id"] != step(item["proof_step_ids"][0])["context_id"]:
                _fail("Coverage proof list differs from report job", "/normalizers")
            signature = (
                kind,
                item["adapter"],
                json.dumps(item["report"], sort_keys=True),
            )
        elif kind == "sanitizer":
            scope(item["requested_files"])
            needed = [
                item[key]
                for key in [
                    "compiler_version_step_id",
                    "nm_version_step_id",
                    "readelf_version_step_id",
                    "link_step_id",
                    "runtime_inspection_step_id",
                ]
            ]
            for object in item["objects"]:
                needed.extend(object.values())
            _unique(item["objects"], "compile_step_id", "/normalizers/objects")
            if (
                len(
                    {
                        item[key]
                        for key in [
                            "compiler_version_step_id",
                            "nm_version_step_id",
                            "readelf_version_step_id",
                        ]
                    }
                )
                != 3
            ):
                _fail(
                    "Sanitizer version probes must be distinct explicit steps",
                    "/normalizers",
                )
            needed.append(tests(item["test_binding_id"])["step_id"])
            same_job(needed)
            signature = (
                kind,
                json.dumps(
                    {key: value for key, value in item.items() if key != "id"},
                    sort_keys=True,
                ),
            )
        else:
            selected(item["report"])
            scope(item["scope_files"])
            if item["context_id"] not in contexts:
                _fail(
                    "Imported diagnostic context is undeclared",
                    "/normalizers/context_id",
                    "UNRESOLVED_REFERENCE",
                )
            if kind != "test_import":
                _absolute(item["source_root"], "/normalizers/source_root")
            identity = {key: value for key, value in item.items() if key != "id"}
            identity["scope_files"] = sorted(item["scope_files"])
            signature = (kind, json.dumps(identity, sort_keys=True))
        if signature in seen:
            _fail(
                "Repeated normalization would duplicate the same selected facts",
                "/normalizers",
                "DUPLICATE_ID",
            )
        seen.add(signature)


def _result(kind: str, document: dict[str, Any]) -> None:
    from .validation import _fail, _unique

    _absolute(document["store"], "/store")
    if not document["reason"].strip():
        _fail("Workflow result requires an actionable reason", "/reason")
    status = document["status"]
    codes = {
        "completed": 0,
        "passed": 0,
        "failed": 1,
        "partial": 3,
        "insufficient_evidence": 3,
        "invalid": 2,
        "cancelled": 130,
    }
    if document["exit_code"] != codes[status]:
        _fail("Result status and exit code disagree", "/exit_code")
    if document["error"] is not None:
        if status in {"completed", "passed"}:
            _fail("Successful operation cannot carry a fatal diagnostic", "/error")
        if (
            document["error"]["code"]
            in {"STALE_SOURCE", "STALE_OUTPUT", "UNVERIFIED_SOURCE", "INPUT_CHANGED"}
            and document["exit_code"] != 3
        ):
            _fail(
                "Changed/unverified workspace facts require recollection exit 3",
                "/exit_code",
            )
    if status == "invalid" and document["error"] is None:
        _fail("Invalid input needs a structured diagnostic", "/error")
    if kind == "check_result":
        policy = document["mode"] == "policy"
        selected = "assessment_artifact_id" if policy else "comparison_artifact_id"
        other = "comparison_artifact_id" if policy else "assessment_artifact_id"
        selected_hash = "policy_sha256" if policy else "baseline_sha256"
        other_hash = "baseline_sha256" if policy else "policy_sha256"
        if (
            document[other] is not None
            or document[other_hash] is not None
            or (not policy and document["facts_base_run"] is not None)
        ):
            _fail("Policy and finding check selections are mutually exclusive", "/mode")
        if status in {"passed", "failed"} and any(
            document[key] is None for key in ["run", selected, selected_hash]
        ):
            _fail("A definite check needs its pinned decision artifact", "/run")
        if (
            policy
            and status in {"passed", "failed"}
            and document["facts_base_run"] is None
        ):
            _fail(
                "Policy check must expose its original unassessed facts base",
                "/facts_base_run",
            )
        if (
            document["run"] is not None
            and document["facts_base_run"] is not None
            and document["run"]["source_digest"]
            != document["facts_base_run"]["source_digest"]
        ):
            _fail(
                "Policy check facts base differs from selected source",
                "/facts_base_run",
            )
        return
    operation = document["operation"]
    _unique(document["normalizers"], "id", "/normalizers")
    refs = [
        document[key]
        for key in ["raw_run", "final_run", "facts_base_run"]
        if document[key] is not None
    ]
    if len({ref["source_digest"] for ref in refs}) > 1:
        _fail("Derived workflow run pins differ in source identity", "/final_run")
    if operation != "collect" and document["normalizers"]:
        _fail("Only collection runs normalizer transforms", "/normalizers")
    for item in document["normalizers"]:
        if item["status"] == "completed":
            if item["run"] is None or not item["fact_artifacts"]:
                _fail(
                    "Completed normalization needs retained typed output pins",
                    "/normalizers",
                )
            if refs and item["run"]["source_digest"] != refs[0]["source_digest"]:
                _fail("Normalizer changed selected source identity", "/normalizers/run")
            expected = {
                "native_analysis": {"analysis_inventory", "observations"},
                "coverage": {"coverage_facts"},
                "sanitizer": {"sanitizer_facts"},
                "gcc_import": {"external_analysis_facts"},
                "external_import": {"external_analysis_facts"},
                "test_import": {"evidence"},
            }[item["kind"]]
            actual = {fact["kind"] for fact in item["fact_artifacts"]}
            optional = (
                {"analysis_metrics"} if item["kind"] == "native_analysis" else set()
            )
            if not (expected <= actual <= expected | optional) or any(
                (fact["id"] is None)
                != (fact["kind"] in {"observations", "analysis_metrics", "evidence"})
                for fact in item["fact_artifacts"]
            ):
                _fail(
                    "Normalizer fact kinds/logical IDs disagree with its family",
                    "/normalizers/fact_artifacts",
                )
            _unique(
                item["fact_artifacts"], "artifact_id", "/normalizers/fact_artifacts"
            )
            _unique(item["fact_artifacts"], "kind", "/normalizers/fact_artifacts")
        elif (
            item["run"] is not None
            or item["fact_artifacts"]
            or item["outcome"] is not None
            or item["usability"] is not None
        ):
            _fail(
                "Unproduced normalization cannot assert child facts/outcomes",
                "/normalizers",
            )
    allowed = {
        "collect": None,
        "assess": "assessment_artifact_id",
        "compare": "comparison_artifact_id",
        "baseline": "baseline_artifact_id",
    }[operation]
    for field in [
        "assessment_artifact_id",
        "comparison_artifact_id",
        "baseline_artifact_id",
    ]:
        if field != allowed and document[field] is not None:
            _fail("Workflow output kind contradicts operation", "/" + field)
    if operation != "compare" and document["upstream_run"] is not None:
        _fail("Only consumer comparison has an upstream run", "/upstream_run")
    if operation != "assess" and (
        document["policy_gate"] is not None or document["facts_base_run"] is not None
    ):
        _fail("Only assessment reports a policy gate/facts base", "/policy_gate")
    if operation == "collect":
        if status in {"failed", "insufficient_evidence"}:
            _fail(
                "Capture uses partial, separate from policy failure/unknown", "/status"
            )
        if status == "completed" and (
            any(
                document[key] is None or document[key]["status"] != "completed"
                for key in ["raw_run", "final_run"]
            )
            or any(item["status"] != "completed" for item in document["normalizers"])
        ):
            _fail(
                "Completed capture contradicts incomplete execution/transforms",
                "/status",
            )
    elif operation == "assess":
        gate = {
            "completed": "passed",
            "failed": "failed",
            "insufficient_evidence": "insufficient_evidence",
        }.get(status)
        if status == "partial":
            _fail(
                "Assessment uses insufficient_evidence, not capture partial", "/status"
            )
        if status in {"completed", "failed"} or (
            status == "insufficient_evidence"
            and document["assessment_artifact_id"] is not None
        ):
            if document["policy_gate"] != gate or any(
                document[key] is None
                for key in [
                    "raw_run",
                    "final_run",
                    "facts_base_run",
                    "assessment_artifact_id",
                ]
            ):
                _fail(
                    "Assessment decision lacks matching gate and lineage pins",
                    "/policy_gate",
                )
        elif document["policy_gate"] is not None:
            _fail("Unproduced assessment cannot assert a policy gate", "/policy_gate")
    else:
        if status in {"failed", "partial"}:
            _fail(
                "Derived metadata operations do not report policy/capture outcomes",
                "/status",
            )
        if status == "completed" and (
            document[allowed] is None
            or document["raw_run"] is None
            or document["final_run"] is None
            or (operation == "compare" and document["upstream_run"] is None)
        ):
            _fail(
                "Completed derived operation lacks its selected artifact/run pins",
                "/final_run",
            )


def semantic(kind: str, document: dict[str, Any]) -> None:
    """Check public data before dispatch or presentation; never run a command."""
    if kind == "collection_request":
        _request(document)
    elif kind == "assessment_lineage":
        from .validation import _fail

        if any(
            document[key]["source_digest"] != document["source_digest"]
            for key in ["facts_base_run", "selected_parent_run"]
        ):
            _fail(
                "Assessment lineage changes the selected source identity",
                "/source_digest",
            )
        if {document["policy_artifact_id"], document["assessment_artifact_id"]} & set(
            document["history_artifact_ids"]
        ):
            _fail(
                "Active policy/assessment cannot also be archived history",
                "/history_artifact_ids",
            )
    else:
        _result(kind, document)


def validate_lineage_bundle(
    flat: list[tuple[str, dict[str, Any]]], manifest: dict[str, Any]
) -> None:
    """Bind lineage roles; runtime separately verifies the reopened facts base."""
    from .validation import _fail

    rows = [row for kind, row in flat if kind == "assessment_lineage"]
    if len(rows) > 1:
        _fail("Only one active assessment lineage is allowed", "/assessment_lineage")
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    for row in rows:
        if any(
            row[key]["run_id"] == manifest["run_id"]
            for key in ["facts_base_run", "selected_parent_run"]
        ):
            _fail(
                "Derived assessment lineage cannot select itself as an ancestor",
                "/assessment_lineage",
            )
        if any(
            sum(
                artifact.get("contract", {}).get("kind") == kind
                for artifact in artifacts.values()
            )
            != 1
            for kind in ["policy", "assessment"]
        ):
            _fail(
                "Assessment lineage requires exactly one active policy and assessment",
                "/assessment_lineage",
            )
        for role, reference in [
            ("base_manifest_artifact_id", "facts_base_run"),
            ("parent_manifest_artifact_id", "selected_parent_run"),
        ]:
            descriptor = artifacts.get(row[role])
            if (
                descriptor is None
                or descriptor["sha256"] != row[reference]["manifest_sha256"]
                or "contract" in descriptor
            ):
                _fail(
                    "Assessment parent/base manifest role is not its original raw bytes",
                    "/assessment_lineage/" + role,
                )
        for role, kind in [
            ("policy_artifact_id", "policy"),
            ("assessment_artifact_id", "assessment"),
        ]:
            descriptor = artifacts.get(row[role])
            if descriptor is None or descriptor.get("contract") != {
                "kind": kind,
                "version": "2.0.0",
            }:
                _fail(
                    "Assessment lineage active document role has the wrong contract",
                    "/assessment_lineage/" + role,
                )
        for identifier in row["history_artifact_ids"]:
            if identifier not in artifacts or "contract" in artifacts[identifier]:
                _fail(
                    "Prior policy/assessment history must be retained generic bytes",
                    "/assessment_lineage/history_artifact_ids",
                )
