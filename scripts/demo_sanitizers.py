#!/usr/bin/env python3
"""Execute explicitly synthetic direct GCC sanitizer/CTest material chains.

No repository mutation or upload. Selected recipe execution is recorded by cppulse's
local collector; unsupported runtime startup remains unavailable, never passed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from cppulse.collection import collect
from cppulse.errors import IntegrityError
from cppulse.identities import context_identity, hash_artifact, snapshot_inputs
from cppulse.run_store import RunStore
from cppulse.sanitizers import (
    ObjectSelection,
    SanitizerSelection,
    persist_gcc_sanitizer,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = (
    "clean",
    "bad",
    "plain-object",
    "substituted-binary",
    "zero-tests",
    "all-skipped",
    "prebuilt-gap",
    "prebuilt-gap-bad",
)
FLAGS = {"asan": "address", "ubsan": "undefined", "tsan": "thread"}
KINDS = {"asan": "1", "ubsan": "2", "tsan": "3"}


def write_json(path: Path, value: Any) -> None:
    """Write an actual checkpoint with readable deterministic JSON bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def selected_tools() -> dict[str, str]:
    """Resolve selected actual host tools and record compiler target/version."""
    tools = {}
    for name in ["g++", "nm", "readelf", "ar", "cmake", "ctest"]:
        value = shutil.which(name)
        if value is None:
            raise RuntimeError(f"Required tool is unavailable: {name}")
        tools[name] = str(Path(value).resolve(strict=True))
    for key, args in [
        ("version", ["-dumpfullversion", "-dumpversion"]),
        ("target", ["-dumpmachine"]),
    ]:
        tools[key] = subprocess.check_output(
            [tools["g++"], *args], text=True, timeout=10
        ).strip()
    tools["sha256"] = hash_artifact(
        tools["g++"], "gcc", "gcc", "application/octet-stream"
    )["sha256"]
    return tools


