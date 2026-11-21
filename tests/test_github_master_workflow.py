"""Contract for GitHub event scope, privileges, and shared CI checks."""

from __future__ import annotations

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
