"""Collection integration retains execution facts without inventing verification."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from cppulse.collection import collect
from cppulse.errors import ContractError
from cppulse.identities import context_identity, snapshot_inputs


def documents(snapshot: Any, kind: str) -> list[dict[str, Any]]:
    """Read typed run artifacts through their frozen descriptors."""
    return [
        snapshot.read_json(entry["id"])
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == kind
    ]


def build_plan(
    workspace: Path, script: str, *, output: str = "build/app", exit_code: int = 0
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Declare a local fixture command with no global-tool discovery."""
    (workspace / "source.cpp").write_text("int value() { return 1; }\n")
    (workspace / "build.py").write_text(script + f"\nraise SystemExit({exit_code})\n")
    context = context_identity(
        {
            "id": "local",
            "compiler": {"name": "fixture", "version": "1"},
            "argv": [sys.executable],
            "working_directory": str(workspace),
            "language_standard": "c++17",
            "target": None,
            "provenance": "observed",
            "dependencies": [],
            "limitations": ["Synthetic local command fixture."],
        }
    )
    source = snapshot_inputs(
        workspace, ["source.cpp", "build.py"], inventory_complete=True
    )
    plan = {
        "version": "2.0.0",
        "id": "local-plan",
        "recipe": {
            "version": "2.0.0",
            "id": "local-recipe",
            "jobs": 1,
            "contexts": ["local"],
            "steps": [
                {
                    "id": "build",
                    "context_id": "local",
                    "argv": [sys.executable, "build.py"],
                    "cwd": ".",
                    "depends_on": [],
                    "inputs": ["build.py", "source.cpp"],
                    "outputs": [output],
                    "timeout_seconds": 10,
                }
            ],
        },
        "bindings": [
            {
                "id": "build-proof",
                "step_id": "build",
                "kind": "build",
                "scope_files": ["source.cpp"],
                "report_path": None,
                "adapter": None,
                "adapter_version": None,
                "inventory_step_id": None,
                "producer_version_step_id": None,
                "execution_log_path": None,
                "exercised_inputs": [output],
            }
        ],
        "limits": {
            "max_log_bytes": 4096,
            "max_artifact_bytes": 65536,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 0.1,
        },
    }
    return plan, source, [context]


def test_collect_retains_typed_plan_and_observed_build(tmp_path: Path) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_bytes(b'fixture artifact')\nprint('actual build')",
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    snapshot.verify()
    assert snapshot.manifest["status"] == "completed"
    assert snapshot.manifest["input_verification"] == "verified"
    assert documents(snapshot, "collection_plan") == [plan]
    assert documents(snapshot, "execution_receipt")[0]["status"] == "passed"
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] == "usable"


def test_missing_successful_output_is_partial_without_changing_receipt(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(tmp_path, "print('exit zero without artifact')")
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "execution_receipt")[0]["status"] == "passed"
    record = documents(snapshot, "evidence")[0]["records"][0]
    assert record["status"] == "error" and record["usability"] == "missing"


def test_invalid_plan_never_runs_command(tmp_path: Path) -> None:
    plan, source, contexts = build_plan(
        tmp_path, "from pathlib import Path\nPath('marker').touch()"
    )
    plan["bindings"][0]["scope_files"] = ["unselected.cpp"]
    with pytest.raises(ContractError):
        collect(
            plan,
            workspace=tmp_path,
            source=source,
            contexts=contexts,
            store=tmp_path / "store",
        )
    assert not (tmp_path / "marker").exists()


