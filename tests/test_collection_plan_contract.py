"""Contracts for explicit collection declarations; no target commands execute."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from cppulse.contracts import load_schema, validate, validate_bundle
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.run_store import RunStore


def digest(value: Any) -> str:
    """Hash a fixture with the public canonical identity projection."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


@pytest.fixture
def plan() -> dict[str, Any]:
    """Declare one selected CMake/build/CTest context with explicit bindings."""
    return {
        "version": "2.0.0",
        "id": "local-cmake",
        "recipe": {
            "version": "2.0.0",
            "id": "cmake-debug",
            "jobs": 2,
            "contexts": ["gcc17"],
            "steps": [
                {
                    "id": "configure",
                    "context_id": "gcc17",
                    "argv": ["cmake", "-S", ".", "-B", "build"],
                    "cwd": ".",
                    "depends_on": [],
                    "inputs": ["CMakeLists.txt"],
                    "outputs": ["build/CMakeCache.txt"],
                    "timeout_seconds": 30,
                },
                {
                    "id": "build",
                    "context_id": "gcc17",
                    "argv": ["cmake", "--build", "build"],
                    "cwd": ".",
                    "depends_on": ["configure"],
                    "inputs": ["build/CMakeCache.txt", "src/main.cpp"],
                    "outputs": ["build/app"],
                    "timeout_seconds": 30,
                },
                {
                    "id": "ctest-version",
                    "context_id": "gcc17",
                    "argv": ["ctest", "--version"],
                    "cwd": ".",
                    "depends_on": [],
                    "inputs": [],
                    "outputs": [],
                    "timeout_seconds": 10,
                },
                {
                    "id": "ctest-inventory",
                    "context_id": "gcc17",
                    "argv": ["ctest", "--show-only=json-v1"],
                    "cwd": "build",
                    "depends_on": ["build"],
                    "inputs": ["build/app"],
                    "outputs": [],
                    "timeout_seconds": 10,
                },
                {
                    "id": "test",
                    "context_id": "gcc17",
                    "argv": ["ctest", "--output-junit", "junit.xml"],
                    "cwd": "build",
                    "depends_on": ["ctest-version", "ctest-inventory"],
                    "inputs": ["build/app"],
                    "outputs": [
                        "build/junit.xml",
                        "build/Testing/Temporary/LastTest.log",
                    ],
                    "timeout_seconds": 30,
                    "environment": {"LC_ALL": "C"},
                },
            ],
        },
        "bindings": [
            {
                "id": "build-evidence",
                "step_id": "build",
                "kind": "build",
                "scope_files": ["src/main.cpp"],
                "report_path": None,
                "execution_log_path": None,
                "adapter": None,
                "adapter_version": None,
                "inventory_step_id": None,
                "producer_version_step_id": None,
                "exercised_inputs": ["build/app"],
            },
            {
                "id": "tests-evidence",
                "step_id": "test",
                "kind": "tests",
                "scope_files": ["src/main.cpp"],
                "report_path": "build/junit.xml",
                "execution_log_path": "build/Testing/Temporary/LastTest.log",
                "adapter": "ctest-junit",
                "adapter_version": "1.0.0",
                "inventory_step_id": "ctest-inventory",
                "producer_version_step_id": "ctest-version",
                "exercised_inputs": ["build/app"],
            },
        ],
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 67108864,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 1,
        },
    }


@pytest.fixture
def manifest(plan: dict[str, Any]) -> dict[str, Any]:
    """Supply source and context objects separately from the portable plan."""
    source_projection = {
        "kind": "application",
        "files": [
            {"path": path, "sha256": "a" * 64, "size_bytes": 10}
            for path in ["CMakeLists.txt", "src/main.cpp"]
        ],
        "inventory_complete": True,
    }
    context_projection = {
        "compiler": {"name": "gcc", "version": "14"},
        "argv": ["g++", "-std=c++17"],
        "working_directory": "/selected/workspace",
        "language_standard": "c++17",
        "target": "x86_64-linux-gnu",
        "provenance": "observed",
        "dependencies": [],
    }
    return {
        "version": "2.0.0",
        "run_id": "run-collection",
        "status": "completed",
        "source": {
            "version": "2.0.0",
            "digest": digest(source_projection),
            **source_projection,
            "limitations": [],
        },
        "contexts": [
            {
                "version": "2.0.0",
                "id": "gcc17",
                "digest": digest(context_projection),
                **context_projection,
                "limitations": [],
            }
        ],
        "stages": [],
        "artifacts": [],
        "started_at": "2026-11-13T10:00:00Z",
        "finished_at": "2026-11-13T10:00:00Z",
        "config_digest": digest(plan),
        "versions": {"cppulse": "0.2.0.dev0"},
        "limitations": [],
    }


