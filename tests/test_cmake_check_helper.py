"""Exercise CMake target plumbing with an explicitly synthetic check driver.

These cases prove CMake ordering/argv/opt-in behavior, not a policy decision.
The installed real-command journey is verified separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@dataclass(frozen=True)
class Project:
    """Private real C++ build plus a labeled synthetic command recorder."""

    source: Path
    build: Path
    store: Path
    policy: Path
    driver: Path
    log: Path
    environment: dict[str, str]


def module_path() -> Path:
    """Read the same packaged resource used by an installed caller."""
    return Path(str(resources.files("cppulse").joinpath("data/Cppulse.cmake")))


def quote(value: Path | str) -> str:
    """Quote one fixture path in CMake source, never in a shell command."""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


@pytest.fixture()
def project(tmp_path: Path) -> Project:
    source = tmp_path / "source with spaces"
    build = tmp_path / "build with spaces"
    source.mkdir()
    store = source / "collected store"
    policy = source / "selected policy.json"
    policy.write_text("{}\n")
    (source / "main.cpp").write_text("int main() { return 0; }\n")
    driver = source / "synthetic check driver"
    driver.write_text(
        "#!/usr/bin/env python3\n"
        '"""Synthetic argv recorder; it never evaluates a policy."""\n'
        "import json, os, pathlib, sys\n"
        "assert sys.argv[1] == 'check', sys.argv\n"
        "assert pathlib.Path(os.environ['CPPULSE_TEST_TARGET']).is_file()\n"
        "pathlib.Path(os.environ['CPPULSE_TEST_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.exit(int(os.environ.get('CPPULSE_TEST_EXIT', '0')))\n"
    )
    driver.chmod(0o755)
    log = tmp_path / "synthetic check argv.json"
    environment = {
        **os.environ,
        "CPPULSE_TEST_TARGET": str(build / "selected"),
        "CPPULSE_TEST_LOG": str(log),
    }
    return Project(source, build, store, policy, driver, log, environment)


def configure(
    project: Project, *, options: str = "", mode: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Configure a real tiny C++ project; required tools may not be skipped."""
    cmake = shutil.which("cmake")
    assert cmake, "CMake is required for the shared native check"
    assert module_path().is_file(), "Installed CMake helper is missing"
    mode = mode or f"POLICY {quote(project.policy)}"
    (project.source / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(CppulseConsumerFixture LANGUAGES CXX)\n"
        "add_executable(selected main.cpp)\n"
        'add_custom_target(unrelated COMMAND "${CMAKE_COMMAND}" -E touch '
        '"${CMAKE_BINARY_DIR}/unrelated-was-built")\n'
        f"include({quote(module_path())})\n"
        "cppulse_add_check(\n"
        "  NAME evidence_check\n"
        f"  EXECUTABLE {quote(project.driver)}\n"
        f"  STORE {quote(project.store)}\n"
        '  WORKSPACE "${CMAKE_CURRENT_SOURCE_DIR}"\n'
        f"  {mode}\n"
        "  DEPENDS selected\n"
        f"  {options}\n"
        ")\n"
        "if(DEFINED discovered_database)\n"
        '  file(WRITE "${CMAKE_BINARY_DIR}/discovered-db.txt" "${discovered_database}")\n'
        "endif()\n"
    )
    return subprocess.run(
        [cmake, "-S", str(project.source), "-B", str(project.build)],
        env=project.environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def build(
    project: Project, target: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Build with argv, preserving the actual failing CMake return status."""
    command = ["cmake", "--build", str(project.build)]
    if target:
        command += ["--target", target]
    return subprocess.run(
        command,
        env=project.environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_default_build_does_not_enforce_or_collect(project: Project) -> None:
    result = configure(project)
    assert result.returncode == 0, result.stderr
    result = build(project)
    assert result.returncode == 0, result.stderr
    assert (project.build / "selected").is_file()
    assert not project.log.exists()
    assert not project.store.exists()


def test_explicit_check_has_selected_dependency_and_preserves_path_arguments(
    project: Project,
) -> None:
    result = configure(project)
    assert result.returncode == 0, result.stderr
    result = build(project, "evidence_check")
    assert result.returncode == 0, result.stderr
    assert not (project.build / "unrelated-was-built").exists()
    assert json.loads(project.log.read_text()) == [
        "check",
        "--store",
        str(project.store),
        "--workspace",
        str(project.source),
        "--policy",
        str(project.policy),
    ]
    assert not project.store.exists(), "The helper must not collect or allocate a store"


def test_normal_build_enforcement_requires_explicit_option(project: Project) -> None:
    result = configure(project, options="ENFORCE_DEFAULT_BUILD")
    assert result.returncode == 0, result.stderr
    result = build(project)
    assert result.returncode == 0, result.stderr
    assert project.log.is_file()


def test_compile_database_discovery_names_actual_generated_context(
    project: Project,
) -> None:
    result = configure(
        project,
        options="EXPORT_COMPILE_COMMANDS CONTEXT_DATABASE_OUT_VAR discovered_database",
    )
    assert result.returncode == 0, result.stderr
    database = Path((project.build / "discovered-db.txt").read_text())
    assert database == project.build / "compile_commands.json"
    commands = json.loads(database.read_text())
    assert any(Path(row["file"]) == project.source / "main.cpp" for row in commands)
    assert not project.log.exists()


@pytest.mark.parametrize("status", [1, 2, 3, 130])
def test_check_failure_is_not_hidden(project: Project, status: int) -> None:
    project.environment["CPPULSE_TEST_EXIT"] = str(status)
    result = configure(project)
    assert result.returncode == 0, result.stderr
    result = build(project, "evidence_check")
    assert result.returncode != 0
    assert project.log.exists()


def test_finding_mode_uses_the_same_explicit_check_contract(project: Project) -> None:
    request = project.source / "finding request.json"
    request.write_text("{}\n")
    result = configure(project, mode=f"FINDINGS {quote(request)}")
    assert result.returncode == 0, result.stderr
    result = build(project, "evidence_check")
    assert result.returncode == 0, result.stderr
    assert json.loads(project.log.read_text())[-2:] == ["--findings", str(request)]


@pytest.mark.parametrize(
    "mode,options",
    [
        (" ", ""),
        ('POLICY "a.json" FINDINGS "b.json"', ""),
        ('POLICY "a.json"', "RUN_ID pinned-run"),
        ('POLICY "a.json"', "MANIFEST_SHA256 " + "a" * 64),
        ('POLICY "a.json"', "UNKNOWN_OPTION"),
    ],
)
def test_invalid_or_ambiguous_build_configuration_fails_before_commands(
    project: Project, mode: str, options: str
) -> None:
    result = configure(project, mode=mode, options=options)
    assert result.returncode != 0
    assert not project.log.exists()


def test_explicit_pin_pair_is_passed_without_resolving_latest(project: Project) -> None:
    digest = "a" * 64
    result = configure(project, options=f"RUN_ID pinned-run MANIFEST_SHA256 {digest}")
    assert result.returncode == 0, result.stderr
    result = build(project, "evidence_check")
    assert result.returncode == 0, result.stderr
    assert json.loads(project.log.read_text())[-4:] == [
        "--run-id",
        "pinned-run",
        "--manifest-sha256",
        digest,
    ]
