"""Exercise synthetic native analysis, actual CMake/CTest and pure policy results.

This is an internal review driver, not a public collect/assess CLI. Every project
command is an explicit recipe step. Separate immutable snapshots retain original
collection, normalized analysis and assessment; previous runs are not rewritten.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from cppulse import __version__
from cppulse.collection import collect
from cppulse.contracts import validate
from cppulse.errors import InputChanged, IntegrityError
from cppulse.identities import (
    context_identity,
    digest_json,
    hash_artifact,
    snapshot_inputs,
    verify_inputs,
)
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.tooling import load_rule_registry

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "clean",
    "findings",
    "partial-parse",
    "disabled-rule",
    "failed-test",
    "missing-tests",
)
RESOURCE_ROOT = "resources/clang"
REGISTRY = "rule-registry.json"
CONFIG = "native-config.json"
RESOURCES = "resource-manifest.json"
REPORT = "native-report/findings.json"
DATABASE = "native-build/compile_commands.json"
NATIVE_JOB = "native-job"
BUILD_JOB = "gcc-job"
REQUESTED_RULES = ["CPP-MEM-001"]


def now() -> str:
    """Return an observed UTC time without synthetic timestamp manipulation."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path: Path, document: dict[str, Any]) -> None:
    """Write deterministic JSON bytes compatible with the store's typed copies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    )
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def executable(value: str | Path) -> str:
    """Resolve one selected executable; do not install or substitute tools."""
    found = shutil.which(str(value))
    if found is None:
        raise RuntimeError(f"Required selected executable is unavailable: {value}")
    selected = Path(found).resolve(strict=True)
    if not selected.is_file() or not os.access(selected, os.X_OK):
        raise RuntimeError(f"Selected executable is not a runnable file: {selected}")
    return str(selected)


def inspect_tools(analyzer: Path, resource_dir: Path) -> dict[str, Any]:
    """Run and record explicit compiler inspection commands, not test outcomes."""
    tools: dict[str, Any] = {
        "cmake": executable("cmake"),
        "ctest": executable("ctest"),
        "compiler": executable("g++"),
        "analyzer": executable(analyzer),
        "resource_directory": str(resource_dir.resolve(strict=True)),
        "cppulse_distribution_version": __version__,
        "inspection_commands": [],
    }
    for key, arguments in [
        ("compiler_version", ["-dumpfullversion", "-dumpversion"]),
        ("compiler_target", ["-dumpmachine"]),
    ]:
        argv = [tools["compiler"], *arguments]
        started = now()
        result = subprocess.run(argv, capture_output=True, timeout=10, check=False)
        tools["inspection_commands"].append(
            {
                "argv": argv,
                "started_at": started,
                "finished_at": now(),
                "exit_code": result.returncode,
                "stdout": result.stdout.decode("utf-8", errors="replace"),
                "stderr": result.stderr.decode("utf-8", errors="replace"),
            }
        )
        if result.returncode or not result.stdout.strip():
            raise RuntimeError(f"Selected compiler inspection failed: {argv}")
        tools[key] = result.stdout.decode("utf-8").strip()
    for name in ["compiler", "analyzer"]:
        tools[name + "_sha256"] = hash_artifact(
            tools[name], name, name, "application/octet-stream"
        )["sha256"]
    return tools


def prepare_workspace(
    directory: Path, fixture: Path, resources: Path, scenario: str
) -> tuple[Path, dict[str, Any], list[str]]:
    """Copy the selected synthetic input and the entire finite resource tree."""
    workspace = directory / "workspace"
    shutil.copytree(fixture, workspace)
    resources = resources.resolve(strict=True)
    if not (resources / "include/stddef.h").is_file():
        raise RuntimeError("Resource directory must contain include/stddef.h")
    for entry in resources.rglob("*"):
        if entry.is_symlink() or (not entry.is_dir() and not entry.is_file()):
            raise IntegrityError(
                f"Resource tree contains a nonregular/link entry: {entry}"
            )
    shutil.copytree(resources, workspace / RESOURCE_ROOT)
    resource_files = sorted(
        entry.relative_to(workspace).as_posix()
        for entry in (workspace / RESOURCE_ROOT).rglob("*")
        if entry.is_file()
    )
    inventory = snapshot_inputs(workspace, resource_files)["files"]
    resource_manifest = {
        "version": "2.0.0",
        "root": RESOURCE_ROOT,
        "files": inventory,
        "limitations": [
            "Finite complete copy of the caller-selected local Clang resource tree; hashes identify these bytes, not their producer authenticity.",
            "This does not inventory host runtime libraries, compiler headers or arbitrary external dependencies.",
        ],
    }
    validate("resource_manifest", resource_manifest)
    write_json(workspace / RESOURCES, resource_manifest)
    write_json(workspace / REGISTRY, load_rule_registry())
    write_json(
        workspace / CONFIG,
        {
            "exclude_paths": ["build/**", "native-build/**", "resources/**"],
            "rules": {"CPP-MEM-001": {"enabled": scenario != "disabled-rule"}},
        },
    )
    source_files = sorted(
        entry.relative_to(workspace).as_posix()
        for entry in workspace.rglob("*")
        if entry.is_file()
    )
    source = snapshot_inputs(
        workspace, source_files, kind="application", inventory_complete=True
    )
    return workspace, source, resource_files


def make_plan(
    scenario: str, workspace: Path, tools: dict[str, Any], resource_files: list[str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Select two real configure jobs and an unbound native-analysis receipt."""
    source_inputs = ["CMakeLists.txt", "main.cpp"]
    switches = [
        "-DCPPULSE_DEMO_TRIGGER_RULE=" + ("ON" if scenario == "findings" else "OFF"),
        "-DCPPULSE_DEMO_PARSE_ERROR="
        + ("ON" if scenario == "partial-parse" else "OFF"),
        "-DCPPULSE_DEMO_TEST_FAILURE=" + ("ON" if scenario == "failed-test" else "OFF"),
    ]

    def configure(build: str) -> list[str]:
        return [
            tools["cmake"],
            "-S",
            ".",
            "-B",
            build,
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_CXX_COMPILER={tools['compiler']}",
            *switches,
        ]

    native_argv = [
        tools["analyzer"],
        "--repo",
        str(workspace),
        "--config",
        str(workspace / CONFIG),
        "--compilation-database",
        str(workspace / DATABASE),
        "--resource-dir",
        str(workspace / RESOURCE_ROOT),
        "--output",
        str(workspace / "native-report"),
    ]
    build_context = context_identity(
        {
            "id": BUILD_JOB,
            "compiler": {
                "name": "GNU",
                "version": tools["compiler_version"],
                "sha256": tools["compiler_sha256"],
            },
            "argv": configure("build"),
            "working_directory": str(workspace),
            "language_standard": "c++17",
            "target": tools["compiler_target"],
            "provenance": "inferred",
            "dependencies": [
                {
                    "id": "host-compiler-runtime-and-headers",
                    "sha256": None,
                    "availability": "unavailable",
                }
            ],
            "limitations": [
                "Coarse selected configure/build/test job; compiler inspection was explicit, but this is not a complete observed compiler-command or runtime dependency closure."
            ],
        }
    )
    native_context = context_identity(
        {
            "id": NATIVE_JOB,
            "compiler": {
                "name": "cppulse-analyzer",
                "version": __version__,
                "sha256": tools["analyzer_sha256"],
            },
            "argv": native_argv,
            "working_directory": str(workspace),
            "language_standard": "c++17",
            "target": tools["compiler_target"],
            "provenance": "inferred",
            "dependencies": [
                {
                    "id": "selected-resource-manifest",
                    "sha256": hash_artifact(
                        workspace / RESOURCES,
                        "resources",
                        "resources.json",
                        "application/json",
                    )["sha256"],
                    "availability": "available",
                }
            ],
            "limitations": [
                "Coarse setup/native job, not an observed per-file compiler context; the native report supplies actual libclang argv/cwd/version later.",
                "Tool version labels the selected cppulse development distribution; exact selected executable bytes are separately hashed. Setup executes CMake/GCC, whose actual argv and executable facts are retained.",
            ],
        }
    )

    def step(
        identifier: str,
        context: str,
        argv: list[str],
        *,
        cwd: str = ".",
        dependencies: list[str] | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": identifier,
            "context_id": context,
            "argv": argv,
            "cwd": cwd,
            "depends_on": dependencies or [],
            "inputs": inputs or [],
            "outputs": outputs or [],
            "timeout_seconds": 60,
        }

    binary = "build/cppulse-policy-demo"
    definition = "build/CTestTestfile.cmake"
    test_report = "build/junit.xml"
    execution_log = "build/Testing/Temporary/LastTest.log"
    steps = [
        step(
            "configure-build",
            BUILD_JOB,
            configure("build"),
            inputs=source_inputs,
            outputs=["build/CMakeCache.txt", "build/compile_commands.json", definition],
        ),
        step(
            "build",
            BUILD_JOB,
            [tools["cmake"], "--build", "build", "--parallel", "2"],
            dependencies=["configure-build"],
            inputs=source_inputs + ["build/CMakeCache.txt"],
            outputs=[binary],
        ),
        step("ctest-version", BUILD_JOB, [tools["ctest"], "--version"]),
        step(
            "ctest-inventory",
            BUILD_JOB,
            [tools["ctest"], "--show-only=json-v1"],
            cwd="build",
            dependencies=["build"],
            inputs=[binary, definition],
        ),
        step(
            "tests",
            BUILD_JOB,
            [
                tools["ctest"],
                "--output-on-failure",
                "--output-junit",
                "unretained.xml" if scenario == "missing-tests" else "junit.xml",
            ],
            cwd="build",
            dependencies=["ctest-version", "ctest-inventory"],
            inputs=[binary, definition],
            outputs=[test_report, execution_log],
        ),
        step(
            "configure-native",
            NATIVE_JOB,
            configure("native-build"),
            inputs=source_inputs,
            outputs=["native-build/CMakeCache.txt", DATABASE],
        ),
        step(
            "native-analysis",
            NATIVE_JOB,
            native_argv,
            dependencies=["configure-native"],
            inputs=["main.cpp", CONFIG, REGISTRY, RESOURCES, DATABASE, *resource_files],
            outputs=[REPORT],
        ),
    ]
    common = {"scope_files": ["main.cpp"]}
    plan = {
        "version": "2.0.0",
        "id": "synthetic-policy-" + scenario,
        "recipe": {
            "version": "2.0.0",
            "id": "synthetic-native-cmake-ctest",
            "jobs": 2,
            "contexts": [BUILD_JOB, NATIVE_JOB],
            "steps": steps,
        },
        "limits": {
            "max_log_bytes": 1024 * 1024,
            "max_artifact_bytes": 64 * 1024 * 1024,
            "max_metadata_bytes": 16 * 1024 * 1024,
            "termination_grace_seconds": 1,
        },
        "bindings": [
            {
                "id": "synthetic-build",
                "step_id": "build",
                "kind": "build",
                **common,
                "exercised_inputs": [binary],
                "report_path": None,
                "adapter": None,
                "adapter_version": None,
                "inventory_step_id": None,
                "producer_version_step_id": None,
                "execution_log_path": None,
            },
            {
                "id": "synthetic-tests",
                "step_id": "tests",
                "kind": "tests",
                **common,
                "exercised_inputs": [binary],
                "report_path": test_report,
                "adapter": "ctest-junit",
                "adapter_version": "1.0.0",
                "inventory_step_id": "ctest-inventory",
                "producer_version_step_id": "ctest-version",
                "execution_log_path": execution_log,
            },
        ],
    }
    return plan, [build_context, native_context]