def test_collection_plan_is_a_local_strict_draft_seven_contract(
    plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    schema = load_schema("collection_plan")
    jsonschema.Draft7Validator.check_schema(schema)
    validate("collection_plan", plan)
    validate_bundle({"run_manifest": manifest, "collection_plan": plan})
    validate_bundle({"run_manifest": manifest, "collection_plan": [plan]})


def test_loading_collection_plan_schema_does_not_share_mutable_state() -> None:
    schema = load_schema("collection_plan")
    schema["properties"].clear()
    assert "bindings" in load_schema("collection_plan")["properties"]


@pytest.mark.parametrize("version", ["1.0.0", "2.1.0", "3.0.0"])
def test_unknown_collection_versions_are_actionable(
    plan: dict[str, Any], version: str
) -> None:
    plan["version"] = version
    with pytest.raises(UnsupportedVersion):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "change",
    [
        "top",
        "binding",
        "limits",
        "recipe",
        "step",
        "source_in_plan",
        "contexts_in_plan",
    ],
)
def test_unknown_collection_options_are_rejected(
    plan: dict[str, Any], change: str
) -> None:
    targets = {
        "top": plan,
        "binding": plan["bindings"][0],
        "limits": plan["limits"],
        "recipe": plan["recipe"],
        "step": plan["recipe"]["steps"][0],
        "source_in_plan": plan,
        "contexts_in_plan": plan,
    }
    key = {"source_in_plan": "source", "contexts_in_plan": "contexts"}.get(
        change, "unknown"
    )
    targets[change][key] = "unsupported"
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "field",
    [
        "max_log_bytes",
        "max_artifact_bytes",
        "max_metadata_bytes",
        "termination_grace_seconds",
    ],
)
@pytest.mark.parametrize("value", [0, -1, True, None])
def test_recorded_collection_limits_must_be_real_positive_bounds(
    plan: dict[str, Any], field: str, value: Any
) -> None:
    plan["limits"][field] = value
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


def test_initial_collection_job_and_log_caps_do_not_change_plain_recipes(
    plan: dict[str, Any]
) -> None:
    plan["recipe"]["jobs"] = 33
    validate("recipe", plan["recipe"])
    with pytest.raises(ContractError):
        validate("collection_plan", plan)
    plan["recipe"]["jobs"] = 32
    plan["limits"]["max_log_bytes"] = 67108864
    validate("collection_plan", plan)
    plan["limits"]["max_log_bytes"] += 1
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


def test_artifact_cap_is_required_and_bounded(plan: dict[str, Any]) -> None:
    del plan["limits"]["max_artifact_bytes"]
    with pytest.raises(ContractError):
        validate("collection_plan", plan)
    plan["limits"]["max_artifact_bytes"] = 268435456
    validate("collection_plan", plan)
    plan["limits"]["max_artifact_bytes"] += 1
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


def test_metadata_cap_is_required_and_separate_from_binary_snapshots(
    plan: dict[str, Any]
) -> None:
    del plan["limits"]["max_metadata_bytes"]
    with pytest.raises(ContractError):
        validate("collection_plan", plan)
    plan["limits"]["max_metadata_bytes"] = 67108864
    plan["limits"]["max_artifact_bytes"] = 1024
    validate("collection_plan", plan)
    plan["limits"]["max_metadata_bytes"] += 1
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


