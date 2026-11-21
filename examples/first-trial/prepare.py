"""Prepare an explicit finite C++ collection request; never build or run tests.

This POSIX example requires the execution-backed CTest adapter's qualified
producer, CTest 3.31.6. Version probes are real setup operations. The public
collector executes the build, inventory and tests later, exactly as declared.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from cppulse.contracts import validate, validate_evaluation_policy
from cppulse.identities import context_identity

FILES = ("CMakeLists.txt", "clamp.h", "checks.cpp")
CONTEXT = "trial-cxx17"


def executable(name: str) -> Path:
    """Resolve an explicitly selected executable without changing PATH."""
    found = shutil.which(name)
    if found is None:
        raise ValueError(f"Executable not found: {name}")
    path = Path(found).resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Executable is not a regular file: {path}")
    return path


def version(tool: Path) -> str:
    """Read the actual setup probe, without relabeling unsupported producers."""
    result = subprocess.run(
        [str(tool), "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    lines = result.stdout.splitlines()
    if not lines:
        raise ValueError(f"Empty version response: {tool}")
    return lines[0]


def step(
    identifier: str,
    argv: list[str],
    inputs: list[str],
    outputs: list[str],
    dependencies: list[str],
    *,
    cwd: str = ".",
) -> dict[str, Any]:
    """Declare argv and finite file identities using existing recipe semantics."""
    return {
        "id": identifier,
        "context_id": CONTEXT,
        "argv": argv,
        "cwd": cwd,
        "depends_on": dependencies,
        "inputs": inputs,
        "outputs": outputs,
        "timeout_seconds": 60,
    }


def documents(
    workspace: Path,
    *,
    compiler: Path,
    compiler_version: str,
    cmake: Path,
    ctest: Path,
    omit_tests: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create declarations only; no result, test count or receipt is fabricated."""
    context = context_identity(
        {
            "id": CONTEXT,
            "compiler": {"name": compiler.name, "version": compiler_version},
            "argv": [str(compiler), "-std=c++17"],
            "working_directory": str(workspace),
            "language_standard": "c++17",
            "target": None,
            "provenance": "observed",
            "dependencies": [],
            "limitations": [
                "Finite authored example on the selected POSIX host/compiler.",
                "Host SDK/header dependency closure is not independently attested.",
            ],
        }
    )
    steps = [
        step(
            "configure",
            [
                str(cmake),
                "-S",
                ".",
                "-B",
                "build",
                f"-DCMAKE_CXX_COMPILER={compiler}",
                "-DCMAKE_BUILD_TYPE=Release",
            ],
            ["CMakeLists.txt"],
            ["build/CMakeCache.txt"],
            [],
        ),
        step(
            "build",
            [str(cmake), "--build", "build", "--parallel", "1"],
            ["build/CMakeCache.txt", "clamp.h", "checks.cpp"],
            ["build/trial-checks"],
            ["configure"],
        ),
    ]
    base_binding = {
        "scope_files": ["clamp.h", "checks.cpp"],
        "report_path": None,
        "adapter": None,
        "adapter_version": None,
        "inventory_step_id": None,
        "producer_version_step_id": None,
        "execution_log_path": None,
        "exercised_inputs": ["build/trial-checks"],
    }
    bindings = [
        {**base_binding, "id": "trial-build", "kind": "build", "step_id": "build"}
    ]
    if not omit_tests:
        steps.extend(
            [
                step("ctest-version", [str(ctest), "--version"], [], [], []),
                step(
                    "inventory",
                    [str(ctest), "--show-only=json-v1"],
                    ["build/trial-checks"],
                    [],
                    ["build"],
                    cwd="build",
                ),
                step(
                    "tests",
                    [str(ctest), "--output-junit", "junit.xml"],
                    ["build/trial-checks"],
                    ["build/junit.xml", "build/Testing/Temporary/LastTest.log"],
                    ["inventory", "ctest-version"],
                    cwd="build",
                ),
            ]
        )
        bindings.append(
            {
                **base_binding,
                "id": "trial-tests",
                "kind": "tests",
                "step_id": "tests",
                "report_path": "build/junit.xml",
                "adapter": "ctest-junit",
                "adapter_version": "1.0.0",
                "inventory_step_id": "inventory",
                "producer_version_step_id": "ctest-version",
                "execution_log_path": "build/Testing/Temporary/LastTest.log",
            }
        )
    request = {
        "version": "2.0.0",
        "id": "first-trial",
        "source": {
            "kind": "header-only",
            "files": list(FILES),
            "inventory_complete": True,
            "limitations": [
                "Completeness is asserted only for these three authored files.",
                "One actual C++17 consumer, not exhaustive library/template coverage.",
            ],
        },
        "contexts": [context],
        "plan": {
            "version": "2.0.0",
            "id": "first-trial-plan",
            "recipe": {
                "version": "2.0.0",
                "id": "first-trial-recipe",
                "contexts": [CONTEXT],
                "jobs": 1,
                "steps": steps,
            },
            "bindings": bindings,
            "limits": {
                "max_log_bytes": 1048576,
                "max_artifact_bytes": 4194304,
                "max_metadata_bytes": 16777216,
                "termination_grace_seconds": 1,
            },
        },
        "normalizers": [],
    }
    policy = {
        "version": "2.0.0",
        "id": "first-trial-tests",
        "policy_version": "1.0.0",
        "evaluator_profile": "1.0.0",
        "standards": [],
        "scope": {"include": ["clamp.h", "checks.cpp"], "exclude": []},
        "contexts": [CONTEXT],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": "tests",
                "title": "Selected consumer tests passed",
                "kind": "test_outcomes",
                "weight": 1,
                "required": True,
                "parameters": {"evidence_ids": ["trial-tests"], "contexts": [CONTEXT]},
                "depends_on": [],
            },
            {
                "id": "context",
                "title": "Selected context was observed",
                "kind": "required_contexts",
                "weight": 1,
                "required": True,
                "parameters": {"contexts": [CONTEXT]},
                "depends_on": [],
            },
        ],
    }
    validate("collection_request", request)
    validate_evaluation_policy(policy)
    return request, policy


def main() -> int:
    """Prepare a fresh workspace after checking explicit local prerequisites."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--compiler", default="c++")
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ctest", default="ctest")
    parser.add_argument("--omit-tests", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.absolute()
    if workspace.exists() or workspace.is_symlink():
        parser.error("Workspace must be a new owned directory; nothing is overwritten")
    try:
        compiler, cmake, ctest = [
            executable(value) for value in [args.compiler, args.cmake, args.ctest]
        ]
        compiler_version = version(compiler)
        cmake_version = version(cmake)
        ctest_version = version(ctest)
        if re.fullmatch(r"ctest version 3\.31\.6", ctest_version) is None:
            raise ValueError(
                f"This execution-backed example requires CTest 3.31.6; got {ctest_version}"
            )
        request, policy = documents(
            workspace,
            compiler=compiler,
            compiler_version=compiler_version,
            cmake=cmake,
            ctest=ctest,
            omit_tests=args.omit_tests,
        )
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    workspace.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        shutil.copyfile(Path(__file__).resolve().parent / name, workspace / name)
    for name, value in [("collection-request.json", request), ("policy.json", policy)]:
        with (workspace / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "prepared_only": True,
                "compiler_version": compiler_version,
                "cmake_version": cmake_version,
                "ctest_version": ctest_version,
                "tests_selected": not args.omit_tests,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