def documents(snapshot: RunSnapshot) -> dict[str, Any]:
    """Load only integrity-checked typed v2 artifacts from one fixed snapshot."""
    result: dict[str, Any] = {"run_manifest": snapshot.manifest}
    for artifact in snapshot.manifest["artifacts"]:
        reference = artifact.get("contract", {})
        if reference.get("version") != "2.0.0":
            continue
        kind = reference["kind"]
        value = snapshot.read_json(artifact["id"])
        if kind == "policy":
            if kind in result:
                raise IntegrityError(
                    "A policy demonstration cannot select multiple policies"
                )
            result[kind] = value
        else:
            result.setdefault(kind, []).append(value)
    return result


def native_roles(snapshot: RunSnapshot) -> dict[str, str]:
    """Resolve role IDs from original typed execution-fact path bindings."""
    selected = [
        fact
        for fact in documents(snapshot).get("execution_facts", [])
        if fact["receipt"]["id"] == "native-analysis"
    ]
    if len(selected) != 1:
        raise IntegrityError("Expected exactly one typed native-analysis receipt")
    fact = selected[0]
    inputs = {
        link["path"]: link["artifact_id"] for link in fact["binding"]["input_artifacts"]
    }
    outputs = {
        link["path"]: link["artifact_id"]
        for link in fact["binding"]["output_artifacts"]
    }
    return {
        "receipt_id": "native-analysis",
        "report_artifact_id": outputs[REPORT],
        "registry_artifact_id": inputs[REGISTRY],
        "config_artifact_id": inputs[CONFIG],
        "compilation_database_artifact_id": inputs[DATABASE],
        "resource_manifest_artifact_id": inputs[RESOURCES],
    }