def test_integer_valued_json_numbers_validate_without_rewriting_the_plan(
    plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    for name in ["max_log_bytes", "max_artifact_bytes", "max_metadata_bytes"]:
        plan["limits"][name] = float(plan["limits"][name])
    original = deepcopy(plan)
    manifest["config_digest"] = digest(plan)
    validate_bundle({"run_manifest": manifest, "collection_plan": plan})
    assert plan == original
    assert all(
        isinstance(plan["limits"][name], float)
        for name in ["max_log_bytes", "max_artifact_bytes", "max_metadata_bytes"]
    )


@pytest.mark.parametrize(
    "change", ["missing", "null", "unsafe", "undeclared", "report_alias", "build_log"]
)
def test_actual_execution_log_is_a_distinct_declared_test_output(
    plan: dict[str, Any], change: str
) -> None:
    build, tests = plan["bindings"]
    if change == "missing":
        del tests["execution_log_path"]
    elif change == "null":
        tests["execution_log_path"] = None
    elif change == "unsafe":
        tests["execution_log_path"] = "../LastTest.log"
    elif change == "undeclared":
        tests["execution_log_path"] = "build/not-declared.log"
    elif change == "report_alias":
        tests["execution_log_path"] = tests["report_path"]
    else:
        build["execution_log_path"] = "build/Testing/Temporary/LastTest.log"
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "../outside",
        "src/../outside",
        "./alias",
        "a//alias",
        "C:/outside",
        "C:\\outside",
        "a\\b",
        "a\x00b",
        "a\nb",
        "a\x7fb",
        "a\x85b",
        "build/NUL",
        "build/con.txt",
        "build/COM1.exe",
        "build/file.",
        "build/file ",
        "build/a:b",
        "build/a?b",
        "build/a*b",
        ".",
    ],
)
def test_plan_output_paths_are_portable_canonical_file_identities(
    plan: dict[str, Any], path: str
) -> None:
    plan["recipe"]["steps"][0]["outputs"] = [path]
    with pytest.raises(ContractError) as error:
        validate("collection_plan", plan)
    assert error.value.code == "UNSAFE_PATH"


def test_spaces_and_unicode_in_canonical_paths_are_data(plan: dict[str, Any]) -> None:
    step = plan["recipe"]["steps"][0]
    step["cwd"] = "folder with spaces/é"
    step["argv"] = ["tool", "argument with spaces", "$(not executed)"]
    validate("collection_plan", plan)


@pytest.mark.parametrize("field", ["scope_files", "exercised_inputs"])
def test_binding_paths_are_checked_independently(
    plan: dict[str, Any], field: str
) -> None:
    plan["bindings"][0][field] = ["../outside"]
    with pytest.raises(ContractError) as error:
        validate("collection_plan", plan)
    assert error.value.code == "UNSAFE_PATH"


