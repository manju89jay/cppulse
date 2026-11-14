"""Validate and run the optional hook template in an isolated Git fixture.

The hook executable is an explicitly synthetic argv recorder. These tests do
not install hooks in this project or claim a real policy decision passed.
"""

from __future__ import annotations

from importlib import resources
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def template() -> Path:
    """Locate the installed-package example, never the project's active hooks."""
    path = Path(
        str(
            resources.files("cppulse").joinpath(
                "data/templates/pre-commit.example.yaml"
            )
        )
    )
    assert path.is_file(), "The optional packaged hook example is missing"
    return path


def framework() -> str:
    """Require the recorded optional tool for this verification-only suite."""
    executable = os.environ.get("CPPULSE_PRE_COMMIT") or shutil.which("pre-commit")
    assert (
        executable
    ), "Install requirements-verification.txt and set CPPULSE_PRE_COMMIT"
    return executable


def test_optional_hook_config_passes_real_framework_validation() -> None:
    result = subprocess.run(
        [framework(), "validate-config", str(template())],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("status", [0, 3])
def test_local_hook_checks_full_declared_scope_without_passing_filenames(
    tmp_path: Path, status: int
) -> None:
    workspace = tmp_path / "synthetic application with spaces"
    workspace.mkdir()
    (workspace / "selected.hpp").write_text("// synthetic tracked fixture\n")
    subprocess.run(["git", "init", "--quiet", str(workspace)], check=True)
    subprocess.run(["git", "-C", str(workspace), "add", "selected.hpp"], check=True)
    commands = tmp_path / "commands"
    commands.mkdir()
    log = tmp_path / "synthetic-hook-arguments.json"
    driver = commands / "cppulse"
    driver.write_text(
        "#!/usr/bin/env python3\n"
        '"""Synthetic hook recorder; no actual policy decision is made."""\n'
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['CPPULSE_TEST_HOOK_LOG']).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.exit(int(os.environ['CPPULSE_TEST_HOOK_EXIT']))\n"
    )
    driver.chmod(0o755)
    result = subprocess.run(
        [
            framework(),
            "run",
            "cppulse-evidence",
            "--all-files",
            "--config",
            str(template()),
        ],
        cwd=workspace,
        env={
            **os.environ,
            "PATH": str(commands) + os.pathsep + os.environ["PATH"],
            "PRE_COMMIT_HOME": str(tmp_path / "isolated-hook-cache"),
            "CPPULSE_TEST_HOOK_LOG": str(log),
            "CPPULSE_TEST_HOOK_EXIT": str(status),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == (0 if status == 0 else 1), result.stdout + result.stderr
    assert json.loads(log.read_text()) == [
        "check",
        "--store",
        "cppulse-output",
        "--workspace",
        ".",
        "--policy",
        "cppulse-policy.json",
    ]
    assert not (workspace / ".git/hooks/pre-commit").exists()