def test_normal_failed_build_retains_usable_failure_and_independent_results(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path, "print('intentional build failure')", exit_code=3
    )
    for name, dependency in [("dependent", ["build"]), ("independent", [])]:
        plan["recipe"]["steps"].append(
            {
                "id": name,
                "context_id": "local",
                "argv": [
                    sys.executable,
                    "-c",
                    f"from pathlib import Path; Path('{name}').write_text('observed artifact')",
                ],
                "cwd": ".",
                "depends_on": dependency,
                "inputs": [],
                "outputs": [name],
                "timeout_seconds": 10,
            }
        )
        plan["bindings"].append(
            {
                **deepcopy(plan["bindings"][0]),
                "id": name + "-proof",
                "step_id": name,
                "exercised_inputs": [name],
            }
        )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    receipts = {
        record["id"]: record for record in documents(snapshot, "execution_receipt")
    }
    records = {
        record["id"]: record for record in documents(snapshot, "evidence")[0]["records"]
    }
    assert snapshot.manifest["status"] == "completed"
    assert (
        receipts["build"]["status"] == "failed" and receipts["build"]["exit_code"] == 3
    )
    assert (
        records["build-proof"]["status"] == "failed"
        and records["build-proof"]["usability"] == "usable"
    )
    assert (
        receipts["dependent"]["status"] == "skipped"
        and not (tmp_path / "dependent").exists()
    )
    assert records["independent-proof"]["status"] == "passed"


def test_oversize_binary_is_not_retained_as_a_binary_claim(tmp_path: Path) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_bytes(b'x' * 5000)",
    )
    plan["limits"]["max_artifact_bytes"] = 1024
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert all(
        entry["size_bytes"] <= 1024
        for entry in snapshot.manifest["artifacts"]
        if entry["media_type"] == "application/octet-stream"
    )
    assert any(
        "max_artifact_bytes" in limitation
        for limitation in snapshot.manifest["limitations"]
    )
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] != "usable"


def test_source_changed_before_collection_does_not_execute(tmp_path: Path) -> None:
    plan, source, contexts = build_plan(
        tmp_path, "from pathlib import Path\nPath('marker').touch()"
    )
    (tmp_path / "source.cpp").write_text("changed after source snapshot\n")
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert not (tmp_path / "marker").exists()
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert documents(snapshot, "execution_receipt")[0]["status"] == "not_attempted"
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] == "stale"


def test_source_mutation_retains_process_success_as_stale_facts(tmp_path: Path) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('source.cpp').write_text('changed by selected command')\nPath('build').mkdir()\nPath('build/app').write_text('output')",
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    assert documents(snapshot, "execution_receipt")[0]["status"] == "passed"
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] == "stale"


def test_unchanged_cached_output_cannot_pass_build_verification(tmp_path: Path) -> None:
    plan, source, contexts = build_plan(tmp_path, "print('no-op build')")
    (tmp_path / "build").mkdir()
    (tmp_path / "build/app").write_text("preexisting cache")
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "execution_receipt")[0]["status"] == "passed"
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] != "usable"


def test_preselected_cancellation_is_retained_without_execution(tmp_path: Path) -> None:
    from cppulse.execution import CancellationToken

    plan, source, contexts = build_plan(
        tmp_path, "from pathlib import Path\nPath('marker').touch()"
    )
    token = CancellationToken()
    token.cancel()
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
        cancel=token,
    )
    assert snapshot.manifest["status"] == "cancelled"
    assert not (tmp_path / "marker").exists()
    assert documents(snapshot, "execution_receipt")[0]["status"] == "cancelled"
    assert not (tmp_path / "store/latest.json").exists()