def selected_policy() -> dict[str, Any]:
    """Select four supported controls with explicit job roles and source scope."""
    controls = [
        (
            "finding-limit",
            "No selected raw-allocation findings",
            "finding_limit",
            {"rule_ids": REQUESTED_RULES, "max_findings": 0, "contexts": [NATIVE_JOB]},
        ),
        (
            "analysis-coverage",
            "Requested source parses completely",
            "minimum_analysis_coverage",
            {"minimum": 100, "contexts": [NATIVE_JOB]},
        ),
        (
            "required-tests",
            "Selected CTest outcomes pass",
            "test_outcomes",
            {"evidence_ids": ["synthetic-tests"], "contexts": [BUILD_JOB]},
        ),
        (
            "required-contexts",
            "Both selected jobs have scoped observed results",
            "required_contexts",
            {"contexts": [BUILD_JOB, NATIVE_JOB]},
        ),
    ]
    return {
        "version": "2.0.0",
        "id": "synthetic-local-policy",
        "policy_version": "1.0.0",
        "standards": [],
        "scope": {"include": ["main.cpp"], "exclude": []},
        "contexts": [BUILD_JOB, NATIVE_JOB],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": identifier,
                "title": title,
                "kind": kind,
                "weight": 1,
                "required": True,
                "parameters": parameters,
                "depends_on": [],
            }
            for identifier, title, kind, parameters in controls
        ],
    }


