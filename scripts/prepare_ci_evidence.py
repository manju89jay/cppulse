#!/usr/bin/env python3
"""Prepare genuine local producer inputs for the root evidence contract tests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import cppulse
from cppulse.adapters.test_results import parse_test_report
from cppulse.consumer import normalize_consumer_usage
from cppulse.coverage import normalize_coverage
from cppulse.run_store import RunStore
from cppulse.workflows import (
    collect_request,
    ensure_current_materials,
    read_documents,
)


SANITIZERS = {
    "asan-clean": "passed",
    "asan-bad": "failed",
    "ubsan-clean": "passed",
    "ubsan-bad": "failed",
    "tsan-clean": "passed",
    "tsan-bad": "failed",
    "asan-zero-tests": "unsupported",
    "asan-plain-object": "unsupported",
    "asan-substituted-binary": "unsupported",
    "asan-all-skipped": "unsupported",
    "asan-prebuilt-gap": "unsupported",
    "asan-prebuilt-gap-bad": "failed",
}

COUNTS = {
    "clean": (2, 2, 0, 0, 0),
    "fail": (1, 0, 1, 0, 0),
    "skip": (1, 0, 0, 1, 0),
    "disabled": (1, 0, 0, 1, 0),
    "zero": (0, 0, 0, 0, 0),
    "pytest": (3, 1, 1, 1, 0),
}


def read(path):
    return json.loads(path.read_bytes())


def write(path, document):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


def sha256(body):
    return hashlib.sha256(body).hexdigest()


def command(cwd, name, argv, expected=0):
    result = subprocess.run(
        argv, cwd=cwd, capture_output=True, timeout=120, check=False
    )
    (cwd / f"{name}.stdout").write_bytes(result.stdout)
    (cwd / f"{name}.stderr").write_bytes(result.stderr)
    write(
        cwd / f"{name}.json",
        {"argv": [str(arg) for arg in argv], "exit": result.returncode},
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"{name} exited {result.returncode}, expected {expected}. See {cwd}."
        )
    return result.stdout


def descriptor(store, workspace, pin):
    return {
        "store": str(store),
        "workspace": str(workspace),
        "run_id": pin["run_id"],
        "manifest_sha256": pin["manifest_sha256"],
    }


def verify_snapshot(row):
    store = RunStore.open_existing(row["store"])
    run = store.open_run(row["run_id"], manifest_sha256=row["manifest_sha256"])
    ensure_current_materials(run, Path(row["workspace"]))
    return run


def checked_coverage(checkout, coverage, console):
    summary = read(coverage / "latest-demo.json")
    policy = read(coverage / "policy-input.json")
    store = Path(summary["store"]).resolve(strict=True)
    workspace = Path(summary["workspace"]).resolve(strict=True)
    if not (store.is_relative_to(coverage) and workspace.is_relative_to(coverage)):
        raise ValueError("Coverage source and store must belong to the declared output")
    if Path(policy.pop("console")).resolve(
        strict=True
    ) != console or policy != descriptor(store, workspace, summary["lcov"]):
        raise ValueError("Policy descriptor does not select this coverage and console")
    row = descriptor(
        store,
        workspace,
        {
            "run_id": summary["raw_run_id"],
            "manifest_sha256": summary["raw_manifest_sha256"],
        },
    )
    raw = verify_snapshot(row)
    roles = runpy.run_path(str(checkout / "scripts/demo_coverage.py"))["roles"]
    for adapter in ("lcov", "cobertura"):
        selection = roles(raw, adapter)
        if selection != summary["roles"][adapter]:
            raise ValueError(f"Coverage summary changed the observed {adapter} roles")
        fact = normalize_coverage(raw, **selection)
        child = verify_snapshot(descriptor(store, workspace, summary[adapter]))
        expected = {"line": (5, 8), "branch": (1, 2)}
        if adapter == "lcov":
            expected["function"] = (2, 3)
        measurements = {
            item["kind"]: (item["covered"], item["total"])
            for file in fact["files"]
            for item in file["measurements"]
        }
        if (
            fact["origin"] != "execution"
            or fact["context_id"] != "gcc-coverage-job"
            or fact["usability"] != "usable"
            or measurements != expected
            or read_documents(child)["coverage_facts"] != [fact]
        ):
            raise ValueError(f"Unexpected real {adapter} coverage or normalized child")
    return row


def header_input(approved, output):
    root = approved / "fr-evd-07/executed"
    workspace = output / "header"
    shutil.copytree(root / "input", workspace)
    (workspace / "build").mkdir()
    plan = runpy.run_path(str(root / "run.py"))["request_document"](workspace)
    depfiles = {"consumer": "build/main.d", "selfcontained": "build/self.d"}
    # EVD116 selects these depfile paths from the actual compiler receipts.
    for step in plan["plan"]["recipe"]["steps"]:
        if step["id"] in depfiles:
            index = step["argv"].index("-MF") + 1
            old = step["argv"][index]
            new = depfiles[step["id"]]
            step["argv"][index] = new
            step["outputs"][step["outputs"].index(old)] = new
    store = output / "header-store"
    write(output / "header-request.json", plan)
    result = collect_request(plan, workspace=workspace, store=store)
    write(output / "header-collection.json", result)
    if result["exit_code"] != 0 or result["status"] != "completed":
        raise RuntimeError("Selected header collection failed")
    row = descriptor(store, workspace, result["final_run"])
    run = verify_snapshot(row)
    facts = {
        fact["receipt"]["id"]: fact for fact in read_documents(run)["execution_facts"]
    }
    for name, path in {**depfiles, "tests": "build/junit.xml"}.items():
        (item,) = [
            item
            for item in facts[name]["binding"]["output_artifacts"]
            if item["path"] == path
        ]
        if run.read_bytes(item["artifact_id"]) != (workspace / path).read_bytes():
            raise ValueError(f"Header {name} material changed after collection")
    return row, workspace / "build/junit.xml"


def junit_inputs(approved, output, clean, tools):
    fixture = approved / "fr-evd-01/executed"
    reports = {"clean": clean}
    exits = {"clean": 0, "fail": 8, "skip": 0, "disabled": 0, "zero": 0, "pytest": 1}
    for mode in ("fail", "skip", "disabled", "zero"):
        workspace = output / f"junit-{mode}"
        workspace.mkdir()
        cmakelists = workspace / "CMakeLists.txt"
        if mode == "disabled":
            shutil.copyfile(fixture / "fixture-disabled.cmake", cmakelists)
        else:
            exit_code = {"fail": 1, "skip": 77, "zero": 0}[mode]
            (workspace / "main.cpp").write_text(
                f"int main() {{ return {exit_code}; }}\n"
            )
            body = (
                "cmake_minimum_required(VERSION 3.16)\n"
                "project(junit_fixture LANGUAGES CXX)\n"
                "add_executable(app main.cpp)\n"
                "enable_testing()\n"
            )
            if mode != "zero":
                body += "add_test(NAME actual-case COMMAND app)\n"
            if mode == "skip":
                body += (
                    "set_tests_properties(actual-case PROPERTIES SKIP_RETURN_CODE 77)\n"
                )
            cmakelists.write_text(body)
        cmake, ctest = tools["cmake"], tools["ctest"]
        command(workspace, "configure", [cmake, "-S", ".", "-B", "build"])
        if mode != "disabled":
            command(workspace, "build", [cmake, "--build", "build"])
        build = workspace / "build"
        command(build, "inventory", [ctest, "--show-only=json-v1"])
        command(build, "execute", [ctest, "--output-junit", "junit.xml"], exits[mode])
        reports[mode] = build / "junit.xml"

    workspace = output / "junit-pytest"
    workspace.mkdir()
    shutil.copyfile(fixture / "fixture-pytest.py", workspace / "test_fixture.py")
    command(
        workspace,
        "execute",
        [
            sys.executable,
            "-m",
            "pytest",
            "-c",
            "/dev/null",
            "-p",
            "no:cacheprovider",
            "--junitxml=junit.xml",
            "test_fixture.py",
        ],
        exits["pytest"],
    )
    reports["pytest"] = workspace / "junit.xml"
    rows = []
    for mode, fields in COUNTS.items():
        path = reports[mode]
        producer = (
            {"name": "pytest", "version": "8.0.0"}
            if mode == "pytest"
            else {"name": "ctest", "version": "3.31.6"}
        )
        adapter = "generic-junit" if mode == "pytest" else "ctest-junit"
        counts = dict(zip(("total", "passed", "failed", "skipped", "errors"), fields))
        parsed = parse_test_report(path, adapter, producer=producer)
        if parsed.usability != "usable" or parsed.counts != counts:
            raise RuntimeError(
                f"Unexpected actual JUnit counts for {mode}: {parsed.counts}"
            )
        rows.append(
            {
                "mode": mode,
                "path": str(path),
                "sha256": sha256(path.read_bytes()),
                "adapter": adapter,
                "producer": producer,
                "counts": counts,
                "native_exit": exits[mode],
            }
        )
    return rows


def sanitizer_inputs(checkout, output, driver, tools):
    store = RunStore(output / "sanitizer-store")
    fixture = checkout / "demo/sanitizer-fixture"
    rows = []
    for case, outcome in SANITIZERS.items():
        family, scenario = case.split("-", 1)
        print(f"Collecting actual sanitizer case {case}", flush=True)
        target = output / f"sanitizer-{case}"
        actual = driver["collect_case"](target, family, scenario, tools, fixture, store)
        write(target / "collection.json", actual)
        plan = target / "plan.json"
        row = descriptor(
            store.root,
            actual["workspace"],
            {
                "run_id": actual["raw_run_id"],
                "manifest_sha256": actual["raw_manifest_sha256"],
            },
        )
        verify_snapshot(row)
        rows.append(
            {
                **row,
                "case": case,
                "sanitizer": family,
                "requested_files": (
                    ["main.cpp", "prebuilt.cpp"]
                    if "prebuilt-gap" in case
                    else ["main.cpp"]
                ),
                "expected_fact": None,
                "expected_outcome": outcome,
                "expected_usability": (
                    "unsupported" if outcome == "unsupported" else "usable"
                ),
                "recipe_id": "synthetic-direct-gcc-sanitizer",
                "recipe_version": "2.0.0",
                "plan": str(plan),
            }
        )
    return str(store.root), rows


def archive_input(checkout, output):
    workspace = output / "archive"
    workspace.mkdir()
    helper = runpy.run_path(str(checkout / "tests/test_consumer_usage.py"))
    capture = helper["collect_actual_use"](workspace)
    snapshot = capture["snapshot"]
    row = descriptor(
        workspace / "store",
        workspace,
        {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256},
    )
    verify_snapshot(row)
    roles, subject = capture["roles"], capture["subject"]
    usage = normalize_consumer_usage(
        snapshot,
        subject,
        usage_id="actual-package-use",
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
        link_map_artifact_id=roles["build/main.map"],
    )
    receipts = capture["facts"]
    expected_steps = {
        "library",
        "archive",
        "configuration",
        "target",
        "consumer",
        "execute",
    }
    if set(receipts) != expected_steps or any(
        fact["receipt"]["status"] != "passed" or fact["receipt"]["exit_code"] != 0
        for fact in receipts.values()
    ):
        raise RuntimeError("Real archive build or executable failed")
    executed = receipts["execute"]["receipt"]
    return {
        **row,
        "status": executed["status"],
        "exit_status": executed["exit_code"],
        "roles": roles,
        "subject": subject,
        "observed_usage": usage,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coverage", type=Path, required=True)
    parser.add_argument("--console", type=Path, required=True)
    args = parser.parse_args()
    checkout, coverage, console = (
        path.resolve(strict=True)
        for path in (args.checkout, args.coverage, args.console)
    )
    output = args.output.resolve()
    output.mkdir()
    approved = checkout / "docs/checkpoints/current/qualification"
    raw_coverage = checked_coverage(checkout, coverage, console)
    command(output, "console", [console, "--help"])
    driver = runpy.run_path(str(checkout / "scripts/demo_sanitizers.py"))
    tools = driver["selected_tools"]()
    write(
        output / "tools.json",
        {
            **tools,
            "console": str(console),
            "console_sha256": sha256(console.read_bytes()),
            "python": sys.executable,
            "cppulse_module": str(Path(cppulse.__file__).resolve()),
        },
    )
    if (tools["version"], tools["target"]) != ("14.2.0", "x86_64-linux-gnu"):
        raise RuntimeError(
            "Required real GNU G++ 14.2.0 x86_64-linux-gnu is unavailable"
        )
    for name in ("cmake", "ctest"):
        version = command(output, f"{name}-version", [tools[name], "--version"])
        if version.splitlines()[0] != f"{name} version 3.31.6".encode():
            raise RuntimeError(f"Required real {name} 3.31.6 is unavailable")
    pytest_version = command(
        output, "pytest-version", [sys.executable, "-m", "pytest", "--version"]
    )
    if pytest_version.strip() != b"pytest 8.0.0":
        raise RuntimeError("Required real pytest 8.0.0 is unavailable")
    header, clean = header_input(approved, output)
    junit = junit_inputs(approved, output, clean, tools)
    archive = archive_input(checkout, output)
    sanitizer_store, cases = sanitizer_inputs(checkout, output, driver, tools)
    target = output / "evidence116-input.json"
    write(
        target,
        {
            "console": str(console),
            "coverage": raw_coverage,
            "header": header,
            "junit": junit,
            "archive": archive,
            "sanitizer_store": sanitizer_store,
            "sanitizer_cases": cases,
        },
    )
    print(target)


if __name__ == "__main__":
    main()
