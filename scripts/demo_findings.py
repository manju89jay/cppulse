"""Run real native finding regression checks over an explicitly synthetic project.

Every target command belongs to the public collection request. Baselines and
checks use the public CLI; this driver does not implement a persistence engine.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

from cppulse.contracts import validate
from cppulse.identities import context_identity
from cppulse.run_store import RunSnapshot, RunStore

from demo_policy import (
    CONFIG,
    DATABASE,
    NATIVE_JOB,
    REGISTRY,
    REPORT,
    RESOURCES,
    ROOT,
    inspect_tools,
    make_plan,
    now,
    prepare_workspace,
    write_json,
)

RULES = ["CPP-MEM-001"]
BASE_MAIN = """// Synthetic verification input, analyzed by the real native engine.
#include "settings.hpp"
int main() {
    /* café */ int* value = new int(5);
    const int result = *value;
    delete value;
    return result == 5 ? selected_zero : 1;
}
"""
CMAKE = """cmake_minimum_required(VERSION 3.16)
project(cppulse-finding-fixture LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_executable(cppulse-policy-demo main.cpp)
add_library(left OBJECT a/same.cpp)
add_library(right OBJECT b/same.cpp)
add_library(spare OBJECT spare.cpp)
foreach(target cppulse-policy-demo left right spare)
  target_include_directories(${target} PRIVATE include)
  target_compile_options(${target} PRIVATE -Wall -Wextra -Werror)
endforeach()
enable_testing()
add_test(NAME selected-policy-consumer COMMAND cppulse-policy-demo)
"""


def fixture(directory: Path) -> None:
    """Write a labeled finite project; no imported repository/history is implied."""
    files = {
        "CMakeLists.txt": CMAKE,
        "main.cpp": BASE_MAIN,
        "spare.cpp": "int spare() { return 0; }\n",
        "a/same.cpp": "int left() { return 0; }\n",
        "b/same.cpp": "int right() { return 0; }\n",
        "include/settings.hpp": "#pragma once\nconstexpr int selected_zero = 0;\n",
    }
    for name, content in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def selected_sources(workspace: Path) -> list[str]:
    """Select the known fixture inputs, excluding owned generated directories."""
    return sorted(
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file()
        and path.relative_to(workspace).parts[0]
        not in {"build", "native-build", "native-report"}
    )


def request_for(
    workspace: Path,
    tools: dict[str, Any],
    resource_files: list[str],
    *,
    extra_flag: str | None = None,
) -> dict[str, Any]:
    """Reuse the accepted actual CMake/CTest/native recipe with captured cleanup."""
    plan, contexts = make_plan("clean", workspace, tools, resource_files)
    sources = selected_sources(workspace)
    translation_units = [name for name in sources if name.endswith(".cpp")]
    project_inputs = [
        name
        for name in sources
        if name.endswith((".cpp", ".hpp")) or name == "CMakeLists.txt"
    ]
    cleanup = {
        "id": "cleanup-owned-generated",
        "context_id": NATIVE_JOB,
        "argv": [
            sys.executable,
            "-c",
            "import shutil; from pathlib import Path; "
            "[shutil.rmtree(Path(name)) for name in "
            "('build','native-build','native-report') if Path(name).exists()]",
        ],
        "cwd": ".",
        "depends_on": [],
        "inputs": [],
        "outputs": [],
        "timeout_seconds": 15,
    }
    for step in plan["recipe"]["steps"]:
        if step["id"].startswith("configure-"):
            step["depends_on"] = [cleanup["id"]]
            step["inputs"] = project_inputs
            if extra_flag:
                step["argv"].append("-DCMAKE_CXX_FLAGS=" + extra_flag)
        elif step["id"] == "build":
            step["inputs"] = [*project_inputs, "build/CMakeCache.txt"]
        elif step["id"] == "native-analysis":
            step["inputs"] = [
                *project_inputs,
                CONFIG,
                REGISTRY,
                RESOURCES,
                DATABASE,
                *resource_files,
            ]
    plan["recipe"]["steps"].insert(0, cleanup)
    for binding in plan["bindings"]:
        binding["scope_files"] = translation_units
    if extra_flag:
        for index, context in enumerate(contexts):
            if context["id"] != NATIVE_JOB:
                updated = deepcopy(context)
                updated["argv"].append("-DCMAKE_CXX_FLAGS=" + extra_flag)
                contexts[index] = context_identity(updated)

    def role(path: str, side: str = "input") -> dict[str, Any]:
        return {"step_id": "native-analysis", "role": side, "path": path}

    request = {
        "version": "2.0.0",
        "id": "synthetic-actual-native-findings",
        "source": {
            "kind": "application",
            "files": sources,
            "inventory_complete": True,
            "limitations": [
                "Finite synthetic verification fixture and copied selected Clang resources; native/CMake/CTest execution is real.",
                "No claim of host dependency closure or detector accuracy is made.",
            ],
        },
        "contexts": contexts,
        "plan": plan,
        "normalizers": [
            {
                "id": "native-findings",
                "kind": "native_analysis",
                "normalizer_version": "1.0.0",
                "step_id": "native-analysis",
                "report": role(REPORT, "output"),
                "registry": role(REGISTRY),
                "config": role(CONFIG),
                "compilation_database": role(DATABASE),
                "resource_manifest": role(RESOURCES),
                "requested_files": translation_units,
                "requested_rules": RULES,
            }
        ],
    }
    validate("collection_request", request)
    return request


class Demo:
    """Record public command inputs, exact results and checked immutable pins."""

    def __init__(self, batch: Path, workspace: Path) -> None:
        self.batch = batch
        self.workspace = workspace
        self.store = batch / "store"
        self.commands: list[dict[str, Any]] = []
        self.cases: list[dict[str, Any]] = []

    def command(self, name: str, arguments: list[str], expected: int) -> dict[str, Any]:
        """Run the public installed-module entry point and retain original streams."""
        argv = [sys.executable, "-m", "cppulse.cli", *arguments]
        started = now()
        result = subprocess.run(argv, capture_output=True, timeout=240, check=False)
        logs = self.batch / "commands"
        logs.mkdir(exist_ok=True)
        (logs / (name + ".stdout.json")).write_bytes(result.stdout)
        (logs / (name + ".stderr.log")).write_bytes(result.stderr)
        self.commands.append(
            {
                "name": name,
                "argv": argv,
                "started_at": started,
                "finished_at": now(),
                "exit_code": result.returncode,
                "expected_exit_code": expected,
            }
        )
        write_json(self.batch / "commands.json", self.commands)
        if result.returncode != expected:
            raise RuntimeError(
                f"{name}: expected exit {expected}, observed {result.returncode}; "
                f"inspect {logs / (name + '.stderr.log')}"
            )
        return json.loads(result.stdout)

    def open(self, reference: dict[str, Any]) -> RunSnapshot:
        """Verify the exact returned run/hash pair, never resolve latest twice."""
        return RunStore.open_existing(self.store).open_run(
            reference["run_id"], manifest_sha256=reference["manifest_sha256"]
        )

    def pins(self, snapshot: RunSnapshot) -> list[str]:
        return [
            "--store",
            str(self.store),
            "--run-id",
            snapshot.run_id,
            "--manifest-sha256",
            snapshot.manifest_sha256,
        ]

    def collect(self, name: str, request: dict[str, Any]) -> RunSnapshot:
        """Capture/normalize via CLI and verify actual native counts and context."""
        path = self.batch / (name + ".collection-request.json")
        write_json(path, request)
        result = self.command(
            name + "-collect",
            [
                "collect",
                "--request",
                str(path),
                "--workspace",
                str(self.workspace),
                "--store",
                str(self.store),
            ],
            0,
        )
        raw, snapshot = self.open(result["raw_run"]), self.open(result["final_run"])
        inventories = typed(snapshot, "analysis_inventory")
        observations = typed(snapshot, "observations")
        counts = Counter(
            row["file"]
            for document in observations
            for row in document["items"]
            if row["rule_id"] in RULES
        )
        self.cases.append(
            {
                "case": name,
                "collection": result,
                "database_sha256": hashlib.sha256(
                    (self.workspace / DATABASE).read_bytes()
                ).hexdigest(),
                "requested_rule_findings": dict(sorted(counts.items())),
                "inventory": inventories,
            }
        )
        if not all(
            item["status"] == "analyzed" and item["context_match"] == "matched"
            for inventory in inventories
            for item in inventory["items"]
        ):
            raise RuntimeError(
                "Actual native fixture must have matched, complete parse facts"
            )
        expected = {
            "baseline": {"main.cpp": 1},
            "line-shift": {"main.cpp": 1},
            "header-cold-recollect": {"main.cpp": 1},
            "new-unique-finding": {"main.cpp": 2},
            "duplicate-anchor": {"main.cpp": 2},
            "duplicate-basenames": {"main.cpp": 1, "a/same.cpp": 1, "b/same.cpp": 1},
            "changed-flags": {"main.cpp": 1},
            "ordinary-rename": {"renamed.cpp": 1},
            "stable-rename-before": {"main.cpp": 1},
            "stable-rename-after": {"spare.cpp": 1},
        }[name]
        if dict(counts) != expected:
            raise RuntimeError(
                f"{name}: actual rule counts {dict(counts)} differ from {expected}"
            )
        raw.verify()
        return snapshot

    def check(
        self,
        name: str,
        snapshot: RunSnapshot,
        request: dict[str, Any],
        expected: int,
    ) -> dict[str, Any]:
        """Check retained facts without invoking any project collection/build."""
        path = self.batch / (name + ".finding-request.json")
        write_json(path, request)
        result = self.command(
            name + "-check",
            [
                "check",
                *self.pins(snapshot),
                "--workspace",
                str(self.workspace),
                "--findings",
                str(path),
            ],
            expected,
        )
        derived = self.open(result["run"])
        comparison = (
            derived.read_json(result["comparison_artifact_id"])
            if result["comparison_artifact_id"]
            else None
        )
        self.cases.append({"case": name, "check": result, "comparison": comparison})
        write_json(self.batch / "cases.json", self.cases)
        return result


def typed(snapshot: RunSnapshot, kind: str) -> list[dict[str, Any]]:
    """Read one explicitly declared contract family from checked retained bytes."""
    return [
        snapshot.read_json(entry["id"])
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == kind
    ]


def run(args: argparse.Namespace) -> Path:
    """Exercise actual finding identities, conservative gaps and cold recollection."""
    batch = args.output.resolve() / "batches" / uuid4().hex
    batch.mkdir(parents=True)
    source_fixture = batch / "fixture"
    fixture(source_fixture)
    tools = inspect_tools(args.analyzer, args.resource_dir)
    write_json(batch / "tools.json", tools)
    workspace, _, resources = prepare_workspace(
        batch, source_fixture, args.resource_dir, "clean"
    )
    demo = Demo(batch, workspace)
    baseline_snapshot = demo.collect(
        "baseline", request_for(workspace, tools, resources)
    )
    scope = {
        "scope_files": ["main.cpp", "spare.cpp", "a/same.cpp", "b/same.cpp"],
        "context_ids": [NATIVE_JOB],
        "rule_ids": RULES,
    }
    baseline_request = {
        "version": "2.0.0",
        "baseline_id": "actual-synthetic-native-baseline",
        "reason": "Explicit reviewed baseline for this synthetic native integration demo.",
        **scope,
    }
    path = batch / "baseline.request.json"
    write_json(path, baseline_request)
    baseline_result = demo.command(
        "baseline-create",
        [
            "baseline",
            "create",
            *demo.pins(baseline_snapshot),
            "--workspace",
            str(workspace),
            "--request",
            str(path),
        ],
        0,
    )
    baseline = demo.open(baseline_result["final_run"])
    check_request = {
        "version": "2.0.0",
        "baseline": {
            "source": "local_run",
            "store": str(demo.store),
            "run_id": baseline.run_id,
            "manifest_sha256": baseline.manifest_sha256,
            "artifact_id": baseline_result["baseline_artifact_id"],
        },
        **scope,
        "max_new": 0,
        "rename_map": [],
    }
    demo.check("unchanged", baseline_snapshot, check_request, 0)
    (workspace / "main.cpp").write_text("\n\n" + BASE_MAIN)
    shifted = demo.collect("line-shift", request_for(workspace, tools, resources))
    if demo.cases[0]["database_sha256"] != demo.cases[-1]["database_sha256"]:
        raise RuntimeError("Line-shift case changed compilation database bytes")
    shifted_result = demo.check("line-shift", shifted, check_request, 0)
    original_observation = next(
        row
        for document in typed(baseline_snapshot, "observations")
        for row in document["items"]
        if row["rule_id"] == RULES[0]
    )
    shifted_observation = next(
        row
        for document in typed(shifted, "observations")
        for row in document["items"]
        if row["rule_id"] == RULES[0]
    )
    if original_observation["fingerprint"] == shifted_observation["fingerprint"]:
        raise RuntimeError("Line-sensitive native-1 fingerprint unexpectedly unchanged")
    shifted_comparison = demo.open(shifted_result["run"]).read_json(
        shifted_result["comparison_artifact_id"]
    )
    if shifted_comparison["counts"]["unchanged"] != 1:
        raise RuntimeError("Unique line anchor did not retain the shifted occurrence")
    (workspace / "include/settings.hpp").write_text(
        "#pragma once\n// Actual selected header mutation.\nconstexpr int selected_zero = 0;\n"
    )
    demo.check("header-stale-before-recollect", shifted, check_request, 3)
    cold = demo.collect(
        "header-cold-recollect", request_for(workspace, tools, resources)
    )
    demo.check("header-cold-recollect", cold, check_request, 0)
    (workspace / "main.cpp").write_text(
        BASE_MAIN.replace(
            "    const int result",
            "    int* extra = new int(7);\n    delete extra;\n    const int result",
        )
    )
    added = demo.collect("new-unique-finding", request_for(workspace, tools, resources))
    demo.check("new-unique-finding", added, check_request, 1)
    (workspace / "main.cpp").write_text(
        BASE_MAIN
        + "int duplicate_anchor() {\n    /* café */ int* value = new int(5);\n    delete value;\n    return 0;\n}\n"
    )
    repeated = demo.collect(
        "duplicate-anchor", request_for(workspace, tools, resources)
    )
    demo.check("duplicate-anchor", repeated, check_request, 3)
    (workspace / "main.cpp").write_text(BASE_MAIN)
    for name, function in [("a/same.cpp", "left"), ("b/same.cpp", "right")]:
        (workspace / name).write_text(
            f"int {function}() {{\n    int* item = new int(3);\n    delete item;\n    return 0;\n}}\n"
        )
    duplicate_paths = demo.collect(
        "duplicate-basenames", request_for(workspace, tools, resources)
    )
    demo.check("duplicate-basenames", duplicate_paths, check_request, 1)
    (workspace / "a/same.cpp").write_text("int left() { return 0; }\n")
    (workspace / "b/same.cpp").write_text("int right() { return 0; }\n")
    changed_context = demo.collect(
        "changed-flags",
        request_for(workspace, tools, resources, extra_flag="-DS7_FINDING_CONTEXT=1"),
    )
    demo.check("changed-flags", changed_context, check_request, 3)
    (workspace / "main.cpp").rename(workspace / "renamed.cpp")
    (workspace / "CMakeLists.txt").write_text(
        CMAKE.replace("cppulse-policy-demo main.cpp", "cppulse-policy-demo renamed.cpp")
    )
    renamed = demo.collect("ordinary-rename", request_for(workspace, tools, resources))
    renamed_request = deepcopy(check_request)
    renamed_request["scope_files"] = [
        "renamed.cpp" if name == "main.cpp" else name for name in scope["scope_files"]
    ]
    demo.check("ordinary-rename", renamed, renamed_request, 3)
    renamed_request["rename_map"] = [{"from": "main.cpp", "to": "renamed.cpp"}]
    demo.check("ordinary-rename-explicit-map", renamed, renamed_request, 3)
    # A predeclared pair keeps source filenames out of the selected CMake
    # mutation. Actual observed parse contexts still decide compatibility.
    (workspace / "renamed.cpp").unlink()
    (workspace / "CMakeLists.txt").write_text(CMAKE)
    (workspace / "main.cpp").write_text(BASE_MAIN)
    (workspace / "spare.cpp").write_text("int spare() { return 0; }\n")
    stable_before = demo.collect(
        "stable-rename-before", request_for(workspace, tools, resources)
    )
    single_scope = {**scope, "scope_files": ["main.cpp"]}
    single_request = {
        **baseline_request,
        **single_scope,
        "baseline_id": "explicit-single-file-rename-baseline",
        "reason": "Explicit single-file scope for a predeclared-path rename experiment.",
    }
    path = batch / "stable-rename.baseline-request.json"
    write_json(path, single_request)
    single_baseline = demo.command(
        "stable-rename-baseline-create",
        [
            "baseline",
            "create",
            *demo.pins(stable_before),
            "--workspace",
            str(workspace),
            "--request",
            str(path),
        ],
        0,
    )
    single_snapshot = demo.open(single_baseline["final_run"])
    (workspace / "main.cpp").write_text("int main() { return 0; }\n")
    (workspace / "spare.cpp").write_text(
        BASE_MAIN.replace("int main()", "int moved_fixture()")
    )
    stable_after = demo.collect(
        "stable-rename-after", request_for(workspace, tools, resources)
    )
    single_check = {
        **check_request,
        "scope_files": ["spare.cpp"],
        "baseline": {
            "source": "local_run",
            "store": str(demo.store),
            "run_id": single_snapshot.run_id,
            "manifest_sha256": single_snapshot.manifest_sha256,
            "artifact_id": single_baseline["baseline_artifact_id"],
        },
        "rename_map": [{"from": "main.cpp", "to": "spare.cpp"}],
    }
    baseline_cell = single_snapshot.read_json(single_baseline["baseline_artifact_id"])[
        "cells"
    ][0]
    inventory = typed(stable_after, "analysis_inventory")[0]
    target = next(item for item in inventory["items"] if item["file"] == "spare.cpp")
    target_context = next(
        context
        for context in stable_after.manifest["contexts"]
        if context["id"] == target["parse_context_id"]
    )
    compatible = baseline_cell["parse_context_digest"] == target_context["digest"]
    demo.check(
        "stable-predeclared-explicit-rename",
        stable_after,
        single_check,
        0 if compatible else 3,
    )
    sarif = demo.command(
        "line-shift-sarif",
        [
            "export-sarif",
            *demo.pins(demo.open(shifted_result["run"])),
            "--comparison-artifact-id",
            shifted_result["comparison_artifact_id"],
        ],
        0,
    )
    write_json(batch / "line-shift.sarif.json", sarif)
    import jsonschema

    official = json.loads(
        (ROOT / "tests/reference/sarif/sarif-schema-2.1.0.json").read_bytes()
    )
    jsonschema.Draft7Validator(official).validate(sarif)
    if len(sarif["runs"][0]["results"]) != 1:
        raise RuntimeError(
            "Scoped SARIF must retain the actual selected native occurrence"
        )
    line = ("\n\n" + BASE_MAIN).splitlines()[int(shifted_observation["line"]) - 1]
    byte_column = int(shifted_observation["column"])
    unicode_column = len(line.encode("utf-8")[: byte_column - 1].decode("utf-8")) + 1
    region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
        "region"
    ]
    if region["startColumn"] != unicode_column or unicode_column == byte_column:
        raise RuntimeError(
            "Actual UTF-8 native byte column was not converted to Unicode codepoints"
        )
    summary = {
        "batch": str(batch),
        "workspace": str(workspace),
        "store": str(demo.store),
        "synthetic_input_real_native_execution": True,
        "commands": demo.commands,
        "cases": demo.cases,
        "sarif": str(batch / "line-shift.sarif.json"),
        "actual_unicode_location": {
            "native_byte_column": byte_column,
            "sarif_codepoint_column": unicode_column,
        },
        "limitations": [
            "Experimental native rules and exact observed contexts; this is not an accuracy or safety benchmark.",
            "Rename mapping does not normalize compiler contexts or establish cross-configuration compatibility.",
            "Every repeated collection records cleanup of owned generated build/report directories; historical runs remain immutable.",
        ],
    }
    write_json(batch / "summary.json", summary)
    write_json(
        args.output.resolve() / "latest-demo.json",
        {"summary": str(batch / "summary.json")},
    )
    return batch


def main() -> None:
    """Run the bounded native integration batch without Git or remote writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/findings-demo")
    parser.add_argument(
        "--analyzer", type=Path, default=ROOT / "analyzer-core/build/cppulse-analyzer"
    )
    parser.add_argument(
        "--resource-dir",
        type=Path,
        default=os.environ.get("CPPULSE_CLANG_RESOURCE_DIR"),
    )
    args = parser.parse_args()
    if args.resource_dir is None:
        parser.error("Supply --resource-dir or CPPULSE_CLANG_RESOURCE_DIR")
    print(run(args))


if __name__ == "__main__":
    main()