def persist_assessment(
    parent: RunSnapshot, workspace: Path, store: RunStore, directory: Path
) -> tuple[RunSnapshot, dict[str, Any]]:
    """Derive an assessed immutable snapshot without changing collected facts."""
    from cppulse.policy import evaluate_policy

    parent.verify()
    policy = selected_policy()
    write_json(directory / "policy.json", policy)
    derivation = {
        "operation": "synthetic-policy-assessment",
        "parent_run_id": parent.run_id,
        "parent_manifest_sha256": parent.manifest_sha256,
        "created_at": now(),
        "cppulse_distribution_version": __version__,
        "policy_sha256": digest_json(policy),
    }
    write_json(directory / "derivation.json", derivation)
    with store.begin() as stage:
        for artifact in parent.manifest["artifacts"]:
            copied = stage.copy_artifact(
                artifact["id"],
                parent.path / artifact["path"],
                artifact["path"],
                artifact["media_type"],
                contract=artifact.get("contract"),
            )
            if copied != artifact:
                raise IntegrityError(
                    "Assessment derivation changed parent artifact bytes"
                )
        stage.write_json(
            "policy/selected.json", policy, contract="policy", artifact_id="demo-policy"
        )
        stage.copy_artifact(
            "demo-derivation",
            directory / "derivation.json",
            "policy/derivation.json",
            "application/json",
        )
        manifest = deepcopy(parent.manifest)
        manifest.update(
            run_id=stage.run_id,
            artifacts=stage.artifacts,
        )
        manifest["limitations"].append(
            "Derived policy snapshot retains its parent's execution window; actual assessment time is recorded separately. Parent identity is retained in policy/derivation.json."
        )
        bundle = documents(parent)
        bundle["run_manifest"] = manifest
        result = evaluate_policy(policy, bundle, generated_at=now())
        stage.write_json(
            "policy/assessment.json",
            result,
            contract="assessment",
            artifact_id="demo-assessment",
        )
        manifest["artifacts"] = stage.artifacts
        manifest["versions"]["cppulse.policy"] = result["evaluator"]["version"]
        manifest["versions"]["cppulse.assessment-runtime"] = __version__
        manifest["stages"].append(
            {
                "id": "demo-policy-evaluation",
                "status": "passed",
                "depends_on": [],
                "reason": "Pure evaluation completed; policy gate is "
                + result["gate"]
                + ". Original producer outcomes are retained.",
            }
        )

        def source_check() -> None:
            issues = verify_inputs(workspace, manifest["source"])
            if issues:
                raise InputChanged(
                    "Demo inputs changed before assessment publication: "
                    + "; ".join(issues)
                )

        assessed = stage.publish(manifest, source_check=source_check)
    assessed.verify()
    write_json(directory / "assessment.json", result)
    return assessed, result


