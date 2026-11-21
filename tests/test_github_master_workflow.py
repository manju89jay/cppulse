"""Contract for GitHub event scope, privileges, and shared CI checks."""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


@pytest.fixture
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_bytes())


def test_automatic_events_target_master_and_manual_dispatch_is_available(
    workflow: dict,
) -> None:
    assert workflow["on"] == {
        "push": {"branches": ["master"]},
        "pull_request": {"branches": ["master"]},
        "workflow_dispatch": None,
    }


def test_workflow_grants_only_read_access_and_drops_checkout_credentials(
    workflow: dict,
) -> None:
    assert workflow["permissions"] == {"contents": "read"}
    for job in workflow["jobs"].values():
        assert "permissions" not in job
        assert not job.get("continue-on-error")
        checkouts = [
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        ]
        assert checkouts and all(
            step["with"]["persist-credentials"] is False for step in checkouts
        )


def test_github_jobs_preserve_required_shared_checks(workflow: dict) -> None:
    expected = {
        "lint": [("--section format", "format")],
        "build-cpp": [("--section native", "native")],
        "test-python": [
            ("--section native", "contracts-native"),
            ("--section root-public --section generated", "contracts"),
            *[
                (f"--section python --component {name}", name)
                for name in ("git-miner", "predictor", "report-engine")
            ],
        ],
        "build-dashboard": [("--section dashboard", "dashboard")],
        "integration": [
            ("--section native --section integration --with-docker", "integration")
        ],
    }
    jobs = workflow["jobs"]
    assert set(jobs) == set(expected)
    assert set(jobs["integration"]["needs"]) == {"build-cpp", "test-python"}
    for name, checks in expected.items():
        job = jobs[name]
        assert job["runs-on"] == "ubuntu-24.04" and not job.get("if")
        steps = [
            step
            for step in job["steps"]
            if "tools/dev.py verify" in step.get("run", "")
        ]
        assert all(
            not step.get("if") and not step.get("continue-on-error") for step in steps
        )
        assert [shlex.split(step["run"]) for step in steps] == [
            shlex.split(
                f"python tools/dev.py verify --scope changed {options} "
                f"--output-dir review/ci/{output}"
            )
            for options, output in checks
        ]


@pytest.mark.parametrize("name", ["build-cpp", "test-python", "integration"])
def test_native_jobs_provision_matching_llvm_and_ctest(
    workflow: dict, name: str
) -> None:
    commands = "\n".join(
        step.get("run", "") for step in workflow["jobs"][name]["steps"]
    )
    assert {"libclang-19-dev", "llvm-19-dev", "cmake==3.31.6"} <= set(
        shlex.split(commands)
    )


def test_format_job_uses_fetched_pull_request_revisions(workflow: dict) -> None:
    checkout, *steps = workflow["jobs"]["lint"]["steps"]
    assert checkout["with"]["fetch-depth"] == 0
    assert steps[-1]["env"] == {
        "CPPULSE_FORMAT_BASE": "${{ github.event.pull_request.base.sha }}",
        "CPPULSE_FORMAT_HEAD": "${{ github.event.pull_request.head.sha }}",
        "CPPULSE_FORMAT_ALL_TRACKED": "${{ github.event_name != 'pull_request' }}",
    }


def test_dashboard_checks_use_the_locked_hosted_toolchain(workflow: dict) -> None:
    steps = workflow["jobs"]["build-dashboard"]["steps"]
    (setup,) = [
        step for step in steps if step.get("uses", "").startswith("actions/setup-node@")
    ]
    (install,) = [
        step
        for step in steps
        if step.get("name") == "Install locked dashboard dependencies"
    ]
    (verify,) = [step for step in steps if "--section dashboard" in step.get("run", "")]
    assert setup["with"]["node-version"] == "20.20.2"
    assert setup["with"]["cache-dependency-path"] == "dashboard/package-lock.json"
    assert steps.index(setup) < steps.index(install) < steps.index(verify)
    assert not install.get("if") and not install.get("continue-on-error")
    assert [shlex.split(line) for line in install["run"].splitlines()] == [
        ["test", "$(npm --version)", "=", "10.8.2"],
        ["npm", "ci", "--prefix", "dashboard"],
    ]


