"""Run transparent synthetic CMake/CTest collection cases; no policy is evaluated."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from cppulse.collection import collect
from cppulse.errors import IntegrityError
from cppulse.identities import context_identity, hash_artifact, snapshot_inputs
from cppulse.run_store import RunStore

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("clean", "failed-test", "failed-build", "missing-report")
SOURCE_FILES = [
    "CMakeLists.txt",
    "include/cppulse_demo/sum.hpp",
    "src/sum.cpp",
    "tests/consumer.cpp",
]


def selected_tool(name: str) -> str:
    """Select an existing host tool without installing or guessing dependencies."""
    selected = shutil.which(name)
    if selected is None:
        raise RuntimeError(f"Required demo tool is unavailable: {name}")
    return str(Path(selected).resolve(strict=True))


def run_case(
    scenario: str, directory: Path, store: RunStore, tools: dict[str, str]
) -> dict[str, Any]:
    """Build one explicitly selected fixture and validate its observed outcome."""
    workspace = directory / "workspace"
    shutil.copytree(ROOT / "demo/evidence-fixture", workspace)
    context_id = "gcc-cxx17"
    configure = [
        tools["cmake"],
        "-S",
        ".",
        "-B",
        "build",
        "-DCMAKE_BUILD_TYPE=Release",
        f"-DCMAKE_CXX_COMPILER={tools['compiler']}",
        "-DCPPULSE_DEMO_COMPILE_ERROR="
        + ("ON" if scenario == "failed-build" else "OFF"),
        "-DCPPULSE_DEMO_FAIL_TEST=" + ("ON" if scenario == "failed-test" else "OFF"),
    ]
    context = context_identity(
        {
            "id": context_id,
            "compiler": {
                "name": "GNU",
                "version": tools["compiler_version"],
                "sha256": hash_artifact(
                    tools["compiler"],
                    "compiler",
                    "compiler",
                    "application/octet-stream",
                )["sha256"],
            },
            "argv": configure,
            "working_directory": ".",
            "language_standard": "c++17",
            "target": tools["compiler_target"],
            "provenance": "inferred",
            "dependencies": [
                {
                    "id": "host-compiler-headers-and-runtime",
                    "sha256": None,
                    "availability": "unavailable",
                }
            ],
            "limitations": [
                "This build-context declaration records the selected configure command, not a complete observed per-translation-unit compiler command or dependency closure. Actual compile_commands.json is retained separately."
            ],
        }
    )

    def step(
        name: str,
        argv: list[str],
        *,
        cwd: str = ".",
        dependencies: list[str] | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": name,
            "context_id": context_id,
            "argv": argv,
            "cwd": cwd,
            "depends_on": dependencies or [],
            "inputs": inputs or [],
            "outputs": outputs or [],
            "timeout_seconds": 60,
        }

    binary = "build/cppulse-demo-consumer"
    archive = "build/libcppulse-demo.a"
    definition = "build/CTestTestfile.cmake"
    test_report = "build/junit.xml"
    execution_log = "build/Testing/Temporary/LastTest.log"
    steps = [
        step(
            "configure",
            configure,
            inputs=SOURCE_FILES,
            outputs=["build/CMakeCache.txt", "build/compile_commands.json", definition],
        ),
        step(
            "build",
            [tools["cmake"], "--build", "build", "--parallel", "2"],
            dependencies=["configure"],
            inputs=SOURCE_FILES + ["build/CMakeCache.txt"],
            outputs=[binary, archive],
        ),
        step("ctest-version", [tools["ctest"], "--version"]),
        step(
            "ctest-inventory",
            [tools["ctest"], "--show-only=json-v1"],
            cwd="build",
            dependencies=["build"],
            inputs=[binary, definition],
        ),
        step(
            "tests",
            [
                tools["ctest"],
                "--output-on-failure",
                "--output-junit",
                "unretained.xml" if scenario == "missing-report" else "junit.xml",
            ],
            cwd="build",
            dependencies=["ctest-version", "ctest-inventory"],
            inputs=[binary, definition],
            outputs=[test_report, execution_log],
        ),
    ]
    common = {"scope_files": SOURCE_FILES}
    plan = {
        "version": "2.0.0",
        "id": "synthetic-" + scenario,
        "recipe": {
            "version": "2.0.0",
            "id": "synthetic-cmake-ctest",
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
                "id": "synthetic-build",
                "step_id": "build",
                "kind": "build",
                **common,
                "exercised_inputs": [binary, archive],
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
    source = snapshot_inputs(
        workspace, SOURCE_FILES, kind="library", inventory_complete=True
    )
    for name, document in [("plan", plan), ("source", source), ("context", context)]:
        (directory / f"{name}.json").write_text(
            json.dumps(document, indent=2), encoding="utf-8"
        )
    snapshot = collect(
        plan, workspace=workspace, source=source, contexts=[context], store=store
    )
    snapshot.verify()
    evidence_entry = next(
        item
        for item in snapshot.manifest["artifacts"]
        if item.get("contract", {}).get("kind") == "evidence"
    )
    evidence = snapshot.read_json(evidence_entry["id"])
    observed = {
        item["id"]: {"status": item["status"], "usability": item["usability"]}
        for item in evidence["records"]
    }
    expected = {
        "clean": ("completed", "passed", "passed", "usable"),
        "failed-test": ("completed", "passed", "failed", "usable"),
        "failed-build": ("completed", "failed", "skipped", "missing"),
        "missing-report": ("partial", "passed", "error", "missing"),
    }[scenario]
    actual = (
        snapshot.manifest["status"],
        observed["synthetic-build"]["status"],
        observed["synthetic-tests"]["status"],
        observed["synthetic-tests"]["usability"],
    )
    if actual != expected:
        raise AssertionError(
            f"{scenario} observed {actual}, expected {expected}; inspect {snapshot.path}"
        )
    return {
        "scenario": scenario,
        "run_id": snapshot.run_id,
        "run_path": str(snapshot.path),
        "status": snapshot.manifest["status"],
        "input_verification": snapshot.manifest["input_verification"],
        "evidence": observed,
        "workspace": str(workspace),
        "context_provenance": "inferred",
    }


def main() -> None:
    """Run selected local fixture commands; preserve every previous demo batch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/collection-demo")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all")
    args = parser.parse_args()
    output = args.output.resolve()
    batch = output / "batches" / uuid4().hex
    batch.mkdir(parents=True)
    tools = {
        "cmake": selected_tool("cmake"),
        "ctest": selected_tool("ctest"),
        "compiler": selected_tool("g++"),
    }
    probes = [
        [tools["compiler"], "-dumpfullversion", "-dumpversion"],
        [tools["compiler"], "-dumpmachine"],
    ]
    for key, command in zip(["compiler_version", "compiler_target"], probes):
        tools[key] = subprocess.check_output(command, text=True, timeout=10).strip()
    (batch / "tools.json").write_text(
        json.dumps({"tools": tools, "inspection_commands": probes}, indent=2),
        encoding="utf-8",
    )
    store = RunStore(output / "store")
    cases = []
    for scenario in SCENARIOS if args.scenario == "all" else [args.scenario]:
        directory = batch / scenario
        directory.mkdir()
        cases.append(run_case(scenario, directory, store, tools))
    if store.format_version == "3.0.0":
        _, latest_completed, latest_attempt = store.resolve_heads()
    else:
        latest_attempt = store.resolve_latest_attempt()
        latest_completed = (
            store.resolve_latest() if (store.root / "latest.json").exists() else None
        )
    if latest_attempt is None:
        raise IntegrityError("Collection fixture did not publish an attempt")
    summary = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "batch": str(batch),
        "store": str(store.root),
        "cases": cases,
        "latest_attempt": latest_attempt.run_id,
        "latest_completed_collection": (
            latest_completed.run_id if latest_completed is not None else None
        ),
        "limitations": [
            "Clearly labeled synthetic fixture, selected GCC/CMake/CTest only; this is not a benchmark, policy assessment, certification or whole-program verification.",
            "Compiler context is declared/inferred; actual per-file compile commands are retained. Source verification covers the selected finite input inventory.",
        ],
    }
    (batch / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "latest-demo.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