def collect_case(
    scenario: str,
    directory: Path,
    store: RunStore,
    tools: dict[str, Any],
    fixture: Path,
) -> dict[str, Any]:
    """Execute real fixture commands and preserve the original observed snapshot."""
    workspace, source, resource_files = prepare_workspace(
        directory, fixture, Path(tools["resource_directory"]), scenario
    )
    plan, contexts = make_plan(scenario, workspace, tools, resource_files)
    for name, document in [
        ("plan", plan),
        ("source", source),
        ("contexts", {"contexts": contexts}),
    ]:
        write_json(directory / f"{name}.json", document)
    snapshot = collect(
        plan, workspace=workspace, source=source, contexts=contexts, store=store
    )
    snapshot.verify()
    roles = native_roles(snapshot)
    typed = documents(snapshot)
    evidence = {
        record["id"]: {"status": record["status"], "usability": record["usability"]}
        for document in typed.get("evidence", [])
        for record in document["records"]
    }
    expected = {
        "clean": ("completed", "passed", "passed", "usable"),
        "findings": ("completed", "passed", "passed", "usable"),
        "partial-parse": ("completed", "failed", "skipped", "missing"),
        "disabled-rule": ("completed", "passed", "passed", "usable"),
        "failed-test": ("completed", "passed", "failed", "usable"),
        "missing-tests": ("partial", "passed", "error", "missing"),
    }[scenario]
    observed = (
        snapshot.manifest["status"],
        evidence["synthetic-build"]["status"],
        evidence["synthetic-tests"]["status"],
        evidence["synthetic-tests"]["usability"],
    )
    if observed != expected:
        raise AssertionError(
            f"{scenario} collection observed {observed}, expected {expected}; inspect {snapshot.path}"
        )
    raw = json.loads(snapshot.read_bytes(roles["report_artifact_id"]))
    item = next(
        row
        for row in raw["metadata"]["analysis"]["files"]
        if Path(row["path"]) == workspace / "main.cpp"
    )
    return {
        "scenario": scenario,
        "directory": str(directory),
        "workspace": str(workspace),
        "raw_run_id": snapshot.run_id,
        "raw_manifest_sha256": snapshot.manifest_sha256,
        "raw_run_path": str(snapshot.path),
        "collection_status": snapshot.manifest["status"],
        "evidence": evidence,
        "native_roles": roles,
        "native_parser": raw["metadata"]["analysis"]["parser"],
        "native_main": item,
        "raw_findings": len(raw["findings"]),
        "resource_files": len(resource_files),
        "source_files": len(source["files"]),
    }


def normalize_case(case: dict[str, Any], store: RunStore) -> dict[str, Any]:
    """Derive and verify typed native facts before enabling policy consumption."""
    if not case.get("raw_manifest_sha256"):
        raise IntegrityError(
            "Collection checkpoint lacks its original manifest SHA; recollect with the current driver"
        )
    parent = store.open_run(
        case["raw_run_id"], manifest_sha256=case["raw_manifest_sha256"]
    )
    parent.verify()

    from cppulse.analysis import persist_native_analysis

    if case.get("normalized_run_id") and case.get("normalized_manifest_sha256"):
        normalized = store.open_run(
            case["normalized_run_id"],
            manifest_sha256=case["normalized_manifest_sha256"],
        )
    else:
        normalized = persist_native_analysis(
            parent,
            workspace=Path(case["workspace"]),
            store=store,
            **case["native_roles"],
            requested_files=["main.cpp"],
            requested_rules=REQUESTED_RULES,
        )
    normalized.verify()
    if normalized.manifest["source"] != parent.manifest["source"]:
        raise IntegrityError(
            "Normalization changed the original selected source identity"
        )
    retained = {
        artifact["id"]: artifact for artifact in normalized.manifest["artifacts"]
    }
    if any(
        retained.get(artifact["id"]) != artifact
        for artifact in parent.manifest["artifacts"]
    ):
        raise IntegrityError(
            "Normalization changed original artifact identities or bytes"
        )
    typed = documents(normalized)
    inventories = typed["analysis_inventory"]
    if len(inventories) != 1:
        raise IntegrityError("Expected exactly one normalized native inventory")
    inventory = inventories[0]
    row = inventory["items"][0]
    if (
        inventory["requested_files"] != ["main.cpp"]
        or inventory["requested_rules"] != REQUESTED_RULES
        or inventory["job_context_id"] != NATIVE_JOB
        or len(inventory["items"]) != 1
        or row["file"] != "main.cpp"
        or row["status"] != case["native_main"]["status"]
        or row["context_source"] != "database"
        or row["context_match"] != "matched"
        or row["finding_count"] != case["raw_findings"]
    ):
        raise AssertionError(
            f"Normalized native scope/outcome differs from actual report: {inventory}"
        )
    contexts = {context["id"]: context for context in normalized.manifest["contexts"]}
    observed = contexts[row["parse_context_id"]]
    if (
        observed["provenance"] != "observed"
        or observed["compiler"]["name"] != "libclang"
        or observed["compiler"]["version"] != case["native_parser"]["version"]
        or observed["argv"] != case["native_main"]["parse_arguments"]
        or observed["working_directory"] != case["native_main"]["working_directory"]
        or row["parse_context_id"] == NATIVE_JOB
    ):
        raise AssertionError(
            "Observed parse context does not retain the actual native trace"
        )
    complete = case["scenario"] not in {"partial-parse", "disabled-rule"}
    if (set(REQUESTED_RULES) <= set(row["executed_rules"])) != complete:
        raise AssertionError(
            "Requested-rule completion contradicts observed parse/config state"
        )
    return {
        **case,
        "normalized_run_id": normalized.run_id,
        "normalized_manifest_sha256": normalized.manifest_sha256,
        "normalized_run_path": str(normalized.path),
        "analysis_inventory": inventory,
    }