def test_python_job_trusts_only_the_declared_checkout(
    workflow: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    steps = workflow["jobs"]["test-python"]["steps"]
    names = [step.get("name") for step in steps]
    registration_index = names.index(
        "Trust the Actions checkout for the pinned Git provider"
    )
    registration = steps[registration_index]
    assert (
        names.index("Build the pinned Git provider for actual local branch tests")
        < registration_index
    )
    assert registration_index < names.index(
        "Build producer prerequisites for actual contract integration"
    )
    assert registration["shell"] == "bash"
    assert not registration.get("if") and not registration.get("continue-on-error")

    checkout = tmp_path / "actions checkout"
    untrusted = [tmp_path / "other repo", checkout / "nested repo"]
    runner_temp = tmp_path / "runner-temp"
    step_environment = runner_temp / "github-env"
    initial_home = tmp_path / "initial-home"
    fresh_home = tmp_path / "fresh-home"
    for directory in (runner_temp, initial_home, fresh_home):
        directory.mkdir()
    for name in (
        "GIT_CONFIG_GLOBAL",
        "GIT_CONFIG_NOSYSTEM",
        "GIT_CONFIG_COUNT",
        "XDG_CONFIG_HOME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(initial_home))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)
    for path in (checkout, *untrusted):
        subprocess.run(["git", "init", "-q", str(path)], check=True)

    def inspect(path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
        )

    monkeypatch.setenv("GIT_TEST_ASSUME_DIFFERENT_OWNER", "1")
    monkeypatch.setenv("GITHUB_WORKSPACE", str(checkout))
    monkeypatch.setenv("RUNNER_TEMP", str(runner_temp))
    monkeypatch.setenv("GITHUB_ENV", str(step_environment))
    for path in (checkout, *untrusted):
        denied = inspect(path)
        assert denied.returncode == 128 and "dubious ownership" in denied.stderr

    subprocess.run(["bash", "-e", "-c", registration["run"]], check=True)
    (environment_line,) = step_environment.read_text().splitlines()
    name, _, value = environment_line.partition("=")
    assert name == "GIT_CONFIG_SYSTEM"
    assert Path(value).parent == runner_temp
    monkeypatch.setenv(name, value)
    monkeypatch.setenv("HOME", str(fresh_home))
    trusted = inspect(checkout)
    assert trusted.returncode == 0 and trusted.stdout.strip() == str(checkout.resolve())
    for path in untrusted:
        denied = inspect(path)
        assert denied.returncode == 128 and "dubious ownership" in denied.stderr
    configured = subprocess.check_output(
        ["git", "config", "--system", "--list"], text=True
    )
    assert configured.splitlines() == [f"safe.directory={checkout.resolve()}"]


def test_shared_formatter_selects_committed_and_local_python_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.check_local import build_checks

    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=tmp_path, text=True).strip()

    git("init", "-q", "--initial-branch=base")
    git("config", "user.name", "CI Contract Test")
    git("config", "user.email", "ci@example.invalid")
    for name in ("scripts", "tools", "tests"):
        (tmp_path / name).mkdir()
    (tmp_path / "tests/unchanged.py").write_text("value = 0\n")
    (tmp_path / "scripts/removed.py").write_text("value = 1\n")
    git("add", ".")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "tests/committed.py").write_text("value = 2\n")
    (tmp_path / "scripts/removed.py").unlink()
    git("add", "-A")
    git("commit", "-qm", "branch")
    assert not git("status", "--porcelain")
    monkeypatch.setenv("CPPULSE_FORMAT_BASE", base)
    monkeypatch.setenv("CPPULSE_FORMAT_HEAD", git("rev-parse", "HEAD"))

    def targets() -> dict[str, tuple[str, ...]]:
        return {
            check.name: check.argv[4:]
            for check in build_checks(tmp_path, {"format"}, tmp_path / "out")
        }

    assert targets() == {
        "black-check": ("tests/committed.py",),
        "ruff-check": ("tests/committed.py",),
    }
    monkeypatch.setenv("CPPULSE_FORMAT_HEAD", "missing-ci-commit")
    with pytest.raises(subprocess.CalledProcessError):
        targets()
    monkeypatch.delenv("CPPULSE_FORMAT_BASE")
    monkeypatch.delenv("CPPULSE_FORMAT_HEAD")
    monkeypatch.setenv("CPPULSE_FORMAT_ALL_TRACKED", "false")
    assert targets() == {}
    monkeypatch.setenv("CPPULSE_FORMAT_ALL_TRACKED", "true")
    assert targets() == {
        "black-check": ("tests/committed.py", "tests/unchanged.py"),
        "ruff-check": ("tests/committed.py", "tests/unchanged.py"),
    }
    (tmp_path / "tools/staged.py").write_text("value = 3\n")
    git("add", "tools/staged.py")
    (tmp_path / "scripts/untracked.py").write_text("value = 4\n")
    assert set(targets()["black-check"]) == {
        "scripts/untracked.py",
        "tests/committed.py",
        "tests/unchanged.py",
        "tools/staged.py",
    }
    monkeypatch.setenv("CPPULSE_FORMAT_ALL_TRACKED", "1")
    with pytest.raises(ValueError, match="must be true or false"):
        targets()
    monkeypatch.delenv("CPPULSE_FORMAT_ALL_TRACKED")
    monkeypatch.setenv("CPPULSE_FORMAT_BASE", base)
    with pytest.raises(ValueError, match="must be supplied together"):
        targets()


