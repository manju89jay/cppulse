"""Public workflow declarations are finite data and never execute commands."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from verification_fixtures import coverage_execution_bundle


def role(step_id, direction, path=None):
    return {"step_id": step_id, "role": direction, "path": path}


def request_document():
    data = coverage_execution_bundle()
    plan = deepcopy(data["collection_plan"])
    steps = plan["recipe"]["steps"]
    template = {
        "context_id": "gcc17",
        "argv": ["/synthetic/tool"],
        "cwd": ".",
        "depends_on": [],
        "inputs": [],
        "outputs": [],
        "timeout_seconds": 10,
    }
    for name in [
        "compiler-version",
        "gcov-version",
        "reporter-version",
        "nm-version",
        "readelf-version",
    ]:
        steps.append({**deepcopy(template), "id": name})
    for name, inputs, outputs, parents in [
        ("nm-object", ["build/main.o"], [], ["compile"]),
        ("elf-object", ["build/main.o"], [], ["compile"]),
        ("elf-binary", ["build/app"], [], ["link"]),
        (
            "native",
            ["src/main.cpp", "registry.json", "config.json"],
            ["native/findings.json"],
            [],
        ),
    ]:
        steps.append(
            {
                **deepcopy(template),
                "id": name,
                "inputs": inputs,
                "outputs": outputs,
                "depends_on": parents,
            }
        )
    next(row for row in steps if row["id"] == "report")["inputs"] += [
        "config.json",
        "gcov",
    ]
    return {
        "version": "2.0.0",
        "id": "public-demo",
        "source": {
            "kind": "application",
            "files": ["src/main.cpp", "registry.json", "config.json", "gcov"],
            "inventory_complete": False,
            "limitations": ["Synthetic finite declaration, no tool was executed."],
        },
        "contexts": deepcopy(data["run_manifest"]["contexts"]),
        "plan": plan,
        "normalizers": [],
    }


def normalizer(kind):
    common = {"id": "normalize-" + kind, "kind": kind, "normalizer_version": "1.0.0"}
    if kind == "native_analysis":
        return {
            **common,
            "step_id": "native",
            "report": role("native", "output", "native/findings.json"),
            "registry": role("native", "input", "registry.json"),
            "config": role("native", "input", "config.json"),
            "compilation_database": None,
            "resource_manifest": None,
            "requested_files": ["src/main.cpp"],
            "requested_rules": ["CPP-MEM-001"],
        }
    if kind == "coverage":
        return {
            **common,
            "step_id": "report",
            "adapter": "lcov",
            "report": role("report", "output", "coverage.info"),
            "producer_version_step_id": "reporter-version",
            "gcov_version_step_id": "gcov-version",
            "compiler_version_step_id": "compiler-version",
            "configuration": role("report", "input", "config.json"),
            "gcov": role("report", "input", "gcov"),
            "proof_step_ids": [
                "compile",
                "link",
                "test",
                "report",
                "compiler-version",
                "gcov-version",
                "reporter-version",
                "ctest-version",
                "ctest-inventory",
            ],
            "test_binding_ids": ["test-evidence"],
            "instrumentation": [
                {
                    "object": role("compile", "output", "build/main.o"),
                    "mapping": role("compile", "output", "build/main.gcno"),
                    "source_files": ["src/main.cpp"],
                }
            ],
            "profiles": [
                {
                    "profile": role("test", "output", "build/main.gcda"),
                    "binary": role("link", "output", "build/app"),
                    "test_step_id": "test",
                }
            ],
        }
    if kind == "sanitizer":
        return {
            **common,
            "sanitizer": "asan",
            "requested_files": ["src/main.cpp"],
            "compiler_version_step_id": "compiler-version",
            "nm_version_step_id": "nm-version",
            "readelf_version_step_id": "readelf-version",
            "objects": [
                {
                    "compile_step_id": "compile",
                    "nm_step_id": "nm-object",
                    "elf_step_id": "elf-object",
                }
            ],
            "link_step_id": "link",
            "runtime_inspection_step_id": "elf-binary",
            "test_binding_id": "test-evidence",
        }
    return {
        **common,
        "report": role("native", "stderr"),
        "context_id": "gcc17",
        "source_root": "/synthetic/original",
        "scope_files": ["src/main.cpp"],
        "producer": {"name": "GNU-G++", "version": "14.2.0"},
    }


@pytest.mark.parametrize(
    "kind", ["native_analysis", "coverage", "sanitizer", "gcc_import"]
)
def test_public_request_supports_each_explicit_accepted_normalizer(kind):
    request = request_document()
    request["normalizers"] = [normalizer(kind)]
    validate("collection_request", request)


def test_raw_collection_and_mixed_finite_normalizers_are_valid_data():
    request = request_document()
    validate("collection_request", request)
    request["normalizers"] = [
        normalizer(kind)
        for kind in ["native_analysis", "coverage", "sanitizer", "gcc_import"]
    ]
    validate("collection_request", request)


def test_request_validation_does_not_execute_declared_commands(monkeypatch):
    import subprocess

    request = request_document()
    request["normalizers"] = [
        normalizer(kind)
        for kind in ["native_analysis", "coverage", "sanitizer", "gcc_import"]
    ]

    def forbidden(*args, **kwargs):
        raise AssertionError("Request validation must not execute target commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    validate("collection_request", request)


def test_gcc_import_scope_order_does_not_hide_duplicate_semantic_selection():
    request = request_document()
    first = normalizer("gcc_import")
    first["scope_files"] = ["src/main.cpp", "config.json"]
    second = deepcopy(first)
    second.update(id="second-import", scope_files=list(reversed(first["scope_files"])))
    request["normalizers"] = [first, second]
    with pytest.raises(ContractError):
        validate("collection_request", request)


@pytest.mark.parametrize("field", ["instrumentation", "profiles"])
def test_coverage_duplicate_material_roles_are_rejected_before_execution(field):
    request = request_document()
    item = normalizer("coverage")
    item[field].append(deepcopy(item[field][0]))
    request["normalizers"] = [item]
    with pytest.raises(ContractError):
        validate("collection_request", request)


@pytest.mark.parametrize(
    "direction,path",
    [
        ("input", "registry.json"),
        ("output", "native/findings.json"),
        ("stdout", None),
        ("stderr", None),
    ],
)
def test_gcc_import_retains_import_origin_from_any_explicit_captured_role(
    direction, path
):
    request = request_document()
    item = normalizer("gcc_import")
    item["report"] = role("native", direction, path)
    request["normalizers"] = [item]
    validate("collection_request", request)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_kind",
        "unknown_version",
        "success_label",
        "arbitrary_module",
        "missing_step",
        "wrong_direction",
        "wrong_path",
        "log_path",
        "wrong_context",
        "unknown_rule",
        "unselected_file",
        "duplicate_id",
        "duplicate_native",
        "duplicate_coverage",
        "duplicate_gcc",
        "missing_test_binding",
        "wrong_profile_step",
        "wrong_compile_pair",
        "wrong_probe",
        "source_overlap",
        "unselected_input",
        "invalid_context_digest",
    ],
)
def test_request_rejects_bad_shapes_and_static_references_before_execution(mutation):
    request = request_document()
    item = normalizer("native_analysis")
    request["normalizers"] = [item]
    if mutation == "unknown_kind":
        item["kind"] = "run_python_module"
    elif mutation == "unknown_version":
        item["normalizer_version"] = "9.0.0"
    elif mutation == "success_label":
        item["passed"] = True
    elif mutation == "arbitrary_module":
        item["module"] = "arbitrary.plugin"
    elif mutation == "missing_step":
        item["report"]["step_id"] = "absent"
    elif mutation == "wrong_direction":
        item["report"] = role("native", "input", "registry.json")
    elif mutation == "wrong_path":
        item["config"]["path"] = "undeclared.json"
    elif mutation == "log_path":
        request["normalizers"] = [normalizer("gcc_import")]
        request["normalizers"][0]["report"]["path"] = "not-null"
    elif mutation == "wrong_context":
        request["normalizers"] = [normalizer("gcc_import")]
        request["normalizers"][0]["context_id"] = "absent"
    elif mutation == "unknown_rule":
        item["requested_rules"] = ["CPP-MEM-999"]
    elif mutation == "unselected_file":
        item["requested_files"] = ["other.cpp"]
    elif mutation.startswith("duplicate"):
        if mutation == "duplicate_coverage":
            item = normalizer("coverage")
        elif mutation == "duplicate_gcc":
            item = normalizer("gcc_import")
        request["normalizers"] = [item, deepcopy(item)]
        if mutation != "duplicate_id":
            request["normalizers"][1]["id"] = "different-id"
    elif mutation == "missing_test_binding":
        request["normalizers"] = [normalizer("sanitizer")]
        request["normalizers"][0]["test_binding_id"] = "absent"
    elif mutation == "wrong_profile_step":
        request["normalizers"] = [normalizer("coverage")]
        request["normalizers"][0]["profiles"][0]["test_step_id"] = "link"
    elif mutation == "wrong_compile_pair":
        request["normalizers"] = [normalizer("coverage")]
        request["normalizers"][0]["instrumentation"][0]["mapping"] = role(
            "link", "output", "build/app"
        )
    elif mutation == "wrong_probe":
        request["normalizers"] = [normalizer("sanitizer")]
        request["normalizers"][0]["nm_version_step_id"] = "absent"
    elif mutation == "source_overlap":
        request["source"]["files"].append("build/app")
    elif mutation == "unselected_input":
        request["source"]["files"].remove("registry.json")
    else:
        request["contexts"][0]["digest"] = "f" * 64
    with pytest.raises(ContractError):
        validate("collection_request", request)


def run_ref(status="completed", source="a" * 64):
    return {
        "run_id": "synthetic-run",
        "manifest_sha256": "b" * 64,
        "status": status,
        "source_digest": source,
    }


def workflow_document(operation="collect"):
    return {
        "version": "2.0.0",
        "operation": operation,
        "store": "/synthetic/store",
        "status": "completed",
        "exit_code": 0,
        "reason": "Synthetic workflow outcome, not an execution claim.",
        "raw_run": run_ref(),
        "final_run": run_ref(),
        "facts_base_run": run_ref() if operation == "assess" else None,
        "upstream_run": None,
        "assessment_artifact_id": None,
        "comparison_artifact_id": None,
        "baseline_artifact_id": None,
        "policy_gate": None,
        "normalizers": [],
        "error": None,
    }


def test_capture_completion_is_not_a_test_or_sanitizer_policy_pass():
    document = workflow_document()
    document["normalizers"] = [
        {
            "id": "san",
            "kind": "sanitizer",
            "status": "completed",
            "outcome": "failed",
            "usability": "usable",
            "fact_artifacts": [
                {"kind": "sanitizer_facts", "artifact_id": "san-facts", "id": "san"}
            ],
            "run": run_ref(),
            "reason": "Captured actual diagnostic, policy remains separate.",
        }
    ]
    validate("workflow_result", document)
    document["normalizers"][0]["fact_artifacts"][0]["kind"] = "coverage_facts"
    with pytest.raises(ContractError):
        validate("workflow_result", document)


@pytest.mark.parametrize("operation", ["assess", "compare", "baseline"])
def test_valid_mutating_workflows_pin_their_own_output_kind(operation):
    document = workflow_document(operation)
    if operation == "assess":
        document.update(assessment_artifact_id="assessment", policy_gate="passed")
    elif operation == "compare":
        document.update(
            comparison_artifact_id="comparison", upstream_run=run_ref(source="c" * 64)
        )
    else:
        document["baseline_artifact_id"] = "baseline"
    validate("workflow_result", document)


@pytest.mark.parametrize(
    "status,gate,code",
    [("failed", "failed", 1), ("insufficient_evidence", "insufficient_evidence", 3)],
)
def test_assessment_gate_failure_and_unknown_are_not_capture_statuses(
    status, gate, code
):
    document = workflow_document("assess")
    document.update(
        status=status,
        exit_code=code,
        policy_gate=gate,
        assessment_artifact_id="assessment",
    )
    validate("workflow_result", document)


def test_comparison_incompatibility_does_not_become_a_policy_failure_exit():
    document = workflow_document("compare")
    document.update(
        status="failed",
        exit_code=1,
        comparison_artifact_id="comparison",
        upstream_run=run_ref(source="c" * 64),
    )
    with pytest.raises(ContractError):
        validate("workflow_result", document)


@pytest.mark.parametrize(
    "status,code", [("partial", 3), ("invalid", 2), ("cancelled", 130)]
)
def test_collect_non_success_results_preserve_known_pins(status, code):
    document = workflow_document()
    document.update(status=status, exit_code=code)
    if status == "partial":
        document["final_run"] = run_ref("partial")
    if status == "invalid":
        document["error"] = {
            "code": "INVALID_CONTRACT",
            "message": "Explicit invalid request.",
            "path": "/plan",
        }
    validate("workflow_result", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "exit",
        "capture_policy",
        "source_mismatch",
        "partial_as_success",
        "assess_without_artifact",
        "wrong_output_kind",
        "unknown_success",
        "silent_normalizer_failure",
    ],
)
def test_workflow_results_reject_contradictory_success(mutation):
    document = workflow_document()
    if mutation == "exit":
        document["exit_code"] = 1
    elif mutation == "capture_policy":
        document["policy_gate"] = "passed"
    elif mutation == "source_mismatch":
        document["final_run"]["source_digest"] = "f" * 64
    elif mutation == "partial_as_success":
        document["final_run"]["status"] = "partial"
    elif mutation == "assess_without_artifact":
        document["operation"] = "assess"
        document["policy_gate"] = "passed"
    elif mutation == "wrong_output_kind":
        document["comparison_artifact_id"] = "comparison"
    elif mutation == "unknown_success":
        document["success"] = True
    else:
        document["normalizers"] = [
            {
                "id": "unavailable",
                "kind": "coverage",
                "status": "unavailable",
                "outcome": None,
                "usability": None,
                "fact_artifacts": [],
                "run": None,
                "reason": "No report was captured.",
            }
        ]
    with pytest.raises(ContractError):
        validate("workflow_result", document)


def check_document(mode="policy"):
    return {
        "version": "2.0.0",
        "mode": mode,
        "store": "/synthetic/store",
        "status": "passed",
        "exit_code": 0,
        "reason": "Synthetic selected gate result.",
        "run": run_ref(),
        "facts_base_run": run_ref() if mode == "policy" else None,
        "assessment_artifact_id": "assessment" if mode == "policy" else None,
        "comparison_artifact_id": "finding-comparison" if mode == "findings" else None,
        "policy_sha256": "c" * 64 if mode == "policy" else None,
        "baseline_sha256": "d" * 64 if mode == "findings" else None,
        "error": None,
    }


@pytest.mark.parametrize("mode", ["policy", "findings"])
def test_check_modes_are_distinct_and_pin_the_selected_decision(mode):
    validate("check_result", check_document(mode))


@pytest.mark.parametrize(
    "status,code",
    [("failed", 1), ("insufficient_evidence", 3), ("invalid", 2), ("cancelled", 130)],
)
def test_check_exit_codes_distinguish_known_failure_unknown_and_invalid(status, code):
    document = check_document()
    document.update(status=status, exit_code=code)
    if status == "invalid":
        document["error"] = {
            "code": "INVALID_SELECTOR",
            "message": "Unknown artifact.",
            "path": "/assessment",
        }
    validate("check_result", document)


def test_stale_outputs_mean_recollect_not_invalid_or_known_policy_failure():
    document = check_document()
    document.update(
        status="insufficient_evidence",
        exit_code=3,
        assessment_artifact_id=None,
        error={
            "code": "STALE_OUTPUT",
            "message": "Generated output changed; recollect.",
            "path": "build/app",
        },
    )
    validate("check_result", document)
    document["exit_code"] = 2
    with pytest.raises(ContractError):
        validate("check_result", document)


def test_check_refuses_ambiguous_policy_and_finding_outputs():
    document = check_document()
    document["comparison_artifact_id"] = "finding-comparison"
    document["baseline_sha256"] = "d" * 64
    with pytest.raises(ContractError):
        validate("check_result", document)


def test_check_base_pin_must_preserve_the_selected_source_identity():
    document = check_document()
    document["facts_base_run"]["source_digest"] = "f" * 64
    with pytest.raises(ContractError):
        validate("check_result", document)


@pytest.mark.parametrize(
    "code", ["STALE_SOURCE", "STALE_OUTPUT", "UNVERIFIED_SOURCE", "INPUT_CHANGED"]
)
def test_recollection_diagnostics_cannot_be_mislabeled_invalid_input(code):
    document = check_document()
    document.update(
        status="invalid",
        exit_code=2,
        error={
            "code": code,
            "message": "Recollect selected workspace facts.",
            "path": "source.cpp",
        },
    )
    with pytest.raises(ContractError):
        validate("check_result", document)


def test_completed_operation_cannot_carry_a_fatal_error():
    document = workflow_document()
    document["error"] = {
        "code": "STALE_SOURCE",
        "message": "Source changed; recollect.",
        "path": "source.cpp",
    }
    with pytest.raises(ContractError):
        validate("workflow_result", document)