def make_plan(
    workspace: Path, sanitizer: str, scenario: str, tools: dict[str, str]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Construct finite direct compile/link/inspection and actual CTest steps."""
    context_id = "gcc-" + sanitizer
    prebuilt = scenario in {"prebuilt-gap", "prebuilt-gap-bad"}
    cflags = [
        "-std=c++17",
        "-O0",
        "-g",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-pthread",
        "-DCPPULSE_SANITIZER_KIND=" + KINDS[sanitizer],
    ]
    if scenario != "plain-object":
        cflags.append("-fsanitize=" + FLAGS[sanitizer])
    if prebuilt:
        cflags.append("-DCPPULSE_USE_PREBUILT=1")
    compile_argv = [tools["g++"], *cflags, "-c", "main.cpp", "-o", "build/main.o"]
    context = context_identity(
        {
            "id": context_id,
            "provenance": "inferred",
            "compiler": {
                "name": "gcc",
                "version": tools["version"],
                "sha256": tools["sha256"],
            },
            "argv": compile_argv,
            "working_directory": str(workspace),
            "language_standard": "c++17",
            "target": tools["target"],
            "dependencies": [
                {
                    "id": "host-headers-runtime-closure",
                    "sha256": None,
                    "availability": "unavailable",
                }
            ],
            "limitations": [
                "Coarse direct GCC sanitizer job. Retained actual compile/link/inspection and CTest receipts provide selected material proof; general host/runtime closure is unavailable."
            ],
        }
    )
    environment = {
        "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1:symbolize=0:suppressions=:log_path=stderr",
        "UBSAN_OPTIONS": "halt_on_error=0:print_stacktrace=0:symbolize=0:suppressions=:log_path=stderr",
        "TSAN_OPTIONS": "halt_on_error=1:report_bugs=1:exitcode=66:symbolize=0:suppressions=:log_path=stderr",
        "LD_PRELOAD": "",
        "LD_AUDIT": "",
        "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH", ""),
        "LC_ALL": "C",
    }

    def step(
        identifier: str,
        argv: list[str],
        *,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        depends: list[str] | None = None,
        cwd: str = ".",
    ) -> dict[str, Any]:
        return {
            "id": identifier,
            "context_id": context_id,
            "argv": argv,
            "cwd": cwd,
            "depends_on": depends or [],
            "inputs": inputs or [],
            "outputs": outputs or [],
            "timeout_seconds": 60,
            "environment": environment,
        }

    steps = [
        step("compiler-version", [tools["g++"], "-dumpfullversion", "-dumpversion"]),
        step("nm-version", [tools["nm"], "--version"]),
        step("readelf-version", [tools["readelf"], "--version"]),
        step(
            "compile",
            compile_argv,
            inputs=["main.cpp"],
            outputs=["build/main.o"],
            depends=["compiler-version"],
        ),
    ]
    link_inputs = ["build/main.o"]
    link_depends = ["compile"]
    if prebuilt:
        steps.extend(
            [
                step(
                    "compile-prebuilt",
                    [
                        tools["g++"],
                        "-std=c++17",
                        "-O0",
                        "-g",
                        "-fno-pie",
                        "-c",
                        "prebuilt.cpp",
                        "-o",
                        "build/prebuilt.o",
                    ],
                    inputs=["prebuilt.cpp"],
                    outputs=["build/prebuilt.o"],
                    depends=["compiler-version"],
                ),
                step(
                    "archive-prebuilt",
                    [tools["ar"], "rcs", "build/libprebuilt.a", "build/prebuilt.o"],
                    inputs=["build/prebuilt.o"],
                    outputs=["build/libprebuilt.a"],
                    depends=["compile-prebuilt"],
                ),
            ]
        )
        link_inputs.append("build/libprebuilt.a")
        link_depends.append("archive-prebuilt")
    steps.extend(
        [
            step(
                "link",
                [
                    tools["g++"],
                    "-no-pie",
                    "-pthread",
                    "-fsanitize=" + FLAGS[sanitizer],
                    *link_inputs,
                    "-o",
                    "build/app",
                ],
                inputs=link_inputs,
                outputs=["build/app"],
                depends=link_depends,
            ),
            step(
                "nm-object",
                [tools["nm"], "-u", "build/main.o"],
                inputs=["build/main.o"],
                depends=["compile", "nm-version"],
            ),
            step(
                "elf-object",
                [tools["readelf"], "-h", "-S", "-r", "-W", "build/main.o"],
                inputs=["build/main.o"],
                depends=["compile", "readelf-version"],
            ),
            step(
                "elf-binary",
                [tools["readelf"], "-h", "-S", "-d", "-s", "-W", "build/app"],
                inputs=["build/app"],
                depends=["link", "readelf-version"],
            ),
        ]
    )
    selected_binary = "build/app"
    selected_dep = "link"
    if scenario == "substituted-binary":
        steps.extend(
            [
                step(
                    "compile-plain",
                    [
                        tools["g++"],
                        "-std=c++17",
                        "-O0",
                        "-g",
                        "-fno-pie",
                        "-DCPPULSE_SANITIZER_KIND=1",
                        "-c",
                        "main.cpp",
                        "-o",
                        "build/plain.o",
                    ],
                    inputs=["main.cpp"],
                    outputs=["build/plain.o"],
                    depends=["compiler-version"],
                ),
                step(
                    "link-plain",
                    [tools["g++"], "-no-pie", "build/plain.o", "-o", "build/plain-app"],
                    inputs=["build/plain.o"],
                    outputs=["build/plain-app"],
                    depends=["compile-plain"],
                ),
            ]
        )
        selected_binary, selected_dep = "build/plain-app", "link-plain"
    configure = [
        tools["cmake"],
        "-S",
        ".",
        "-B",
        "build",
        "-DCPPULSE_SANITIZER_BINARY=" + str(workspace / selected_binary),
        "-DCPPULSE_SANITIZER_CASE="
        + ("bad" if scenario in {"bad", "prebuilt-gap-bad"} else "clean"),
        "-DCPPULSE_REGISTER_TESTS=" + ("OFF" if scenario == "zero-tests" else "ON"),
        "-DCPPULSE_SKIP_TEST=" + ("ON" if scenario == "all-skipped" else "OFF"),
    ]
    definition = "build/CTestTestfile.cmake"
    steps.extend(
        [
            step(
                "configure",
                configure,
                inputs=["CMakeLists.txt", "CTestCustom.cmake", "CTestCustom.ctest"],
                outputs=[
                    definition,
                    "build/CTestCustom.cmake",
                    "build/CTestCustom.ctest",
                ],
                depends=[selected_dep],
            ),
            step("ctest-version", [tools["ctest"], "--version"]),
            step(
                "inventory",
                [tools["ctest"], "--show-only=json-v1"],
                inputs=[
                    selected_binary,
                    definition,
                    "build/CTestCustom.cmake",
                    "build/CTestCustom.ctest",
                ],
                depends=[selected_dep, "configure"],
                cwd="build",
            ),
            step(
                "tests",
                [tools["ctest"], "--output-on-failure", "--output-junit", "junit.xml"],
                inputs=[
                    selected_binary,
                    definition,
                    "build/CTestCustom.cmake",
                    "build/CTestCustom.ctest",
                ],
                outputs=["build/junit.xml", "build/Testing/Temporary/LastTest.log"],
                depends=["ctest-version", "inventory"],
                cwd="build",
            ),
        ]
    )
    return {
        "version": "2.0.0",
        "id": sanitizer + "-" + scenario,
        "recipe": {
            "version": "2.0.0",
            "id": "synthetic-direct-gcc-sanitizer",
            "jobs": 2,
            "contexts": [context_id],
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
                "id": "sanitizer-tests",
                "step_id": "tests",
                "kind": "tests",
                "scope_files": ["main.cpp", *(["prebuilt.cpp"] if prebuilt else [])],
                "exercised_inputs": [selected_binary],
                "report_path": "build/junit.xml",
                "adapter": "ctest-junit",
                "adapter_version": "1.0.0",
                "inventory_step_id": "inventory",
                "producer_version_step_id": "ctest-version",
                "execution_log_path": "build/Testing/Temporary/LastTest.log",
            }
        ],
    }, [context]


def collect_case(
    directory: Path,
    sanitizer: str,
    scenario: str,
    tools: dict[str, str],
    fixture: Path,
    store: RunStore,
) -> dict[str, Any]:
    """Collect fresh selected fixture commands into original immutable records."""
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    for name in [
        "main.cpp",
        "prebuilt.cpp",
        "CMakeLists.txt",
        "CTestCustom.cmake",
        "CTestCustom.ctest",
    ]:
        shutil.copyfile(fixture / name, workspace / name)
    (workspace / "build").mkdir()
    source = snapshot_inputs(
        workspace,
        [
            "main.cpp",
            "prebuilt.cpp",
            "CMakeLists.txt",
            "CTestCustom.cmake",
            "CTestCustom.ctest",
        ],
        kind="application",
        inventory_complete=False,
    )
    plan, contexts = make_plan(workspace, sanitizer, scenario, tools)
    write_json(directory / "plan.json", plan)
    write_json(directory / "source.json", source)
    write_json(directory / "contexts.json", contexts)
    snapshot = collect(
        plan, workspace=workspace, source=source, contexts=contexts, store=store
    )
    snapshot.verify()
    return {
        "sanitizer": sanitizer,
        "scenario": scenario,
        "workspace": str(workspace),
        "raw_run_id": snapshot.run_id,
        "raw_manifest_sha256": snapshot.manifest_sha256,
        "raw_run_path": str(snapshot.path),
        "collection_status": snapshot.manifest["status"],
    }


def normalize_case(case: dict[str, Any], store: RunStore) -> dict[str, Any]:
    """Normalize pinned original bytes, preserving operational unknowns."""
    snapshot = store.open_run(
        case["raw_run_id"], manifest_sha256=case["raw_manifest_sha256"]
    )
    snapshot.verify()
    selection = SanitizerSelection(
        id=case["sanitizer"] + "-" + case["scenario"],
        sanitizer=case["sanitizer"],
        requested_files=(
            ("main.cpp", "prebuilt.cpp")
            if case["scenario"].startswith("prebuilt-gap")
            else ("main.cpp",)
        ),
        compiler_version_receipt_id="compiler-version",
        nm_version_receipt_id="nm-version",
        readelf_version_receipt_id="readelf-version",
        objects=(ObjectSelection("compile", "nm-object", "elf-object"),),
        link_receipt_id="link",
        runtime_inspection_receipt_id="elf-binary",
        test_evidence_id="sanitizer-tests",
    )
    if case.get("normalized_run_id"):
        if not case.get("normalized_manifest_sha256"):
            raise IntegrityError(
                "Normalized checkpoint lacks its original manifest SHA"
            )
        normalized = store.open_run(
            case["normalized_run_id"],
            manifest_sha256=case["normalized_manifest_sha256"],
        )
    else:
        normalized = persist_gcc_sanitizer(
            snapshot,
            workspace=Path(case["workspace"]),
            store=store,
            selection=selection,
        )
    normalized.verify()
    if any(
        normalized.manifest[key] != snapshot.manifest[key]
        for key in ["source", "config_digest"]
    ):
        raise IntegrityError(
            "Sanitizer checkpoint changed original source/config identity"
        )
    retained = {row["id"]: row for row in normalized.manifest["artifacts"]}
    if any(retained.get(row["id"]) != row for row in snapshot.manifest["artifacts"]):
        raise IntegrityError("Sanitizer checkpoint changed original artifacts")
    artifact = next(
        row
        for row in normalized.manifest["artifacts"]
        if row.get("contract", {}).get("kind") == "sanitizer_facts"
    )
    facts = normalized.read_json(artifact["id"])
    if facts["id"] != selection.id or facts["sanitizer"] != selection.sanitizer:
        raise IntegrityError("Sanitizer checkpoint belongs to another selected case")
    return {
        **case,
        "normalized_run_id": normalized.run_id,
        "normalized_manifest_sha256": normalized.manifest_sha256,
        "normalized_run_path": str(normalized.path),
        "selection": asdict(selection),
        "facts": facts,
    }


def main() -> None:
    """Run fresh actual cases or normalize a manifest-pinned prior collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=ROOT / "demo/sanitizer-fixture")
    parser.add_argument("--output", type=Path, default=ROOT / "output/sanitizer-demo")
    parser.add_argument("--sanitizer", choices=["all", *FLAGS], default="all")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--resume-batch", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.resume_batch:
        summary = json.loads(args.resume_batch.read_text())
        directory = args.resume_batch.parent
        store = RunStore(summary["store"])
    else:
        directory = output / "batches" / uuid4().hex
        directory.mkdir(parents=True)
        store = RunStore(directory / "store")
        tools = selected_tools()
        summary = {
            "label": "Explicitly synthetic GCC sanitizer/CTest selected-input demonstration",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tools": tools,
            "store": str(directory / "store"),
            "cases": [],
            "phase": "collection",
        }
        selected_sans = list(FLAGS) if args.sanitizer == "all" else [args.sanitizer]
        for sanitizer in selected_sans:
            scenarios = (
                SCENARIOS
                if args.scenario == "all" and sanitizer == "asan"
                else (("clean", "bad") if args.scenario == "all" else (args.scenario,))
            )
            for scenario in scenarios:
                case = collect_case(
                    directory / (sanitizer + "-" + scenario),
                    sanitizer,
                    scenario,
                    tools,
                    args.fixture.resolve(),
                    store,
                )
                summary["cases"].append(case)
                write_json(directory / "collection-summary.json", summary)
                print(
                    json.dumps(
                        {
                            "sanitizer": sanitizer,
                            "scenario": scenario,
                            "raw_run_id": case["raw_run_id"],
                            "collection_status": case["collection_status"],
                        }
                    ),
                    flush=True,
                )
    if not args.collect_only:
        for index, case in enumerate(summary["cases"]):
            summary["cases"][index] = normalize_case(case, store)
            write_json(directory / "normalization-summary.json", summary)
            facts = summary["cases"][index]["facts"]
            print(
                json.dumps(
                    {
                        "sanitizer": case["sanitizer"],
                        "scenario": case["scenario"],
                        "outcome": facts["outcome"],
                        "usability": facts["usability"],
                        "diagnostics": len(facts["diagnostics"]),
                        "limitations": facts["limitations"][-1:],
                    }
                ),
                flush=True,
            )
        summary["phase"] = "normalized"
        summary["outcome_counts"] = {
            key: sum(case["facts"]["outcome"] == key for case in summary["cases"])
            for key in ["passed", "failed", "error", "unsupported", "missing"]
        }
    write_json(directory / "summary.json", summary)
    write_json(output / "latest-demo.json", summary)
    print(str(output / "latest-demo.json"))


if __name__ == "__main__":
    main()
