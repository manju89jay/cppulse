"""Finite request and transparent launcher checks for the public demo harness."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
from types import ModuleType
from typing import Any

import cppulse
import pytest

from cppulse.contracts import validate


@pytest.fixture()
def driver(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.syspath_prepend(str(Path(__file__).parents[1] / "scripts"))
    return importlib.import_module("demo_evidence")


def test_request_has_finite_original_native_roles_and_ordered_cleanup(
    tmp_path: Path, driver: ModuleType
) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "main.cpp").write_text("int main() { return 0; }\n")
    (fixture / "CMakeLists.txt").write_text("# synthetic unit fixture\n")
    resources = tmp_path / "resources"
    (resources / "include").mkdir(parents=True)
    (resources / "include/stddef.h").write_text("// synthetic resource\n")
    directory = tmp_path / "case"
    directory.mkdir()
    workspace, source, files = driver.prepare_workspace(
        directory, fixture, resources, "clean"
    )
    driver.add_cmake_check(workspace, directory / "store", directory / "policy.json")
    source = driver.snapshot_inputs(
        workspace,
        sorted(
            path.relative_to(workspace).as_posix()
            for path in workspace.rglob("*")
            if path.is_file()
        ),
        inventory_complete=True,
    )
    tools = {
        "cmake": "/selected/cmake",
        "ctest": "/selected/ctest",
        "compiler": "/selected/g++",
        "analyzer": "/selected/analyzer",
        "compiler_version": "14.2.0",
        "compiler_target": "x86_64-linux-gnu",
        "compiler_sha256": "a" * 64,
        "analyzer_sha256": "b" * 64,
    }
    request = driver.make_request("clean", workspace, source, files, tools)
    validate("collection_request", request)
    steps = request["plan"]["recipe"]["steps"]
    cleanup = steps[0]
    assert cleanup["id"] == "clean-owned-generated"
    assert cleanup["argv"] == [
        "/selected/cmake",
        "-E",
        "rm",
        "-rf",
        "build",
        "native-build",
        "native-report",
    ]
    assert cleanup["inputs"] == cleanup["outputs"] == []
    for step in steps:
        if step["id"].startswith("configure-"):
            assert "clean-owned-generated" in step["depends_on"]
    selected = request["normalizers"][0]
    assert selected["report"] == {
        "step_id": "native-analysis",
        "role": "output",
        "path": "native-report/findings.json",
    }
    assert selected["resource_manifest"]["path"] == "resource-manifest.json"
    assert selected["requested_files"] == ["main.cpp"]
    assert selected["requested_rules"] == ["CPP-MEM-001"]
    assert request["source"]["files"] == sorted(row["path"] for row in source["files"])


def test_cmake_setup_uses_packaged_resource_and_transparent_public_cli(
    tmp_path: Path, driver: ModuleType
) -> None:
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    (workspace / "CMakeLists.txt").write_text("# fixture\n")
    launcher = driver.add_cmake_check(
        workspace, tmp_path / "store", tmp_path / "policy.json"
    )
    assert launcher.is_file()
    assert "-m cppulse.cli" in launcher.read_text()
    assert "PYTHONPATH" not in launcher.read_text()
    assert (
        (workspace / "cmake/Cppulse.cmake").read_bytes().startswith(b"# Explicit local")
    )
    source = (workspace / "CMakeLists.txt").read_text()
    assert "DEPENDS cppulse-policy-demo" in source
    assert "ENFORCE_DEFAULT_BUILD" not in source
    result = subprocess.run(
        [str(launcher), "--version"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(Path(cppulse.__file__).parents[1])},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_cmake_mixed_output_parser_preserves_final_typed_result(
    driver: ModuleType,
) -> None:
    expected = {"version": "2.0.0", "mode": "policy", "exit_code": 3}
    text = (
        "[100%] Building fixture\n"
        + json.dumps(expected, indent=2)
        + "\nmake: failed\n"
    )
    assert (
        driver.command_document(text, "check_result", validate_document=False)
        == expected
    )
    with pytest.raises(RuntimeError, match="JSON object"):
        driver.command_document("No JSON was produced", "check_result")


def test_report_formats_are_explicit_unique_and_never_silently_skip_pdf(
    driver: ModuleType,
) -> None:
    assert driver.report_formats("json,html") == ("json", "html")
    assert driver.report_formats("pdf") == ("pdf",)
    for value in ["", "json,json", "json,png", "json, html"]:
        with pytest.raises(argparse.ArgumentTypeError):
            driver.report_formats(value)


@pytest.mark.parametrize(
    "normalized_file,normalized_context",
    [
        ("main.cpp", "actual-parse"),
        ("other.cpp", "actual-parse"),
        ("main.cpp", "wrong-parse"),
    ],
)
def test_native_path_check_accepts_actual_relative_report_identity(
    tmp_path: Path,
    driver: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    normalized_file: str,
    normalized_context: str,
) -> None:
    inventory = {
        "id": "analysis",
        "requested_files": ["main.cpp"],
        "requested_rules": ["CPP-MEM-001"],
        "job_context_id": "native-job",
        "items": [
            {
                "file": "main.cpp",
                "status": "analyzed",
                "context_match": "matched",
                "executed_rules": ["CPP-MEM-001"],
                "parse_context_id": "actual-parse",
            }
        ],
    }
    bundle = {
        "analysis_inventory": [inventory],
        "observations": [
            {
                "analysis_inventory_id": "analysis",
                "items": [
                    {
                        "id": "finding",
                        "file": normalized_file,
                        "context_id": normalized_context,
                    }
                ],
            }
        ],
    }
    report = {
        "metadata": {"repo_path": str(tmp_path)},
        "findings": [
            {
                "file": "main.cpp",
                "rule_id": "CPP-MEM-001",
                "severity": "warning",
                "category": "memory_safety",
            }
        ],
        "summary": {
            "total_findings": 1,
            "by_severity": {"warning": 1},
            "by_category": {"memory_safety": 1},
        },
    }

    class Snapshot:
        def read_json(
            self, identifier: str, *, contract: tuple[str, str]
        ) -> dict[str, Any]:
            assert contract == ("findings", "prototype_v1")
            return report

    monkeypatch.setattr(driver, "documents", lambda _: bundle)
    monkeypatch.setattr(
        driver, "native_roles", lambda _: {"report_artifact_id": "raw-report"}
    )
    if normalized_file != "main.cpp" or normalized_context != "actual-parse":
        with pytest.raises(RuntimeError, match="Normalized observation path/context"):
            driver.verify_native(Snapshot(), "findings")
        return
    result = driver.verify_native(Snapshot(), "findings")
    assert result["selected_rule_findings"] == 1
    assert result["observation_ids"] == ["finding"]


def test_launch_failure_retains_attempt_without_inventing_exit(
    tmp_path: Path, driver: ModuleType
) -> None:
    commands = driver.Commands(tmp_path / "logs")
    with pytest.raises(RuntimeError, match="not launched"):
        commands.run("missing", [str(tmp_path / "absent")], cwd=tmp_path)
    record = json.loads((tmp_path / "logs/commands.json").read_text())["commands"][0]
    assert record["status"] == "launch_error" and record["exit_code"] is None
    assert record["argv"] == [str(tmp_path / "absent")]
    assert (tmp_path / "logs/missing.stdout.log").read_bytes() == b""


def test_timeout_retains_partial_raw_output_without_inventing_exit(
    tmp_path: Path, driver: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def timed_out(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(
            args[0], 300, output=b"partial\r\n", stderr=b"warning\x00"
        )

    monkeypatch.setattr(driver.subprocess, "run", timed_out)
    commands = driver.Commands(tmp_path / "logs")
    with pytest.raises(RuntimeError, match="timed out"):
        commands.run("slow", ["selected-command"], cwd=tmp_path)
    record = json.loads((tmp_path / "logs/commands.json").read_text())["commands"][0]
    assert record["status"] == "timeout" and record["exit_code"] is None
    assert record["capture_status"] == "partial"
    assert (tmp_path / "logs/slow.stdout.log").read_bytes() == b"partial\r\n"
    assert (tmp_path / "logs/slow.stderr.log").read_bytes() == b"warning\x00"


def test_optional_wrapper_bytes_are_in_harness_inventory(
    tmp_path: Path, driver: ModuleType
) -> None:
    wrapper = tmp_path / "entrypoint.sh"
    wrapper.write_bytes(b"#!/bin/bash\n# explicit copied wrapper\n")
    selected = driver.harness_inventory(wrapper)
    assert len(selected) == 3
    assert selected[-1]["absolute_path"] == str(wrapper)
    assert (
        selected[-1]["sha256"]
        == driver.hash_artifact(wrapper, "wrapper", "wrapper", "text/plain")["sha256"]
    )