def ctest_fixture(
    workspace: Path,
    *,
    fail_test: bool = False,
    compile_error: bool = False,
    no_tests: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Declare real CMake and CTest commands for an isolated synthetic C++ input."""
    import shutil

    cmake = shutil.which("cmake")
    ctest = shutil.which("ctest")
    assert cmake is not None and ctest is not None, "CMake/CTest prerequisites required"
    (workspace / "main.cpp").write_text(
        "invalid C++ fixture\n"
        if compile_error
        else f"int main() {{ return {1 if fail_test else 0}; }}\n"
    )
    (workspace / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\nproject(collection-fixture LANGUAGES CXX)\nadd_executable(app main.cpp)\nenable_testing()\n"
        + ("" if no_tests else "add_test(NAME actual-case COMMAND app)\n")
    )
    context = context_identity(
        {
            "id": "native",
            "compiler": {"name": "gcc", "version": "14.2"},
            "argv": ["c++"],
            "working_directory": str(workspace),
            "language_standard": None,
            "target": None,
            "provenance": "observed",
            "dependencies": [],
            "limitations": ["Synthetic fixture; source scope is declared."],
        }
    )
    source = snapshot_inputs(
        workspace, ["main.cpp", "CMakeLists.txt"], inventory_complete=True
    )

    def step(
        name: str,
        argv: list[str],
        inputs: list[str],
        outputs: list[str],
        depends: list[str],
        cwd: str = ".",
    ) -> dict[str, Any]:
        return {
            "id": name,
            "context_id": "native",
            "argv": argv,
            "cwd": cwd,
            "depends_on": depends,
            "inputs": inputs,
            "outputs": outputs,
            "timeout_seconds": 30,
        }

    steps = [
        step(
            "configure",
            [cmake, "-S", ".", "-B", "build"],
            ["CMakeLists.txt"],
            ["build/CMakeCache.txt"],
            [],
        ),
        step(
            "build",
            [cmake, "--build", "build"],
            ["build/CMakeCache.txt", "main.cpp"],
            ["build/app"],
            ["configure"],
        ),
        step("version", [ctest, "--version"], [], [], []),
        step(
            "inventory",
            [ctest, "--show-only=json-v1"],
            ["build/app"],
            [],
            ["build"],
            "build",
        ),
        step(
            "tests",
            [ctest, "--output-junit", "junit.xml"],
            ["build/app"],
            ["build/junit.xml", "build/Testing/Temporary/LastTest.log"],
            ["version", "inventory"],
            "build",
        ),
    ]
    base = {
        "scope_files": ["main.cpp"],
        "report_path": None,
        "adapter": None,
        "adapter_version": None,
        "inventory_step_id": None,
        "producer_version_step_id": None,
        "execution_log_path": None,
        "exercised_inputs": ["build/app"],
    }
    plan = {
        "version": "2.0.0",
        "id": "native-plan",
        "recipe": {
            "version": "2.0.0",
            "id": "native-recipe",
            "contexts": ["native"],
            "jobs": 2,
            "steps": steps,
        },
        "bindings": [
            {**base, "id": "native-build", "kind": "build", "step_id": "build"},
            {
                **base,
                "id": "native-tests",
                "kind": "tests",
                "step_id": "tests",
                "report_path": "build/junit.xml",
                "adapter": "ctest-junit",
                "adapter_version": "1.0.0",
                "inventory_step_id": "inventory",
                "producer_version_step_id": "version",
                "execution_log_path": "build/Testing/Temporary/LastTest.log",
            },
        ],
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 1048576,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 0.1,
        },
    }
    return plan, source, [context]


@pytest.mark.parametrize(
    "fail_test,no_tests,expected,total",
    [
        (False, False, "passed", 1),
        (True, False, "failed", 1),
        (False, True, "skipped", 0),
    ],
)
def test_real_ctest_collection_matches_binary_and_exact_counts(
    tmp_path: Path, fail_test: bool, no_tests: bool, expected: str, total: int
) -> None:
    plan, source, contexts = ctest_fixture(
        tmp_path, fail_test=fail_test, no_tests=no_tests
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    snapshot.verify()
    records = {
        record["id"]: record for record in documents(snapshot, "evidence")[0]["records"]
    }
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    assert snapshot.manifest["status"] == "completed"
    assert records["native-tests"]["status"] == expected
    assert records["native-tests"]["usability"] == "usable"
    assert records["native-tests"]["producer"]["version"] == "3.31.6"
    assert records["native-tests"]["producer"]["sha256"]
    assert receipt["tests"]["total"] == total
    assert receipt["status"] == ("failed" if fail_test else "passed")


def test_real_compiler_failure_keeps_failed_build_and_skipped_tests(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path, compile_error=True)
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    records = {
        record["id"]: record for record in documents(snapshot, "evidence")[0]["records"]
    }
    assert snapshot.manifest["status"] == "completed"
    assert (
        records["native-build"]["status"] == "failed"
        and records["native-build"]["usability"] == "usable"
    )
    assert records["native-tests"]["status"] == "skipped"
    assert "tests" not in next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )


def test_zero_exit_missing_junit_is_partial_and_counts_unknown(tmp_path: Path) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    plan["recipe"]["steps"][-1]["argv"] = [
        plan["recipe"]["steps"][2]["argv"][0],
        "--version",
    ]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert snapshot.manifest["status"] == "partial"
    assert receipt["status"] == "passed" and "tests" not in receipt
    assert record["usability"] == "missing"


def test_publication_source_race_republishes_without_rerunning_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse.run_store import StagedRun

    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('counter').write_text(Path('counter').read_text()+'x' if Path('counter').exists() else 'x')\nPath('build').mkdir()\nPath('build/app').write_text('fresh')",
    )
    original = StagedRun.publish
    calls = []

    def mutate(stage: Any, manifest: dict[str, Any], **kwargs: Any) -> Any:
        calls.append(stage.run_id)
        if len(calls) == 1:
            (tmp_path / "source.cpp").write_text("mutation in publication window\n")
        return original(stage, manifest, **kwargs)

    monkeypatch.setattr(StagedRun, "publish", mutate)
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert len(calls) == 2 and calls[0] != calls[1]
    assert (tmp_path / "counter").read_text() == "x"
    assert (
        snapshot.manifest["status"] == "partial"
        and snapshot.manifest["input_verification"] == "unverified"
    )
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] == "stale"
    assert (tmp_path / "store/.staging" / calls[0]).is_dir()
    assert not (tmp_path / "store/latest.json").exists()


def test_unexpected_publication_error_preserves_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse.run_store import StagedRun

    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('fresh')",
    )

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("synthetic store write failure")

    monkeypatch.setattr(StagedRun, "publish", fail)
    with pytest.raises(RuntimeError, match="synthetic store") as error:
        collect(
            plan,
            workspace=tmp_path,
            source=source,
            contexts=contexts,
            store=tmp_path / "store",
        )
    assert list((tmp_path / "store/.staging").glob("*"))
    assert not (tmp_path / "store/latest_attempt.json").exists()
    assert any(
        "Private collection material retained" in note for note in error.value.__notes__
    )


def test_non_utf8_version_stdout_is_unknown_not_an_unhandled_exception(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    plan["recipe"]["steps"][2]["argv"] = [
        sys.executable,
        "-c",
        "import sys; sys.stdout.buffer.write(b'\\xff')",
    ]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert (
        documents(snapshot, "evidence")[0]["records"][1]["usability"] == "unsupported"
    )


def test_actual_test_report_cannot_borrow_a_different_version_tool_hash(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    plan["recipe"]["steps"][2]["argv"] = [
        sys.executable,
        "-c",
        "print('ctest version 3.31.6')",
    ]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert snapshot.manifest["status"] == "partial"
    assert record["status"] == "error" and record["usability"] == "mismatched"


def test_inventory_filter_cannot_bind_unselected_report_cases(tmp_path: Path) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    plan["recipe"]["steps"][3]["argv"].extend(["-R", "no-such-case"])
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert snapshot.manifest["status"] == "partial"
    assert record["usability"] == "mismatched"
    assert any("selection differ" in limitation for limitation in record["limitations"])


def test_compiled_but_uninvoked_binary_cannot_be_tested_evidence(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    with (tmp_path / "CMakeLists.txt").open("a") as stream:
        stream.write("add_executable(unused main.cpp)\n")
    source = snapshot_inputs(
        tmp_path, ["main.cpp", "CMakeLists.txt"], inventory_complete=True
    )
    plan["recipe"]["steps"][1]["outputs"].append("build/unused")
    for step in plan["recipe"]["steps"][3:]:
        step["inputs"].append("build/unused")
    plan["bindings"][1]["exercised_inputs"] = ["build/unused"]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert snapshot.manifest["status"] == "partial"
    assert record["usability"] == "mismatched"
    assert any(
        "not directly invoked" in limitation for limitation in record["limitations"]
    )


def test_binary_removed_during_ctest_stays_operationally_unknown(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    (tmp_path / "main.cpp").write_text(
        "#include <cstdio>\nint main(int, char** argv) { return std::remove(argv[0]); }\n"
    )
    source = snapshot_inputs(
        tmp_path, ["main.cpp", "CMakeLists.txt"], inventory_complete=True
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    assert receipt["status"] == "passed" and receipt["exit_code"] == 0
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "evidence")[0]["records"][1]["usability"] == "mismatched"


def test_actual_process_writing_malformed_report_cannot_verify_tests(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    plan["recipe"]["steps"][-1]["argv"] = [
        sys.executable,
        "-c",
        "from pathlib import Path; Path('junit.xml').write_text('<testsuite><broken>')",
    ]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    assert receipt["status"] == "passed" and "tests" not in receipt
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "evidence")[0]["records"][1]["usability"] == "malformed"


def test_report_hash_disagreement_never_attaches_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses
    import cppulse.collection as module

    original = module.parse_test_report

    def substitute(*args: Any, **kwargs: Any) -> Any:
        return dataclasses.replace(original(*args, **kwargs), report_sha256="0" * 64)

    monkeypatch.setattr(module, "parse_test_report", substitute)
    plan, source, contexts = ctest_fixture(tmp_path)
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    assert "tests" not in receipt
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "evidence")[0]["records"][1]["usability"] == "mismatched"


def test_inventory_version_requires_integers_not_boolean_aliases(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace
    import cppulse.collection as module

    path = tmp_path / "inventory.json"
    path.write_text(
        json.dumps(
            {
                "kind": "ctestInfo",
                "version": {"major": True, "minor": False},
                "tests": [],
            }
        )
    )
    item = SimpleNamespace(
        receipt={"id": "inventory", "status": "passed"}, logs_truncated=False
    )
    capture = SimpleNamespace(
        files={module._id("log:inventory:stdout"): SimpleNamespace(path=path)}
    )
    with pytest.raises(module._MaterialError, match="version"):
        module._inventory(item, capture)


def test_all_disabled_ctest_cases_are_skipped_not_passed(tmp_path: Path) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    with (tmp_path / "CMakeLists.txt").open("a") as stream:
        stream.write("set_tests_properties(actual-case PROPERTIES DISABLED TRUE)\n")
    source = snapshot_inputs(
        tmp_path, ["main.cpp", "CMakeLists.txt"], inventory_complete=True
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    assert snapshot.manifest["status"] == "completed"
    assert record["status"] == "skipped" and record["usability"] == "usable"
    assert receipt["tests"] == {
        "total": 1,
        "passed": 0,
        "failed": 0,
        "skipped": 1,
        "errors": 0,
    }


def test_failed_report_overrides_a_synthetic_zero_exit_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise an inconsistent receipt using real retained failed CTest material."""
    import cppulse.collection as module

    original = module.run_recipe

    def inconsistent(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        receipt = next(
            item.receipt for item in result.steps if item.receipt["id"] == "tests"
        )
        assert receipt["status"] == "failed"
        receipt.update(
            status="passed",
            exit_code=0,
            reason="Synthetic zero-exit receipt for normalization regression",
        )
        return result

    monkeypatch.setattr(module, "run_recipe", inconsistent)
    plan, source, contexts = ctest_fixture(tmp_path, fail_test=True)
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert receipt["status"] == "passed" and receipt["tests"]["failed"] == 1
    assert record["status"] == "failed" and record["usability"] == "usable"


def test_timeout_retains_operational_status_without_passed_evidence(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path, "import time\nprint('started',flush=True)\ntime.sleep(5)"
    )
    plan["recipe"]["steps"][0]["timeout_seconds"] = 0.1
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "execution_receipt")[0]["status"] == "timed_out"
    assert documents(snapshot, "evidence")[0]["records"][0]["status"] == "timed_out"
    assert not (tmp_path / "store/latest.json").exists()


def test_maximum_length_user_ids_do_not_become_unsafe_artifact_paths(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('artifact')",
    )
    step = "x" * 128
    plan["recipe"]["steps"][0]["id"] = step
    plan["bindings"][0]["step_id"] = step
    plan["bindings"][0]["id"] = "y" * 128
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    snapshot.verify()
    assert snapshot.manifest["status"] == "completed"
    assert all(len(entry["id"]) <= 128 for entry in snapshot.manifest["artifacts"])


def test_valid_host_executable_name_uses_host_rules_not_source_path_rules(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(tmp_path, "print('not invoked')")
    host = tmp_path / "host-tools"
    host.mkdir()
    executable = host / "t:local"
    executable.write_text("#!/bin/sh\nmkdir -p build\nprintf 'artifact' > build/app\n")
    executable.chmod(0o700)
    plan["recipe"]["steps"][0]["argv"] = [str(executable)]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "completed"
    assert documents(snapshot, "evidence")[0]["records"][0]["usability"] == "usable"


def test_schema_valid_integer_float_limits_preserve_original_plan(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('artifact')",
    )
    plan["limits"]["max_log_bytes"] = 4096.0
    plan["limits"]["max_artifact_bytes"] = 65536.0
    plan["limits"]["max_metadata_bytes"] = 16777216.0
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "completed"
    assert documents(snapshot, "collection_plan") == [plan]


def test_decoy_test_directory_cannot_borrow_selected_inventory(tmp_path: Path) -> None:
    import subprocess

    plan, source, contexts = ctest_fixture(tmp_path)
    (tmp_path / "main.cpp").write_text(
        '#include <fstream>\nint main() { std::ofstream("selected-marker") << 1; }\n'
    )
    source = snapshot_inputs(
        tmp_path, ["main.cpp", "CMakeLists.txt"], inventory_complete=True
    )
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    cmake = plan["recipe"]["steps"][0]["argv"][0]
    (decoy / "CMakeLists.txt").write_text(
        f'cmake_minimum_required(VERSION 3.16)\nproject(decoy LANGUAGES NONE)\nenable_testing()\nadd_test(NAME actual-case COMMAND "{cmake}" -E true)\n'
    )
    subprocess.run(
        [cmake, "-S", str(decoy), "-B", str(decoy / "build")],
        check=True,
        capture_output=True,
    )
    test = plan["recipe"]["steps"][-1]
    test["argv"] = [
        test["argv"][0],
        "--test-dir",
        str(decoy / "build"),
        "--output-junit",
        str(tmp_path / "build/junit.xml"),
    ]
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert not (tmp_path / "build/selected-marker").exists()
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert snapshot.manifest["status"] == "partial"
    assert record["usability"] != "usable" or record["status"] != "passed"


def test_generated_test_definition_rewrite_cannot_borrow_old_inventory(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    (tmp_path / "main.cpp").write_text(
        '#include <fstream>\nint main() { std::ofstream("selected-marker") << 1; }\n'
    )
    source = snapshot_inputs(
        tmp_path, ["main.cpp", "CMakeLists.txt"], inventory_complete=True
    )
    cmake = plan["recipe"]["steps"][0]["argv"][0]
    script = f"from pathlib import Path; Path('build/CTestTestfile.cmake').write_text('add_test(actual-case \\\"{cmake}\\\" -E true)\\n'); Path('build/rewrite-receipt').write_text('rewritten')"
    plan["recipe"]["steps"].insert(
        -1,
        {
            "id": "rewrite",
            "context_id": "native",
            "argv": [sys.executable, "-c", script],
            "cwd": ".",
            "depends_on": ["inventory"],
            "inputs": ["build/app"],
            "outputs": ["build/rewrite-receipt"],
            "timeout_seconds": 10,
        },
    )
    plan["recipe"]["steps"][-1]["depends_on"].append("rewrite")
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert not (tmp_path / "build/selected-marker").exists()
    record = documents(snapshot, "evidence")[0]["records"][1]
    assert snapshot.manifest["status"] == "partial"
    assert record["usability"] != "usable" or record["status"] != "passed"


def test_observed_file_and_control_metadata_caps_are_separate_and_explicit(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('artifact')\nprint('x'*10000)",
    )
    plan["limits"].update(max_artifact_bytes=1024, max_metadata_bytes=16384)
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    for entry in snapshot.manifest["artifacts"]:
        limit = 16384 if entry["media_type"] == "application/json" else 1024
        assert entry["size_bytes"] <= limit
    assert (snapshot.path / "run_manifest.json").stat().st_size <= 16384
    assert any(
        "archived log is a prefix" in limitation
        for limitation in snapshot.manifest["limitations"]
    )


def test_infeasible_control_metadata_limit_rejects_before_commands(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path, "from pathlib import Path\nPath('marker').touch()"
    )
    plan["limits"]["max_metadata_bytes"] = 64
    with pytest.raises(ContractError, match="control metadata"):
        collect(
            plan,
            workspace=tmp_path,
            source=source,
            contexts=contexts,
            store=tmp_path / "store",
        )
    assert not (tmp_path / "marker").exists()


def test_missing_actual_execution_log_cannot_verify_report_claims(
    tmp_path: Path,
) -> None:
    plan, source, contexts = ctest_fixture(tmp_path)
    # The JUnit output is real, but the explicitly selected command log is absent.
    plan["bindings"][1]["execution_log_path"] = "build/absent-last-test.log"
    plan["recipe"]["steps"][-1]["outputs"][-1] = "build/absent-last-test.log"
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    record = documents(snapshot, "evidence")[0]["records"][1]
    receipt = next(
        record
        for record in documents(snapshot, "execution_receipt")
        if record["id"] == "tests"
    )
    assert snapshot.manifest["status"] == "partial"
    assert receipt["status"] == "passed" and receipt["tests"]["total"] == 1
    assert record["usability"] == "missing"


def test_generated_binary_replacement_cannot_keep_usable_source_binding(
    tmp_path: Path,
) -> None:
    import shutil

    plan, source, contexts = ctest_fixture(tmp_path)
    replacement = shutil.which("true")
    assert replacement is not None
    script = f"from pathlib import Path; import shutil; shutil.copyfile({replacement!r},'build/app'); Path('build/replacement-receipt').write_text('replaced')"
    plan["recipe"]["steps"].insert(
        2,
        {
            "id": "replace-binary",
            "context_id": "native",
            "argv": [sys.executable, "-c", script],
            "cwd": ".",
            "depends_on": ["build"],
            "inputs": [],
            "outputs": ["build/replacement-receipt"],
            "timeout_seconds": 10,
        },
    )
    next(step for step in plan["recipe"]["steps"] if step["id"] == "inventory")[
        "depends_on"
    ].append("replace-binary")
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "evidence")[0]["records"][1]["usability"] != "usable"


def test_execution_log_hash_disagreement_is_unusable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import dataclasses
    from cppulse.adapters import ctest_log

    original = ctest_log.parse_ctest_log

    def substitute(*args: Any, **kwargs: Any) -> Any:
        return dataclasses.replace(original(*args, **kwargs), report_sha256="0" * 64)

    monkeypatch.setattr(ctest_log, "parse_ctest_log", substitute)
    plan, source, contexts = ctest_fixture(tmp_path)
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    assert snapshot.manifest["status"] == "partial"
    assert documents(snapshot, "evidence")[0]["records"][1]["usability"] == "mismatched"


def test_late_manifest_metadata_cap_preserves_stage_and_previous_latest(
    tmp_path: Path,
) -> None:
    from cppulse.errors import IntegrityError
    from cppulse.run_store import RunStore

    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir(exist_ok=True)\nPath('build/app').write_text('fresh artifact')",
    )
    store = RunStore(tmp_path / "store")
    previous = collect(
        plan, workspace=tmp_path, source=source, contexts=contexts, store=store
    )
    manifest_size = (previous.path / "run_manifest.json").stat().st_size
    control_max = max(
        entry["size_bytes"]
        for entry in previous.manifest["artifacts"]
        if entry["media_type"] == "application/json"
    )
    assert manifest_size > control_max + 200
    plan["limits"]["max_metadata_bytes"] = manifest_size - 100
    with pytest.raises(IntegrityError, match="max_metadata_bytes"):
        collect(plan, workspace=tmp_path, source=source, contexts=contexts, store=store)
    assert store.resolve_latest().run_id == previous.run_id
    assert store.resolve_latest_attempt().run_id == previous.run_id
    assert any(path.is_file() for path in (tmp_path / "store/.staging").rglob("*"))
