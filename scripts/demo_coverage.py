"""Run a labeled synthetic C++ coverage fixture through explicit local receipts.

This internal review driver never installs tools or modifies Git references.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

from cppulse.collection import collect
from cppulse.identities import context_identity, hash_artifact, snapshot_inputs
from cppulse.run_store import RunSnapshot

SOURCE = """// Explicitly synthetic coverage fixture, not product source or a benchmark.
int choose(int value) {
    if (value > 0) {
        return value + 1;
    }
    return 0;
}
int unused(int value) {
    return value * 2;
}
int main() {
    return choose(1) == 2 ? 0 : 1;
}
"""
JOB = "gcc-coverage-job"


def write_json(path: Path, document: dict[str, Any]) -> None:
    """Retain a deterministic local review document."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")


def selected_tool(value: str) -> str:
    """Select an existing executable explicitly, with no installation fallback."""
    found = shutil.which(value)
    if not found:
        raise RuntimeError(f"Selected executable is unavailable: {value}")
    return str(Path(found).resolve(strict=True))


def prepare_collection(
    directory: Path, *, compiler: str, gcov: str, gcovr: str, cmake: str, ctest: str
) -> tuple[RunSnapshot, Path]:
    """Compile/run one real binary and retain its fresh notes/profiles/reports."""
    workspace = directory / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "build").mkdir()
    (workspace / "tools").mkdir()
    shutil.copyfile(gcov, workspace / "tools/gcov")
    (workspace / "tools/gcov").chmod(0o755)
    (workspace / "main.cpp").write_text(SOURCE)
    (workspace / "coverage.cfg").write_text(
        "# Explicitly empty selected gcovr configuration.\n"
    )
    (workspace / "CMakeLists.txt").write_text(
        'cmake_minimum_required(VERSION 3.16)\nproject(cppulse_coverage_fixture LANGUAGES NONE)\nenable_testing()\nadd_test(NAME coverage-consumer COMMAND "${CMAKE_SOURCE_DIR}/build/app")\n'
    )
    source = snapshot_inputs(
        workspace,
        ["main.cpp", "coverage.cfg", "CMakeLists.txt", "tools/gcov"],
        kind="application",
        inventory_complete=True,
    )
    compile_argv = [
        compiler,
        "--coverage",
        "-O0",
        "-g",
        "-std=c++17",
        "-c",
        "main.cpp",
        "-o",
        "build/main.o",
    ]
    context = context_identity(
        {
            "id": JOB,
            "compiler": {
                "name": "GNU",
                "version": "14.2.0",
                "sha256": hash_artifact(
                    compiler, "compiler", "compiler", "application/octet-stream"
                )["sha256"],
            },
            "argv": compile_argv,
            "working_directory": str(workspace),
            "language_standard": "c++17",
            "target": None,
            "provenance": "inferred",
            "dependencies": [],
            "limitations": [
                "Selected finite synthetic GCC coverage job; host runtime and compiler dependency closure are not inventoried."
            ],
        }
    )

    def step(
        identifier: str,
        argv: list[str],
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        depends: list[str] | None = None,
        cwd: str = ".",
    ) -> dict[str, Any]:
        return {
            "id": identifier,
            "context_id": JOB,
            "argv": argv,
            "cwd": cwd,
            "inputs": inputs or [],
            "outputs": outputs or [],
            "depends_on": depends or [],
            "timeout_seconds": 60,
        }

    copied_gcov = str(workspace / "tools/gcov")
    report_argv = [
        gcovr,
        "--config",
        "coverage.cfg",
        "--root",
        str(workspace),
        "--object-directory",
        str(workspace),
        "--gcov-executable",
        copied_gcov,
        "--no-markers",
        "--lcov-format-version",
        "1.x",
        "--lcov",
        "coverage.info",
        "--cobertura",
        "coverage.xml",
        "build/main.gcda",
    ]
    steps = [
        step("compiler-version", [compiler, "--version"]),
        step("gcov-version", [copied_gcov, "--version"], ["tools/gcov"]),
        step("gcovr-version", [gcovr, "--version"]),
        step(
            "compile",
            compile_argv,
            ["main.cpp"],
            ["build/main.o", "build/main.gcno"],
            ["compiler-version"],
        ),
        step(
            "link",
            [compiler, "--coverage", "build/main.o", "-o", "build/app"],
            ["build/main.o"],
            ["build/app"],
            ["compile"],
        ),
        step(
            "configure-tests",
            [cmake, "-S", ".", "-B", "test-build"],
            ["CMakeLists.txt"],
            ["test-build/CTestTestfile.cmake", "test-build/CMakeCache.txt"],
        ),
        step("ctest-version", [ctest, "--version"]),
        step(
            "ctest-inventory",
            [ctest, "--show-only=json-v1"],
            ["build/app", "test-build/CTestTestfile.cmake"],
            depends=["link", "configure-tests"],
            cwd="test-build",
        ),
        step(
            "tests",
            [ctest, "--output-on-failure", "--output-junit", "junit.xml"],
            ["build/app", "test-build/CTestTestfile.cmake"],
            [
                "build/main.gcda",
                "test-build/junit.xml",
                "test-build/Testing/Temporary/LastTest.log",
            ],
            ["ctest-version", "ctest-inventory"],
            "test-build",
        ),
        step(
            "coverage-report",
            report_argv,
            [
                "main.cpp",
                "tools/gcov",
                "coverage.cfg",
                "build/main.gcno",
                "build/main.gcda",
            ],
            ["coverage.info", "coverage.xml"],
            ["compile", "tests", "gcovr-version", "gcov-version"],
        ),
    ]
    binding = {
        "id": "coverage-tests",
        "step_id": "tests",
        "kind": "tests",
        "scope_files": ["main.cpp"],
        "exercised_inputs": ["build/app"],
        "report_path": "test-build/junit.xml",
        "execution_log_path": "test-build/Testing/Temporary/LastTest.log",
        "adapter": "ctest-junit",
        "adapter_version": "1.0.0",
        "inventory_step_id": "ctest-inventory",
        "producer_version_step_id": "ctest-version",
    }
    plan = {
        "version": "2.0.0",
        "id": "synthetic-gcc-coverage",
        "recipe": {
            "version": "2.0.0",
            "id": "gcc14-gcovr88-coverage",
            "jobs": 1,
            "contexts": [JOB],
            "steps": steps,
        },
        "bindings": [binding],
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 67108864,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 1,
        },
    }
    snapshot = collect(
        plan,
        workspace=workspace,
        source=source,
        contexts=[context],
        store=directory / "store",
    )
    snapshot.verify()
    return snapshot, workspace