def finish_case(case: dict[str, Any], store: RunStore) -> dict[str, Any]:
    """Assess verified normalized facts and assert selected policy outcomes."""
    case = normalize_case(case, store)
    normalized = store.open_run(
        case["normalized_run_id"], manifest_sha256=case["normalized_manifest_sha256"]
    )
    assessed, result = persist_assessment(
        normalized, Path(case["workspace"]), store, Path(case["directory"])
    )
    controls = {row["id"]: row["status"] for row in result["controls"]}
    expected_gate = {
        "clean": "passed",
        "findings": "failed",
        "partial-parse": "failed",
        "disabled-rule": "insufficient_evidence",
        "failed-test": "failed",
        "missing-tests": "insufficient_evidence",
    }[case["scenario"]]
    if result["gate"] != expected_gate:
        raise AssertionError(
            f"{case['scenario']} gate {result['gate']}, expected {expected_gate}; inspect {assessed.path}"
        )
    expectations = {
        "clean": {key: "passed" for key in controls},
        "findings": {
            "finding-limit": "failed",
            "required-tests": "passed",
            "analysis-coverage": "passed",
        },
        "partial-parse": {
            "finding-limit": "unknown",
            "analysis-coverage": "failed",
            "required-tests": "unknown",
        },
        "disabled-rule": {
            "finding-limit": "unknown",
            "analysis-coverage": "passed",
            "required-tests": "passed",
        },
        "failed-test": {
            "finding-limit": "passed",
            "required-tests": "failed",
            "analysis-coverage": "passed",
        },
        "missing-tests": {
            "finding-limit": "passed",
            "required-tests": "unknown",
            "analysis-coverage": "passed",
        },
    }[case["scenario"]]
    # A usable observed failed build/partial parse can establish that its job
    # was exercised; outcome requirements remain separate controls.
    expectations["required-contexts"] = "passed"
    if any(controls[key] != expected for key, expected in expectations.items()):
        raise AssertionError(
            f"{case['scenario']} controls {controls}, expected {expectations}"
        )
    return {
        **case,
        "assessed_run_id": assessed.run_id,
        "assessed_manifest_sha256": assessed.manifest_sha256,
        "assessed_run_path": str(assessed.path),
        "gate": result["gate"],
        "controls": controls,
        "weights": result["weights"],
        "scores": result["scores"],
        "input_verification": assessed.manifest["input_verification"],
    }


