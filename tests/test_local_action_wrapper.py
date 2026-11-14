"""Local-only action-wrapper control tests, with a labeled synthetic CLI.

No GitHub runner, token, API, repository ref or real policy engine is used.
The actual installed CLI journey is tested separately.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / ".github/actions/cppulse/entrypoint.sh"


@dataclass(frozen=True)
class Action:
    """Private wrapper environment without any real service credentials."""

    directory: Path
    arguments: Path
    git_calls: Path
    outputs: Path
    environment: dict[str, str]


@pytest.fixture()
def action(tmp_path: Path) -> Action:
    directory = tmp_path / "application with spaces"
    directory.mkdir()
    commands = tmp_path / "commands"
    commands.mkdir()
    arguments, git_calls, outputs = (
        tmp_path / "synthetic-cli-arguments.json",
        tmp_path / "forbidden-git-call.json",
        tmp_path / "local-runner-output.txt",
    )
    driver = commands / "cppulse"
    driver.write_text(
        "#!/usr/bin/env python3\n"
        '"""Synthetic wrapper fixture; no policy decision is performed."""\n'
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['CPPULSE_TEST_ARGS']).write_text(json.dumps(sys.argv[1:]))\n"
        "print(json.dumps({'fixture': 'synthetic wrapper control result'}))\n"
        "sys.exit(int(os.environ.get('CPPULSE_TEST_STATUS','0')))\n"
    )
    driver.chmod(0o755)
    git = commands / "git"
    git.write_text(
        "#!/usr/bin/env python3\n"
        '"""Trap Git commands; never touch a repository or contact a server."""\n'
        "import json, os, pathlib, sys\n"
        "pathlib.Path(os.environ['CPPULSE_TEST_GIT']).write_text(json.dumps(sys.argv[1:]))\n"
        "sys.exit(97)\n"
    )
    git.chmod(0o755)
    environment = {
        "PATH": str(commands) + os.pathsep + "/usr/bin:/bin",
        "CPPULSE_TEST_ARGS": str(arguments),
        "CPPULSE_TEST_GIT": str(git_calls),
        "GITHUB_OUTPUT": str(outputs),
        "GITHUB_WORKSPACE": str(directory),
        "GITHUB_TOKEN": "",
        "GITHUB_EVENT_PATH": "",
        "GITHUB_REPOSITORY": "",
        "INPUT_REPO_PATH": str(directory),
        "INPUT_STORE_PATH": str(directory / "selected store"),
        "INPUT_POLICY_FILE": str(directory / "selected policy.json"),
        "INPUT_FINDING_REQUEST": "",
        "INPUT_BASE_REF": "",
        "INPUT_POST_COMMENT": "false",
        "INPUT_GENERATE_PDF": "false",
        "INPUT_FAIL_ON_REGRESSION": "false",
    }
    return Action(directory, arguments, git_calls, outputs, environment)


def invoke(action: Action) -> subprocess.CompletedProcess[str]:
    """Run the local wrapper against traps, never a real service or Git repo."""
    return subprocess.run(
        ["/bin/bash", str(ENTRY)],
        cwd=action.directory,
        env=action.environment,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )


@pytest.mark.parametrize("status", [0, 1, 2, 3, 130])
def test_local_wrapper_uses_shared_check_and_preserves_its_exit(
    action: Action, status: int
) -> None:
    action.environment["CPPULSE_TEST_STATUS"] = str(status)
    result = invoke(action)
    assert result.returncode == status, result.stderr
    assert json.loads(result.stdout) == {"fixture": "synthetic wrapper control result"}
    assert json.loads(action.arguments.read_text()) == [
        "check",
        "--store",
        action.environment["INPUT_STORE_PATH"],
        "--workspace",
        str(action.directory),
        "--policy",
        action.environment["INPUT_POLICY_FILE"],
    ]
    assert not action.git_calls.exists()
    assert f"exit-code={status}\n" in action.outputs.read_text()


def test_finding_request_uses_same_engine_without_checkout(action: Action) -> None:
    action.environment["INPUT_POLICY_FILE"] = ""
    action.environment["INPUT_FINDING_REQUEST"] = str(
        action.directory / "finding comparison.json"
    )
    result = invoke(action)
    assert result.returncode == 0, result.stderr
    assert json.loads(action.arguments.read_text())[-2:] == [
        "--findings",
        action.environment["INPUT_FINDING_REQUEST"],
    ]
    assert not action.git_calls.exists()


@pytest.mark.parametrize(
    "values",
    [
        {"INPUT_POST_COMMENT": "true"},
        {"INPUT_BASE_REF": "origin/main"},
        {"INPUT_GENERATE_PDF": "true"},
        {"INPUT_POLICY_FILE": ""},
        {"INPUT_FINDING_REQUEST": "ambiguous.json"},
        {"INPUT_STORE_PATH": ""},
    ],
)
def test_unsupported_or_ambiguous_options_fail_before_any_commands(
    action: Action, values: dict[str, str]
) -> None:
    action.environment.update(values)
    result = invoke(action)
    assert result.returncode == 2, result.stderr
    assert not action.arguments.exists()
    assert not action.git_calls.exists()


def test_action_metadata_has_no_implicit_comment_or_token() -> None:
    document = yaml.safe_load((ENTRY.parent / "action.yml").read_text())
    assert document["inputs"]["post-comment"]["default"] == "false"
    assert document["inputs"]["github-token"]["default"] == ""
    assert "GITHUB_TOKEN" not in document["runs"].get("env", {})
