"""Existing CI configuration delegates checks without claiming a CI execution."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_existing_github_jobs_call_the_shared_local_facade() -> None:
    document = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    for name, job in document["jobs"].items():
        commands = "\n".join(step.get("run", "") for step in job["steps"])
        assert "tools/dev.py verify" in commands, name
        assert "--scope changed" in commands, name
        assert "pytest -v" not in commands
        assert "cmake --build" not in commands


def test_existing_gitlab_jobs_call_the_same_facade() -> None:
    document = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
    jobs = {
        name: value
        for name, value in document.items()
        if isinstance(value, dict) and "script" in value
    }
    assert jobs
    for name, job in jobs.items():
        commands = "\n".join(job["script"])
        assert "tools/dev.py verify" in commands, name
        assert "--scope changed" in commands, name
        assert "pytest -v" not in commands
        assert "cmake --build" not in commands


def test_gitlab_coverage_reports_point_to_actual_shared_outputs() -> None:
    document = yaml.safe_load((ROOT / ".gitlab-ci.yml").read_text())
    for component in ["git-miner", "predictor", "report-engine"]:
        job = document["test:" + component]
        assert job["artifacts"]["reports"]["coverage_report"] == {
            "coverage_format": "cobertura",
            "path": f"review/ci/{component}/{component}-coverage.xml",
        }