def test_explicit_hosted_root_selection_preserves_unfiltered_default(
    tmp_path: Path,
) -> None:
    from scripts.check_local import (
        DEFAULT_SECTIONS,
        HISTORICAL_ROOT_TESTS,
        build_checks,
    )

    (complete,) = build_checks(tmp_path, {"root"}, tmp_path)
    (public,) = build_checks(tmp_path, {"root-public"}, tmp_path)
    assert "root-public" not in DEFAULT_SECTIONS
    assert complete.name == "root-tests" and public.name == "root-tests-public"
    assert complete.argv == public.argv[:5]
    assert public.argv[5:] == tuple(
        f"--deselect={node}" for node in HISTORICAL_ROOT_TESTS
    )
    assert len(HISTORICAL_ROOT_TESTS) == len(set(HISTORICAL_ROOT_TESTS)) == 5


def test_fmt_example_acquires_dependencies_before_execution(workflow: dict) -> None:
    steps = workflow["jobs"]["test-python"]["steps"]
    names = [step.get("name") for step in steps]
    fetch = names.index("Acquire the locked fmt source for the consumer example")
    verify = names.index("Verify the two fmt consumer configurations")
    retain = names.index("Retain fmt source pins and actual consumer records")
    assert (
        fetch
        < verify
        < retain
        < names.index("Shared public source contracts, scope and generated checks")
    )
    assert all(
        not steps[index].get("if") and not steps[index].get("continue-on-error")
        for index in (fetch, verify)
    )
    assert 'demo_fmt_matrix.py fetch --output "$RUNNER_TEMP/cppulse-fmt-source"' in (
        steps[fetch]["run"]
    )
    assert "demo_fmt_matrix.py run" in steps[verify]["run"]
    assert '--fmt-source "$RUNNER_TEMP/cppulse-fmt-source/fmt"' in steps[verify]["run"]
    assert steps[retain]["if"] == "always()"