@pytest.mark.parametrize(
    "change", ["duplicate_step", "missing_dep", "cycle", "context"]
)
def test_embedded_recipe_graph_and_context_rules_are_not_bypassed(
    plan: dict[str, Any], change: str
) -> None:
    steps = plan["recipe"]["steps"]
    if change == "duplicate_step":
        steps.append(deepcopy(steps[0]))
    elif change == "missing_dep":
        steps[0]["depends_on"] = ["absent"]
    elif change == "cycle":
        steps[0]["depends_on"] = ["test"]
    else:
        steps[0]["context_id"] = "absent"
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize("change", ["duplicate_id", "duplicate_kind", "missing_step"])
def test_binding_identity_and_step_references_are_unambiguous(
    plan: dict[str, Any], change: str
) -> None:
    if change == "missing_step":
        plan["bindings"][0]["step_id"] = "absent"
    else:
        extra = deepcopy(plan["bindings"][0])
        if change == "duplicate_kind":
            extra["id"] = "different-id"
        plan["bindings"].append(extra)
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "change",
    [
        "empty_artifacts",
        "empty_scope",
        "wrong_build_output",
        "wrong_test_input",
        "wrong_report",
        "build_adapter",
        "tests_null_adapter",
        "unknown_adapter",
        "unknown_adapter_version",
    ],
)
def test_evidence_bindings_are_explicit_and_versioned(
    plan: dict[str, Any], change: str
) -> None:
    build, tests = plan["bindings"]
    if change == "empty_artifacts":
        build["exercised_inputs"] = []
    elif change == "empty_scope":
        build["scope_files"] = []
    elif change == "wrong_build_output":
        build["exercised_inputs"] = ["build/not-produced"]
    elif change == "wrong_test_input":
        tests["exercised_inputs"] = ["build/not-consumed"]
    elif change == "wrong_report":
        tests["report_path"] = "build/not-produced.xml"
    elif change == "build_adapter":
        build["adapter"] = "ctest-junit"
        build["adapter_version"] = "1.0.0"
    elif change == "tests_null_adapter":
        tests["adapter"] = None
    elif change == "unknown_adapter":
        tests["adapter"] = "generic-junit"
    else:
        tests["adapter_version"] = "2.0.0"
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "case_alias",
        "ancestor",
        "cwd_collision",
        "git_metadata",
        "self_input",
        "unordered_generated_input",
    ],
)
def test_outputs_cannot_alias_each_other_or_have_unordered_provenance(
    plan: dict[str, Any], change: str
) -> None:
    configure, build, _, _, tests = plan["recipe"]["steps"]
    if change == "duplicate":
        configure["outputs"].append("build/app")
    elif change == "case_alias":
        configure["outputs"].append("BUILD/App")
    elif change == "ancestor":
        configure["outputs"].append("build/app/subfile")
    elif change == "cwd_collision":
        configure["outputs"].append("build")
    elif change == "git_metadata":
        configure["outputs"].append(".git/config")
    elif change == "self_input":
        build["inputs"].append("build/app")
    else:
        tests["depends_on"] = ["configure"]
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "change",
    [
        "build_inventory",
        "null_inventory",
        "null_version",
        "missing_inventory",
        "missing_version",
        "nonancestor_inventory",
        "nonancestor_version",
        "different_version_context",
        "same_proof_step",
        "inventory_omits_artifact",
    ],
)
def test_test_artifact_proof_steps_are_explicit_and_context_bound(
    plan: dict[str, Any], change: str
) -> None:
    build, tests = plan["bindings"]
    steps = {step["id"]: step for step in plan["recipe"]["steps"]}
    if change == "build_inventory":
        build["inventory_step_id"] = "ctest-inventory"
    elif change == "null_inventory":
        tests["inventory_step_id"] = None
    elif change == "null_version":
        tests["producer_version_step_id"] = None
    elif change == "missing_inventory":
        tests["inventory_step_id"] = "absent"
    elif change == "missing_version":
        tests["producer_version_step_id"] = "absent"
    elif change == "nonancestor_inventory":
        steps["test"]["depends_on"] = ["build", "ctest-version"]
    elif change == "nonancestor_version":
        steps["test"]["depends_on"] = ["ctest-inventory"]
    elif change == "different_version_context":
        steps["ctest-version"]["context_id"] = "clang17"
        plan["recipe"]["contexts"].append("clang17")
    elif change == "same_proof_step":
        tests["producer_version_step_id"] = tests["inventory_step_id"]
    else:
        steps["ctest-inventory"]["inputs"] = []
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "change",
    [
        "scope",
        "input",
        "output_source",
        "output_source_directory",
        "context",
        "config_digest",
        "changed_limit",
        "changed_artifact_limit",
        "changed_metadata_limit",
    ],
)
def test_bundle_resolves_selected_subject_context_and_actual_plan_digest(
    plan: dict[str, Any], manifest: dict[str, Any], change: str
) -> None:
    if change == "scope":
        plan["bindings"][0]["scope_files"] = ["not-selected.cpp"]
    elif change == "input":
        plan["recipe"]["steps"][0]["inputs"] = ["not-selected.txt"]
    elif change == "output_source":
        plan["recipe"]["steps"][0]["outputs"].append("src/main.cpp")
    elif change == "output_source_directory":
        plan["recipe"]["steps"][0]["outputs"].append("src")
    elif change == "context":
        manifest["contexts"] = []
    elif change == "config_digest":
        manifest["config_digest"] = "b" * 64
    elif change == "changed_limit":
        plan["limits"]["max_log_bytes"] *= 2
    elif change == "changed_artifact_limit":
        plan["limits"]["max_artifact_bytes"] *= 2
    else:
        plan["limits"]["max_metadata_bytes"] *= 2
    if change not in {
        "config_digest",
        "changed_limit",
        "changed_artifact_limit",
        "changed_metadata_limit",
    }:
        manifest["config_digest"] = digest(plan)
    with pytest.raises(ContractError):
        validate_bundle({"run_manifest": manifest, "collection_plan": plan})


@pytest.mark.parametrize(
    "change", ["argv_nul", "environment_key", "environment_nul", "unused_context"]
)
def test_invalid_process_options_are_rejected_without_execution(
    plan: dict[str, Any], change: str
) -> None:
    step = plan["recipe"]["steps"][0]
    if change == "argv_nul":
        step["argv"].append("invalid\x00argument")
    elif change == "environment_key":
        step["environment"] = {"INVALID=KEY": "value"}
    elif change == "environment_nul":
        step["environment"] = {"NAME": "invalid\x00value"}
    else:
        plan["recipe"]["contexts"].append("unused")
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