def roles(snapshot: RunSnapshot, adapter: str) -> dict[str, Any]:
    """Resolve original role IDs from the checked observed path bindings."""
    facts = [
        snapshot.read_json(entry["id"])
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "execution_facts"
    ]
    by_receipt = {row["receipt"]["id"]: row for row in facts}

    def bound(receipt: str, direction: str, path: str) -> str:
        return next(
            row["artifact_id"]
            for row in by_receipt[receipt]["binding"][direction + "_artifacts"]
            if row["path"] == path
        )

    evidence = [
        snapshot.read_json(entry["id"])
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == "evidence"
    ]
    return {
        "receipt_id": "coverage-report",
        "report_artifact_id": bound(
            "coverage-report",
            "output",
            "coverage.info" if adapter == "lcov" else "coverage.xml",
        ),
        "adapter": adapter,
        "producer_version_receipt_id": "gcovr-version",
        "gcov_version_receipt_id": "gcov-version",
        "compiler_version_receipt_id": "compiler-version",
        "configuration_artifact_id": bound("coverage-report", "input", "coverage.cfg"),
        "gcov_artifact_id": bound("coverage-report", "input", "tools/gcov"),
        "proof_receipt_ids": [row["receipt"]["id"] for row in facts],
        "test_evidence_ids": [
            row["id"]
            for document in evidence
            for row in document["records"]
            if row["kind"] == "tests"
        ],
        "instrumentation": [
            {
                "object_artifact_id": bound("compile", "output", "build/main.o"),
                "mapping_artifact_id": bound("compile", "output", "build/main.gcno"),
                "source_files": ["main.cpp"],
            }
        ],
        "profiles": [
            {
                "artifact_id": bound("tests", "output", "build/main.gcda"),
                "binary_artifact_id": bound("link", "output", "build/app"),
                "test_receipt_id": "tests",
            }
        ],
    }


def main() -> None:
    """Run collection, optionally followed by gated typed coverage normalization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/coverage-demo"))
    parser.add_argument("--compiler", default="g++-14")
    parser.add_argument("--gcov", default="gcov-14")
    parser.add_argument("--gcovr", required=True)
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ctest", default="ctest")
    parser.add_argument("--collection-only", action="store_true")
    arguments = parser.parse_args()
    directory = arguments.output.resolve() / uuid4().hex
    snapshot, workspace = prepare_collection(
        directory,
        **{
            key: selected_tool(getattr(arguments, key))
            for key in ["compiler", "gcov", "gcovr", "cmake", "ctest"]
        },
    )
    summary: dict[str, Any] = {
        "fixture": "explicitly synthetic, actual compiler/test/coverage execution",
        "raw_run_id": snapshot.run_id,
        "raw_manifest_sha256": snapshot.manifest_sha256,
        "workspace": str(workspace),
        "store": str(directory / "store"),
        "raw_status": snapshot.manifest["status"],
        "roles": {
            adapter: roles(snapshot, adapter) for adapter in ["lcov", "cobertura"]
        },
    }
    if not arguments.collection_only:
        from cppulse.coverage import persist_coverage

        for adapter in ["lcov", "cobertura"]:
            derived = persist_coverage(
                snapshot,
                workspace=workspace,
                store=directory / "store",
                **summary["roles"][adapter],
            )
            derived.verify()
            document = next(
                derived.read_json(entry["id"])
                for entry in derived.manifest["artifacts"]
                if entry.get("contract", {}).get("kind") == "coverage_facts"
            )
            counts = {
                row["kind"]: {
                    "covered": row["covered"],
                    "total": row["total"],
                    "method": row["method"],
                }
                for row in document["files"][0]["measurements"]
            }
            expected = {"line": (5, 8), "branch": (1, 2)}
            if adapter == "lcov":
                expected["function"] = (2, 3)
            if {
                kind: (row["covered"], row["total"]) for kind, row in counts.items()
            } != expected:
                raise RuntimeError(
                    "Actual fixture coverage differs from its explicitly checked expected counters"
                )
            if any(
                entry not in derived.manifest["artifacts"]
                for entry in snapshot.manifest["artifacts"]
            ):
                raise RuntimeError(
                    "Coverage publication changed a parent artifact descriptor"
                )
            summary[adapter] = {
                "run_id": derived.run_id,
                "manifest_sha256": derived.manifest_sha256,
                "coverage_facts_id": document["id"],
                "counts": counts,
            }
    write_json(directory / "summary.json", summary)
    write_json(arguments.output.resolve() / "latest-demo.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