def main() -> None:
    """Run a reproducible internal review batch without Git or remote writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/policy-demo")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    parser.add_argument("--fixture", type=Path, default=ROOT / "demo/policy-fixture")
    parser.add_argument(
        "--analyzer", type=Path, default=ROOT / "analyzer-core/build/cppulse-analyzer"
    )
    parser.add_argument(
        "--resource-dir",
        type=Path,
        default=os.environ.get("CPPULSE_CLANG_RESOURCE_DIR"),
    )
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument(
        "--collect-only",
        action="store_true",
        help="Retain actual producer cases while normalization is separately gated",
    )
    phase.add_argument(
        "--normalize-only",
        action="store_true",
        help="Persist typed analysis facts before the separate policy consumer gate",
    )
    parser.add_argument(
        "--resume-batch",
        type=Path,
        help="Normalize/assess an existing collection batch without rerunning commands",
    )
    args = parser.parse_args()
    if args.resume_batch:
        if args.collect_only:
            parser.error("--resume-batch and --collect-only are mutually exclusive")
        batch = args.resume_batch.resolve(strict=True)
        checkpoint = batch / "normalization-summary.json"
        if not checkpoint.exists():
            checkpoint = batch / "collection-summary.json"
        summary = json.loads(checkpoint.read_bytes())
        output = Path(summary["output_root"])
        store = RunStore(Path(summary["store"]))
    else:
        if args.resource_dir is None:
            parser.error(
                "Supply --resource-dir or CPPULSE_CLANG_RESOURCE_DIR for the matching local Clang resource tree"
            )
        output = args.output.resolve()
        batch = output / "batches" / uuid4().hex
        batch.mkdir(parents=True)
        tools = inspect_tools(args.analyzer, args.resource_dir)
        write_json(batch / "tools.json", tools)
        store = RunStore(output / "store")
        cases = []
        for scenario in SCENARIOS if args.scenario == "all" else [args.scenario]:
            directory = batch / scenario
            directory.mkdir()
            cases.append(
                collect_case(
                    scenario, directory, store, tools, args.fixture.resolve(strict=True)
                )
            )
            write_json(
                batch / "collection-summary.json",
                {
                    "output_root": str(output),
                    "store": str(store.root),
                    "batch": str(batch),
                    "cases": cases,
                },
            )
        summary = json.loads((batch / "collection-summary.json").read_bytes())
    if args.normalize_only:
        summary["cases"] = [normalize_case(case, store) for case in summary["cases"]]
        write_json(batch / "normalization-summary.json", summary)
    elif not args.collect_only:
        summary["cases"] = [finish_case(case, store) for case in summary["cases"]]
    latest_attempt = store.resolve_latest_attempt()
    latest_completed = (
        store.resolve_latest() if (store.root / "latest.json").exists() else None
    )
    completed_collection = next(
        (
            case
            for case in reversed(summary["cases"])
            if case["collection_status"] == "completed"
        ),
        None,
    )
    summary.update(
        verified_at=now(),
        phase=(
            "collection"
            if args.collect_only
            else "normalization" if args.normalize_only else "assessment"
        ),
        tools=json.loads((batch / "tools.json").read_bytes()),
        selected_job_contexts={"native": NATIVE_JOB, "build_tests": BUILD_JOB},
        scenario_count=len(summary["cases"]),
        collection_status_counts=dict(
            Counter(case["collection_status"] for case in summary["cases"])
        ),
        gate_counts=dict(
            Counter(case["gate"] for case in summary["cases"] if "gate" in case)
        ),
        control_status_counts=dict(
            Counter(
                status
                for case in summary["cases"]
                for status in case.get("controls", {}).values()
            )
        ),
        latest_attempt=latest_attempt.run_id,
        latest_attempt_manifest_sha256=latest_attempt.manifest_sha256,
        latest_completed_collection=(
            completed_collection["raw_run_id"] if completed_collection else None
        ),
        latest_completed_collection_manifest_sha256=(
            completed_collection["raw_manifest_sha256"]
            if completed_collection
            else None
        ),
        latest_completed_snapshot=latest_completed.run_id if latest_completed else None,
        latest_completed_snapshot_manifest_sha256=(
            latest_completed.manifest_sha256 if latest_completed else None
        ),
        limitations=[
            "Clearly labeled synthetic single-TU input; these are actual selected commands and observed outcomes, not an accuracy/performance benchmark or upstream defect report.",
            "Coarse job contexts remain declared/inferred; per-file libclang contexts are observed separately. Finite selected resources/inputs are hashed, without a complete host dependency/authenticity claim.",
            "Internal S5 review script only; public collection/assessment CLI and unified evidence presentation remain subsequent work.",
        ],
    )
    write_json(batch / "summary.json", summary)
    write_json(output / "latest-demo.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