@pytest.mark.parametrize(
    "name",
    [
        "GITHUB_TOKEN",
        "password",
        "AWS_SECRET_ACCESS_KEY",
        "API_KEY",
        "api-key",
        "apikey",
        "PASSWD",
    ],
)
def test_sensitive_environment_names_are_not_persisted(
    plan: dict[str, Any], name: str
) -> None:
    plan["recipe"]["steps"][0]["environment"] = {name: "redacted-fixture-value"}
    with pytest.raises(ContractError) as error:
        validate("collection_plan", plan)
    assert error.value.code == "SENSITIVE_ENVIRONMENT"
    assert "redacted-fixture-value" not in str(error.value)


@pytest.mark.parametrize("name", ["", "invalid\x00name", 3])
def test_environment_keys_fail_with_structured_errors(
    plan: dict[str, Any], name: Any
) -> None:
    plan["recipe"]["steps"][0]["environment"] = {name: "value"}
    with pytest.raises(ContractError):
        validate("collection_plan", plan)


def another_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Give an independent second plan unambiguous output and binding identities."""
    second = deepcopy(plan)
    second["id"] = "second-plan"
    second["recipe"]["id"] = "second-recipe"
    for step in second["recipe"]["steps"]:
        for key in ["inputs", "outputs"]:
            step[key] = [path.replace("build/", "other/") for path in step[key]]
        if step["cwd"] == "build":
            step["cwd"] = "other"
    for binding in second["bindings"]:
        binding["id"] = "other-" + binding["id"]
        binding["exercised_inputs"] = [
            path.replace("build/", "other/") for path in binding["exercised_inputs"]
        ]
        if binding["report_path"]:
            binding["report_path"] = binding["report_path"].replace("build/", "other/")
        if binding["execution_log_path"]:
            binding["execution_log_path"] = binding["execution_log_path"].replace(
                "build/", "other/"
            )
    return second


def test_multiple_plan_bundle_is_order_independent_and_keeps_steps_local(
    plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    second = another_plan(plan)
    projection = {
        "collection_plans": sorted([plan, second], key=lambda item: item["id"])
    }
    manifest["config_digest"] = digest(projection)
    validate_bundle({"run_manifest": manifest, "collection_plan": [plan, second]})
    validate_bundle({"run_manifest": manifest, "collection_plan": [second, plan]})


def test_generated_artifact_cannot_be_relabeled_as_a_different_context(
    plan: dict[str, Any]
) -> None:
    plan["recipe"]["contexts"].append("clang17")
    plan["recipe"]["steps"][4]["context_id"] = "clang17"
    with pytest.raises(ContractError) as error:
        validate("collection_plan", plan)
    assert error.value.code == "SUBJECT_MISMATCH"


def test_independent_context_dags_can_share_selected_source_inputs(
    plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    other = another_plan(plan)
    for step in other["recipe"]["steps"]:
        step["id"] = "clang-" + step["id"]
        step["depends_on"] = ["clang-" + value for value in step["depends_on"]]
        step["context_id"] = "clang17"
    for binding in other["bindings"]:
        binding["step_id"] = "clang-" + binding["step_id"]
        for key in ["inventory_step_id", "producer_version_step_id"]:
            if binding[key] is not None:
                binding[key] = "clang-" + binding[key]
    plan["recipe"]["contexts"].append("clang17")
    plan["recipe"]["steps"].extend(other["recipe"]["steps"])
    plan["bindings"].extend(other["bindings"])
    context = deepcopy(manifest["contexts"][0])
    context["id"] = "clang17"
    context["compiler"] = {"name": "clang", "version": "19"}
    context["argv"] = ["clang++", "-std=c++17"]
    context["digest"] = digest(
        {
            key: value
            for key, value in context.items()
            if key not in {"id", "digest", "version", "limitations"}
        }
    )
    manifest["contexts"].append(context)
    manifest["config_digest"] = digest(plan)
    validate_bundle({"run_manifest": manifest, "collection_plan": plan})


@pytest.mark.parametrize(
    "change", ["plan_id", "recipe_id", "binding_id", "output", "standalone_recipe"]
)
def test_multiple_plan_bundle_rejects_ambiguous_global_identities(
    plan: dict[str, Any], manifest: dict[str, Any], change: str
) -> None:
    second = another_plan(plan)
    if change == "plan_id":
        second["id"] = plan["id"]
    elif change == "recipe_id":
        second["recipe"]["id"] = plan["recipe"]["id"]
    elif change == "binding_id":
        second["bindings"][0]["id"] = plan["bindings"][0]["id"]
    elif change == "output":
        second["recipe"]["steps"][0]["outputs"].append("build/app")
    manifest["config_digest"] = digest(
        {"collection_plans": sorted([plan, second], key=lambda item: item["id"])}
    )
    bundle = {"run_manifest": manifest, "collection_plan": [plan, second]}
    if change == "standalone_recipe":
        bundle["recipe"] = plan["recipe"]
    with pytest.raises(ContractError):
        validate_bundle(bundle)


def test_empty_plan_list_is_not_an_effective_collection(
    manifest: dict[str, Any]
) -> None:
    with pytest.raises(ContractError):
        validate_bundle({"run_manifest": manifest, "collection_plan": []})


@pytest.mark.parametrize("multiple", [False, True])
def test_run_store_retains_typed_plan_artifacts_with_the_same_bundle_rules(
    plan: dict[str, Any], manifest: dict[str, Any], tmp_path: Path, multiple: bool
) -> None:
    plans = [plan, another_plan(plan)] if multiple else [plan]
    projection = (
        {"collection_plans": sorted(plans, key=lambda item: item["id"])}
        if multiple
        else plan
    )
    manifest["config_digest"] = digest(projection)
    store = RunStore(tmp_path / "store")
    with store.begin(manifest["run_id"]) as staged:
        for index, document in enumerate(plans):
            staged.write_json(
                f"plans/{index}.json",
                document,
                contract="collection_plan",
                artifact_id=f"plan-{index}",
            )
        manifest["artifacts"] = staged.artifacts
        snapshot = staged.publish(manifest)
    assert snapshot.manifest["input_verification"] == "unverified"
    for index, document in enumerate(plans):
        assert (
            snapshot.read_json(f"plans/{index}.json", contract="collection_plan")
            == document
        )


def bound_build_facts(manifest: dict[str, Any]) -> dict[str, Any]:
    """Make synthetic observed facts to check reference agreement, not execution."""
    manifest["artifacts"] = [
        {
            "id": "build-output",
            "path": "artifacts/app",
            "sha256": "a" * 64,
            "size_bytes": 10,
            "media_type": "application/octet-stream",
        }
    ]
    receipt = {
        "version": "2.0.0",
        "id": "executed-build",
        "source_digest": manifest["source"]["digest"],
        "context_id": "gcc17",
        "producer": {"name": "cmake", "version": "3.25.1"},
        "argv": ["cmake", "--build", "build"],
        "cwd": "/selected/workspace",
        "status": "passed",
        "reason": "",
        "exit_code": 0,
        "signal": None,
        "started_at": manifest["started_at"],
        "finished_at": manifest["finished_at"],
        "artifact_ids": ["build-output"],
        "log_artifact_ids": [],
        "depends_on": [],
    }
    evidence = {
        "version": "2.0.0",
        "source_digest": manifest["source"]["digest"],
        "records": [
            {
                "id": "build-evidence",
                "context_id": "gcc17",
                "producer": {"name": "cppulse-collector", "version": "0.2.0.dev0"},
                "origin": "execution",
                "kind": "build",
                "status": "passed",
                "usability": "usable",
                "artifact_ids": ["build-output"],
                "receipt_id": "executed-build",
                "scope": {"files": ["src/main.cpp"]},
                "limitations": [],
            }
        ],
    }
    return {"execution_receipt": receipt, "evidence": evidence}


def test_existing_evidence_matches_its_declared_collection_binding(
    plan: dict[str, Any], manifest: dict[str, Any]
) -> None:
    facts = bound_build_facts(manifest)
    validate_bundle({"run_manifest": manifest, "collection_plan": plan, **facts})


@pytest.mark.parametrize("change", ["kind", "context", "scope", "origin"])
def test_unrelated_evidence_cannot_occupy_a_collection_binding_id(
    plan: dict[str, Any], manifest: dict[str, Any], change: str
) -> None:
    facts = bound_build_facts(manifest)
    record = facts["evidence"]["records"][0]
    if change == "kind":
        record["kind"] = "review"
    elif change == "context":
        other = deepcopy(manifest["contexts"][0])
        other["id"] = "other-context"
        manifest["contexts"].append(other)
        record["context_id"] = "other-context"
    elif change == "scope":
        record["scope"]["files"] = ["CMakeLists.txt"]
    else:
        record["origin"] = "import"
        record["receipt_id"] = None
    with pytest.raises(ContractError) as error:
        validate_bundle({"run_manifest": manifest, "collection_plan": plan, **facts})
    assert error.value.code == "SUBJECT_MISMATCH"
